#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
import asyncio
import json
import logging
from typing import Dict, Optional
from uuid import uuid4

import psycopg2
import yaml
from juju.unit import Unit
from lightkube import AsyncClient
from lightkube.resources.core_v1 import Pod
from pytest_operator.plugin import OpsTest
from tenacity import RetryError, Retrying, stop_after_attempt, wait_exponential

from ...helpers.helpers import get_juju_secret


async def check_relation_data_existence(
    ops_test: OpsTest,
    application_name: str,
    relation_name: str,
    key: str,
    exists: bool = True,
) -> bool:
    """Checks for the existence of a key in the relation data.

    Args:
        ops_test: The ops test framework instance
        application_name: The name of the application
        relation_name: Name of the relation to get relation data from
        key: Key of data to be checked
        exists: Whether to check for the existence or non-existence

    Returns:
        whether the key exists in the relation data
    """
    try:
        # Retry mechanism used to wait for some events to be triggered,
        # like the relation departed event.
        for attempt in Retrying(
            stop=stop_after_attempt(10), wait=wait_exponential(multiplier=1, min=2, max=30)
        ):
            with attempt:
                data = await get_application_relation_data(
                    ops_test,
                    application_name,
                    relation_name,
                    key,
                )
                if exists:
                    assert data is not None
                else:
                    assert data is None
        return True
    except RetryError:
        return False


async def get_application_relation_data(
    ops_test: OpsTest,
    application_name: str,
    relation_name: str,
    key: str,
    relation_id: Optional[str] = None,
) -> Optional[str]:
    """Get relation data for an application.

    Args:
        ops_test: The ops test framework instance
        application_name: The name of the application
        relation_name: name of the relation to get connection data from
        key: key of data to be retrieved
        relation_id: id of the relation to get connection data from

    Returns:
        the data that was requested or None
            if no data in the relation

    Raises:
        ValueError if it's not possible to get application unit data
            or if there is no data for the particular relation endpoint
            and/or alias.
    """
    unit_name = f"{application_name}/0"
    raw_data = (await ops_test.juju("show-unit", unit_name))[1]
    if not raw_data:
        raise ValueError(f"no unit info could be grabbed for {unit_name}")
    data = yaml.safe_load(raw_data)
    # Filter the data based on the relation name.
    relation_data = [v for v in data[unit_name]["relation-info"] if v["endpoint"] == relation_name]
    if relation_id:
        # Filter the data based on the relation id.
        relation_data = [v for v in relation_data if v["relation-id"] == relation_id]
    if len(relation_data) == 0:
        raise ValueError(
            f"no relation data could be grabbed on relation with endpoint {relation_name}"
        )
    return relation_data[0]["application-data"].get(key)


async def run_sql_on_application_charm(
    ops_test,
    unit_name: str,
    query: str,
    dbname: str,
    relation_name,
    readonly: bool = False,
    timeout=30,
):
    """Runs the given sql query on the given application charm."""
    client_unit = ops_test.model.units.get(unit_name)
    params = {
        "dbname": dbname,
        "query": query,
        "relation-name": relation_name,
        "readonly": readonly,
    }
    logging.info(f"running query: \n {query}")
    logging.info(params)
    action = await client_unit.run_action("run-sql", **params)
    result = await asyncio.wait_for(action.wait(), timeout)
    logging.info(f"query results: {result.results}")
    return result.results


async def get_tls_flags(
    ops_test: OpsTest,
    application_name: str,
    relation_name: str,
) -> tuple[str, str]:
    if secret_uri := await get_application_relation_data(
        ops_test,
        application_name,
        relation_name,
        "secret-tls",
    ):
        secret_data = await get_juju_secret(ops_test, secret_uri)
        return secret_data["tls"], secret_data["tls-ca"]
    else:
        return (
            await get_application_relation_data(ops_test, application_name, relation_name, "tls"),
            await get_application_relation_data(
                ops_test, application_name, relation_name, "tls-ca"
            ),
        )


async def build_connection_string(
    ops_test: OpsTest,
    application_name: str,
    relation_name: str,
    *,
    relation_id: Optional[str] = None,
    read_only_endpoint: bool = False,
    database: Optional[str] = None,
) -> str:
    """Build a PostgreSQL connection string.

    Args:
        ops_test: The ops test framework instance
        application_name: The name of the application
        relation_name: name of the relation to get connection data from
        relation_id: id of the relation to get connection data from
        read_only_endpoint: whether to choose the read-only endpoint
            instead of the read/write endpoint
        database: optional database to be used in the connection string

    Returns:
        a PostgreSQL connection string
    """
    # Get the connection data exposed to the application through the relation.
    if database is None:
        database = f"{application_name.replace('-', '_')}_{relation_name.replace('-', '_')}"

    if secret_uri := await get_application_relation_data(
        ops_test,
        application_name,
        relation_name,
        "secret-user",
        relation_id,
    ):
        secret_data = await get_juju_secret(ops_test, secret_uri)
        username = secret_data["username"]
        password = secret_data["password"]
    else:
        username = await get_application_relation_data(
            ops_test, application_name, relation_name, "username", relation_id
        )
        password = await get_application_relation_data(
            ops_test, application_name, relation_name, "password", relation_id
        )
    endpoints = await get_application_relation_data(
        ops_test,
        application_name,
        relation_name,
        "read-only-endpoints" if read_only_endpoint else "endpoints",
        relation_id,
    )
    host = endpoints.split(",")[0].split(":")[0]

    return f"dbname='{database}' user='{username}' host='{host}' port={endpoints.split(',')[0].split(':')[1]} password='{password}' connect_timeout=10"


async def check_new_relation(
    ops_test: OpsTest, unit_name, relation_name, dbname, table_name="smoke_test"
):
    """Smoke test to check relation is online.

    When using this check on multiple test applications connected to one database, set table_name
    to a unique variable for each application.
    """
    test_data = "some data"
    query = (
        f"DROP TABLE IF EXISTS {table_name};"
        f"CREATE TABLE {table_name}(data TEXT);"
        f"INSERT INTO {table_name}(data) VALUES('{test_data}');"
        f"SELECT data FROM {table_name};"
    )
    run_query = await run_sql_on_application_charm(
        ops_test,
        unit_name=unit_name,
        query=query,
        dbname=dbname,
        relation_name=relation_name,
    )

    query_results = json.loads(run_query.get("results", "[]"))
    assert len(query_results) > 0 and test_data in query_results[0], (
        f"smoke check failed. Query output: {run_query}"
    )


async def delete_pod(ops_test: OpsTest, unit_name: str) -> None:
    """Delete a pod."""
    model = ops_test.model.info
    client = AsyncClient(namespace=model.name)
    await client.delete(Pod, name=unit_name.replace("/", "-"))


async def fetch_action_get_credentials(unit: Unit) -> Dict:
    """Helper to run an action to fetch connection info.

    Args:
        unit: The juju unit on which to run the get_credentials action for credentials
    Returns:
        A dictionary with the username, password and access info for the service
    """
    action = await unit.run_action(action_name="get-credentials")
    result = await action.wait()
    return result.results


def check_exposed_connection(credentials, tls):
    table_name = "expose_test"
    smoke_val = str(uuid4())

    sslmode = "require" if tls else "disable"
    if "uris" in credentials["postgresql"]:
        uri = credentials["postgresql"]["uris"]
        connstr = f"{uri}?connect_timeout=1&sslmode={sslmode}"
    else:
        host, port = credentials["postgresql"]["endpoints"].split(":")
        user = credentials["postgresql"]["username"]
        password = credentials["postgresql"]["password"]
        database = credentials["postgresql"]["database"]
        connstr = f"dbname='{database}' user='{user}' host='{host}' port='{port}' password='{password}' connect_timeout=1 sslmode={sslmode}"
    connection = psycopg2.connect(connstr)
    connection.autocommit = True
    smoke_query = (
        f"DROP TABLE IF EXISTS {table_name};"
        f"CREATE TABLE {table_name}(data TEXT);"
        f"INSERT INTO {table_name}(data) VALUES('{smoke_val}');"
        f"SELECT data FROM {table_name} WHERE data = '{smoke_val}';"
    )
    cursor = connection.cursor()
    cursor.execute(smoke_query)

    assert smoke_val == cursor.fetchone()[0]
