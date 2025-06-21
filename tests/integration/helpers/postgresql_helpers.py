#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
import itertools
from pathlib import Path

import psycopg2
import yaml
from juju.unit import Unit
from pytest_operator.plugin import OpsTest

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
PG = "postgresql-k8s"


async def check_database_users_existence(
    ops_test: OpsTest,
    users_that_should_exist: list[str],
    users_that_should_not_exist: list[str],
    pg_user: str,
    pg_user_password: str,
    admin: bool = False,
) -> None:
    """Checks that applications users exist in the database.

    Args:
        ops_test: The ops test framework
        users_that_should_exist: List of users that should exist in the database
        users_that_should_not_exist: List of users that should not exist in the database
        admin: Whether to check if the existing users are superusers
        pg_user: an admin user that can access the database
        pg_user_password: password for `pg_user`
    """
    unit = ops_test.model.applications[PG].units[0]
    unit_address = await get_unit_address(ops_test, unit.name)

    # Retrieve all users in the database.
    output = await execute_query_on_unit(
        unit_address,
        pg_user,
        pg_user_password,
        (
            "SELECT CONCAT(usename, ':', usesuper) FROM pg_catalog.pg_user;"
            if admin
            else "SELECT usename FROM pg_catalog.pg_user;"
        ),
    )
    # Assert users that should exist.
    for user in users_that_should_exist:
        if admin:
            # The t flag indicates the user is a superuser.
            assert f"{user}:t" in output
        else:
            assert user in output

    # Assert users that should not exist.
    for user in users_that_should_not_exist:
        assert user not in output


async def check_database_creation(
    ops_test: OpsTest, database: str, user: str, password: str
) -> None:
    """Checks that database and tables are successfully created for the application.

    Args:
        ops_test: The ops test framework
        database: Name of the database that should have been created
        user: an admin user that can access the database
        password: password for `user`
    """
    for unit in ops_test.model.applications[PG].units:
        unit_address = await get_unit_address(ops_test, unit.name)

        # Ensure database exists in PostgreSQL.
        output = await execute_query_on_unit(
            unit_address,
            user,
            password,
            "SELECT datname FROM pg_database;",
        )
        assert database in output

        # Ensure that application tables exist in the database
        output = await execute_query_on_unit(
            unit_address,
            user,
            password,
            "SELECT table_name FROM information_schema.tables;",
            database=database,
        )
        assert len(output)


async def execute_query_on_unit(
    unit_address: str,
    user: str,
    password: str,
    query: str,
    database: str = "postgres",
):
    """Execute given PostgreSQL query on a unit.

    Args:
        unit_address: The public IP address of the unit to execute the query on.
        user: user to execute as.
        password: The PostgreSQL superuser password.
        query: Query to execute.
        database: Optional database to connect to (defaults to postgres database).

    Returns:
        A list of rows that were potentially returned from the query.
    """
    with (
        psycopg2.connect(
            f"dbname='{database}' user='{user}' host='{unit_address}' password='{password}' connect_timeout=10"
        ) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(query)
        output = list(itertools.chain(*cursor.fetchall()))
    return output


async def get_postgres_primary(ops_test: OpsTest) -> str:
    """Get the PostgreSQL primary unit.

    Args:
        ops_test: ops_test instance.

    Returns:
        the current PostgreSQL primary unit.
    """
    action = await ops_test.model.units.get(f"{PG}/0").run_action("get-primary")
    action = await action.wait()
    return action.results["primary"]


async def get_unit_address(ops_test: OpsTest, unit_name: str) -> str:
    """Get unit IP address.

    Args:
        ops_test: The ops test framework instance
        unit_name: The name of the unit

    Returns:
        IP address of the unit
    """
    status = await ops_test.model.get_status()
    return status["applications"][unit_name.split("/")[0]].units[unit_name]["address"]


async def run_command_on_unit(ops_test: OpsTest, unit_name: str, command: str) -> str:
    """Run a command on a specific unit.

    Args:
        ops_test: The ops test framework instance
        unit_name: The name of the unit to run the command on
        command: The command to run

    Returns:
        the command output if it succeeds, otherwise raises an exception.
    """
    complete_command = f"ssh --container postgresql {unit_name} {command}"
    return_code, stdout, _ = await ops_test.juju(*complete_command.split())
    if return_code != 0:
        raise Exception(
            "Expected command %s to succeed instead it failed: %s", command, return_code
        )
    return stdout


def get_unit_by_index(app: str, units: list, index: int) -> Unit | None:
    """Get unit by index.

    Args:
        app: Name of the application
        units: List of units
        index: index of the unit to get
    """
    for unit in units:
        if unit.name == f"{app}/{index}":
            return unit


async def get_leader_unit(ops_test: OpsTest, app: str) -> Unit | None:
    leader_unit = None
    for unit in ops_test.model.applications[app].units:
        if await unit.is_leader_from_status():
            leader_unit = unit
            break

    return leader_unit
