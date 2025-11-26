#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
import time

import psycopg2
import pytest
import tenacity
from pytest_operator.plugin import OpsTest

from .helpers.helpers import CHARM_SERIES, PG, PGB, PGB_METADATA, get_data_integrator_credentials
from .juju_ import juju_major_version

logger = logging.getLogger(__name__)

DATA_INTEGRATOR = "data-integrator"
SLOW_TIMEOUT = 15 * 60
MODEL_CONFIG = {"logging-config": "<root>=INFO;unit=DEBUG"}
TEST_DATABASE_NAME = "testdatabase"

TLS_SETUP_SLEEP_TIME = 30
if juju_major_version >= 3:
    TLS_APP_NAME = "self-signed-certificates"
    TLS_CHANNEL = "1/stable"
    TLS_BASE = "ubuntu@24.04"
    TLS_CONFIG = {"ca-common-name": "Test CA"}
else:
    TLS_APP_NAME = "tls-certificates-operator"
    TLS_CHANNEL = "legacy/stable"
    TLS_BASE = "ubuntu@22.04"
    TLS_CONFIG = {"generate-self-signed-certificates": "true", "ca-common-name": "Test CA"}


async def confirm_cluster_ip_endpoints(ops_test: OpsTest) -> None:
    """Helper function to test the cluster ip endpoints."""
    for attempt in tenacity.Retrying(
        reraise=True,
        stop=tenacity.stop_after_delay(SLOW_TIMEOUT),
        wait=tenacity.wait_fixed(10),
    ):
        with attempt:
            data_integrator_unit = ops_test.model.applications[DATA_INTEGRATOR].units[0]
            credentials = await get_data_integrator_credentials(data_integrator_unit)

    assert credentials["postgresql"]["database"] == TEST_DATABASE_NAME, "Database is empty"
    username = credentials["postgresql"]["username"]
    assert username is not None, "Username is empty"
    password = credentials["postgresql"]["password"]
    assert password is not None, "Password is empty"

    endpoint_name = f"pgbouncer-k8s-service.{ops_test.model.name}.svc.cluster.local"
    assert credentials["postgresql"]["endpoints"] == f"{endpoint_name}:6432", (
        "Endpoint is unexpected"
    )

    assert (
        credentials["postgresql"]["uris"]
        == f"postgresql://{username}:{password}@{endpoint_name}:6432/{TEST_DATABASE_NAME}"
    ), "URIs is unexpected"


async def confirm_endpoint_connectivity(ops_test: OpsTest) -> str:
    """Helper to confirm endpoint connectivity."""
    for attempt in tenacity.Retrying(
        reraise=True,
        stop=tenacity.stop_after_delay(SLOW_TIMEOUT),
        wait=tenacity.wait_fixed(10),
    ):
        with attempt:
            data_integrator_unit = ops_test.model.applications[DATA_INTEGRATOR].units[0]
            credentials = await get_data_integrator_credentials(data_integrator_unit)
            assert credentials["postgresql"]["uris"] is not None, "URIs is missing"

            database = credentials["postgresql"]["database"]
            user = credentials["postgresql"]["username"]
            password = credentials["postgresql"]["password"]
            endpoints = credentials["postgresql"]["endpoints"]
            host, port = endpoints.split(",")[0].split(":")

            with (
                psycopg2.connect(
                    f"dbname='{database}' user='{user}' password='{password}' host='{host}' port='{port}' connect_timeout=10"
                ) as connection,
                connection.cursor() as cursor,
            ):
                cursor.execute("SELECT 1;")
                assert cursor.fetchone()[0] == 1, "Unable to execute query"

            return endpoints


@pytest.mark.abort_on_fail
async def test_expose_external(ops_test, charm) -> None:
    """Test the expose-external config option."""
    await ops_test.model.set_config(MODEL_CONFIG)

    pgbouncer_resources = {
        "pgbouncer-image": PGB_METADATA["resources"]["pgbouncer-image"]["upstream-source"]
    }

    logger.info("Deploying postgresql-k8s, pgbouncer-k8s and data-integrator")
    await asyncio.gather(
        ops_test.model.deploy(
            PG,
            channel="14/edge",
            application_name=PG,
            config={"profile": "testing"},
            series=CHARM_SERIES,
            num_units=1,
            trust=True,
        ),
        ops_test.model.deploy(
            charm,
            application_name=PGB,
            series=CHARM_SERIES,
            resources=pgbouncer_resources,
            num_units=1,
            trust=True,
        ),
        ops_test.model.deploy(
            DATA_INTEGRATOR,
            channel="latest/edge",
            application_name=DATA_INTEGRATOR,
            series=CHARM_SERIES,
            config={"database-name": TEST_DATABASE_NAME},
            num_units=1,
        ),
    )

    logger.info("Relating postgresql-k8s, pgbouncer-k8s and data-integrator")
    async with ops_test.fast_forward("60s"):
        await ops_test.model.relate(f"{PG}:database", f"{PGB}:backend-database")
        await ops_test.model.relate(f"{PGB}:database", f"{DATA_INTEGRATOR}:postgresql")

        await ops_test.model.wait_for_idle(
            apps=[PG, PGB, DATA_INTEGRATOR], status="active", timeout=SLOW_TIMEOUT, idle_period=30
        )

        logger.info("Testing endpoint when expose-external=false (default)")
        await confirm_cluster_ip_endpoints(ops_test)

        logger.info("Testing endpoint when expose-external=nodeport")
        pgbouncer_application = ops_test.model.applications[PGB]

        await pgbouncer_application.set_config({"expose-external": "nodeport"})
        await ops_test.model.wait_for_idle(
            apps=[PGB],
            status="active",
            timeout=SLOW_TIMEOUT,
        )

        nodeport_endpoints = await confirm_endpoint_connectivity(ops_test)

        logger.info("Testing endpoint when expose-external=loadbalancer")
        await pgbouncer_application.set_config({"expose-external": "loadbalancer"})
        await ops_test.model.wait_for_idle(
            apps=[PGB],
            status="active",
            timeout=SLOW_TIMEOUT,
        )

        load_balancer_endpoints = await confirm_endpoint_connectivity(ops_test)

        assert nodeport_endpoints != load_balancer_endpoints, (
            "Endpoints did not change for expose-external=loadbalancer"
        )


@pytest.mark.abort_on_fail
async def test_expose_external_with_tls(ops_test: OpsTest) -> None:
    """Test endpoints when pgbouncer-k8s is related to a TLS operator."""
    pgbouncer_application = ops_test.model.applications[PGB]

    logger.info("Resetting expose-external=false")
    await pgbouncer_application.set_config({"expose-external": "false"})
    await ops_test.model.wait_for_idle(
        apps=[PGB],
        status="active",
        timeout=SLOW_TIMEOUT,
    )

    logger.info("Deploying TLS operator")
    await ops_test.model.deploy(
        TLS_APP_NAME,
        channel=TLS_CHANNEL,
        config=TLS_CONFIG,
        base=TLS_BASE,
    )
    async with ops_test.fast_forward("60s"):
        await ops_test.model.wait_for_idle(
            apps=[TLS_APP_NAME],
            status="active",
            timeout=SLOW_TIMEOUT,
        )

        logger.info("Relating pgbouncer-k8s with TLS operator")
        await ops_test.model.relate(PGB, TLS_APP_NAME)

        time.sleep(TLS_SETUP_SLEEP_TIME)

        logger.info("Testing endpoint when expose-external=false(default)")
        await confirm_cluster_ip_endpoints(ops_test)

        logger.info("Testing endpoint when expose-external=nodeport")
        await pgbouncer_application.set_config({"expose-external": "nodeport"})
        await ops_test.model.wait_for_idle(
            apps=[PGB],
            status="active",
            timeout=SLOW_TIMEOUT,
        )

        nodeport_endpoints = await confirm_endpoint_connectivity(ops_test)

        logger.info("Testing endpoint when expose-external=loadbalancer")
        await pgbouncer_application.set_config({"expose-external": "loadbalancer"})
        await ops_test.model.wait_for_idle(
            apps=[PGB],
            status="active",
            timeout=SLOW_TIMEOUT,
        )

        load_balancer_endpoints = await confirm_endpoint_connectivity(ops_test)

        assert nodeport_endpoints != load_balancer_endpoints, (
            "Endpoints did not change for expose-external=loadbalancer"
        )
