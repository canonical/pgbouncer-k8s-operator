# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging

import pytest
from pytest_operator.plugin import OpsTest

from .. import markers
from ..helpers.helpers import (
    CHARM_SERIES,
    PG,
    PGB,
    PGB_METADATA,
    scale_application,
    wait_for_relation_joined_between,
    wait_for_relation_removed_between,
)

logger = logging.getLogger(__name__)

RELATION = "backend-database"
FINOS_WALTZ = "finos-waltz"


@pytest.mark.abort_on_fail
async def test_deploy_at_scale(ops_test, charm):
    # Build, deploy, and relate charms.
    resources = {
        "pgbouncer-image": PGB_METADATA["resources"]["pgbouncer-image"]["upstream-source"],
    }
    async with ops_test.fast_forward():
        await ops_test.model.deploy(
            charm,
            resources=resources,
            application_name=PGB,
            num_units=3,
            series=CHARM_SERIES,
            trust=True,
        )
        (
            await ops_test.model.wait_for_idle(
                apps=[PGB], status="blocked", timeout=1000, wait_for_exact_units=3
            ),
        )


@markers.amd64_only  # finos-waltz-k8s charm not available for arm64
@pytest.mark.abort_on_fail
async def test_scaled_relations(ops_test: OpsTest):
    """Test that the pgbouncer and postgres charms can relate to one another."""
    # Build, deploy, and relate charms.
    async with ops_test.fast_forward():
        await asyncio.gather(
            # Edge 5 is the new postgres charm
            ops_test.model.deploy(
                PG, channel="14/edge", trust=True, num_units=3, config={"profile": "testing"}
            ),
            ops_test.model.deploy("finos-waltz-k8s", application_name=FINOS_WALTZ, channel="edge"),
        )

        await asyncio.gather(
            ops_test.model.wait_for_idle(
                apps=[PGB], status="blocked", timeout=1000, wait_for_exact_units=3
            ),
            ops_test.model.wait_for_idle(
                apps=[PG],
                status="active",
                timeout=1000,
                wait_for_exact_units=3,
            ),
        )

        await ops_test.model.add_relation(f"{PGB}:{RELATION}", f"{PG}:database")
        wait_for_relation_joined_between(ops_test, f"{PG}:database", f"{PGB}:{RELATION}")
        await asyncio.gather(
            ops_test.model.wait_for_idle(apps=[PGB], status="active", timeout=1000),
            ops_test.model.wait_for_idle(
                apps=[PG], status="active", timeout=1000, wait_for_exact_units=3
            ),
        )

        await ops_test.model.add_relation(f"{PGB}:db", f"{FINOS_WALTZ}:db")
        wait_for_relation_joined_between(ops_test, f"{PGB}:db", f"{FINOS_WALTZ}:db")
        await asyncio.gather(
            ops_test.model.wait_for_idle(apps=[PGB, FINOS_WALTZ], status="active", timeout=1000),
            ops_test.model.wait_for_idle(
                apps=[PG], status="active", timeout=1000, wait_for_exact_units=3
            ),
        )


@markers.amd64_only  # finos-waltz-k8s charm not available for arm64
async def test_scaling(ops_test: OpsTest):
    """Test data is replicated to new units after a scale up."""
    # Ensure the initial number of units in the application.
    initial_scale = 3
    async with ops_test.fast_forward():
        await scale_application(ops_test, PGB, initial_scale)
        await asyncio.gather(
            ops_test.model.wait_for_idle(apps=[PGB, FINOS_WALTZ], status="active", timeout=1000),
            ops_test.model.wait_for_idle(
                apps=[PG], status="active", timeout=1000, wait_for_exact_units=3
            ),
        )

        # Scale down the application.
        await scale_application(ops_test, PGB, initial_scale - 1)
        await asyncio.gather(
            ops_test.model.wait_for_idle(apps=[PGB, FINOS_WALTZ], status="active", timeout=1000),
            ops_test.model.wait_for_idle(
                apps=[PG], status="active", timeout=1000, wait_for_exact_units=3
            ),
        )


@markers.amd64_only  # finos-waltz-k8s charm not available for arm64
async def test_exit_relations(ops_test: OpsTest):
    """Test that we can exit relations with multiple units without breaking anything."""
    async with ops_test.fast_forward():
        await ops_test.model.remove_application(FINOS_WALTZ)
        wait_for_relation_removed_between(ops_test, f"{PGB}:db", f"{FINOS_WALTZ}:db")
        await ops_test.model.wait_for_idle(apps=[PG, PGB], status="active", timeout=1000)

        await ops_test.model.remove_application(PG)
        wait_for_relation_removed_between(ops_test, f"{PG}:database", f"{PGB}:{RELATION}")
        await ops_test.model.wait_for_idle(apps=[PGB], status="blocked", timeout=1000)
