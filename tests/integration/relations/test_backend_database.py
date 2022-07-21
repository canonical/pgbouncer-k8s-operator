# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from tests.integration.relations.helpers.helpers import (
    get_cfg,
    get_userlist,
    wait_for_relation_joined_between,
    wait_for_relation_removed_between,
)
from tests.integration.relations.helpers.postgres_helpers import (
    check_database_users_existence,
)

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
PGB = METADATA["name"]
PG = "postgresql-k8s"
RELATION = "backend-database"


@pytest.mark.abort_on_fail
async def test_create_backend_db_admin_legacy_relation(ops_test: OpsTest):
    """Test that the pgbouncer and postgres charms can relate to one another."""
    # Build, deploy, and relate charms.
    charm = await ops_test.build_charm(".")
    resources = {
        "pgbouncer-image": METADATA["resources"]["pgbouncer-image"]["upstream-source"],
    }

    await asyncio.gather(
        ops_test.model.deploy(
            charm,
            resources=resources,
            application_name=PGB,
        ),
        # Edge 5 is the new postgres charm
        ops_test.model.deploy(PG, channel="edge", trust=True, num_units=3),
    )
    await asyncio.gather(
        ops_test.model.wait_for_idle(apps=[PGB], status="active", timeout=1000),
        ops_test.model.wait_for_idle(
            apps=[PG], status="active", timeout=1000, wait_for_exact_units=3
        ),
    )

    relation = await ops_test.model.relate(f"{PGB}:{RELATION}", f"{PG}:database")
    wait_for_relation_joined_between(ops_test, PG, PGB)
    await ops_test.model.wait_for_idle(apps=[PGB, PG], status="active", timeout=1000),

    pgb_user = f"relation_id_{relation.id}"
    userlist = await get_userlist(ops_test)
    pgb_password = userlist[pgb_user]
    cfg = await get_cfg(ops_test)
    assert pgb_user in cfg["pgbouncer"]["admin_users"]

    await check_database_users_existence(ops_test, [pgb_user], [], pgb_user, pgb_password)

    # Remove relation but keep pg application because we're going to need it for future tests.
    await ops_test.model.applications[PG].remove_relation(f"{PGB}:{RELATION}", f"{PG}:database")
    wait_for_relation_removed_between(ops_test, PG, PGB)
    await ops_test.model.wait_for_idle(apps=[PG, PGB], status="active", timeout=1000),

    userlist = await get_userlist(ops_test)
    cfg = await get_cfg(ops_test)
    assert pgb_user not in userlist.keys()
    assert pgb_user not in cfg["pgbouncer"]["admin_users"]


async def test_pgbouncer_stable_when_deleting_postgres(ops_test: OpsTest):
    await ops_test.model.relate(f"{PGB}:{RELATION}", f"{PG}:database")
    wait_for_relation_joined_between(ops_test, PG, PGB)
    await asyncio.gather(
        ops_test.model.wait_for_idle(apps=[PGB], status="active", timeout=1000),
        ops_test.model.wait_for_idle(
            apps=[PG], status="active", timeout=1000, wait_for_exact_units=3
        ),
    )

    await ops_test.model.applications[PG].remove()
    wait_for_relation_removed_between(ops_test, PG, PGB)
    await ops_test.model.wait_for_idle(apps=[PGB], status="active", timeout=1000)
