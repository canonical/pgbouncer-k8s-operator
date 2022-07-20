# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest
from tenacity import RetryError, Retrying, stop_after_delay, wait_fixed

from tests.integration.relations.helpers.helpers import (
    new_relation_joined,
    relation_exited,
)

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
PG = "postgresql-k8s"
RELATION = "backend-database"


@pytest.mark.abort_on_fail
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
        ops_test.model.deploy(PG, channel="edge", trust=True, num_units=3),
    )
    await asyncio.gather(
        ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000),
        ops_test.model.wait_for_idle(
            apps=[PG], status="active", timeout=1000, wait_for_exact_units=3
        ),
    )

    await ops_test.model.relate(f"{APP_NAME}:{RELATION}", f"{PG}:database")

    # wait for new relation to exist before waiting for idle.
    try:
        for attempt in Retrying(stop=stop_after_delay(3 * 60), wait=wait_fixed(3)):
            with attempt:
                if new_relation_joined(ops_test, APP_NAME, PG):
                    break
    except RetryError:
        assert False, "New relation failed to join mongodb after 5 minutes."

    await ops_test.model.wait_for_idle(apps=[APP_NAME, PG], status="active", timeout=1000),


async def test_backend_db_admin_legacy_relation_remove_relation(ops_test: OpsTest):
    # Remove relation but keep pg application because we're going to need it for future tests.
    await ops_test.model.applications[PG].remove_relation(
        f"{APP_NAME}:{RELATION}", f"{PG}:database"
    )

    # wait for new relation to exist before waiting for idle.
    try:
        for attempt in Retrying(stop=stop_after_delay(3 * 60), wait=wait_fixed(3)):
            with attempt:
                if relation_exited(ops_test, RELATION):
                    break
    except RetryError:
        assert False, "New relation failed to join mongodb after 5 minutes."

    await ops_test.model.wait_for_idle(apps=[PG, APP_NAME], status="active", timeout=1000),


async def test_pgbouncer_stable_when_deleting_postgres(ops_test: OpsTest):
    await ops_test.model.relate(f"{APP_NAME}:{RELATION}", f"{PG}:database")
    await asyncio.gather(
        ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000),
        ops_test.model.wait_for_idle(
            apps=[PG], status="active", timeout=1000, wait_for_exact_units=3
        ),
    )

    await ops_test.model.applications[PG].remove()
    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000)
