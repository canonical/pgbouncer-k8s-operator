# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging

import pytest
from pytest_operator.plugin import OpsTest
from tenacity import RetryError, Retrying, stop_after_delay, wait_fixed

from .. import markers
from ..helpers.helpers import (
    CHARM_SERIES,
    PGB,
    PGB_METADATA,
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
    get_postgres_primary,
    run_command_on_unit,
)
from ..juju_ import juju_major_version

logger = logging.getLogger(__name__)

if juju_major_version < 3:
    tls_certificates_app_name = "tls-certificates-operator"
    tls_channel = "legacy/stable"
    tls_config = {"generate-self-signed-certificates": "true", "ca-common-name": "Test CA"}
else:
    tls_certificates_app_name = "self-signed-certificates"
    tls_channel = "latest/stable"
    tls_config = {"ca-common-name": "Test CA"}
FINOS_WALTZ = "finos-waltz"
PG = "postgresql-k8s"
RELATION = "backend-database"


@pytest.mark.abort_on_fail
async def test_relate_pgbouncer_to_postgres(ops_test: OpsTest, charm):
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
                series=CHARM_SERIES,
                trust=True,
            ),
            # Edge 5 is the new postgres charm
            ops_test.model.deploy(
                PG, channel="14/edge", trust=True, num_units=3, config={"profile": "testing"}
            ),
        )
        await asyncio.gather(
            ops_test.model.wait_for_idle(apps=[PGB], status="blocked", timeout=1000),
            ops_test.model.wait_for_idle(
                apps=[PG],
                status="active",
                timeout=1000,
                wait_for_exact_units=3,
                raise_on_error=False,
            ),
        )

        relation = await ops_test.model.add_relation(f"{PGB}:{RELATION}", f"{PG}:database")
        wait_for_relation_joined_between(ops_test, f"{PGB}:{RELATION}", f"{PG}:database")
        (await ops_test.model.wait_for_idle(apps=[PGB, PG], status="active", timeout=1000),)

        cfg = await get_cfg(ops_test, f"{PGB}/0")
        logging.info(cfg)
        pgb_user, pgb_password = await get_backend_user_pass(ops_test, relation)
        assert cfg["pgbouncer"]["auth_query"]

        await check_database_users_existence(ops_test, [pgb_user], [], pgb_user, pgb_password)

        # Remove relation but keep pg application because we're going to need it for future tests.
        await ops_test.model.applications[PG].remove_relation(
            f"{PGB}:{RELATION}", f"{PG}:database"
        )
        pgb_unit = ops_test.model.applications[PGB].units[0]
        logging.info(await get_app_relation_databag(ops_test, pgb_unit.name, relation.id))
        wait_for_relation_removed_between(ops_test, f"{PG}:database", f"{PGB}:{RELATION}")
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
                    if "auth_query" not in cfg["pgbouncer"]:
                        break
        except RetryError:
            assert False, "pgbouncer config files failed to update in 3 minutes"

        cfg = await get_cfg(ops_test, f"{PGB}/0")
        logging.info(cfg)


@markers.amd64_only  # finos-waltz-k8s charm not available for arm64
async def test_tls_encrypted_connection_to_postgres(ops_test: OpsTest):
    async with ops_test.fast_forward():
        # Relate PgBouncer to PostgreSQL.
        relation = await ops_test.model.add_relation(f"{PGB}:{RELATION}", f"{PG}:database")
        wait_for_relation_joined_between(ops_test, f"{PGB}:{RELATION}", f"{PG}:database")
        await ops_test.model.wait_for_idle(apps=[PGB, PG], status="active", timeout=1000)
        pgb_user, _ = await get_backend_user_pass(ops_test, relation)

        # Deploy TLS Certificates operator.
        await ops_test.model.deploy(
            tls_certificates_app_name, config=tls_config, channel=tls_channel
        )
        await ops_test.model.wait_for_idle(
            apps=[tls_certificates_app_name], status="active", timeout=1000
        )

        # Relate it to the PostgreSQL to enable TLS.
        await ops_test.model.relate(PG, tls_certificates_app_name)
        await ops_test.model.wait_for_idle(status="active", timeout=1000)

        await ops_test.model.applications[PG].set_config({"logging_log_connections": "True"})
        await ops_test.model.wait_for_idle(apps=[PG], status="active", idle_period=30)

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
            'grep "database=waltz SSL enabled" /var/log/postgresql/postgresql*.log',
        )
        assert f"connection authorized: user={pgb_user} database=waltz SSL enabled" in logs, (
            "TLS is not being used on connections to PostgreSQL"
        )


@markers.amd64_only  # finos-waltz-k8s charm not available for arm64
# (and this test depends on previous test with finos-waltz-k8s charm)
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
        monitoring_username = f"pgbouncer_stats_{PGB}".replace("-", "_")
        leader_cfg = await get_cfg(ops_test, f"{PGB}/0")
        leader_userlist = await get_userlist(ops_test, f"{PGB}/0")

        assert monitoring_username in leader_cfg["pgbouncer"]["stats_users"]
        assert username in leader_userlist

        for unit_id in [1, 2]:
            unit_name = f"{PGB}/{unit_id}"
            cfg = await get_cfg(ops_test, unit_name)
            userlist = await get_userlist(ops_test, unit_name)
            assert monitoring_username in cfg["pgbouncer"]["stats_users"]
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
