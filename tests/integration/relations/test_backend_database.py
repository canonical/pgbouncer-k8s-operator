# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from tests.integration.helpers.helpers import get_cfg

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
POSTGRESQL = "postgresql-k8s"


@pytest.mark.abort_on_fail
@pytest.mark.relations
async def test_create_backend_db_admin_legacy_relation(ops_test: OpsTest):
    """Test that the pgbouncer and postgres charms can relate to one another."""
    # Build, deploy, and relate charms.
    charm = await ops_test.build_charm(".")
    resources = {
        "pgbouncer-image": METADATA["resources"]["pgbouncer-image"]["upstream-source"],
    }
    await asyncio.gather(
        ops_test.model.deploy(
            charm,
            resources=resources,
            application_name=APP_NAME,
        ),
        # Edge 5 is the new postgres charm
        ops_test.model.deploy(POSTGRESQL, channel="edge", trust=True, num_units=3),
    )
    await asyncio.gather(
        ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000),
        ops_test.model.wait_for_idle(
            apps=[POSTGRESQL], status="active", timeout=1000, wait_for_exact_units=3
        ),
    )

    relation = await ops_test.model.relate(
        f"{APP_NAME}:backend-database", f"{POSTGRESQL}:database"
    )
    ops_test.model.wait_for_idle(apps=[APP_NAME, POSTGRESQL], status="active", timeout=1000),

    unit = ops_test.model.units[f"{APP_NAME}/0"]
    cfg = await get_cfg(unit)
    logging.error(cfg.render())
    assert f"relation_id_{relation.id}" in cfg["pgbouncer"]["admin_users"]


@pytest.mark.relations
async def test_backend_db_admin_legacy_relation_remove_relation(ops_test: OpsTest):
    # Remove relation but keep pg application because we're going to need it for future tests.
    await ops_test.model.applications[POSTGRESQL].remove_relation(
        f"{APP_NAME}:backend-database", f"{POSTGRESQL}:database"
    )
    await asyncio.gather(
        ops_test.model.wait_for_idle(apps=[POSTGRESQL], status="active", timeout=1000),
        ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000),
    )


@pytest.mark.relations
async def test_pgbouncer_stable_when_deleting_postgres(ops_test: OpsTest):
    await ops_test.model.relate(f"{APP_NAME}:backend-database", f"{POSTGRESQL}:database")
    await asyncio.gather(
        ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000),
        ops_test.model.wait_for_idle(
            apps=[POSTGRESQL], status="active", timeout=1000, wait_for_exact_units=3
        ),
    )

    ops_test.model.applications[POSTGRESQL].remove()
    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000)
