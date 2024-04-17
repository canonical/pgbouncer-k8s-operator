#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import psycopg2
import pytest
import yaml
from pytest_operator.plugin import OpsTest

from .helpers.ha_helpers import (
    start_continuous_writes,
    stop_continuous_writes,
)
from .helpers.helpers import (
    CHARM_SERIES,
    CLIENT_APP_NAME,
    PGB,
    PGB_METADATA,
    POSTGRESQL_APP_NAME,
    app_name,
    get_endpoint_info,
    get_juju_secret,
    get_unit_info,
)
from .juju_ import juju_major_version

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
DATA_INTEGRATOR = "data-integrator"
MODEL_CONFIG = {"logging-config": "<root>=INFO;unit=DEBUG"}


if juju_major_version < 3:
    TLS_CERTIFICATES_APP_NAME = "tls-certificates-operator"
    TLS_CHANNEL = "legacy/stable"
    TLS_CONFIG = {"generate-self-signed-certificates": "true", "ca-common-name": "Test CA"}
else:
    TLS_CERTIFICATES_APP_NAME = "self-signed-certificates"
    TLS_CHANNEL = "latest/stable"
    TLS_CONFIG = {"ca-common-name": "Test CA"}
DATABASE_UNITS = 3


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, pgb_charm):
    """Test the deployment of the charm."""
    # Build and deploy applications
    await ops_test.model.set_config(MODEL_CONFIG)
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
                num_units=1,
                series=CHARM_SERIES,
                trust=True,
            )

    if not await app_name(ops_test, DATA_INTEGRATOR):
        wait_for_apps = True
        async with ops_test.fast_forward():
            await ops_test.model.deploy(
                DATA_INTEGRATOR,
                channel="latest/edge",
                application_name=DATA_INTEGRATOR,
                series=CHARM_SERIES,
                config={"database-name": "test"},
                num_units=1,
            )
    await ops_test.model.relate(PGB, DATA_INTEGRATOR)

    if not await app_name(ops_test, CLIENT_APP_NAME):
        wait_for_apps = True
        async with ops_test.fast_forward():
            await ops_test.model.deploy(
                CLIENT_APP_NAME,
                application_name=CLIENT_APP_NAME,
                series=CHARM_SERIES,
                channel="edge",
            )
    await ops_test.model.relate(PGB, f"{CLIENT_APP_NAME}:first-database")

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

    if not await app_name(ops_test, TLS_CERTIFICATES_APP_NAME):
        wait_for_apps = True
        # Deploy TLS Certificates operator.
        await ops_test.model.deploy(
            TLS_CERTIFICATES_APP_NAME, config=TLS_CONFIG, channel=TLS_CHANNEL
        )
        # Relate it to the PgBouncer to enable TLS.
        await ops_test.model.relate(PGB, TLS_CERTIFICATES_APP_NAME)
        await ops_test.model.relate(TLS_CERTIFICATES_APP_NAME, POSTGRESQL_APP_NAME)

    if wait_for_apps:
        await ops_test.model.wait_for_idle(status="active", timeout=1200)


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_node_port_and_clusterip_setup(ops_test: OpsTest):
    """Test the nodeport."""
    # Test the writes to the database using the client app
    psql_app = ops_test.model.applications.get(POSTGRESQL_APP_NAME)
    await start_continuous_writes(ops_test, psql_app.name)

    for app in [DATA_INTEGRATOR, CLIENT_APP_NAME]:
        if app == DATA_INTEGRATOR:
            endpoint = await get_endpoint_info(ops_test, f"{app}/0", "postgresql")
            assert "svc.cluster.local" not in endpoint
        else:
            endpoint = await get_endpoint_info(ops_test, f"{app}/0", "first-database")
            assert "svc.cluster.local" in endpoint

    await stop_continuous_writes(ops_test)


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_data_integrator(ops_test: OpsTest):
    """Test the connection."""
    endpoint = "postgresql"
    info = (await get_unit_info(ops_test, f"{DATA_INTEGRATOR}/0"))["relation-info"]
    info = list(filter(lambda x: x["endpoint"] == endpoint, info))[0]["application-data"]
    userpass = await get_juju_secret(ops_test, info["secret-user"])
    host, nodeport = info["endpoints"].split(":")

    connection_string = (
        f"dbname='{info['database']}' user='{userpass['username']}'"
        f" host='{host}' port='{nodeport}' "
        f"password='{userpass['password']}' connect_timeout=10"
    )

    with psycopg2.connect(connection_string) as connection, connection.cursor() as cursor:
        cursor.execute("select * from information_schema.tables;")
        results = cursor.fetchone()
        assert info["database"] in results
    connection.close()
