#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
import os

import pytest
import tenacity
from pytest_operator.plugin import OpsTest

from .helpers.helpers import (
    CHARM_SERIES,
    CLIENT_APP_NAME,
    PG,
    PGB,
    PGB_METADATA,
    get_status_log,
)

logger = logging.getLogger(__name__)
RELATION = "backend-database"
UNTRUST_ERROR_MESSAGE = f"Insufficient permissions, try: `juju trust {PGB} --scope=cluster`"


@pytest.mark.abort_on_fail
async def test_trust(ops_test: OpsTest, charm):
    """Test the deployment of the charm."""
    async with ops_test.fast_forward():
        logger.info("Deploying applications")

        # Build and deploy applications
        await asyncio.gather(
            ops_test.model.deploy(
                charm,
                resources={
                    "pgbouncer-image": PGB_METADATA["resources"]["pgbouncer-image"][
                        "upstream-source"
                    ]
                },
                application_name=PGB,
                num_units=1,
                series=CHARM_SERIES,
                trust=False,
            ),
            ops_test.model.deploy(
                CLIENT_APP_NAME,
                application_name=CLIENT_APP_NAME,
                series=CHARM_SERIES,
                channel="edge",
            ),
            ops_test.model.deploy(
                PG,
                channel=os.environ["POSTGRESQL_CHARM_CHANNEL"],
                trust=True,
                num_units=1,
                config={"profile": "testing"},
            ),
        )

        logger.info(f"Waiting until {PGB} blocked due to lack of trust")
        await ops_test.model.block_until(
            lambda: ops_test.model.applications[PGB].status == "blocked", timeout=1200
        )

        for attempt in tenacity.Retrying(
            stop=tenacity.stop_after_attempt(3), wait=tenacity.wait_fixed(10)
        ):
            with attempt:
                status_log = await get_status_log(
                    ops_test, ops_test.model.applications[PGB].units[0]
                )
                assert UNTRUST_ERROR_MESSAGE in status_log

        logger.info(f"Trusting application {PGB}")
        await ops_test.juju("trust", PGB, "--scope=cluster")

        logger.info(f"Relating application {PGB} with {PG}")
        await ops_test.model.relate(PGB, PG)
        await ops_test.model.wait_for_idle(apps=[PG, PGB], status="active", timeout=1200)

        logger.info(f"Relating application {PGB} with {CLIENT_APP_NAME}")
        await ops_test.model.relate(PGB, f"{CLIENT_APP_NAME}:database")
        await ops_test.model.wait_for_idle(apps=[CLIENT_APP_NAME], status="active", timeout=1200)
