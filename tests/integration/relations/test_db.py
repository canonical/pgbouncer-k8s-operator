# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import yaml
from pytest_operator.plugin import OpsTest

from tests.integration.relations.helpers.helpers import (
    get_app_relation_databag,
    get_backend_user_pass,
    get_cfg,
    get_legacy_relation_username,
    get_pgb_log,
    wait_for_relation_joined_between,
    wait_for_relation_removed_between,
)
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
                num_units=3,
            ),
            ops_test.model.deploy(PG, num_units=3, trust=True, channel="edge"),
            ops_test.model.deploy("finos-waltz-k8s", application_name=FINOS_WALTZ, channel="edge"),
        )

        await asyncio.gather(
            ops_test.model.wait_for_idle(
                apps=[PG],
                status="active",
                timeout=1000,
                wait_for_exact_units=3,
            ),
            ops_test.model.wait_for_idle(
                apps=[PGB],
                status="active",
                raise_on_blocked=True,
                timeout=1000,
                wait_for_exact_units=3,
            ),
        )
        backend_relation = await ops_test.model.relate(f"{PGB}:backend-database", f"{PG}:database")
        wait_for_relation_joined_between(ops_test, PGB, PG)
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

        finos_relation = await ops_test.model.relate(f"{PGB}:db", f"{FINOS_WALTZ}:db")
        wait_for_relation_joined_between(ops_test, PGB, FINOS_WALTZ)
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
            apps=[ANOTHER_FINOS_WALTZ],
            status="blocked",
            raise_on_blocked=False,
            timeout=1000,
        )
        another_finos_relation = await ops_test.model.relate(
            f"{PGB}:db", f"{ANOTHER_FINOS_WALTZ}:db"
        )
        wait_for_relation_joined_between(ops_test, PGB, ANOTHER_FINOS_WALTZ)
        await ops_test.model.wait_for_idle(
            apps=[PG, PGB, FINOS_WALTZ, ANOTHER_FINOS_WALTZ],
            status="active",
            timeout=1000,
            raise_on_error=False,
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
        wait_for_relation_removed_between(ops_test, PGB, ANOTHER_FINOS_WALTZ)
        await ops_test.model.wait_for_idle(
            apps=[PG, PGB, FINOS_WALTZ], status="active", timeout=1000
        )

        await check_database_users_existence(
            ops_test, [finos_user], [another_finos_user], pgb_user, pgb_password
        )

        # Remove the first deployment of Finos Waltz.
        await ops_test.model.remove_application(FINOS_WALTZ)
        wait_for_relation_removed_between(ops_test, PGB, FINOS_WALTZ)
        await ops_test.model.wait_for_idle(apps=[PGB, PG], status="active", timeout=1000)

        await check_database_users_existence(ops_test, [], [finos_user], pgb_user, pgb_password)

        cfg = await get_cfg(ops_test)
        logger.info(cfg)
        assert finos_user not in cfg["pgbouncer"]["admin_users"]
        assert another_finos_user not in cfg["pgbouncer"]["admin_users"]

        assert "waltz" not in cfg["databases"].keys()
        assert "waltz_standby" not in cfg["databases"].keys()

        logger.info(await get_pgb_log(ops_test))
