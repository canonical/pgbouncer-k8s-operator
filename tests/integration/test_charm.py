#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from .helpers.helpers import CHARM_SERIES, get_cfg, run_command_on_unit

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
PGB = METADATA["name"]


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, pgb_charm):
    """Build and deploy pgbouncer charm."""
    resources = {
        "pgbouncer-image": METADATA["resources"]["pgbouncer-image"]["upstream-source"],
    }
    async with ops_test.fast_forward():
        await ops_test.model.deploy(
            pgb_charm,
            resources=resources,
            application_name=PGB,
            series=CHARM_SERIES,
        )
        await ops_test.model.wait_for_idle(apps=[PGB], status="blocked", timeout=1000)


async def test_config_updates(ops_test: OpsTest):
    """Test updating charm config updates pgbouncer config & relation data."""
    pgbouncer_app = ops_test.model.applications[PGB]
    port = "6464"
    async with ops_test.fast_forward():
        await pgbouncer_app.set_config({"listen_port": port})
        await ops_test.model.wait_for_idle(apps=[PGB], status="blocked", timeout=1000)

        cfg = await get_cfg(ops_test, f"{PGB}/0")
        logger.info(cfg)
        logger.info(await pgbouncer_app.get_config())
        assert cfg["pgbouncer"]["listen_port"] == port


async def test_multiple_pebble_services(ops_test: OpsTest):
    """Test we have the correct pebble services."""
    unit = ops_test.model.applications[PGB].units[0]
    core_count = await run_command_on_unit(ops_test, unit.name, "nproc --all")
    get_services = await run_command_on_unit(ops_test, unit.name, "/charm/bin/pebble services")

    services = get_services.splitlines()[1:]
    # PGB services per core plus one monitoring service
    assert len(services) == int(core_count) + 2

    for service in services:
        service = service.split()
        if service[0] not in ["metrics_server", "logrotate"]:
            assert service[1] == "enabled"
            assert service[2] == "active"


async def test_logrotate(ops_test: OpsTest):
    """Verify that logs will be rotated."""
    unit = ops_test.model.applications[PGB].units[0]
    await run_command_on_unit(ops_test, unit.name, "logrotate -f /etc/logrotate.conf")

    cmd = f"ssh {PGB}/0 sudo ls /var/logs/{PGB}/instance_0"
    return_code, output, _ = await ops_test.juju(*cmd.split(" "))
    output = await run_command_on_unit(ops_test, unit.name, "ls /var/log/pgbouncer/instance_0")
    logs = output.strip().split()
    logs.remove("pgbouncer.log")
    # Pebble should rotate the logs on startup
    assert len(logs) > 1, "Log not rotated"
