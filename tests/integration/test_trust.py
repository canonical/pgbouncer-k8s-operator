#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import pytest
from pytest_operator.plugin import OpsTest

from .helpers.helpers import (
    CHARM_SERIES,
    CLIENT_APP_NAME,
    PG,
    PGB,
    PGB_METADATA,
    get_leader_unit,
)

logger = logging.getLogger(__name__)
RELATION = "backend-database"
UNTRUST_ERROR_MESSAGE = f"Insufficient permissions, try: `juju trust {PGB} --scope=cluster`"


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, pgb_charm):
    """Test the deployment of the charm."""
    async with ops_test.fast_forward():
        # Build and deploy applications
        await ops_test.model.deploy(
            pgb_charm,
            resources={
                "pgbouncer-image": PGB_METADATA["resources"]["pgbouncer-image"]["upstream-source"]
            },
            application_name=PGB,
            num_units=1,
            series=CHARM_SERIES,
            trust=False,
        )
        await ops_test.model.deploy(
            CLIENT_APP_NAME,
            application_name=CLIENT_APP_NAME,
            series=CHARM_SERIES,
            channel="edge",
        )
        await ops_test.model.deploy(
            PG,
            channel="14/edge",
            trust=True,
            num_units=1,
            config={"profile": "testing"},
        )
        await ops_test.model.relate(PGB, PG)
        await ops_test.model.wait_for_idle(
            apps=[PGB, PG], status="active", timeout=1200, raise_on_error=False
        )

        await ops_test.model.relate(PGB, f"{CLIENT_APP_NAME}:database")
        await ops_test.model.wait_for_idle(apps=[PGB], status="blocked", timeout=1200)

    leader_unit = await get_leader_unit(ops_test, PGB)
    assert leader_unit.workload_status == "blocked"
    assert leader_unit.workload_status_message == UNTRUST_ERROR_MESSAGE


@pytest.mark.group(1)
async def test_trust_blocked_deployment(ops_test: OpsTest):
    """Trust existing blocked deployment.

    Assert on the application status recovering to active.
    """
    await ops_test.juju("trust", PGB, "--scope=cluster")
    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(apps=[PGB], status="active", timeout=1000)
