#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
import asyncio
import logging

import pytest
from pytest_operator.plugin import OpsTest

from constants import BACKEND_RELATION_NAME

from .helpers.helpers import (
    CHARM_SERIES,
    PG,
    PGB,
    PGB_METADATA,
)
from .relations.pgbouncer_provider.helpers import check_new_relation

logger = logging.getLogger(__name__)

CLIENT_APP_NAME = "postgresql-test-app"
SECONDARY_CLIENT_APP_NAME = "secondary-application"
DATA_INTEGRATOR_APP_NAME = "data-integrator"
PGB_RESOURCES = {
    "pgbouncer-image": PGB_METADATA["resources"]["pgbouncer-image"]["upstream-source"]
}
APP_NAMES = [CLIENT_APP_NAME, PG, PGB]
FIRST_DATABASE_RELATION_NAME = "first-database"
APPLICATION_FIRST_DBNAME = "postgresql_test_app_first_database"


@pytest.mark.abort_on_fail
async def test_in_place_upgrade(ops_test: OpsTest, pgb_charm):
    """Test basic functionality of database relation interface."""
    # Deploy both charms (multiple units for each application to test that later they correctly
    # set data in the relation application databag using only the leader unit).
    logger.info("Deploying PGB...")
    await asyncio.gather(
        ops_test.model.deploy(
            CLIENT_APP_NAME,
            application_name=CLIENT_APP_NAME,
            series=CHARM_SERIES,
            channel="edge",
        ),
        ops_test.model.deploy(
            pgb_charm,
            resources=PGB_RESOURCES,
            application_name=PGB,
            num_units=2,
            series=CHARM_SERIES,
            trust=True,
        ),
        ops_test.model.deploy(
            PG,
            application_name=PG,
            num_units=2,
            channel="14/edge",
            trust=True,
            config={"profile": "testing"},
        ),
    )
    await ops_test.model.add_relation(f"{PGB}:{BACKEND_RELATION_NAME}", f"{PG}:database")

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(apps=[PGB, PG], status="active")

    # Relate the charms and wait for them exchanging some connection data.
    global client_relation
    client_relation = await ops_test.model.add_relation(
        f"{CLIENT_APP_NAME}:{FIRST_DATABASE_RELATION_NAME}", PGB
    )

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(apps=APP_NAMES, status="active", raise_on_blocked=True)

    # This test hasn't passed if we can't pass a tiny amount of data through the new relation
    await check_new_relation(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        relation_id=client_relation.id,
        dbname=APPLICATION_FIRST_DBNAME,
        relation_name=FIRST_DATABASE_RELATION_NAME,
    )

    leader = None
    for unit in ops_test.model.applications[PGB].units:
        if await unit.is_leader_from_status():
            leader = unit
            break

    action = await leader.run_action("pre-upgrade-check")
    await action.wait()

    await ops_test.model.wait_for_idle(apps=APP_NAMES, status="active", raise_on_blocked=True)

    logger.info("Upgrading last PGB...")
    await ops_test.model.applications[PGB].refresh(path=pgb_charm)
    await ops_test.model.wait_for_idle(apps=[PGB], status="active", raise_on_blocked=True)

    logger.info("Resuming upgrade...")
    action = await leader.run_action("resume-upgrade")
    await action.wait()

    await ops_test.model.wait_for_idle(apps=[PGB], status="active", raise_on_blocked=True)

    await check_new_relation(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        relation_id=client_relation.id,
        dbname=APPLICATION_FIRST_DBNAME,
        relation_name=FIRST_DATABASE_RELATION_NAME,
    )
