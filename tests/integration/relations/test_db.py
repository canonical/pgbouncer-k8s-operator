# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging

import pytest
from pytest_operator.plugin import OpsTest

from constants import EXTENSIONS_BLOCKING_MESSAGE

from .. import markers
from ..helpers.helpers import (
    CHARM_SERIES,
    CLIENT_APP_NAME,
    PG,
    PGB,
    PGB_METADATA,
    get_app_relation_databag,
    get_backend_user_pass,
    get_cfg,
    get_leader_unit,
    get_legacy_relation_username,
    wait_for_relation_joined_between,
    wait_for_relation_removed_between,
)
from ..helpers.postgresql_helpers import (
    check_database_creation,
    check_database_users_existence,
)

FINOS_WALTZ = "finos-waltz"
ANOTHER_FINOS_WALTZ = "another-finos-waltz"

logger = logging.getLogger(__name__)


@markers.amd64_only  # finos-waltz-k8s charm not available for arm64
@pytest.mark.abort_on_fail
async def test_create_db_legacy_relation(ops_test: OpsTest, charm):
    """Test that the pgbouncer and postgres charms can relate to one another."""
    # Build, deploy, and relate charms.
    resources = {
        "pgbouncer-image": PGB_METADATA["resources"]["pgbouncer-image"]["upstream-source"],
    }

    async with ops_test.fast_forward():
        await asyncio.gather(
            ops_test.model.deploy(
                charm,
                resources=resources,
                application_name=PGB,
                num_units=3,
                series=CHARM_SERIES,
                trust=True,
            ),
            ops_test.model.deploy(
                PG, num_units=3, trust=True, channel="14/edge", config={"profile": "testing"}
            ),
            ops_test.model.deploy("finos-waltz-k8s", application_name=FINOS_WALTZ, channel="edge"),
        )

        # TODO test adding both relations simultaneously
        backend_relation = await ops_test.model.add_relation(
            f"{PGB}:backend-database", f"{PG}:database"
        )
        wait_for_relation_joined_between(ops_test, f"{PGB}:backend-database", f"{PG}:database")
        await ops_test.model.wait_for_idle(apps=[PG, PGB], status="active", timeout=1000)

        pgb_user, pgb_password = await get_backend_user_pass(ops_test, backend_relation)
        await check_database_users_existence(
            ops_test,
            [pgb_user],
            [],
            admin=True,
            pg_user=pgb_user,
            pg_user_password=pgb_password,
        )

        finos_relation = await ops_test.model.add_relation(f"{PGB}:db", f"{FINOS_WALTZ}:db")
        wait_for_relation_joined_between(ops_test, f"{PGB}:db", f"{FINOS_WALTZ}:db")
        await ops_test.model.wait_for_idle(
            apps=[PG, PGB, FINOS_WALTZ], status="active", timeout=1000
        )
        await check_database_creation(ops_test, "waltz", pgb_user, pgb_password)
        finos_user = get_legacy_relation_username(ops_test, finos_relation.id)
        await check_database_users_existence(ops_test, [finos_user], [], pgb_user, pgb_password)

        # Deploy second finos
        await ops_test.model.deploy(
            "finos-waltz-k8s", application_name=ANOTHER_FINOS_WALTZ, channel="edge"
        )
        await ops_test.model.wait_for_idle(
            apps=[ANOTHER_FINOS_WALTZ], status="blocked", raise_on_blocked=False, timeout=1000
        )
        another_finos_relation = await ops_test.model.add_relation(
            f"{PGB}:db", f"{ANOTHER_FINOS_WALTZ}:db"
        )
        wait_for_relation_joined_between(ops_test, f"{PGB}:db", f"{ANOTHER_FINOS_WALTZ}:db")
        await ops_test.model.wait_for_idle(
            apps=[PG, PGB, FINOS_WALTZ, ANOTHER_FINOS_WALTZ], status="active", timeout=1000
        )

        # In this case, the database name is the same as in the first deployment
        # because it's a fixed value in Finos Waltz charm.
        await check_database_creation(ops_test, "waltz", pgb_user, pgb_password)
        another_finos_user = get_legacy_relation_username(ops_test, another_finos_relation.id)
        logger.info([finos_user, another_finos_user])
        await check_database_users_existence(
            ops_test, [finos_user, another_finos_user], [], pgb_user, pgb_password
        )

        # test that changing config updates relation data
        pgbouncer_app = ops_test.model.applications[PGB]
        port = "6464"
        await pgbouncer_app.set_config({"listen_port": port})
        await ops_test.model.wait_for_idle(
            apps=[PG, PGB, FINOS_WALTZ, ANOTHER_FINOS_WALTZ],
            status="active",
            timeout=1000,
        )

        finos_unit = ops_test.model.applications[FINOS_WALTZ].units[0]
        finos_app_databag = await get_app_relation_databag(
            ops_test, finos_unit.name, finos_relation.id
        )
        logger.info(finos_app_databag)
        assert port == finos_app_databag.get("port")

        another_finos_unit = ops_test.model.applications[ANOTHER_FINOS_WALTZ].units[0]
        another_finos_app_databag = await get_app_relation_databag(
            ops_test, another_finos_unit.name, another_finos_relation.id
        )
        logger.info(another_finos_app_databag)
        assert port == another_finos_app_databag.get("port")

        # Scale down the second deployment of Finos Waltz and confirm that the first deployment
        # is still active.
        await ops_test.model.remove_application(ANOTHER_FINOS_WALTZ)
        wait_for_relation_removed_between(ops_test, f"{PGB}:db", f"{ANOTHER_FINOS_WALTZ}:db")
        await ops_test.model.wait_for_idle(
            apps=[PG, PGB, FINOS_WALTZ], status="active", timeout=1000
        )

        await check_database_users_existence(
            ops_test, [finos_user], [another_finos_user], pgb_user, pgb_password
        )

        for unit in ops_test.model.applications[PGB].units:
            cfg = await get_cfg(ops_test, unit.name)
            logger.info(cfg)
            assert "waltz" in cfg["databases"]
            assert "waltz_standby" in cfg["databases"]

        # Remove the first deployment of Finos Waltz.
        await ops_test.model.remove_application(FINOS_WALTZ, block_until_done=True)
        wait_for_relation_removed_between(ops_test, f"{PGB}:db", f"{FINOS_WALTZ}:db")
        await ops_test.model.wait_for_idle(apps=[PGB, PG], status="active", timeout=1000)

        await check_database_users_existence(ops_test, [], [finos_user], pgb_user, pgb_password)

        for unit in ops_test.model.applications[PGB].units:
            cfg = await get_cfg(ops_test, unit.name)
            logger.info(cfg)
            assert "waltz" not in cfg["databases"]
            assert "waltz_standby" not in cfg["databases"]


@markers.amd64_only  # finos-waltz-k8s charm not available for arm64
# (and this test depends on previous test with finos-waltz-k8s charm)
async def test_extensions_blocking(ops_test: OpsTest) -> None:
    """Test the relation blocks with extensions."""
    logger.info("Deploying test app")
    await ops_test.model.deploy(CLIENT_APP_NAME, channel="latest/edge")
    await ops_test.model.add_relation(f"{PGB}:db", f"{CLIENT_APP_NAME}:db")

    logger.info("Wait for PGB to block due to extensions")
    leader_unit = await get_leader_unit(ops_test, PGB)
    await ops_test.model.block_until(
        lambda: leader_unit.workload_status_message == EXTENSIONS_BLOCKING_MESSAGE, timeout=1000
    )
    await ops_test.model.applications[PGB].destroy_relation(f"{PGB}:db", f"{CLIENT_APP_NAME}:db")
    await ops_test.model.wait_for_idle(apps=[PGB], status="active", idle_period=15)

    logger.info("Rerelate with extensions enabled")
    config = {"plugin_pg_trgm_enable": "True", "plugin_unaccent_enable": "True"}
    await ops_test.model.applications[PG].set_config(config)
    await ops_test.model.wait_for_idle(apps=[PG], status="active", idle_period=15)
    await ops_test.model.relate(f"{PGB}:db", f"{CLIENT_APP_NAME}:db")
    await ops_test.model.wait_for_idle(
        apps=[PG, PGB],
        status="active",
        raise_on_blocked=False,
        timeout=3000,
    )
