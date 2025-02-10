# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import json
import logging
import shutil
import zipfile
from pathlib import Path
from typing import Union

import pytest
from lightkube import Client
from lightkube.resources.apps_v1 import StatefulSet
from pytest_operator.plugin import OpsTest
from tenacity import Retrying, stop_after_attempt, wait_fixed

from constants import BACKEND_RELATION_NAME

from .helpers.ha_helpers import (
    are_writes_increasing,
    check_writes,
    start_continuous_writes,
)
from .helpers.helpers import (
    CHARM_SERIES,
    CLIENT_APP_NAME,
    PG,
    PGB,
    PGB_METADATA,
)
from .helpers.postgresql_helpers import (
    get_leader_unit,
    get_unit_by_index,
)
from .relations.pgbouncer_provider.helpers import get_application_relation_data

logger = logging.getLogger(__name__)

TIMEOUT = 600
PGB_RESOURCES = {
    "pgbouncer-image": PGB_METADATA["resources"]["pgbouncer-image"]["upstream-source"]
}
FIRST_DATABASE_RELATION_NAME = "database"


@pytest.mark.abort_on_fail
async def test_deploy_latest(ops_test: OpsTest, charm) -> None:
    """Simple test to ensure that the PostgreSQL and application charms get deployed."""
    await asyncio.gather(
        ops_test.model.deploy(
            CLIENT_APP_NAME,
            application_name=CLIENT_APP_NAME,
            series=CHARM_SERIES,
            channel="edge",
        ),
        ops_test.model.deploy(
            PGB,
            application_name=PGB,
            num_units=3,
            channel="1/edge",
            trust=True,
        ),
        ops_test.model.deploy(
            PG,
            application_name=PG,
            num_units=3,
            channel="14/edge",
            trust=True,
            config={"profile": "testing"},
        ),
    )
    await asyncio.gather(
        ops_test.model.add_relation(f"{PGB}:{BACKEND_RELATION_NAME}", f"{PG}:database"),
        ops_test.model.add_relation(f"{CLIENT_APP_NAME}:{FIRST_DATABASE_RELATION_NAME}", PGB),
    )

    logger.info("Wait for applications to become active")
    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=[PG, PGB, CLIENT_APP_NAME],
            status="active",
            timeout=1200,
            raise_on_error=False,
        )
    assert len(ops_test.model.applications[PG].units) == 3
    assert len(ops_test.model.applications[PGB].units) == 3


@pytest.mark.abort_on_fail
async def test_pre_upgrade_check(ops_test: OpsTest) -> None:
    """Test that the pre-upgrade-check action runs successfully."""
    logger.info("Get leader unit")
    leader_unit = await get_leader_unit(ops_test, PGB)
    assert leader_unit is not None, "No leader unit found"

    for attempt in Retrying(stop=stop_after_attempt(2), wait=wait_fixed(30), reraise=True):
        with attempt:
            logger.info("Run pre-upgrade-check action")
            action = await leader_unit.run_action("pre-upgrade-check")
            await action.wait()

    logger.info("Assert partition is set to 2")
    client = Client()
    stateful_set = client.get(res=StatefulSet, namespace=ops_test.model.info.name, name=PGB)

    assert stateful_set.spec.updateStrategy.rollingUpdate.partition == 2, "Partition not set to 2"


@pytest.mark.abort_on_fail
async def test_upgrade_from_edge(ops_test: OpsTest, continuous_writes, charm) -> None:
    # Start an application that continuously writes data to the database.
    logger.info("starting continuous writes to the database")
    await start_continuous_writes(ops_test, PGB)

    # Check whether writes are increasing.
    logger.info("checking whether writes are increasing")
    await are_writes_increasing(ops_test)

    resources = PGB_RESOURCES
    application = ops_test.model.applications[PGB]

    logger.info("Refresh the charm")
    await application.refresh(path=charm, resources=resources)

    logger.info("Wait for upgrade to complete on first upgrading unit")
    # highest ordinal unit always the first to upgrade
    unit = get_unit_by_index(PGB, application.units, 2)

    async with ops_test.fast_forward("60s"):
        await ops_test.model.block_until(lambda: unit.workload_status == "active", timeout=TIMEOUT)
        await ops_test.model.wait_for_idle(apps=[PGB], idle_period=30, timeout=TIMEOUT)

    logger.info("Resume upgrade")
    leader_unit = await get_leader_unit(ops_test, PGB)
    action = await leader_unit.run_action("resume-upgrade")
    await action.wait()

    logger.info("Wait for upgrade to complete")
    async with ops_test.fast_forward("60s"):
        await ops_test.model.wait_for_idle(
            apps=[PGB], status="active", idle_period=30, timeout=TIMEOUT
        )

    # Check whether writes are increasing.
    logger.info("checking whether writes are increasing")
    await are_writes_increasing(ops_test)

    # Verify that no writes to the database were missed after stopping the writes
    # (check that all the units have all the writes).
    logger.info("checking whether no writes were lost")
    await check_writes(ops_test)


@pytest.mark.abort_on_fail
async def test_fail_and_rollback(ops_test, continuous_writes, charm) -> None:
    # Start an application that continuously writes data to the database.
    logger.info("starting continuous writes to the database")
    await start_continuous_writes(ops_test, PGB)

    # Check whether writes are increasing.
    logger.info("checking whether writes are increasing")
    await are_writes_increasing(ops_test)

    logger.info("Get leader unit")
    leader_unit = await get_leader_unit(ops_test, PGB)
    assert leader_unit is not None, "No leader unit found"

    for attempt in Retrying(stop=stop_after_attempt(2), wait=wait_fixed(30), reraise=True):
        with attempt:
            logger.info("Run pre-upgrade-check action")
            action = await leader_unit.run_action("pre-upgrade-check")
            await action.wait()

    filename = Path(charm).name
    fault_charm = Path("/tmp/", filename)
    shutil.copy(charm, fault_charm)

    logger.info("Inject dependency fault")
    await inject_dependency_fault(ops_test, PGB, fault_charm)

    application = ops_test.model.applications[PGB]

    logger.info("Refresh the charm")
    await application.refresh(path=fault_charm)

    logger.info("Get first upgrading unit")
    # Highest ordinal unit always the first to upgrade.
    unit = get_unit_by_index(PGB, application.units, 2)

    logger.info("Wait for upgrade to fail on first upgrading unit")
    async with ops_test.fast_forward("60s"):
        await ops_test.model.block_until(
            lambda: unit.workload_status == "blocked",
            timeout=TIMEOUT,
        )

    logger.info("Ensure continuous_writes while in failure state on remaining units")
    await are_writes_increasing(ops_test)

    logger.info("Re-run pre-upgrade-check action")
    action = await leader_unit.run_action("pre-upgrade-check")
    await action.wait()

    logger.info("Re-refresh the charm")
    await application.refresh(path=charm)

    async with ops_test.fast_forward("60s"):
        await ops_test.model.block_until(lambda: unit.workload_status == "active", timeout=TIMEOUT)
        await ops_test.model.wait_for_idle(apps=[PGB], idle_period=30, timeout=TIMEOUT)

    logger.info("Resume upgrade")
    action = await leader_unit.run_action("resume-upgrade")
    await action.wait()

    logger.info("Wait for application to recover")
    async with ops_test.fast_forward("60s"):
        await ops_test.model.wait_for_idle(apps=[PGB], status="active", timeout=TIMEOUT)

    logger.info("Ensure continuous_writes after rollback procedure")
    await are_writes_increasing(ops_test)

    # Verify that no writes to the database were missed after stopping the writes
    # (check that all the units have all the writes).
    logger.info("Checking whether no writes were lost")
    await check_writes(ops_test)

    # Remove fault charm file.
    fault_charm.unlink()


async def inject_dependency_fault(
    ops_test: OpsTest, application_name: str, charm_file: Union[str, Path]
) -> None:
    """Inject a dependency fault into the PostgreSQL charm."""
    # Query running dependency to overwrite with incompatible version.
    dependencies = await get_application_relation_data(
        ops_test, application_name, "upgrade", "dependencies"
    )
    loaded_dependency_dict = json.loads(dependencies)
    loaded_dependency_dict["charm"]["upgrade_supported"] = "^15"
    loaded_dependency_dict["charm"]["version"] = "15.0"

    # Overwrite dependency.json with incompatible version.
    with zipfile.ZipFile(charm_file, mode="a") as charm_zip:
        charm_zip.writestr("src/dependency.json", json.dumps(loaded_dependency_dict))
