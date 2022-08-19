# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest
from tenacity import RetryError, Retrying, stop_after_delay, wait_fixed

from tests.integration.helpers.helpers import (
    get_app_relation_databag,
    get_backend_user_pass,
    get_cfg,
    get_pgb_log,
    get_userlist,
    scale_application,
    wait_for_relation_joined_between,
    wait_for_relation_removed_between,
)
from tests.integration.helpers.postgresql_helpers import check_database_users_existence

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
PGB = METADATA["name"]
PG = "postgresql-k8s"
RELATION = "backend-database"


@pytest.mark.backend
@pytest.mark.abort_on_fail
async def test_relate_pgbouncer_to_postgres(ops_test: OpsTest):
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
            # Edge 5 is the new postgres charm
            ops_test.model.deploy(PG, channel="edge", trust=True, num_units=3),
        )
        await asyncio.gather(
            ops_test.model.wait_for_idle(apps=[PGB], status="active", timeout=1000),
            ops_test.model.wait_for_idle(
                apps=[PG], status="active", timeout=1000, wait_for_exact_units=3
            ),
        )

        relation = await ops_test.model.add_relation(f"{PGB}:{RELATION}", f"{PG}:database")
        wait_for_relation_joined_between(ops_test, PG, PGB)
        await ops_test.model.wait_for_idle(apps=[PGB, PG], status="active", timeout=1000),

        cfg = await get_cfg(ops_test)
        logging.info(cfg.render())
        pgb_user, pgb_password = await get_backend_user_pass(ops_test, relation)
        assert pgb_user in cfg["pgbouncer"]["admin_users"]
        assert cfg["pgbouncer"]["auth_query"]

        await check_database_users_existence(ops_test, [pgb_user], [], pgb_user, pgb_password)

        # Remove relation but keep pg application because we're going to need it for future tests.
        await ops_test.model.applications[PG].remove_relation(
            f"{PGB}:{RELATION}", f"{PG}:database"
        )
        pgb_unit = ops_test.model.applications[PGB].units[0]
        logging.info(await get_app_relation_databag(ops_test, pgb_unit.name, relation.id))
        wait_for_relation_removed_between(ops_test, PG, PGB)
        await ops_test.model.wait_for_idle(apps=[PG, PGB], status="active", timeout=1000),

        # Wait for pgbouncer charm to update its config files.
        try:
            for attempt in Retrying(stop=stop_after_delay(3 * 60), wait=wait_fixed(3)):
                with attempt:
                    cfg = await get_cfg(ops_test)
                    if (
                        pgb_user not in cfg["pgbouncer"]["admin_users"]
                        and "auth_query" not in cfg["pgbouncer"].keys()
                    ):
                        break
        except RetryError:
            assert False, "pgbouncer config files failed to update in 3 minutes"

        cfg = await get_cfg(ops_test)
        logging.info(cfg.render())
        logger.info(await get_pgb_log(ops_test))


@pytest.mark.backend
async def test_pgbouncer_stable_when_deleting_postgres(ops_test: OpsTest):
    async with ops_test.fast_forward():
        relation = await ops_test.model.add_relation(f"{PGB}:{RELATION}", f"{PG}:database")
        wait_for_relation_joined_between(ops_test, PG, PGB)
        await asyncio.gather(
            ops_test.model.wait_for_idle(apps=[PGB], status="active", timeout=1000),
            ops_test.model.wait_for_idle(
                apps=[PG], status="active", timeout=1000, wait_for_exact_units=3
            ),
        )

        await scale_application(ops_test, PGB, 3)
        await asyncio.gather(
            ops_test.model.wait_for_idle(
                apps=[PGB], status="active", timeout=1000, wait_for_exact_units=3
            ),
            ops_test.model.wait_for_idle(
                apps=[PG], status="active", timeout=1000, wait_for_exact_units=3
            ),
        )

        username = f"relation_id_{relation.id}"
        cfg_0 = await get_cfg(ops_test, f"{PGB}/0")
        userlist_0 = await get_userlist(ops_test, f"{PGB}/0")

        assert username in cfg_0["pgbouncer"]["admin_users"]
        assert username in userlist_0.keys()

        for unit_id in [1, 2]:
            unit_name = f"{PGB}/{unit_id}"
            cfg = await get_cfg(ops_test, unit_name)
            userlist = await get_userlist(ops_test, unit_name)
            assert username in cfg["pgbouncer"]["admin_users"]
            assert username in userlist.keys()

            assert cfg == cfg_0
            assert userlist == userlist_0

        # TODO test deleting leader

        await scale_application(ops_test, PGB, 1)
        await asyncio.gather(
            ops_test.model.wait_for_idle(
                apps=[PGB], status="active", timeout=1000, wait_for_exact_units=1
            ),
            ops_test.model.wait_for_idle(
                apps=[PG], status="active", timeout=1000, wait_for_exact_units=3
            ),
        )
