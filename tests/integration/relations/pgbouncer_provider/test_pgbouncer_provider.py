#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
import asyncio
import json
import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from constants import BACKEND_RELATION_NAME
from tests.integration.helpers.helpers import (
    get_app_relation_databag,
    get_backend_relation,
    get_backend_user_pass,
    get_cfg,
    get_legacy_relation_username,
    scale_application,
    wait_for_relation_joined_between,
)
from tests.integration.helpers.postgresql_helpers import (
    check_database_creation,
    check_database_users_existence,
)
from tests.integration.relations.pgbouncer_provider.helpers import (
    build_connection_string,
    check_new_relation,
    get_application_relation_data,
    run_sql_on_application_charm,
)

logger = logging.getLogger(__name__)

CLIENT_APP_NAME = "application"
PG = "postgresql-k8s"
PG_2 = "another-postgresql-k8s"
PGB_METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
PGB = "pgbouncer-k8s"
PGB_2 = "another-pgbouncer-k8s"
APP_NAMES = [CLIENT_APP_NAME, PG, PGB]
FIRST_DATABASE_RELATION_NAME = "first-database"
SECOND_DATABASE_RELATION_NAME = "second-database"
MULTIPLE_DATABASE_CLUSTERS_RELATION_NAME = "multiple-database-clusters"
TEST_DBNAME = "application_first_database"
CLIENT_UNIT_NAME = f"{CLIENT_APP_NAME}/0"


@pytest.mark.abort_on_fail
@pytest.mark.client_relation
@pytest.mark.dev
async def test_database_relation_with_charm_libraries(
    ops_test: OpsTest, application_charm, pgb_charm
):
    """Test basic functionality of database relation interface."""
    # Deploy both charms (multiple units for each application to test that later they correctly
    # set data in the relation application databag using only the leader unit).
    async with ops_test.fast_forward():
        await asyncio.gather(
            ops_test.model.deploy(
                application_charm,
                application_name=CLIENT_APP_NAME,
                resources={"application-image": "ubuntu:latest"},
            ),
            ops_test.model.deploy(
                pgb_charm,
                resources={
                    "pgbouncer-image": PGB_METADATA["resources"]["pgbouncer-image"][
                        "upstream-source"
                    ]
                },
                application_name=PGB,
                num_units=2,
            ),
            ops_test.model.deploy(
                PG,
                application_name=PG,
                num_units=2,
                channel="edge",
                trust=True,
            ),
        )
        await ops_test.model.add_relation(f"{PGB}:{BACKEND_RELATION_NAME}", f"{PG}:database")
        await ops_test.model.wait_for_idle(raise_on_blocked=True)
        # Relate the charms and wait for them exchanging some connection data.
        global client_relation
        client_relation = await ops_test.model.add_relation(
            f"{CLIENT_APP_NAME}:{FIRST_DATABASE_RELATION_NAME}", PGB
        )

    await ops_test.model.wait_for_idle(apps=APP_NAMES, status="active", raise_on_blocked=True)


@pytest.mark.client_relation
async def test_no_read_only_endpoint_in_standalone_cluster(ops_test: OpsTest):
    """Test that there is no read-only endpoint in a standalone cluster."""
    await scale_application(ops_test, PGB, 1)
    await check_new_relation(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        relation_id=client_relation.id,
        dbname=TEST_DBNAME,
    )

    unit = ops_test.model.applications[CLIENT_APP_NAME].units[0]
    databag = await get_app_relation_databag(ops_test, unit.name, client_relation.id)
    assert not databag.get(
        "read-only-endpoints", None
    ), f"read-only-endpoints in pgb databag: {databag}"


@pytest.mark.client_relation
async def test_read_only_endpoint_in_scaled_up_cluster(ops_test: OpsTest):
    """Test that there is read-only endpoint in a scaled up cluster."""
    await scale_application(ops_test, PGB, 2)
    await check_new_relation(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        relation_id=client_relation.id,
        dbname=TEST_DBNAME,
    )

    unit = ops_test.model.applications[CLIENT_APP_NAME].units[0]
    databag = await get_app_relation_databag(ops_test, unit.name, client_relation.id)
    read_only_endpoints = databag.get("read-only-endpoints", None)
    assert read_only_endpoints, f"read-only-endpoints not in pgb databag: {databag}"


@pytest.mark.client_relation
async def test_database_usage(ops_test: OpsTest):
    """Check we can update and delete things."""
    update_query = (
        "DROP TABLE IF EXISTS test;"
        "INSERT INTO test(data) VALUES('some data');"
        "SELECT data FROM test;"
    )
    run_update_query = await run_sql_on_application_charm(
        ops_test,
        unit_name=CLIENT_UNIT_NAME,
        query=update_query,
        dbname=TEST_DBNAME,
        relation_id=client_relation.id,
    )
    assert "some data" in json.loads(run_update_query["results"])[0]


@pytest.mark.client_relation
async def test_database_version(ops_test: OpsTest):
    """Check version is accurate."""
    version_query = "SELECT version();"
    run_version_query = await run_sql_on_application_charm(
        ops_test,
        unit_name=CLIENT_UNIT_NAME,
        query=version_query,
        dbname=TEST_DBNAME,
        relation_id=client_relation.id,
    )
    # Get the version of the database and compare with the information that
    # was retrieved directly from the database.
    version = await get_application_relation_data(
        ops_test, CLIENT_APP_NAME, FIRST_DATABASE_RELATION_NAME, "version"
    )
    assert version in json.loads(run_version_query["results"])[0][0]


@pytest.mark.client_relation
async def test_readonly_reads(ops_test: OpsTest):
    """Check we can read things in readonly."""
    select_query = "SELECT data FROM test;"
    run_select_query_readonly = await run_sql_on_application_charm(
        ops_test,
        unit_name=CLIENT_UNIT_NAME,
        query=select_query,
        dbname=TEST_DBNAME,
        relation_id=client_relation.id,
        readonly=True,
    )
    assert "some data" in json.loads(run_select_query_readonly["results"])[0]


@pytest.mark.client_relation
async def test_cant_write_in_readonly(ops_test: OpsTest):
    """Check we can't write in readonly."""
    drop_query = "DROP TABLE test;"
    run_drop_query_readonly = await run_sql_on_application_charm(
        ops_test,
        unit_name=CLIENT_UNIT_NAME,
        query=drop_query,
        dbname=TEST_DBNAME,
        relation_id=client_relation.id,
        readonly=True,
    )
    assert run_drop_query_readonly["Code"] == "1"


@pytest.mark.client_relation
async def test_database_admin_permissions(ops_test: OpsTest):
    """Test admin permissions."""
    create_database_query = "CREATE DATABASE another_database;"
    run_create_database_query = await run_sql_on_application_charm(
        ops_test,
        unit_name=CLIENT_UNIT_NAME,
        query=create_database_query,
        dbname=TEST_DBNAME,
        relation_id=client_relation.id,
    )
    assert "no results to fetch" in json.loads(run_create_database_query["results"])

    create_user_query = "CREATE USER another_user WITH ENCRYPTED PASSWORD 'test-password';"
    run_create_user_query = await run_sql_on_application_charm(
        ops_test,
        unit_name=CLIENT_UNIT_NAME,
        query=create_user_query,
        dbname=TEST_DBNAME,
        relation_id=client_relation.id,
    )
    assert "no results to fetch" in json.loads(run_create_user_query["results"])


@pytest.mark.client_relation
async def test_two_applications_doesnt_share_the_same_relation_data(
    ops_test: OpsTest, application_charm
):
    """Test that two different application connect to the database with different credentials."""
    # Set some variables to use in this test.
    another_application_app_name = "another-application"
    all_app_names = [another_application_app_name]
    all_app_names.extend(APP_NAMES)

    # Deploy another application.
    await ops_test.model.deploy(
        application_charm,
        application_name=another_application_app_name,
        resources={"application-image": "ubuntu:latest"},
    )
    await ops_test.model.wait_for_idle(status="active")

    # Relate the new application with the database
    # and wait for them exchanging some connection data.
    await ops_test.model.add_relation(
        f"{another_application_app_name}:{FIRST_DATABASE_RELATION_NAME}", PGB
    )
    await ops_test.model.wait_for_idle(status="active")

    # Assert the two application have different relation (connection) data.
    application_connection_string = await build_connection_string(
        ops_test, CLIENT_APP_NAME, FIRST_DATABASE_RELATION_NAME
    )
    another_application_connection_string = await build_connection_string(
        ops_test, another_application_app_name, FIRST_DATABASE_RELATION_NAME
    )

    assert application_connection_string != another_application_connection_string


@pytest.mark.client_relation
async def test_an_application_can_connect_to_multiple_database_clusters(
    ops_test: OpsTest, pgb_charm
):
    """Test that an application can connect to different clusters of the same database."""
    async with ops_test.fast_forward():
        await asyncio.gather(
            ops_test.model.deploy(
                pgb_charm,
                resources={
                    "pgbouncer-image": PGB_METADATA["resources"]["pgbouncer-image"][
                        "upstream-source"
                    ]
                },
                application_name=PGB_2,
                num_units=2,
            ),
            ops_test.model.deploy(
                PG,
                application_name=PG_2,
                num_units=2,
                channel="edge",
                trust=True,
            ),
        )
        await ops_test.model.add_relation(f"{PGB_2}:{BACKEND_RELATION_NAME}", f"{PG_2}:database")
        await ops_test.model.wait_for_idle(status="active")
    # Relate the application with both database clusters
    # and wait for them exchanging some connection data.
    first_cluster_relation = await ops_test.model.add_relation(
        f"{CLIENT_APP_NAME}:{MULTIPLE_DATABASE_CLUSTERS_RELATION_NAME}", PGB
    )
    second_cluster_relation = await ops_test.model.add_relation(
        f"{CLIENT_APP_NAME}:{MULTIPLE_DATABASE_CLUSTERS_RELATION_NAME}", PGB_2
    )
    await ops_test.model.wait_for_idle(status="active")

    # Retrieve the connection string to both database clusters using the relation ids and assert
    # they are different.
    application_connection_string = await build_connection_string(
        ops_test,
        CLIENT_APP_NAME,
        MULTIPLE_DATABASE_CLUSTERS_RELATION_NAME,
        relation_id=first_cluster_relation.id,
    )
    another_application_connection_string = await build_connection_string(
        ops_test,
        CLIENT_APP_NAME,
        MULTIPLE_DATABASE_CLUSTERS_RELATION_NAME,
        relation_id=second_cluster_relation.id,
    )
    assert application_connection_string != another_application_connection_string


@pytest.mark.client_relation
async def test_an_application_can_request_multiple_databases(ops_test: OpsTest, application_charm):
    """Test that an application can request additional databases using the same interface."""
    # Relate the charms using another relation and wait for them exchanging some connection data.
    await ops_test.model.add_relation(f"{CLIENT_APP_NAME}:{SECOND_DATABASE_RELATION_NAME}", PGB)
    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(apps=APP_NAMES, status="active")

    # Get the connection strings to connect to both databases.
    first_database_connection_string = await build_connection_string(
        ops_test, CLIENT_APP_NAME, FIRST_DATABASE_RELATION_NAME
    )
    second_database_connection_string = await build_connection_string(
        ops_test, CLIENT_APP_NAME, SECOND_DATABASE_RELATION_NAME
    )

    # Assert the two application have different relation (connection) data.
    assert first_database_connection_string != second_database_connection_string


@pytest.mark.client_relation
async def test_legacy_relation_compatibility(ops_test: OpsTest):
    finos = "finos-waltz-k8s"
    await ops_test.model.deploy(finos, application_name=finos, channel="edge"),
    finos_relation = await ops_test.model.add_relation(f"{PGB}:db", f"{finos}:db")
    wait_for_relation_joined_between(ops_test, PGB, finos)
    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(status="active", timeout=600)

    backend_relation = get_backend_relation(ops_test)
    pgb_user, pgb_password = await get_backend_user_pass(ops_test, backend_relation)
    await check_database_creation(ops_test, "waltz", pgb_user, pgb_password)
    finos_user = get_legacy_relation_username(ops_test, finos_relation.id)
    await check_database_users_existence(ops_test, [finos_user], [], pgb_user, pgb_password)

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(status="active", timeout=600)

    await check_new_relation(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        relation_id=client_relation.id,
        dbname=TEST_DBNAME,
    )


@pytest.mark.dev
@pytest.mark.client_relation
async def test_scaling(ops_test: OpsTest):
    """Check these relations all work when scaling pgbouncer."""
    await scale_application(ops_test, PGB, 1)
    await ops_test.model.wait_for_idle()
    await check_new_relation(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        relation_id=client_relation.id,
        dbname=TEST_DBNAME,
    )

    await scale_application(ops_test, PGB, 2)
    await ops_test.model.wait_for_idle()
    await check_new_relation(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        relation_id=client_relation.id,
        dbname=TEST_DBNAME,
    )


@pytest.mark.client_relation
async def test_relation_broken(ops_test: OpsTest):
    """Test that the user is removed when the relation is broken."""
    async with ops_test.fast_forward():
        # Retrieve the relation user.
        relation_user = await get_application_relation_data(
            ops_test, CLIENT_APP_NAME, FIRST_DATABASE_RELATION_NAME, "username"
        )

        # Break the relation.
        await ops_test.model.applications[PGB].remove_relation(
            f"{PGB}:database", f"{CLIENT_APP_NAME}:{FIRST_DATABASE_RELATION_NAME}"
        )
        await ops_test.model.wait_for_idle(apps=APP_NAMES, status="active", raise_on_blocked=True)
        backend_rel = get_backend_relation(ops_test)
        pg_user, pg_pass = await get_backend_user_pass(ops_test, backend_rel)

        # Check that the relation user was removed from the database.
        await check_database_users_existence(
            ops_test, [], [relation_user], pg_user=pg_user, pg_user_password=pg_pass
        )

    # check relation data was correctly removed from config
    pgb_unit_name = ops_test.model.applications[PGB].units[0].name
    cfg = await get_cfg(ops_test, pgb_unit_name)
    assert "first-database" not in cfg["databases"].keys()
    assert "first-database_readonly" not in cfg["databases"].keys()
