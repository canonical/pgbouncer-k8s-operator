# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest
from tenacity import RetryError, Retrying, stop_after_delay, wait_fixed

from ..helpers.helpers import (
    CHARM_SERIES,
    get_app_relation_databag,
    get_backend_relation,
    get_backend_user_pass,
    get_cfg,
    get_userlist,
    scale_application,
    wait_for_relation_joined_between,
    wait_for_relation_removed_between,
)
from ..helpers.postgresql_helpers import (
    check_database_users_existence,
    enable_connections_logging,
    get_postgres_primary,
    run_command_on_unit,
)

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
FINOS_WALTZ = "finos-waltz"
PGB = METADATA["name"]
PG = "postgresql-k8s"
TLS = "tls-certificates-operator"
RELATION = "backend-database"


@pytest.mark.abort_on_fail
async def test_relate_pgbouncer_to_postgres(ops_test: OpsTest, pgb_charm):
    """Test that the pgbouncer and postgres charms can relate to one another."""
    # Build, deploy, and relate charms.
    resources = {
        "pgbouncer-image": METADATA["resources"]["pgbouncer-image"]["upstream-source"],
    }
    async with ops_test.fast_forward():
        await asyncio.gather(
            ops_test.model.deploy(
                pgb_charm,
                resources=resources,
                application_name=PGB,
                series=CHARM_SERIES,
            ),
            # Edge 5 is the new postgres charm
            ops_test.model.deploy(PG, channel="edge", trust=True, num_units=3),
        )
        await asyncio.gather(
            ops_test.model.wait_for_idle(apps=[PGB], status="blocked", timeout=1000),
            ops_test.model.wait_for_idle(
                apps=[PG], status="active", timeout=1000, wait_for_exact_units=3
            ),
        )

        relation = await ops_test.model.add_relation(f"{PGB}:{RELATION}", f"{PG}:database")
        wait_for_relation_joined_between(ops_test, PG, PGB)
        await ops_test.model.wait_for_idle(apps=[PGB, PG], status="active", timeout=1000),

        cfg = await get_cfg(ops_test, f"{PGB}/0")
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
        await asyncio.gather(
            ops_test.model.wait_for_idle(apps=[PGB], status="blocked", timeout=1000),
            ops_test.model.wait_for_idle(
                apps=[PG], status="active", timeout=1000, wait_for_exact_units=3
            ),
        )

        # Wait for pgbouncer charm to update its config files.
        try:
            for attempt in Retrying(stop=stop_after_delay(3 * 60), wait=wait_fixed(3)):
                with attempt:
                    cfg = await get_cfg(ops_test, f"{PGB}/0")
                    if (
                        pgb_user not in cfg["pgbouncer"]["admin_users"]
                        and "auth_query" not in cfg["pgbouncer"].keys()
                    ):
                        break
        except RetryError:
            assert False, "pgbouncer config files failed to update in 3 minutes"

        cfg = await get_cfg(ops_test, f"{PGB}/0")
        logging.info(cfg.render())


async def test_tls_encrypted_connection_to_postgres(ops_test: OpsTest):
    async with ops_test.fast_forward():
        # Relate PgBouncer to PostgreSQL.
        relation = await ops_test.model.add_relation(f"{PGB}:{RELATION}", f"{PG}:database")
        wait_for_relation_joined_between(ops_test, PG, PGB)
        await ops_test.model.wait_for_idle(apps=[PGB, PG], status="active", timeout=1000)
        pgb_user, _ = await get_backend_user_pass(ops_test, relation)

        # Deploy TLS Certificates operator.
        config = {"generate-self-signed-certificates": "true", "ca-common-name": "Test CA"}
        await ops_test.model.deploy(TLS, config=config)
        await ops_test.model.wait_for_idle(apps=[TLS], status="active", timeout=1000)

        # Relate it to the PostgreSQL to enable TLS.
        await ops_test.model.relate(PG, TLS)
        await ops_test.model.wait_for_idle(status="active", timeout=1000)

        # Enable additional logs on the PostgreSQL instance to check TLS
        # being used in a later step.
        await enable_connections_logging(ops_test, f"{PG}/0")

        # Deploy an app and relate it to PgBouncer to open a connection
        # between PgBouncer and PostgreSQL.
        await ops_test.model.deploy(
            "finos-waltz-k8s", application_name=FINOS_WALTZ, channel="edge"
        )
        await ops_test.model.add_relation(f"{PGB}:db", f"{FINOS_WALTZ}:db")
        await ops_test.model.wait_for_idle(
            apps=[PG, PGB, FINOS_WALTZ], status="active", timeout=1000
        )

        # Check the logs to ensure TLS is being used by PgBouncer.
        postgresql_primary_unit = await get_postgres_primary(ops_test)
        logs = await run_command_on_unit(
            ops_test,
            postgresql_primary_unit,
            'grep "database=waltz SSL enabled" /var/log/postgresql/postgresql.log',
        )
        assert (
            f"connection authorized: user={pgb_user} database=waltz SSL enabled" in logs
        ), "TLS is not being used on connections to PostgreSQL"


async def test_pgbouncer_stable_when_deleting_postgres(ops_test: OpsTest):
    async with ops_test.fast_forward():
        await scale_application(ops_test, PGB, 3)
        await asyncio.gather(
            ops_test.model.wait_for_idle(
                apps=[PGB], status="active", timeout=1000, wait_for_exact_units=3
            ),
            ops_test.model.wait_for_idle(
                apps=[PG], status="active", timeout=1000, wait_for_exact_units=3
            ),
        )

        relation = get_backend_relation(ops_test)
        username = f"relation_id_{relation.id}"
        leader_cfg = await get_cfg(ops_test, f"{PGB}/0")
        leader_userlist = await get_userlist(ops_test, f"{PGB}/0")

        assert username in leader_cfg["pgbouncer"]["admin_users"]
        assert username in leader_userlist

        for unit_id in [1, 2]:
            unit_name = f"{PGB}/{unit_id}"
            cfg = await get_cfg(ops_test, unit_name)
            userlist = await get_userlist(ops_test, unit_name)
            assert username in cfg["pgbouncer"]["admin_users"]
            assert username in userlist

            assert cfg == leader_cfg
            assert userlist == leader_userlist

        # TODO test deleting leader

        await scale_application(ops_test, PGB, 1, expected_status="active")
        await asyncio.gather(
            ops_test.model.wait_for_idle(
                apps=[PGB], status="active", timeout=1000, wait_for_exact_units=1
            ),
            ops_test.model.wait_for_idle(
                apps=[PG], status="active", timeout=1000, wait_for_exact_units=3
            ),
        )
