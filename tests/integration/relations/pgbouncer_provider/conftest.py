#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import pytest
from pytest_operator.plugin import OpsTest


@pytest.fixture(scope="module")
async def application_charm(ops_test: OpsTest):
    """Build the application charm."""
    charm_path = "tests/integration/relations/pgbouncer_provider/application-charm"
    return await ops_test.build_charm(charm_path)


@pytest.fixture(scope="module")
async def pgb_charm(ops_test: OpsTest):
    """Build the pgbouncer charm."""
    return await ops_test.build_charm(".")
