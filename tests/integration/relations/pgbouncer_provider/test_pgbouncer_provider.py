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
from tests.integration.helpers.helpers import scale_application
from tests.integration.helpers.postgresql_helpers import check_database_users_existence
from tests.integration.relations.pgbouncer_provider.helpers import (
    build_connection_string,
    check_relation_data_existence,
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
ALIASED_MULTIPLE_DATABASE_CLUSTERS_RELATION_NAME = "aliased-multiple-database-clusters"


# TODO reinstate before merge
# @pytest.mark.abort_on_fail
@pytest.mark.client_relation
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
        relation = await ops_test.model.add_relation(
            f"{CLIENT_APP_NAME}:{FIRST_DATABASE_RELATION_NAME}", PGB
        )

    await ops_test.model.wait_for_idle(apps=APP_NAMES, status="active", raise_on_blocked=True)

    client_unit_name = f"{CLIENT_APP_NAME}/0"
    dbname = "application_first_database"

    # Check we can update and delete things
    update_query = (
        "DROP TABLE IF EXISTS test;"
        "CREATE TABLE test(data TEXT);"
        "INSERT INTO test(data) VALUES('some data');"
        "SELECT data FROM test;"
    )
    run_update_query = await run_sql_on_application_charm(
        ops_test,
        unit_name=client_unit_name,
        query=update_query,
        dbname=dbname,
        relation_id=relation.id,
    )
    assert "some data" in json.loads(run_update_query["results"])[0]

    # Check version is accurate
    version_query = "SELECT version();"
    run_version_query = await run_sql_on_application_charm(
        ops_test,
        unit_name=client_unit_name,
        query=version_query,
        dbname=dbname,
        relation_id=relation.id,
    )
    # Get the version of the database and compare with the information that
    # was retrieved directly from the database.
    version = await get_application_relation_data(
        ops_test, CLIENT_APP_NAME, FIRST_DATABASE_RELATION_NAME, "version"
    )
    logging.info(run_version_query)
    logging.info(version)
    assert version in json.loads(run_version_query["results"])[0][0]

    # Check we can read things in readonly
    select_query = "SELECT data FROM test;"
    run_select_query_readonly = await run_sql_on_application_charm(
        ops_test,
        unit_name=client_unit_name,
        query=select_query,
        dbname=dbname,
        relation_id=relation.id,
        readonly=True,
    )
    assert "some data" in json.loads(run_select_query_readonly["results"])[0]

    # check we can't write in readonly
    drop_query = "DROP TABLE test;"
    run_drop_query_readonly = await run_sql_on_application_charm(
        ops_test,
        unit_name=client_unit_name,
        query=drop_query,
        dbname=dbname,
        relation_id=relation.id,
        readonly=True,
    )
    assert "no results to fetch" in json.loads(run_drop_query_readonly["results"])

    # Test admin permissions
    create_database_query = "CREATE DATABASE another_database;"
    run_create_database_query = await run_sql_on_application_charm(
        ops_test,
        unit_name=client_unit_name,
        query=create_database_query,
        dbname=dbname,
        relation_id=relation.id,
    )
    assert "no results to fetch" in json.loads(run_create_database_query["results"])

    create_user_query = "CREATE USER another_user WITH ENCRYPTED PASSWORD 'test-password';"
    run_create_user_query = await run_sql_on_application_charm(
        ops_test,
        unit_name=client_unit_name,
        query=create_user_query,
        dbname=dbname,
        relation_id=relation.id,
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

    # Retrieve the connection string to both database clusters using the relation aliases
    # and assert they are different.
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


# TODO revisit readonly function
@pytest.mark.skip
@pytest.mark.client_relation
async def test_no_read_only_endpoint_in_standalone_cluster(ops_test: OpsTest):
    """Test that there is no read-only endpoint in a standalone cluster."""
    async with ops_test.fast_forward():
        # Scale down the database.
        await scale_application(ops_test, PGB, 1)

        # Try to get the connection string of the database using the read-only endpoint.
        # It should not be available anymore.
        assert await check_relation_data_existence(
            ops_test,
            CLIENT_APP_NAME,
            FIRST_DATABASE_RELATION_NAME,
            "read-only-endpoints",
            exists=False,
        )


# TODO revisit readonly function
@pytest.mark.skip
@pytest.mark.client_relation
async def test_read_only_endpoint_in_scaled_up_cluster(ops_test: OpsTest):
    """Test that there is read-only endpoint in a scaled up cluster."""
    async with ops_test.fast_forward():
        # Scale up the database.
        await scale_application(ops_test, PGB, 3)

        # Try to get the connection string of the database using the read-only endpoint.
        # It should be available again.
        assert await check_relation_data_existence(
            ops_test,
            CLIENT_APP_NAME,
            FIRST_DATABASE_RELATION_NAME,
            "read-only-endpoints",
            exists=True,
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
            f"{PGB}", f"{CLIENT_APP_NAME}:{FIRST_DATABASE_RELATION_NAME}"
        )
        await ops_test.model.wait_for_idle(apps=APP_NAMES, status="active", raise_on_blocked=True)

        # Check that the relation user was removed from the database.
        await check_database_users_existence(ops_test, [], [relation_user], database_app_name=PG)
        # TODO check relation data was correctly removed from config
