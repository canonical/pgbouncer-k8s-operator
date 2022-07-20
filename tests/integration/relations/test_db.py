# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest
from tenacity import RetryError, Retrying, stop_after_delay, wait_fixed

from tests.integration.relations.helpers.helpers import get_cfg, get_userlist, new_relation_joined
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
            ops_test.model.deploy("finos-waltz-k8s", application_name=FINOS_WALTZ, channel="edge"),
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
        backend_relation = await ops_test.model.relate(f"{PGB}:backend-database", f"{PG}:database")
        await ops_test.model.wait_for_idle(apps=[PG, PGB], status="active", timeout=1000)

        userlist = await get_userlist(ops_test)
        username = f"relation_id_{backend_relation.id}"
        password = userlist[username]

        finos_relation = await ops_test.model.relate(f"{PGB}:db", f"{FINOS_WALTZ}:db")
        await ops_test.model.wait_for_idle(
            apps=[PG, PGB, FINOS_WALTZ], status="active", timeout=1000
        )
        await check_database_creation(ops_test, "waltz", username, password)
        finos_user = [f"relation_id_{finos_relation.id}"]
        await check_database_users_existence(ops_test, finos_user, [], username, password)

        await ops_test.model.deploy(
            "finos-waltz-k8s", application_name=ANOTHER_FINOS_WALTZ, channel="edge"
        )
        await ops_test.model.wait_for_idle(
            apps=[ANOTHER_FINOS_WALTZ],
            status="blocked",
            raise_on_blocked=False,
            timeout=1000,
        )
        logger.error((await get_cfg(ops_test)).render())
        logger.error(await get_userlist(ops_test))
        second_finos_relation = await ops_test.model.relate(
            f"{PGB}:db", f"{ANOTHER_FINOS_WALTZ}:db"
        )

        # wait for new relation to exist before waiting for idle.
        try:
            for attempt in Retrying(stop=stop_after_delay(3 * 60), wait=wait_fixed(3)):
                with attempt:
                    if new_relation_joined(ops_test, PGB, ANOTHER_FINOS_WALTZ):
                        break
        except RetryError:
            assert False, "New relation failed to join after 3 minutes."

        await ops_test.model.wait_for_idle(
            apps=[PG, PGB, FINOS_WALTZ, ANOTHER_FINOS_WALTZ], status="active", timeout=1000
        )
        logger.error((await get_cfg(ops_test)).render())
        logger.error(await get_userlist(ops_test))

        # In this case, the database name is the same as in the first deployment
        # because it's a fixed value in Finos Waltz charm.
        await check_database_creation(ops_test, "waltz", username, password)
        second_finos_user = [f"relation_id_{second_finos_relation.id}"]
        await check_database_users_existence(
            ops_test, finos_user + second_finos_user, [], username, password
        )

        # Scale down the second deployment of Finos Waltz and confirm that the first deployment
        # is still active.
        await ops_test.model.remove_application(ANOTHER_FINOS_WALTZ)

        await ops_test.model.wait_for_idle(
            apps=[PG, PGB, FINOS_WALTZ], status="active", timeout=1000
        )

        second_finos_user = []
        await check_database_users_existence(
            ops_test, finos_user, second_finos_user, username, password
        )

        # Remove the first deployment of Finos Waltz.
        await ops_test.model.remove_application(FINOS_WALTZ)
        await ops_test.model.wait_for_idle(apps=[PGB, PG], status="active", timeout=1000)
