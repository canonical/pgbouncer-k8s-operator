#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

DATA_INTEGRATOR = "data-integrator"
DATABASE_NAME = "test_database"
POSTGRESQL = "postgresql-k8s"
PGBOUNCER = "pgbouncer-k8s"

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
PGB = METADATA["name"]

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
async def test_deploy(ops_test: OpsTest):
    await asyncio.gather(
        ops_test.model.deploy(DATA_INTEGRATOR, channel="edge", num_units=1, series="jammy"),
    )
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR])
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "blocked"

    # config database name

    config = {"database-name": DATABASE_NAME}
    await ops_test.model.applications[DATA_INTEGRATOR].set_config(config)

    # test the active/waiting status for relation
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR])
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "blocked"


async def test_deploy_and_relate_postgresql(ops_test: OpsTest):
    """Test the relation with PostgreSQL and database accessibility."""
    await asyncio.gather(
        ops_test.model.deploy(
            POSTGRESQL,
            channel="edge",
            num_units=1,
            series="jammy",
            trust=True,
        )
    )
    await ops_test.model.wait_for_idle(
        apps=[POSTGRESQL],
        status="active",
    )
    assert ops_test.model.applications[POSTGRESQL].status == "active"
    await ops_test.model.add_relation(DATA_INTEGRATOR, POSTGRESQL)
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, POSTGRESQL])
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "active"

    # get credential for PostgreSQL
    await ops_test.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:postgresql", f"{POSTGRESQL}:database"
    )

    await ops_test.model.wait_for_idle(apps=[POSTGRESQL, DATA_INTEGRATOR])
    await ops_test.model.add_relation(DATA_INTEGRATOR, POSTGRESQL)
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, POSTGRESQL])

    logger.info(f"Unlock (unreleate) {DATA_INTEGRATOR} for the PgBouncer tests")
    await ops_test.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:postgresql", f"{POSTGRESQL}:database"
    )


async def test_deploy_and_relate_pgbouncer(ops_test: OpsTest):
    """Test the relation with PgBouncer and database accessibility."""
    logger.info(f"Test the relation with {PGBOUNCER}.")
    charm = await ops_test.build_charm(".")
    resources = {
        "pgbouncer-image": METADATA["resources"]["pgbouncer-image"]["upstream-source"],
    }

    await asyncio.gather(
        ops_test.model.deploy(
            charm,
            application_name=PGBOUNCER,
            resources=resources,
            num_units=1,
            series="jammy",
        ),
    )
    await ops_test.model.add_relation(PGBOUNCER, POSTGRESQL)
    await ops_test.model.add_relation(PGBOUNCER, DATA_INTEGRATOR)
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, PGBOUNCER], status="active")
    assert ops_test.model.applications[DATA_INTEGRATOR].status == "active"

    logger.info("Remove relation and test connection again")
    await ops_test.model.applications[DATA_INTEGRATOR].remove_relation(
        f"{DATA_INTEGRATOR}:postgresql", f"{PGBOUNCER}:database"
    )

    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, PGBOUNCER])
    await ops_test.model.add_relation(DATA_INTEGRATOR, PGBOUNCER)
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR, PGBOUNCER])
