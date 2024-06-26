#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import pytest
from pytest_operator.plugin import OpsTest
from tenacity import Retrying, stop_after_delay, wait_fixed

from . import architecture
from .helpers.helpers import CLIENT_APP_NAME


@pytest.fixture(scope="module")
async def pgb_charm(ops_test: OpsTest):
    """Build the pgbouncer charm."""
    if architecture.architecture == "amd64":
        index = 0
    elif architecture.architecture == "arm64":
        index = 1
    else:
        raise ValueError(architecture.architecture)
    return await ops_test.build_charm(".", bases_index=index)


@pytest.fixture
async def continuous_writes(ops_test: OpsTest) -> None:
    """Cleans up continuous writes after a test run."""
    yield
    # Clear the written data at the end.
    for attempt in Retrying(stop=stop_after_delay(60 * 5), wait=wait_fixed(3), reraise=True):
        with attempt:
            action = (
                await ops_test.model.applications[CLIENT_APP_NAME]
                .units[0]
                .run_action("clear-continuous-writes")
            )
            await action.wait()
            assert action.results["result"] == "True", "Unable to clear up continuous_writes table"
