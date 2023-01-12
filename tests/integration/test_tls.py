# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from tests.integration.helpers.helpers import (
    deploy_postgres_k8s_bundle,
    get_backend_relation,
)
from tests.integration.helpers.postgresql_helpers import (
    enable_connections_logging,
    get_postgres_primary,
    run_command_on_unit,
)

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
FINOS_WALTZ = "finos-waltz"
PGB = METADATA["name"]
PG = "postgresql-k8s"
TLS = "tls-certificates-operator"
RELATION = "backend-database"


@pytest.mark.tls
async def test_tls_encrypted_connection_to_postgres(ops_test: OpsTest):
    async with ops_test.fast_forward():
        # Relate PgBouncer to PostgreSQL.
        await deploy_postgres_k8s_bundle(ops_test)
        relation = get_backend_relation(ops_test)

        # Enable additional logs on the PostgreSQL instance to check TLS
        # being used in a later step.
        await enable_connections_logging(ops_test, f"{PG}/0")

        # Deploy an app and relate it to PgBouncer to open a connection
        # between PgBouncer and PostgreSQL.
        await ops_test.model.deploy(
            "finos-waltz-k8s", application_name=FINOS_WALTZ, channel="edge"
        )
        relation = await ops_test.model.add_relation(f"{PGB}:db", f"{FINOS_WALTZ}:db")
        await ops_test.model.wait_for_idle(
            apps=[PG, PGB, FINOS_WALTZ, TLS], status="active", timeout=600
        )

        # Check the logs to ensure TLS is being used by PgBouncer.
        postgresql_primary_unit = await get_postgres_primary(ops_test)
        logs = await run_command_on_unit(
            ops_test, postgresql_primary_unit, "/charm/bin/pebble logs -n=all"
        )
        assert (
            f"connection authorized: user=relation_id_{relation.id} database=waltz"
            " SSL enabled (protocol=TLSv1.2, cipher=ECDHE-RSA-AES256-GCM-SHA384, bits=256)" in logs
        ), "TLS is not being used on connections to PostgreSQL"
