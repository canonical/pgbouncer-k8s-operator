#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
import asyncio
import json
import logging
import os

import psycopg2
import pytest
from pytest_operator.plugin import OpsTest

from constants import BACKEND_RELATION_NAME, PEER_RELATION_NAME

from ... import markers
from ...helpers.helpers import (
    CHARM_SERIES,
    PG,
    PGB,
    PGB_METADATA,
    get_app_relation_databag,
    get_backend_relation,
    get_backend_user_pass,
    get_cfg,
    get_legacy_relation_username,
    scale_application,
    wait_for_relation_joined_between,
)
from ...helpers.postgresql_helpers import (
    check_database_creation,
    check_database_users_existence,
)
from .helpers import (
    build_connection_string,
    check_new_relation,
    delete_pod,
    get_application_relation_data,
    run_sql_on_application_charm,
)

logger = logging.getLogger(__name__)

CLIENT_APP_NAME = "postgresql-test-app"
SECONDARY_CLIENT_APP_NAME = "secondary-application"
DATA_INTEGRATOR_APP_NAME = "data-integrator"
PGB_RESOURCES = {
    "pgbouncer-image": PGB_METADATA["resources"]["pgbouncer-image"]["upstream-source"]
}
APP_NAMES = [CLIENT_APP_NAME, PG, PGB]
FIRST_DATABASE_RELATION_NAME = "database"
SECOND_DATABASE_RELATION_NAME = "second-database"

APPLICATION_FIRST_DBNAME = "postgresql_test_app_database"
SECONDARY_APPLICATION_FIRST_DBNAME = "secondary_application_database"
SECONDARY_APPLICATION_SECOND_DBNAME = "secondary_application_second_database"


@pytest.mark.abort_on_fail
async def test_database_relation_with_charm_libraries(ops_test: OpsTest, charm):
    """Test basic functionality of database relation interface."""
    # Deploy both charms (multiple units for each application to test that later they correctly
    # set data in the relation application databag using only the leader unit).
    await asyncio.gather(
        ops_test.model.deploy(
            CLIENT_APP_NAME,
            application_name=CLIENT_APP_NAME,
            series=CHARM_SERIES,
            channel="latest/edge",
            config=(
                {"extra_user_roles": "CREATEDB,CREATEROLE"}
                if os.environ["POSTGRESQL_CHARM_CHANNEL"].split("/")[0] == "14"
                else None
            ),
        ),
        ops_test.model.deploy(
            charm,
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
            channel=os.environ["POSTGRESQL_CHARM_CHANNEL"],
            trust=True,
            config={"profile": "testing"},
        ),
    )
    await ops_test.model.add_relation(f"{PGB}:{BACKEND_RELATION_NAME}", f"{PG}:database")

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=[PGB, PG],
            status="active",
            raise_on_blocked=False,
            timeout=1200,
        )

    # Relate the charms and wait for them exchanging some connection data.
    await ops_test.model.add_relation(f"{CLIENT_APP_NAME}:{FIRST_DATABASE_RELATION_NAME}", PGB)

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(apps=APP_NAMES, status="active")

    # Check that on juju 3 we have secrets and no username and password in the rel databag
    if hasattr(ops_test.model, "list_secrets"):
        logger.info("checking for secrets")
        secret_uri, password, auth_file = await asyncio.gather(
            get_application_relation_data(
                ops_test,
                CLIENT_APP_NAME,
                FIRST_DATABASE_RELATION_NAME,
                "secret-user",
            ),
            get_application_relation_data(
                ops_test,
                CLIENT_APP_NAME,
                FIRST_DATABASE_RELATION_NAME,
                "password",
            ),
            get_application_relation_data(
                ops_test,
                PGB,
                PEER_RELATION_NAME,
                "auth-file",
            ),
        )
        assert secret_uri is not None
        assert password is None
        assert auth_file is None

    # This test hasn't passed if we can't pass a tiny amount of data through the new relation
    await check_new_relation(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        dbname=APPLICATION_FIRST_DBNAME,
        relation_name=FIRST_DATABASE_RELATION_NAME,
    )


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
        relation_name=FIRST_DATABASE_RELATION_NAME,
    )
    assert "some data" in json.loads(run_update_query["results"])[0]


async def test_database_version(ops_test: OpsTest):
    """Check version is accurate."""
    version_query = "SELECT version();"
    run_version_query = await run_sql_on_application_charm(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        query=version_query,
        dbname=APPLICATION_FIRST_DBNAME,
        relation_name=FIRST_DATABASE_RELATION_NAME,
    )
    # Get the version of the database and compare with the information that
    # was retrieved directly from the database.
    version = await get_application_relation_data(
        ops_test, CLIENT_APP_NAME, FIRST_DATABASE_RELATION_NAME, "version"
    )
    assert version in json.loads(run_version_query["results"])[0][0]


async def test_readonly_reads(ops_test: OpsTest):
    """Check we can read things in readonly."""
    select_query = "SELECT data FROM test;"
    run_select_query_readonly = await run_sql_on_application_charm(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        query=select_query,
        dbname=APPLICATION_FIRST_DBNAME,
        relation_name=FIRST_DATABASE_RELATION_NAME,
        readonly=True,
    )
    assert "some data" in json.loads(run_select_query_readonly["results"])[0]


async def test_cant_write_in_readonly(ops_test: OpsTest):
    """Check we can't write in readonly."""
    drop_query = "DROP TABLE test;"
    run_drop_query_readonly = await run_sql_on_application_charm(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        query=drop_query,
        dbname=APPLICATION_FIRST_DBNAME,
        relation_name=FIRST_DATABASE_RELATION_NAME,
        readonly=True,
    )
    if "Code" in run_drop_query_readonly:
        retcode = run_drop_query_readonly["Code"]
    else:
        retcode = run_drop_query_readonly["return-code"]
    assert int(retcode) == 1


async def test_database_admin_permissions(ops_test: OpsTest):
    """Test admin permissions."""
    if os.environ["POSTGRESQL_CHARM_CHANNEL"].split("/")[0] != "14":
        pytest.skip(
            "Skipping check for database and user creation permissions on PostgreSQL above 14, as they are not supported."
        )
    create_database_query = "CREATE DATABASE another_database;"
    run_create_database_query = await run_sql_on_application_charm(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        query=create_database_query,
        dbname=APPLICATION_FIRST_DBNAME,
        relation_name=FIRST_DATABASE_RELATION_NAME,
    )
    assert "no results to fetch" in json.loads(run_create_database_query["results"])

    create_user_query = "CREATE USER another_user WITH ENCRYPTED PASSWORD 'test-password';"
    run_create_user_query = await run_sql_on_application_charm(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        query=create_user_query,
        dbname=APPLICATION_FIRST_DBNAME,
        relation_name=FIRST_DATABASE_RELATION_NAME,
    )
    assert "no results to fetch" in json.loads(run_create_user_query["results"])


async def test_no_read_only_endpoint_in_standalone_cluster(ops_test: OpsTest):
    """Test that there is a read-only endpoint in a standalone cluster."""
    unit = ops_test.model.applications[CLIENT_APP_NAME].units[0]
    await scale_application(ops_test, PGB, 1)
    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=APP_NAMES, status="active", timeout=600, idle_period=40
        )
    await check_new_relation(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        dbname=APPLICATION_FIRST_DBNAME,
        relation_name=FIRST_DATABASE_RELATION_NAME,
    )

    relations = [
        relation
        for relation in ops_test.model.applications[PGB].relations
        if not relation.is_peer
        and f"{relation.requires.application_name}:{relation.requires.name}"
        == f"{CLIENT_APP_NAME}:database"
    ]
    unit = ops_test.model.applications[CLIENT_APP_NAME].units[0]
    databag = await get_app_relation_databag(ops_test, unit.name, relations[0].id)
    assert databag.get("read-only-endpoints", None), (
        f"read-only-endpoints not in pgb databag: {databag}"
    )


async def test_read_only_endpoint_in_scaled_up_cluster(ops_test: OpsTest):
    """Test that there is read-only endpoint in a scaled up cluster."""
    await scale_application(ops_test, PGB, 2)
    await ops_test.model.wait_for_idle(apps=APP_NAMES, status="active", timeout=600)
    await check_new_relation(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        dbname=APPLICATION_FIRST_DBNAME,
        relation_name=FIRST_DATABASE_RELATION_NAME,
    )

    relations = [
        relation
        for relation in ops_test.model.applications[PGB].relations
        if not relation.is_peer
        and f"{relation.requires.application_name}:{relation.requires.name}"
        == f"{CLIENT_APP_NAME}:database"
    ]
    unit = ops_test.model.applications[CLIENT_APP_NAME].units[0]
    databag = await get_app_relation_databag(ops_test, unit.name, relations[0].id)
    read_only_endpoints = databag.get("read-only-endpoints", None)
    assert read_only_endpoints, f"read-only-endpoints not in pgb databag: {databag}"


async def test_each_relation_has_unique_credentials(ops_test: OpsTest):
    """Test that two different applications connect to the database with different credentials."""
    all_app_names = [SECONDARY_CLIENT_APP_NAME, *APP_NAMES]

    # Deploy secondary application.
    await ops_test.model.deploy(
        CLIENT_APP_NAME,
        application_name=SECONDARY_CLIENT_APP_NAME,
        series=CHARM_SERIES,
        channel="edge",
    )
    await ops_test.model.wait_for_idle(status="blocked", apps=[SECONDARY_CLIENT_APP_NAME])

    # Relate the new application with the database
    # and wait for them exchanging some connection data.
    await ops_test.model.add_relation(
        f"{SECONDARY_CLIENT_APP_NAME}:{FIRST_DATABASE_RELATION_NAME}", PGB
    )
    wait_for_relation_joined_between(
        ops_test, f"{SECONDARY_CLIENT_APP_NAME}:{FIRST_DATABASE_RELATION_NAME}", f"{PGB}:database"
    )
    await ops_test.model.wait_for_idle(status="active", apps=all_app_names)

    # Check both relations can connect
    await check_new_relation(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        dbname=APPLICATION_FIRST_DBNAME,
        relation_name=FIRST_DATABASE_RELATION_NAME,
    )
    await check_new_relation(
        ops_test,
        unit_name=ops_test.model.applications[SECONDARY_CLIENT_APP_NAME].units[0].name,
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


async def test_an_application_can_request_multiple_databases(ops_test: OpsTest):
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


@markers.amd64_only  # finos-waltz-k8s charm not available for arm64
async def test_legacy_relation_compatibility(ops_test: OpsTest):
    finos = "finos-waltz-k8s"
    (await ops_test.model.deploy(finos, application_name=finos, channel="edge"),)
    finos_relation = await ops_test.model.add_relation(f"{PGB}:db", f"{finos}:db")
    wait_for_relation_joined_between(ops_test, f"{PGB}:db", f"{finos}:db")
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
        dbname=APPLICATION_FIRST_DBNAME,
        relation_name=FIRST_DATABASE_RELATION_NAME,
    )


async def test_multiple_pgb_can_connect_to_one_backend(ops_test: OpsTest, charm):
    pgb_secondary = f"{PGB}-secondary"
    await ops_test.model.deploy(
        charm,
        resources=PGB_RESOURCES,
        application_name=pgb_secondary,
        series=CHARM_SERIES,
        trust=True,
    )
    async with ops_test.fast_forward():
        (await ops_test.model.wait_for_idle(apps=[pgb_secondary], status="blocked"),)

    await ops_test.model.add_relation(f"{pgb_secondary}:{BACKEND_RELATION_NAME}", f"{PG}:database")
    wait_for_relation_joined_between(
        ops_test, f"{pgb_secondary}:{BACKEND_RELATION_NAME}", f"{PG}:database"
    )

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(apps=[*APP_NAMES, pgb_secondary])

    await ops_test.model.add_relation(
        f"{SECONDARY_CLIENT_APP_NAME}:{SECOND_DATABASE_RELATION_NAME}", pgb_secondary
    )
    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle()

    # Check new relation works
    await check_new_relation(
        ops_test,
        unit_name=ops_test.model.applications[SECONDARY_CLIENT_APP_NAME].units[0].name,
        dbname=SECONDARY_APPLICATION_SECOND_DBNAME,
        table_name="check_multiple_pgb_connected_to_one_postgres",
        relation_name=SECOND_DATABASE_RELATION_NAME,
    )
    # Check the new relation hasn't affected existing connectivity
    await check_new_relation(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        relation_name=FIRST_DATABASE_RELATION_NAME,
        dbname=APPLICATION_FIRST_DBNAME,
    )


async def test_scaling(ops_test: OpsTest):
    """Check these relations all work when scaling pgbouncer."""
    await scale_application(ops_test, PGB, 1)
    await ops_test.model.wait_for_idle(apps=APP_NAMES)
    await check_new_relation(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        dbname=APPLICATION_FIRST_DBNAME,
        relation_name=FIRST_DATABASE_RELATION_NAME,
    )

    await scale_application(ops_test, PGB, 2)
    await ops_test.model.wait_for_idle(apps=APP_NAMES)
    await check_new_relation(
        ops_test,
        unit_name=ops_test.model.applications[CLIENT_APP_NAME].units[0].name,
        dbname=APPLICATION_FIRST_DBNAME,
        relation_name=FIRST_DATABASE_RELATION_NAME,
    )


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
    assert "database" not in cfg["databases"]
    assert "database_readonly" not in cfg["databases"]


async def test_relation_with_data_integrator(ops_test: OpsTest):
    """Test that the charm can be related to the data integrator without extra user roles."""
    config = {"database-name": "test-database"}
    await ops_test.model.deploy(
        DATA_INTEGRATOR_APP_NAME,
        channel="edge",
        config=config,
    )
    await ops_test.model.add_relation(f"{PGB}:database", DATA_INTEGRATOR_APP_NAME)
    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(status="active")


@markers.amd64_only  # indico charm not available for arm64
async def test_indico_database(ops_test: OpsTest) -> None:
    """Tests deploying and relating to the Indico charm."""
    async with ops_test.fast_forward(fast_interval="30s"):
        await ops_test.model.deploy(
            "indico",
            channel="stable",
            application_name="indico",
            num_units=1,
        )
        await ops_test.model.deploy(
            "redis-k8s", channel="latest/edge", application_name="redis-broker"
        )
        await ops_test.model.deploy(
            "redis-k8s", channel="latest/edge", application_name="redis-cache"
        )
        await asyncio.gather(
            ops_test.model.relate("redis-broker", "indico:redis-broker"),
            ops_test.model.relate("redis-cache", "indico:redis-cache"),
        )

        # Wait for model to stabilise
        await ops_test.model.wait_for_idle(
            apps=["indico"],
            status="waiting",
            timeout=1000,
        )

        # Verify that the charm doesn't block when the extensions are enabled.
        logger.info("Verifying that the charm doesn't block when the extensions are enabled")
        config = {"plugin_pg_trgm_enable": "True", "plugin_unaccent_enable": "True"}
        await ops_test.model.applications[PG].set_config(config)
        await ops_test.model.wait_for_idle(apps=[PG], status="active")
        await ops_test.model.relate(PGB, "indico")
        await ops_test.model.wait_for_idle(
            apps=[PG, PGB, "indico"], status="active", timeout=2000, raise_on_error=False
        )

        # FIXME: Pebble in Indico doesn't survive the subsequent restart. Investigate further
        await ops_test.model.remove_application("indico", block_until_done=True)


async def test_connection_is_possible_after_pod_deletion(ops_test: OpsTest) -> None:
    """Tests that the connection is possible after the pod is deleted."""
    await ops_test.model.applications[PGB].set_config({"expose-external": "nodeport"})
    await ops_test.model.wait_for_idle(
        apps=[PGB],
        status="active",
        timeout=600,
        idle_period=30,
    )

    # Delete the pod.
    unit = ops_test.model.applications[PGB].units[0]
    await delete_pod(ops_test, unit.name)
    await ops_test.model.wait_for_idle(status="active", idle_period=3)

    await asyncio.sleep(20)

    # Test the connection.
    connection_string = await build_connection_string(
        ops_test, DATA_INTEGRATOR_APP_NAME, relation_name="postgresql", database="test-database"
    )
    connection = None
    try:
        connection = psycopg2.connect(connection_string)
    except psycopg2.Error:
        assert False, "failed to connect to PgBouncer after deleting it's pod"
    finally:
        if connection is not None:
            connection.close()
