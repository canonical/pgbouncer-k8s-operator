# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from tests.integration.relations.helpers.postgresql_helpers  import (
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
PG = "postgresql-k8s"
PSQL = "psql"
APPS = [PG, PGB, PSQL]

@pytest.mark.skip
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

@pytest.mark.skip
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
                application_name=PG,
                trust=True,
                num_units=DATABASE_UNITS,
            ),
            ops_test.model.deploy(
                FIRST_DISCOURSE_APP_NAME, application_name=FIRST_DISCOURSE_APP_NAME
            ),
            ops_test.model.deploy(REDIS_APP_NAME, application_name=REDIS_APP_NAME),
        )
        await ops_test.model.wait_for_idle(
            apps=[PG, REDIS_APP_NAME], status="active", timeout=1000
        )
        # Discourse becomes blocked waiting for relations.
        await ops_test.model.wait_for_idle(
            apps=[FIRST_DISCOURSE_APP_NAME], status="blocked", timeout=1000
        )


@pytest.mark.skip
async def test_discourse(ops_test: OpsTest):
    # Test the first Discourse charm.
    # Add both relations to Discourse (PostgreSQL and Redis)
    # and wait for it to be ready.
    relation = await ops_test.model.add_relation(
        f"{PG}:db-admin",
        FIRST_DISCOURSE_APP_NAME,
    )
    await ops_test.model.add_relation(
        REDIS_APP_NAME,
        FIRST_DISCOURSE_APP_NAME,
    )
    await ops_test.model.wait_for_idle(
        apps=[PG, FIRST_DISCOURSE_APP_NAME, REDIS_APP_NAME],
        status="active",
        timeout=2000,  # Discourse takes a longer time to become active (a lot of setup).
    )

    # Check for the correct databases and users creation.
    await check_database_creation(ops_test, "discourse-k8s")
    discourse_users = [f"relation_id_{relation.id}"]
    await check_database_users_existence(ops_test, discourse_users, [], admin=True)


@pytest.mark.skip
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
        f"{PG}:db-admin",
        SECOND_DISCOURSE_APP_NAME,
    )
    await ops_test.model.wait_for_idle(
        apps=[PG, SECOND_DISCOURSE_APP_NAME, REDIS_APP_NAME],
        status="active",
        timeout=2000,  # Discourse takes a longer time to become active (a lot of setup).
    )

    # Check for the correct databases and users creation.
    await check_database_creation(ops_test, "discourse-charmers-discourse-k8s")
    discourse_users = [f"relation_id_{relation.id}"]
    await check_database_users_existence(ops_test, discourse_users, [], admin=True)
