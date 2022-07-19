# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from tests.integration.relations.helpers.postgresql_helpers import (
    check_database_creation,
    check_database_users_existence,
)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
PGB = METADATA["name"]
PG = "postgresql-k8s"
FINOS_WALTZ = "finos-waltz"
ANOTHER_FINOS_WALTZ = "another-finos-waltz"

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
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
            # Deploy finos-waltz charm
            ops_test.model.deploy(
                "finos-waltz-k8s", application_name=FINOS_WALTZ, channel="edge"
            ),
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
                apps=[PGB],
                status="active",
                timeout=1000,
            ),
        )
        backend_relation_id = await ops_test.model.relate(f"{PGB}:backend-database", f"{PG}:database"),
        await ops_test.model.wait_for_idle(
            apps=[PG, PGB], status="active", timeout=1000
        )
        backend_relation = next(rel for rel in ops_test.model.relations if rel.id == backend_relation_id)
        username = backend_relation.data[backend_relation.app].get("username")
        password = backend_relation.data[backend_relation.app].get("password")

        relation_id = (await ops_test.model.relate(f"{PGB}:db", f"{FINOS_WALTZ}:db"),)
        await ops_test.model.wait_for_idle(
            apps=[PG, PGB, FINOS_WALTZ], status="active", timeout=1000
        )
        await check_database_creation(ops_test, "waltz", username, password)
        finos_waltz_users = [f"relation_id_{relation_id}"]
        await check_database_users_existence(ops_test, finos_waltz_users, [], username, password)

        await ops_test.model.deploy(
            "finos-waltz-k8s", application_name=ANOTHER_FINOS_WALTZ, channel="edge"
        )
        await ops_test.model.wait_for_idle(
            apps=[ANOTHER_FINOS_WALTZ],
            status="blocked",
            raise_on_blocked=False,
            timeout=1000,
        )
        another_relation_id = (await ops_test.model.relate(f"{PGB}:db", f"{ANOTHER_FINOS_WALTZ}:db"),)
        # In this case, the database name is the same as in the first deployment
        # because it's a fixed value in Finos Waltz charm.
        await check_database_creation(ops_test, "waltz", username, password)
        another_finos_waltz_users = [f"relation_id_{another_relation_id}"]
        await check_database_users_existence(
            ops_test, finos_waltz_users + another_finos_waltz_users, [], username, password
        )

        # Scale down the second deployment of Finos Waltz and confirm that the first deployment
        # is still active.
        await ops_test.model.remove_application(
            ANOTHER_FINOS_WALTZ, block_until_done=True
        )

        another_finos_waltz_users = []
        await check_database_users_existence(
            ops_test, finos_waltz_users, another_finos_waltz_users, username, password
        )

        # Remove the first deployment of Finos Waltz.
        await ops_test.model.remove_application(FINOS_WALTZ, block_until_done=True)

        await ops_test.model.wait_for_idle(apps=[PGB, PG], status="active", timeout=1000)

        # Remove the other deployment of Finos Waltz.
        await ops_test.model.remove_application(ANOTHER_FINOS_WALTZ, block_until_done=True)

        await ops_test.model.wait_for_idle(apps=[PGB, PG], status="active", timeout=1000)
