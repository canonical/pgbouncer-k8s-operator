#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml
from lightkube import AsyncClient
from lightkube.resources.core_v1 import Pod
from pytest_operator.plugin import OpsTest
from tenacity import RetryError, Retrying, stop_after_delay, wait_fixed

from tests.integration.helpers.helpers import get_cfg

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
PGB = METADATA["name"]


@pytest.mark.dev
@pytest.mark.standalone
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


@pytest.mark.standalone
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


@pytest.mark.dev
@pytest.mark.standalone
async def test_kill_controller(ops_test: OpsTest):
    """Kill controller pod and see what pgb/juju does."""
    aclient = AsyncClient(namespace=f"controller-{ops_test.controller_name}")
    await aclient.delete(Pod, name="controller-0")
    # Recreating the controller can take a while, so wait for ages to ensure it's all good.

    # Wait for pgbouncer charm to update its config files.
    try:
        for attempt in Retrying(stop=stop_after_delay(10 * 60), wait=wait_fixed(3)):
            with attempt:
                try:
                    await ops_test.model.wait_for_idle(
                        apps=[PGB], status="active", timeout=600, idle_period=60
                    )
                    break
                except OSError:
                    # We're breaking k8s here, so if there's an OSError, just retry.
                    pass
    except RetryError:
        assert False, "PGB never reached an idle state after controller deletion."
