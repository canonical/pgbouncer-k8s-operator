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

from .helpers.helpers import CHARM_SERIES, get_leader_unit, wait_for_relation_joined_between

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
        stderr=asyncio.subprocess.PIPE,
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
            stderr=asyncio.subprocess.PIPE,
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
async def test_deploy_without_trust(ops_test: OpsTest, pgb_charm):
    """Build and deploy the charm with trust set to false.

    Assert on the unit status being blocked due to lack of trust.
    """
    resources = {
        "pgbouncer-image": METADATA["resources"]["pgbouncer-image"]["upstream-source"],
    }
    async with ops_test.fast_forward():
        await asyncio.gather(
            ops_test.model.deploy(
                pgb_charm,
                resources=resources,
                application_name=PGB,
                series=CHARM_SERIES,
                trust=True,
            ),
            # Edge 5 is the new postgres charm
            ops_test.model.deploy(
                PG, channel="14/edge", trust=True, num_units=3, config={"profile": "testing"}
            ),
        )
        await asyncio.gather(
            ops_test.model.wait_for_idle(apps=[PGB], status="blocked", timeout=1000),
            ops_test.model.wait_for_idle(
                apps=[PG], status="active", timeout=1000, wait_for_exact_units=3
            ),
        )

        await ops_test.model.add_relation(f"{PGB}:{RELATION}", f"{PG}:database")
        wait_for_relation_joined_between(ops_test, PG, PGB)
        await ops_test.model.wait_for_idle(apps=[PGB, PG], status="blocked", timeout=1000)

    leader_unit = await get_leader_unit(ops_test, PGB)
    assert leader_unit.workload_status == "blocked"
    assert leader_unit.workload_status_message == UNTRUST_ERROR_MESSAGE


@pytest.mark.group(1)
async def test_trust_blocked_deployment(ops_test: OpsTest):
    """Trust existing blocked deployment.

    Assert on the application status recovering to active.
    """
    await ops_test.juju("trust", PGB, "--scope=cluster")

    await ops_test.model.wait_for_idle(apps=[PGB], status="active", timeout=1000)
