#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
import pytest as pytest
from pytest_operator.plugin import OpsTest

from . import architecture, markers
from .helpers.helpers import (
    CHARM_SERIES,
    CLIENT_APP_NAME,
    PGB,
    PGB_METADATA,
    POSTGRESQL_APP_NAME,
    app_name,
    check_tls,
    deploy_and_relate_application_with_pgbouncer,
    scale_application,
)
from .juju_ import juju_major_version

MATTERMOST_APP_NAME = "mattermost-k8s"
if juju_major_version < 3:
    tls_certificates_app_name = "tls-certificates-operator"
    if architecture.architecture == "arm64":
        tls_channel = "legacy/edge"
    else:
        tls_channel = "legacy/stable"
    tls_config = {"generate-self-signed-certificates": "true", "ca-common-name": "Test CA"}
else:
    tls_certificates_app_name = "self-signed-certificates"
    if architecture.architecture == "arm64":
        tls_channel = "latest/edge"
    else:
        tls_channel = "latest/stable"
    tls_config = {"ca-common-name": "Test CA"}
APPLICATION_UNITS = 2
DATABASE_UNITS = 3


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, pgb_charm):
    """Build and deploy pgbouncer charm."""
    wait_for_apps = False

    if not await app_name(ops_test):
        wait_for_apps = True
        async with ops_test.fast_forward():
            await ops_test.model.deploy(
                pgb_charm,
                resources={
                    "pgbouncer-image": PGB_METADATA["resources"]["pgbouncer-image"][
                        "upstream-source"
                    ]
                },
                application_name=PGB,
                num_units=APPLICATION_UNITS,
                series=CHARM_SERIES,
                trust=True,
            )

    if not await app_name(ops_test, CLIENT_APP_NAME):
        wait_for_apps = True
        async with ops_test.fast_forward():
            await ops_test.model.deploy(
                CLIENT_APP_NAME,
                application_name=CLIENT_APP_NAME,
                series=CHARM_SERIES,
                channel="edge",
            )
    # remove preexisting relation if any so that we can know the rel id
    relations = [
        relation
        for relation in ops_test.model.applications[PGB].relations
        if not relation.is_peer
        and f"{relation.requires.application_name}:{relation.requires.name}"
        == f"{CLIENT_APP_NAME}:first-database"
    ]
    if relations:
        await ops_test.model.applications[PGB].remove_relation(
            f"{PGB}:database", f"{CLIENT_APP_NAME}:first-database"
        )
        await ops_test.model.wait_for_idle(status="active", timeout=1000)
    global client_relation
    client_relation = await ops_test.model.relate(PGB, f"{CLIENT_APP_NAME}:first-database")

    if not await app_name(ops_test, POSTGRESQL_APP_NAME):
        wait_for_apps = True
        # Deploy Postgresql operator
        await ops_test.model.deploy(
            POSTGRESQL_APP_NAME,
            channel="14/edge",
            trust=True,
            num_units=DATABASE_UNITS,
            config={"profile": "testing"},
        )
        await ops_test.model.relate(PGB, POSTGRESQL_APP_NAME)

    if not await app_name(ops_test, tls_certificates_app_name):
        wait_for_apps = True
        # Deploy TLS Certificates operator.
        await ops_test.model.deploy(
            tls_certificates_app_name, config=tls_config, channel=tls_channel
        )
        # Relate it to the PgBouncer to enable TLS.
        await ops_test.model.relate(PGB, tls_certificates_app_name)
        await ops_test.model.relate(tls_certificates_app_name, POSTGRESQL_APP_NAME)

    if wait_for_apps:
        async with ops_test.fast_forward():
            await ops_test.model.wait_for_idle(status="active", timeout=1200)


@pytest.mark.group(1)
async def test_scale_up_pgb(ops_test: OpsTest) -> None:
    """Scale up PGB while TLS is enabled.

    Args:
        ops_test: The ops test framework
    """
    pgb_app = await app_name(ops_test)
    num_units = len(ops_test.model.applications[pgb_app].units)
    async with ops_test.fast_forward():
        # scale up
        await scale_application(ops_test, PGB, num_units + 1)
        await ops_test.model.wait_for_idle(status="active", timeout=1000)
    assert len(ops_test.model.applications[pgb_app].units) == num_units + 1


@pytest.mark.group(1)
async def test_scale_down_pgb(ops_test: OpsTest) -> None:
    """Scale down PGB while TLS is enabled.

    Args:
        ops_test: The ops test framework
    """
    pgb_app = await app_name(ops_test)
    num_units = len(ops_test.model.applications[pgb_app].units)
    async with ops_test.fast_forward():
        # scale up
        await scale_application(ops_test, PGB, num_units - 1)
        await ops_test.model.wait_for_idle(status="active", timeout=1000)
    assert len(ops_test.model.applications[pgb_app].units) == num_units - 1


@pytest.mark.group(1)
async def test_remove_tls(ops_test: OpsTest) -> None:
    """Removes the TLS relation and check through the test app the it is off.

    Args:
        ops_test: The ops test framework
    """
    await ops_test.model.applications[PGB].remove_relation(
        f"{PGB}:certificates", f"{tls_certificates_app_name}:certificates"
    )
    await ops_test.model.wait_for_idle(status="active", timeout=1000)
    assert await check_tls(ops_test, client_relation.id, False)


@pytest.mark.group(1)
async def test_add_tls(ops_test: OpsTest) -> None:
    """Rejoins the TLS relation and check through the test app the it is on.

    Args:
        ops_test: The ops test framework
    """
    await ops_test.model.relate(PGB, tls_certificates_app_name)
    await ops_test.model.wait_for_idle(status="active", timeout=1000)
    assert await check_tls(ops_test, client_relation.id, True)


@pytest.mark.group(1)
@markers.amd64_only  # mattermost-k8s charm not available for arm64
async def test_mattermost_db(ops_test: OpsTest) -> None:
    """Deploy Mattermost to test the 'db' relation.

    Mattermost needs TLS enabled on PgBouncer to correctly connect to it.

    Args:
        ops_test: The ops test framework
    """
    async with ops_test.fast_forward():
        # Deploy Mattermost
        await deploy_and_relate_application_with_pgbouncer(
            ops_test, MATTERMOST_APP_NAME, MATTERMOST_APP_NAME, APPLICATION_UNITS, status="waiting"
        )
        await ops_test.model.remove_application(MATTERMOST_APP_NAME, block_until_done=True)
