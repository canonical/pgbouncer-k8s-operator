# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from tests.integration.helpers.postgresql import (
    check_database_creation,
    check_database_users_existence,
)

FINOS_WALTZ_APP_NAME = "finos-waltz"
ANOTHER_FINOS_WALTZ_APP_NAME = "another-finos-waltz"
APPLICATION_UNITS = 1
DATABASE_UNITS = 3

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
PGB = METADATA["name"]
PG = "postgresql"
PSQL = "psql"
APPS = [PG, PGB, PSQL]


@pytest.mark.smoke
@pytest.mark.abort_on_fail
@pytest.mark.legacy_relations
async def test_create_db_legacy_relation(ops_test: OpsTest):
    """Test that the pgbouncer and postgres charms can relate to one another."""
    # Build, deploy, and relate charms.
    charm = await ops_test.build_charm(".")
    resources = {
        "pgbouncer-image": METADATA["resources"]["pgbouncer-image"]["upstream-source"],
    }

    async with ops_test.fast_forward():
        await asyncio.gather(
            ops_test.model.deploy(
                charm,
                resources=resources,
                application_name=PGB,
            ),
            ops_test.model.deploy(PG, num_units=3, trust=True, channel="edge"),
            # Deploy a psql client shell charm
            ops_test.model.deploy("postgresql-charmers-postgresql-client", application_name=PSQL),
        )
        await asyncio.gather(
            ops_test.model.wait_for_idle(
                apps=[PG],
                status="active",
                raise_on_blocked=True,
                timeout=1000,
                wait_for_exact_units=3,
            ),
            ops_test.model.wait_for_idle(
                apps=[PGB, FINOS_WALTZ_APP_NAME],
                status="active",
                raise_on_blocked=True,
                timeout=1000,
                wait_for_exact_units=3,
            )
        )
        await asyncio.gather(
            # Add relations
            ops_test.model.add_relation(f"{PGB}:db", f"{PSQL}:db"),
            ops_test.model.add_relation(f"{PGB}:backend-database", f"{PG}:database"),
        )
        await ops_test.model.wait_for_idle(apps=[PG, PGB], status="active", timeout=1000)

    ops_test.model.applications[PGB].get_relation()

    # TODO assert cli database is created
    # TODO assert db-admin user is created
    # TODO assert we can actually connect from finos-waltz charm
    # TODO user and password are the same in relation data, backend db, and pgb config
    # assert False


@pytest.mark.legacy_relations
async def test_finos_waltz_db(ops_test: OpsTest) -> None:
    """Deploy Finos Waltz to test the 'db' relation.
    Args:
        ops_test: The ops test framework
    """
    async with ops_test.fast_forward():
        # Build and deploy the PostgreSQL charm.
        charm = await ops_test.build_charm(".")
        # Wait until the PostgreSQL charm is successfully deployed.
        await ops_test.model.wait_for_idle(
            apps=[PG],
            status="active",
            raise_on_blocked=True,
            timeout=1000,
            wait_for_exact_units=DATABASE_UNITS,
        )

        # Deploy and test the first deployment of Finos Waltz.
        relation_id = await deploy_and_relate_application_with_postgresql(
            ops_test, "finos-waltz-k8s", FINOS_WALTZ_APP_NAME, APPLICATION_UNITS, channel="edge"
        )
        await check_database_creation(ops_test, "waltz")

        finos_waltz_users = [f"relation_id_{relation_id}"]

        await check_database_users_existence(ops_test, finos_waltz_users, [])

        # Deploy and test another deployment of Finos Waltz.
        another_relation_id = await deploy_and_relate_application_with_postgresql(
            ops_test,
            "finos-waltz-k8s",
            ANOTHER_FINOS_WALTZ_APP_NAME,
            APPLICATION_UNITS,
            channel="edge",
        )
        # In this case, the database name is the same as in the first deployment
        # because it's a fixed value in Finos Waltz charm.
        await check_database_creation(ops_test, "waltz")

        another_finos_waltz_users = [f"relation_id_{another_relation_id}"]

        await check_database_users_existence(
            ops_test, finos_waltz_users + another_finos_waltz_users, []
        )

        # Scale down the second deployment of Finos Waltz and confirm that the first deployment
        # is still active.
        await ops_test.model.remove_application(
            ANOTHER_FINOS_WALTZ_APP_NAME, block_until_done=True
        )

        another_finos_waltz_users = []
        await check_database_users_existence(
            ops_test, finos_waltz_users, another_finos_waltz_users
        )

        # Remove the first deployment of Finos Waltz.
        await ops_test.model.remove_application(FINOS_WALTZ_APP_NAME, block_until_done=True)

        # Remove the PostgreSQL application.
        await ops_test.model.remove_application(PG, block_until_done=True)


@pytest.mark.legacy_relations
async def test_remove_db_legacy_relation(ops_test: OpsTest):
    """Test that removing relations still works ok."""
    await ops_test.model.applications[PGB].remove_relation(f"{PGB}:db", f"{PSQL}:db")
    await ops_test.model.wait_for_idle(apps=[PGB, PG], status="active", timeout=1000)


@pytest.mark.legacy_relations
async def test_delete_db_application_while_in_legacy_relation(ops_test: OpsTest):
    """Test that the pgbouncer charm stays online when the db disconnects for some reason."""
    await ops_test.model.add_relation(f"{PGB}:db", f"{PSQL}:db")
    await ops_test.model.wait_for_idle(apps=APPS, status="active", timeout=1000)

    await ops_test.model.remove_application(PSQL)
    await ops_test.model.wait_for_idle(apps=[PGB, PG], status="active", timeout=1000)
