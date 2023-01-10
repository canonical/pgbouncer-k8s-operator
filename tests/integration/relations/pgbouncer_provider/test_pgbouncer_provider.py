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
SECONDARY_CLIENT_APP_NAME = "secondary-application"
PG = "postgresql-k8s"
PGB_METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
PGB_RESOURCES = {
    "pgbouncer-image": PGB_METADATA["resources"]["pgbouncer-image"]["upstream-source"]
}
PGB = "pgbouncer-k8s"
APP_NAMES = [CLIENT_APP_NAME, PG, PGB]
FIRST_DATABASE_RELATION_NAME = "first-database"
SECOND_DATABASE_RELATION_NAME = "second-database"

APPLICATION_FIRST_DBNAME = "application_first_database"
SECONDARY_APPLICATION_FIRST_DBNAME = "secondary_application_first_database"
SECONDARY_APPLICATION_SECOND_DBNAME = "secondary_application_second_database"


@pytest.mark.abort_on_fail
@pytest.mark.client_relation
async def test_database_relation_with_charm_libraries(
    ops_test: OpsTest, application_charm, pgb_charm
):
    """Test basic functionality of database relation interface."""
    # Deploy both charms (multiple units for each application to test that later they correctly
    # set data in the relation application databag using only the leader unit).
    await asyncio.gather(
        ops_test.model.deploy(
            application_charm,
            application_name=CLIENT_APP_NAME,
            resources={"application-image": "ubuntu:latest"},
        ),
        ops_test.model.deploy(
            pgb_charm,
            resources=PGB_RESOURCES,
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


@pytest.mark.client_relation
async def test_database_usage(ops_test: OpsTest):
    """Check we can update and delete things."""
    update_query = (
        "DROP TABLE IF EXISTS test;"
        "CREATE TABLE test(data TEXT);"
        "INSERT INTO test(data) VALUES('some data');"
        "SELECT data FROM test;"
    )
    run_update_query = await run_sql_on_application_charm(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        query=update_query,
        dbname=APPLICATION_FIRST_DBNAME,
        relation_id=client_relation.id,
        relation_name=FIRST_DATABASE_RELATION_NAME,
    )
    assert "some data" in json.loads(run_update_query["results"])[0]


@pytest.mark.client_relation
async def test_database_version(ops_test: OpsTest):
    """Check version is accurate."""
    version_query = "SELECT version();"
    run_version_query = await run_sql_on_application_charm(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        query=version_query,
        dbname=APPLICATION_FIRST_DBNAME,
        relation_id=client_relation.id,
        relation_name=FIRST_DATABASE_RELATION_NAME,
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
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        query=select_query,
        dbname=APPLICATION_FIRST_DBNAME,
        relation_id=client_relation.id,
        relation_name=FIRST_DATABASE_RELATION_NAME,
        readonly=True,
    )
    assert "some data" in json.loads(run_select_query_readonly["results"])[0]


@pytest.mark.client_relation
async def test_cant_write_in_readonly(ops_test: OpsTest):
    """Check we can't write in readonly."""
    drop_query = "DROP TABLE test;"
    run_drop_query_readonly = await run_sql_on_application_charm(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        query=drop_query,
        dbname=APPLICATION_FIRST_DBNAME,
        relation_id=client_relation.id,
        relation_name=FIRST_DATABASE_RELATION_NAME,
        readonly=True,
    )
    assert run_drop_query_readonly["Code"] == "1"


@pytest.mark.client_relation
async def test_database_admin_permissions(ops_test: OpsTest):
    """Test admin permissions."""
    create_database_query = "CREATE DATABASE another_database;"
    run_create_database_query = await run_sql_on_application_charm(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        query=create_database_query,
        dbname=APPLICATION_FIRST_DBNAME,
        relation_id=client_relation.id,
        relation_name=FIRST_DATABASE_RELATION_NAME,
    )
    assert "no results to fetch" in json.loads(run_create_database_query["results"])

    create_user_query = "CREATE USER another_user WITH ENCRYPTED PASSWORD 'test-password';"
    run_create_user_query = await run_sql_on_application_charm(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        query=create_user_query,
        dbname=APPLICATION_FIRST_DBNAME,
        relation_id=client_relation.id,
        relation_name=FIRST_DATABASE_RELATION_NAME,
    )
    assert "no results to fetch" in json.loads(run_create_user_query["results"])


@pytest.mark.client_relation
async def test_no_read_only_endpoint_in_standalone_cluster(ops_test: OpsTest):
    """Test that there is no read-only endpoint in a standalone cluster."""
    unit = ops_test.model.applications[CLIENT_APP_NAME].units[0]
    await scale_application(ops_test, PGB, 1)
    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=APP_NAMES, status="active", timeout=600, idle_period=30
        )
    await check_new_relation(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        relation_id=client_relation.id,
        dbname=APPLICATION_FIRST_DBNAME,
        relation_name=FIRST_DATABASE_RELATION_NAME,
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
    await ops_test.model.wait_for_idle(apps=APP_NAMES, status="active", timeout=600)
    await check_new_relation(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        relation_id=client_relation.id,
        dbname=APPLICATION_FIRST_DBNAME,
        relation_name=FIRST_DATABASE_RELATION_NAME,
    )

    unit = ops_test.model.applications[CLIENT_APP_NAME].units[0]
    databag = await get_app_relation_databag(ops_test, unit.name, client_relation.id)
    read_only_endpoints = databag.get("read-only-endpoints", None)
    assert read_only_endpoints, f"read-only-endpoints not in pgb databag: {databag}"


@pytest.mark.client_relation
async def test_each_relation_has_unique_credentials(ops_test: OpsTest, application_charm):
    """Test that two different applications connect to the database with different credentials."""
    all_app_names = [SECONDARY_CLIENT_APP_NAME] + APP_NAMES

    # Deploy secondary application.
    await ops_test.model.deploy(
        application_charm,
        application_name=SECONDARY_CLIENT_APP_NAME,
        resources={"application-image": "ubuntu:latest"},
    )
    await ops_test.model.wait_for_idle(status="active", apps=all_app_names)

    # Relate the new application with the database
    # and wait for them exchanging some connection data.
    secondary_relation = await ops_test.model.add_relation(
        f"{SECONDARY_CLIENT_APP_NAME}:{FIRST_DATABASE_RELATION_NAME}", PGB
    )
    wait_for_relation_joined_between(ops_test, PGB, SECONDARY_CLIENT_APP_NAME)
    await ops_test.model.wait_for_idle(status="active", apps=all_app_names)

    # Check both relations can connect
    await check_new_relation(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        relation_id=client_relation.id,
        dbname=APPLICATION_FIRST_DBNAME,
        relation_name=FIRST_DATABASE_RELATION_NAME,
    )
    await check_new_relation(
        ops_test,
        unit_name=ops_test.model.applications[SECONDARY_CLIENT_APP_NAME].units[0].name,
        relation_id=secondary_relation.id,
        dbname=SECONDARY_APPLICATION_FIRST_DBNAME,
        table_name="check_multiple_apps_connected_to_one_cluster",
        relation_name=FIRST_DATABASE_RELATION_NAME,
    )

    # Assert the two application have different relation (connection) data.
    app_connstr = await build_connection_string(
        ops_test, CLIENT_APP_NAME, FIRST_DATABASE_RELATION_NAME
    )
    secondary_app_connstr = await build_connection_string(
        ops_test, SECONDARY_CLIENT_APP_NAME, FIRST_DATABASE_RELATION_NAME
    )

    logger.info(app_connstr)
    logger.info(secondary_app_connstr)
    assert app_connstr != secondary_app_connstr


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
        dbname=APPLICATION_FIRST_DBNAME,
        relation_name=FIRST_DATABASE_RELATION_NAME,
    )


@pytest.mark.client_relation
async def test_multiple_pgb_can_connect_to_one_backend(ops_test: OpsTest, pgb_charm):
    pgb_secondary = f"{PGB}-secondary"
    await ops_test.model.deploy(
        pgb_charm,
        resources=PGB_RESOURCES,
        application_name=pgb_secondary,
    )
    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(apps=[pgb_secondary], status="active"),

    await ops_test.model.add_relation(f"{pgb_secondary}:{BACKEND_RELATION_NAME}", f"{PG}:database")
    wait_for_relation_joined_between(ops_test, PG, pgb_secondary)

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(apps=APP_NAMES + [pgb_secondary])

    secondary_relation = await ops_test.model.add_relation(
        f"{SECONDARY_CLIENT_APP_NAME}:{SECOND_DATABASE_RELATION_NAME}", pgb_secondary
    )
    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle()

    # Check new relation works
    await check_new_relation(
        ops_test,
        unit_name=ops_test.model.applications[SECONDARY_CLIENT_APP_NAME].units[0].name,
        relation_id=secondary_relation.id,
        dbname=SECONDARY_APPLICATION_SECOND_DBNAME,
        table_name="check_multiple_pgb_connected_to_one_postgres",
        relation_name=SECOND_DATABASE_RELATION_NAME,
    )
    # Check the new relation hasn't affected existing connectivity
    await check_new_relation(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        relation_id=client_relation.id,
        relation_name=FIRST_DATABASE_RELATION_NAME,
        dbname=APPLICATION_FIRST_DBNAME,
    )


@pytest.mark.client_relation
async def test_scaling(ops_test: OpsTest):
    """Check these relations all work when scaling pgbouncer."""
    await scale_application(ops_test, PGB, 1)
    await ops_test.model.wait_for_idle(apps=APP_NAMES)
    await check_new_relation(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        relation_id=client_relation.id,
        dbname=APPLICATION_FIRST_DBNAME,
        relation_name=FIRST_DATABASE_RELATION_NAME,
    )

    await scale_application(ops_test, PGB, 2)
    await ops_test.model.wait_for_idle(apps=APP_NAMES)
    await check_new_relation(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        relation_id=client_relation.id,
        dbname=APPLICATION_FIRST_DBNAME,
        relation_name=FIRST_DATABASE_RELATION_NAME,
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
