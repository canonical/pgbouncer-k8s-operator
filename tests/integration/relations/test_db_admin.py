# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from tests.integration.helpers import helpers

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
        ops_test.model.add_relation(f"{PGB}:backend-db-admin", f"{PG}:db-admin"),
    )
    await ops_test.model.wait_for_idle(apps=[PG, PGB], status="active", timeout=1000)

    unit = ops_test.model.units["pgbouncer-operator/0"]
    cfg = await helpers.get_cfg(unit)
    assert "pg_master" in list(cfg["databases"].keys())
    assert "cli" in cfg["databases"].keys()

    # TODO assert cli database is created
    # TODO assert db-admin user is created
    # TODO assert we can actually connect from psql charm
    # TODO user and password are the same in relation data, backend db, and pgb config
    # assert False


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
    unit = ops_test.model.units["pgbouncer-operator/0"]
    cfg = await helpers.get_cfg(unit)
    expected_databases = [
        "pg_master",
        "pgb_postgres_standby_0",
        "pgb_postgres_standby_1",
        "cli",
        "cli_standby_0",
        "cli_standby_1",
    ]
    for database in expected_databases:
        assert database in cfg["databases"].keys()


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
    unit = ops_test.model.units["pgbouncer-operator/0"]
    cfg = await helpers.get_cfg(unit)
    assert "pg_master" in cfg["databases"].keys()
    assert "cli" in cfg["databases"].keys()


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
    unit = ops_test.model.units["pgbouncer-operator/0"]
    cfg = await helpers.get_cfg(unit)
    assert "pg_master" in cfg["databases"].keys()
    assert "cli" in cfg["databases"].keys()


@pytest.mark.legacy_relations
async def test_remove_db_admin_legacy_relation(ops_test: OpsTest):
    """Test that removing relations still works ok."""
    await ops_test.model.applications[PGB].remove_relation(f"{PGB}:db-admin", f"{PSQL}:db")
    await ops_test.model.wait_for_idle(apps=[PGB, PG], status="active", timeout=1000)

    unit = ops_test.model.units["pgbouncer-operator/0"]
    cfg = await helpers.get_cfg(unit)
    assert "pg_master" in cfg["databases"].keys()
    assert "cli" not in cfg["databases"].keys()


@pytest.mark.legacy_relations
async def test_delete_db_admin_application_while_in_legacy_relation(ops_test: OpsTest):
    """Test that the pgbouncer charm stays online when the db-admin disconnects for some reason."""
    await ops_test.model.add_relation(f"{PGB}:db-admin", f"{PSQL}:db")
    await ops_test.model.wait_for_idle(apps=APPS, status="active", timeout=1000)

    await ops_test.model.remove_application(PSQL)
    await ops_test.model.wait_for_idle(apps=[PGB, PG], status="active", timeout=1000)
