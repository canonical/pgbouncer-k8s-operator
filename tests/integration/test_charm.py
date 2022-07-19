#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]

@pytest.mark.skip
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    """Build and deploy pgbouncer charm."""
    #charm = await ops_test.build_charm(".")
    resources = {
        "pgbouncer-image": METADATA["resources"]["pgbouncer-image"]["upstream-source"],
    }
    await ops_test.model.deploy(
        "./pgbouncer-k8s-operator_ubuntu-20.04-amd64.charm",
        resources=resources,
        application_name=APP_NAME,
    )
    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000)

    get_userlist = await ops_test.juju("ssh" , "--container", "pgbouncer", "pgbouncer-k8s-operator/0", "cat", "/var/lib/postgresql/pgbouncer/userlist.txt")
    logger.error(get_userlist)
