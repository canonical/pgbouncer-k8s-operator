#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
import time
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from .helpers.helpers import (
    CHARM_SERIES,
    CLIENT_APP_NAME,
    get_leader_unit,
)

logger = logging.getLogger(__name__)
METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
PGB = METADATA["name"]
PG = "postgresql-k8s"
RELATION = "backend-database"
MAX_RETRIES = 20
UNTRUST_ERROR_MESSAGE = f"Insufficient permissions, try: `juju trust {PGB} --scope=cluster`"


@pytest.mark.group(1)
async def test_enable_rbac(ops_test: OpsTest):
    """Enables RBAC from inside test runner's environment.

    Assert on permission enforcement being active.
    """
    enable_rbac_call = await asyncio.create_subprocess_exec(
        "sudo",
        "microk8s",
        "enable",
        "rbac",
        stdout=asyncio.subprocess.PIPE,
        stderr=None,
    )
    await enable_rbac_call.communicate()

    is_default_auth = None
    retries = 0
    while is_default_auth != "no" and retries < MAX_RETRIES:
        rbac_check = await asyncio.create_subprocess_exec(
            "microk8s",
            "kubectl",
            "auth",
            "can-i",
            "get",
            "cm",
            "-A",
            "--as=system:serviceaccount:default:no-permissions",
            stdout=asyncio.subprocess.PIPE,
            stderr=None,
        )
        stdout, _ = await rbac_check.communicate()
        if stdout:
            is_default_auth = stdout.decode().split()[0]
            logger.info(f"Response from rbac check ('no' means enabled): {is_default_auth}")
        retries += 1

    assert is_default_auth == "no"


@pytest.mark.group(1)
async def test_model_connectivity(ops_test: OpsTest):
    """Tries to regain connectivity to model after microK8s restart."""
    retries = 0
    while retries < MAX_RETRIES:
        try:
            await ops_test.model.connect_current()
            status = await ops_test.model.get_status()
            logger.info(f"Connection established: {status}")
            return
        except Exception as e:
            logger.info(f"Connection attempt failed: {e}")
            retries += 1
            logger.info(f"Retrying ({retries}/{MAX_RETRIES})...")
            time.sleep(3)

    logger.error(f"Max retries number of {MAX_RETRIES} reached. Unable to connect.")
    assert False


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, pgb_charm):
    """Test the deployment of the charm."""
    async with ops_test.fast_forward():
        # Build and deploy applications
        await ops_test.model.deploy(
            pgb_charm,
            resources={
                "pgbouncer-image": METADATA["resources"]["pgbouncer-image"]["upstream-source"]
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
