#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from tests.integration.relations.helpers.helpers import get_cfg

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
PGB = METADATA["name"]

@pytest.mark.skip
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    """Build and deploy pgbouncer charm."""
    charm = await ops_test.build_charm(".")
    resources = {
        "pgbouncer-image": METADATA["resources"]["pgbouncer-image"]["upstream-source"],
    }
    async with ops_test.fast_forward():
        await ops_test.model.deploy(
            charm,
            resources=resources,
            application_name=PGB,
        )
        await ops_test.model.wait_for_idle(apps=[PGB], status="active", timeout=1000)

@pytest.mark.skip
async def test_config_updates(ops_test: OpsTest):
    """Test updating charm config updates pgbouncer config."""
    # test that changing config updates relation data
    pgbouncer_app = ops_test.model.applications[PGB]
    port = "6464"
    async with ops_test.fast_forward():
        await pgbouncer_app.set_config({"listen_port": port})
        await ops_test.model.wait_for_idle(apps=[PGB], status="active", timeout=1000)

        cfg = await get_cfg(ops_test, f"{PGB}/0")
        logger.info(cfg)
        logger.info(await pgbouncer_app.get_config())
        assert cfg["pgbouncer"]["listen_port"] == port
