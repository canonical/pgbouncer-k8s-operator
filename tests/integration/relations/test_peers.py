# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest
from tenacity import RetryError, Retrying, stop_after_delay, wait_fixed

from tests.integration.helpers.helpers import (
    get_app_relation_databag,
    get_backend_user_pass,
    get_cfg,
    get_pgb_log,
    get_userlist,
    scale_application,
    wait_for_relation_joined_between,
    wait_for_relation_removed_between,
)
from tests.integration.helpers.postgresql_helpers import check_database_users_existence

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
PGB = METADATA["name"]
PG = "postgresql-k8s"
RELATION = "backend-database"
FINOS_WALTZ = "finos-waltz"


@pytest.mark.scaling
@pytest.mark.abort_on_fail
async def deploy(ops_test: OpsTest):
    """Test that the pgbouncer and postgres charms can relate to one another."""
    # Build, deploy, and relate charms.
    charm = await ops_test.build_charm(".")
    resources = {
        "pgbouncer-image": METADATA["resources"]["pgbouncer-image"]["upstream-source"],
    }
    async with ops_test.fast_forward():
        await asyncio.gather(
            ops_test.model.deploy(charm, resources=resources, application_name=PGB, num_units=3),
            # Edge 5 is the new postgres charm
            ops_test.model.deploy(PG, channel="edge", trust=True, num_units=3),
            ops_test.model.deploy("finos-waltz-k8s", application_name=FINOS_WALTZ, channel="edge"),
            ops_test.model.add_relation(f"{PGB}:{RELATION}", f"{PG}:database"),
            ops_test.model.add_relation(f"{PGB}:db", f"{FINOS_WALTZ}:db"),
        )

        wait_for_relation_joined_between(ops_test, PG, PGB)
        wait_for_relation_joined_between(ops_test, PGB, FINOS_WALTZ)

        await asyncio.gather(
            ops_test.model.wait_for_idle(apps=[PGB, FINOS_WALTZ], status="active", timeout=1000),
            ops_test.model.wait_for_idle(
                apps=[PG], status="active", timeout=1000, wait_for_exact_units=3
            ),
        )

@pytest.mark.scaling
async def test_scale_pgb_up(ops_test: OpsTest):
    """Test we can scale pgbouncer up without any issues."""


@pytest.mark.scaling
async def test_operation_while_scaled_up(ops_test: OpsTest):
    """Test we can scale pgbouncer up without any issues."""


@pytest.mark.scaling
async def test_scale_pgb_down(ops_test: OpsTest):
    """Test we can scale pgbouncer down without any issues."""

