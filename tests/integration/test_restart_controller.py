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


@pytest.mark.dev
@pytest.mark.standalone
async def test_kill_controller(ops_test: OpsTest):
    """Kill controller pod and see what pgb/juju does."""
    aclient = AsyncClient(namespace=f"controller-{ops_test.controller_name}")
    await aclient.delete(Pod, name="controller-0")
    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=[PGB], status="active", timeout=1000, idle_period=60
        )
