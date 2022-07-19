# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from tests.integration.helpers.postgresql_helpers import (
    check_database_creation,
    check_database_users_existence,
    get_unit_address,
)

FIRST_DISCOURSE_APP_NAME = "discourse-k8s"
SECOND_DISCOURSE_APP_NAME = "discourse-charmers-discourse-k8s"
REDIS_APP_NAME = "redis-k8s"
APPLICATION_UNITS = 1
DATABASE_UNITS = 3

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
PGB = METADATA["name"]
PG = "postgresql"
PSQL = "psql"
APPS = [PG, PGB, PSQL]


@pytest.mark.abort_on_fail
@pytest.mark.legacy_relations
async def test_create_db_admin_legacy_relation(ops_test: OpsTest):
    """Test that the pgbouncer and postgres charms can relate to one another."""
    # Build, deploy, and relate charms.
    charm = await ops_test.build_charm(".")
    await asyncio.gather(
        ops_test.model.deploy(
            charm,
            application_name=PGB,
        ),
        ops_test.model.deploy(PG),
        # Deploy a psql client shell charm
        ops_test.model.deploy("postgresql-charmers-postgresql-client", application_name=PSQL),
    )
    await asyncio.gather(
        # Add relations
        ops_test.model.add_relation(f"{PGB}:db-admin", f"{PSQL}:db"),
        ops_test.model.add_relation(f"{PGB}:backend-database", f"{PG}:database"),
    )
    await ops_test.model.wait_for_idle(apps=[PG, PGB], status="active", timeout=1000)

    # TODO assert cli database is created
    # TODO assert db-admin user is created
    # TODO assert we can actually connect from psql charm
    # TODO user and password are the same in relation data, backend db, and pgb config
    # assert False


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    """Build the charm-under-test and deploy it.
    Assert on the unit status before any relations/configurations take place.
    """
    async with ops_test.fast_forward():
        # Build and deploy charm from local source folder (and also redis from Charmhub).
        # Both are needed by Discourse charms.
        charm = await ops_test.build_charm(".")
        resources = {
            "postgresql-image": METADATA["resources"]["postgresql-image"]["upstream-source"],
        }
        await asyncio.gather(
            ops_test.model.deploy(
                charm,
                resources=resources,
                application_name=DATABASE_APP_NAME,
                trust=True,
                num_units=DATABASE_UNITS,
            ),
            ops_test.model.deploy(
                FIRST_DISCOURSE_APP_NAME, application_name=FIRST_DISCOURSE_APP_NAME
            ),
            ops_test.model.deploy(REDIS_APP_NAME, application_name=REDIS_APP_NAME),
        )
        await ops_test.model.wait_for_idle(
            apps=[DATABASE_APP_NAME, REDIS_APP_NAME], status="active", timeout=1000
        )
        # Discourse becomes blocked waiting for relations.
        await ops_test.model.wait_for_idle(
            apps=[FIRST_DISCOURSE_APP_NAME], status="blocked", timeout=1000
        )


@pytest.mark.legacy_relations
async def test_add_replicas(ops_test: OpsTest):
    # We have to scale up backend because otherwise psql enters a waiting status for every unit
    # that doesn't have a backend unit.
    await asyncio.gather(
        ops_test.model.applications[PG].add_units(count=2),
        ops_test.model.applications[PSQL].add_units(count=2),
    )
    await asyncio.gather(
        ops_test.model.wait_for_idle(
            apps=[PG], status="active", timeout=1000, wait_for_exact_units=3
        ),
        ops_test.model.wait_for_idle(
            apps=[PSQL], status="active", timeout=1000, wait_for_exact_units=3
        ),
        ops_test.model.wait_for_idle(apps=[PGB], status="active"),
    )


@pytest.mark.legacy_relations
async def test_remove_db_admin_unit(ops_test: OpsTest):
    await ops_test.model.destroy_unit("psql/1")
    await asyncio.gather(
        ops_test.model.wait_for_idle(
            apps=[PSQL], status="active", timeout=1000, wait_for_exact_units=2
        ),
        ops_test.model.wait_for_idle(
            apps=[PG, PGB],
            status="active",
            timeout=1000,
        ),
    )


@pytest.mark.legacy_relations
async def test_remove_backend_unit(ops_test: OpsTest):
    await ops_test.model.destroy_unit("postgresql/1")
    await asyncio.gather(
        ops_test.model.wait_for_idle(
            apps=[PG], status="active", timeout=1000, wait_for_exact_units=2
        ),
        ops_test.model.wait_for_idle(apps=[PGB, PSQL], status="active", timeout=1000),
    )


# TODO verify we're removing the correct leader
@pytest.mark.legacy_relations
async def test_remove_db_admin_leader(ops_test: OpsTest):
    await ops_test.model.destroy_unit("psql/0")
    await asyncio.gather(
        ops_test.model.wait_for_idle(
            apps=[PSQL], status="active", timeout=1000, wait_for_exact_units=1
        ),
        ops_test.model.wait_for_idle(
            apps=[PG, PGB],
            status="active",
            timeout=1000,
        ),
    )


# TODO verify we're removing the correct leader
@pytest.mark.legacy_relations
async def test_remove_backend_leader(ops_test: OpsTest):
    await ops_test.model.destroy_unit("postgresql/0")
    await asyncio.gather(
        ops_test.model.wait_for_idle(
            apps=[PG], status="active", timeout=1000, wait_for_exact_units=1
        ),
        ops_test.model.wait_for_idle(apps=[PGB, PSQL], status="active", timeout=1000),
    )


@pytest.mark.legacy_relations
async def test_remove_db_admin_legacy_relation(ops_test: OpsTest):
    """Test that removing relations still works ok."""
    await ops_test.model.applications[PGB].remove_relation(f"{PGB}:db-admin", f"{PSQL}:db")
    await ops_test.model.wait_for_idle(apps=[PGB, PG], status="active", timeout=1000)


@pytest.mark.legacy_relations
async def test_delete_db_admin_application_while_in_legacy_relation(ops_test: OpsTest):
    """Test that the pgbouncer charm stays online when the db-admin disconnects for some reason."""
    await ops_test.model.add_relation(f"{PGB}:db-admin", f"{PSQL}:db")
    await ops_test.model.wait_for_idle(apps=APPS, status="active", timeout=1000)

    await ops_test.model.remove_application(PSQL)
    await ops_test.model.wait_for_idle(apps=[PGB, PG], status="active", timeout=1000)





async def test_discourse(ops_test: OpsTest):
    # Test the first Discourse charm.
    # Add both relations to Discourse (PostgreSQL and Redis)
    # and wait for it to be ready.
    relation = await ops_test.model.add_relation(
        f"{DATABASE_APP_NAME}:db-admin",
        FIRST_DISCOURSE_APP_NAME,
    )
    await ops_test.model.add_relation(
        REDIS_APP_NAME,
        FIRST_DISCOURSE_APP_NAME,
    )
    await ops_test.model.wait_for_idle(
        apps=[DATABASE_APP_NAME, FIRST_DISCOURSE_APP_NAME, REDIS_APP_NAME],
        status="active",
        timeout=2000,  # Discourse takes a longer time to become active (a lot of setup).
    )

    # Check for the correct databases and users creation.
    await check_database_creation(ops_test, "discourse-k8s")
    discourse_users = [f"relation_id_{relation.id}"]
    await check_database_users_existence(ops_test, discourse_users, [], admin=True)


async def test_discourse_from_discourse_charmers(ops_test: OpsTest):
    # Test the second Discourse charm.

    # Get the Redis instance IP address.
    redis_host = await get_unit_address(ops_test, f"{REDIS_APP_NAME}/0")

    # Deploy Discourse and wait for it to be blocked waiting for database relation.
    await ops_test.model.deploy(
        SECOND_DISCOURSE_APP_NAME,
        application_name=SECOND_DISCOURSE_APP_NAME,
        config={
            "redis_host": redis_host,
            "developer_emails": "user@foo.internal",
            "external_hostname": "foo.internal",
            "smtp_address": "127.0.0.1",
            "smtp_domain": "foo.internal",
        },
    )
    # Discourse becomes blocked waiting for PostgreSQL relation.
    await ops_test.model.wait_for_idle(
        apps=[SECOND_DISCOURSE_APP_NAME], status="blocked", timeout=1000
    )

    # Relate PostgreSQL and Discourse, waiting for Discourse to be ready.
    relation = await ops_test.model.add_relation(
        f"{DATABASE_APP_NAME}:db-admin",
        SECOND_DISCOURSE_APP_NAME,
    )
    await ops_test.model.wait_for_idle(
        apps=[DATABASE_APP_NAME, SECOND_DISCOURSE_APP_NAME, REDIS_APP_NAME],
        status="active",
        timeout=2000,  # Discourse takes a longer time to become active (a lot of setup).
    )

    # Check for the correct databases and users creation.
    await check_database_creation(ops_test, "discourse-charmers-discourse-k8s")
    discourse_users = [f"relation_id_{relation.id}"]
    await check_database_users_existence(ops_test, discourse_users, [], admin=True)