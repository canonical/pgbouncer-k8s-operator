#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
import logging
from asyncio import gather

import pytest as pytest
from pytest_operator.plugin import OpsTest

from constants import BACKEND_RELATION_NAME

from .helpers.helpers import CHARM_SERIES, PG, PGB, PGB_METADATA

logger = logging.getLogger(__name__)


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_config_parameters(ops_test: OpsTest, pgb_charm) -> None:
    """Build and deploy one unit of PostgreSQL and then test config with wrong parameters."""
    # Build and deploy the PostgreSQL charm.
    async with ops_test.fast_forward():
        await gather(
            ops_test.model.deploy(
                pgb_charm,
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
                PG,
                application_name=PG,
                num_units=1,
                channel="14/edge",
                config={"profile": "testing"},
            ),
        )
        await ops_test.model.add_relation(f"{PGB}:{BACKEND_RELATION_NAME}", f"{PG}:database")

    await ops_test.model.wait_for_idle(status="active", timeout=600)

    unit = ops_test.model.applications[PGB].units[0]
    test_string = "abcXYZ123"

    configs = {
        "listen_port": "0",
        "pool_mode": test_string,
        "max_db_connections": "-1",
    }

    for key, val in configs.items():
        logger.info(key)
        await ops_test.model.applications[PGB].set_config({key: val})
        await ops_test.model.block_until(
            lambda: ops_test.model.units[f"{PGB}/0"].workload_status == "blocked",
            timeout=100,
        )
        assert "Configuration Error" in unit.workload_status_message

        await ops_test.model.applications[PGB].reset_config([key])
        await ops_test.model.block_until(
            lambda: ops_test.model.units[f"{PGB}/0"].workload_status == "active",
            timeout=100,
        )
