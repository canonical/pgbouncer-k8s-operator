#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
import pytest as pytest
from pytest_operator.plugin import OpsTest

from tests.integration.helpers.helpers import (
    PGB,
    PGB_METADATA,
    POSTGRESQL_APP_NAME,
    deploy_and_relate_application_with_pgbouncer,
)

MATTERMOST_APP_NAME = "mattermost"
TLS_CERTIFICATES_APP_NAME = "tls-certificates-operator"
APPLICATION_UNITS = 2
DATABASE_UNITS = 3


@pytest.mark.tls_tests
async def test_mattermost_db(ops_test: OpsTest) -> None:
    """Deploy Mattermost to test the 'db' relation.

    Mattermost needs TLS enabled on PostgreSQL to correctly connect to it.

    Args:
        ops_test: The ops test framework
    """
    charm = await ops_test.build_charm(".")
    async with ops_test.fast_forward():
        await ops_test.model.deploy(
            charm,
            resources={
                "pgbouncer-image": PGB_METADATA["resources"]["pgbouncer-image"]["upstream-source"]
            },
            application_name=PGB,
            num_units=APPLICATION_UNITS,
        )
        # Deploy Postgresql operator
        await ops_test.model.deploy(
            POSTGRESQL_APP_NAME, channel="edge", trust=True, num_units=DATABASE_UNITS
        )
        await ops_test.model.relate(PGB, POSTGRESQL_APP_NAME)
        # Deploy TLS Certificates operator.
        config = {"generate-self-signed-certificates": "true", "ca-common-name": "Test CA"}
        await ops_test.model.deploy(TLS_CERTIFICATES_APP_NAME, channel="beta", config=config)
        # Relate it to the PgBouncer to enable TLS.
        await ops_test.model.relate(PGB, TLS_CERTIFICATES_APP_NAME)
        await ops_test.model.relate(TLS_CERTIFICATES_APP_NAME, POSTGRESQL_APP_NAME)
        await ops_test.model.wait_for_idle(status="active", timeout=1000)

        # Deploy Mattermost
        await deploy_and_relate_application_with_pgbouncer(
            ops_test, "mattermost-k8s", MATTERMOST_APP_NAME, APPLICATION_UNITS, status="waiting"
        )
