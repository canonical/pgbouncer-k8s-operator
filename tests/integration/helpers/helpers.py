#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from configparser import ConfigParser
from multiprocessing import ProcessError
from pathlib import Path
from typing import Dict, Optional

import yaml
from juju.unit import Unit
from pytest_operator.plugin import OpsTest
from tenacity import (
    RetryError,
    Retrying,
    stop_after_attempt,
    stop_after_delay,
    wait_fixed,
)

from constants import AUTH_FILE_PATH, PGB_DIR

from ..juju_ import run_action

CHARM_SERIES = "jammy"
CLIENT_APP_NAME = "postgresql-test-app"
PGB_METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
PGB = PGB_METADATA["name"]
PG = "postgresql-k8s"
POSTGRESQL_APP_NAME = "postgresql-k8s"


def get_backend_relation(ops_test: OpsTest):
    """Gets the backend-database relation used to connect pgbouncer to the backend."""
    return get_joining_relations(ops_test, PGB, PG)[0]


def get_joining_relations(ops_test: OpsTest, app_1: str, app_2: str):
    """Gets every relation in this model that joins app_1 and app_2."""
    relations = []
    for rel in ops_test.model.relations:
        apps = [endpoint["application-name"] for endpoint in rel.data["endpoints"]]
        if app_1 in apps and app_2 in apps:
            relations.append(rel)
    return relations


def get_legacy_relation_username(ops_test: OpsTest, relation_id: int):
    """Gets a username as it should be generated in the db and db-admin legacy relations."""
    app_name = ops_test.model.applications[PGB].name
    model_name = ops_test.model_name
    return f"{app_name}_user_{relation_id}_{model_name}".replace("-", "_")


async def get_unit_info(ops_test: OpsTest, unit_name: str) -> Dict:
    """Gets the databags from the given relation.

    Args:
        ops_test: ops_test testing instance
        unit_name: name of the unit

    Returns:
        A dict containing all unit information available to juju
    """
    get_databag = await ops_test.juju(
        "show-unit",
        unit_name,
        "--format=json",
    )
    return json.loads(get_databag[1])[unit_name]


async def get_endpoint_info(ops_test: OpsTest, unit_name: str, endpoint: str) -> str:
    """Gets the endpoint information from the given unit.

    Args:
        ops_test: ops_test testing instance
        unit_name: name of the unit
        endpoint: name of the endpoint

    Returns:
        A str containing endpoint information available to juju
    """
    get_databag = await ops_test.juju(
        "show-unit",
        unit_name,
        "--format=json",
    )
    relation_info = json.loads(get_databag[1])[unit_name]["relation-info"]
    return next(filter(lambda x: x["endpoint"] == endpoint, relation_info))["application-data"][
        "endpoints"
    ]


async def get_app_relation_databag(ops_test: OpsTest, unit_name: str, relation_id: int) -> Dict:
    """Gets the app relation databag from the given relation.

    Juju show-unit command is backwards, so you have to pass the unit_name of the unit to which the
    data is presented, not the unit that presented the data.

    Args:
        ops_test: ops_test testing instance
        unit_name: name of the unit to which this databag is presented
        relation_id: id of the required relation

    Returns:
        App databag for the relation with the given ID, or None if nothing can be found.
    """
    unit_data = await get_unit_info(ops_test, unit_name)
    relations = unit_data["relation-info"]
    for relation in relations:
        if relation["relation-id"] == relation_id:
            return relation.get("application-data", None)

    return None


async def get_juju_secret(ops_test: OpsTest, secret_uri: str) -> Dict[str, str]:
    """Retrieve juju secret."""
    secret_unique_id = secret_uri.split("/")[-1]
    complete_command = f"show-secret {secret_uri} --reveal --format=json"
    _, stdout, _ = await ops_test.juju(*complete_command.split())
    return json.loads(stdout)[secret_unique_id]["content"]["Data"]


async def get_backend_user_pass(ops_test, backend_relation):
    pgb_unit = ops_test.model.applications[PGB].units[0]
    backend_databag = await get_app_relation_databag(ops_test, pgb_unit.name, backend_relation.id)
    if secret_uri := backend_databag.get("secret-user"):
        secret_data = await get_juju_secret(ops_test, secret_uri)
        return (secret_data["username"], secret_data["password"])

    pgb_user = backend_databag["username"]
    pgb_password = backend_databag["password"]
    return (pgb_user, pgb_password)


async def get_cfg(ops_test: OpsTest, unit_name: str) -> dict:
    """Gets pgbouncer config from pgbouncer container."""
    parser = ConfigParser()
    parser.optionxform = str
    parser.read_string(
        await cat_file_from_unit(ops_test, f"{PGB_DIR}/instance_0/pgbouncer.ini", unit_name)
    )

    cfg = dict(parser)
    # Convert Section objects to dictionaries, so they can hold dictionaries themselves.
    for section, data in cfg.items():
        cfg[section] = dict(data)

    # ConfigParser object creates a DEFAULT section of an .ini file, which we don't need.
    del cfg["DEFAULT"]

    return cfg


async def get_userlist(ops_test: OpsTest, unit_name) -> str:
    """Gets pgbouncer logs from pgbouncer container."""
    return await cat_file_from_unit(ops_test, AUTH_FILE_PATH, unit_name)


async def run_command_on_unit(ops_test: OpsTest, unit_name: str, command: str) -> str:
    """Run a command on a specific unit.

    Args:
        ops_test: The ops test framework instance
        unit_name: The name of the unit to run the command on
        command: The command to run

    Returns:
        the command output if it succeeds, otherwise raises an exception.
    """
    complete_command = f"ssh --container pgbouncer {unit_name} {command}"
    return_code, stdout, _ = await ops_test.juju(*complete_command.split())
    if return_code != 0:
        raise Exception(
            "Expected command %s to succeed instead it failed: %s", command, return_code
        )
    return stdout


async def cat_file_from_unit(ops_test: OpsTest, filepath: str, unit_name: str) -> str:
    """Gets a file from the pgbouncer container of a pgbouncer application unit."""
    cat_cmd = f"ssh --container pgbouncer {unit_name} cat {filepath}"
    return_code, output, _ = await ops_test.juju(*cat_cmd.split(" "))
    if return_code != 0:
        raise ProcessError(
            "Expected cat command %s to succeed instead it failed: %s", cat_cmd, return_code
        )
    return output


def wait_for_relation_joined_between(
    ops_test: OpsTest, endpoint_one: str, endpoint_two: str
) -> None:
    """Wait for relation to be be created before checking if it's waiting or idle.

    Args:
        ops_test: running OpsTest instance
        endpoint_one: one endpoint of the relation. Doesn't matter if it's provider or requirer.
        endpoint_two: the other endpoint of the relation.
    """
    try:
        for attempt in Retrying(stop=stop_after_delay(3 * 60), wait=wait_fixed(3)):
            with attempt:
                assert new_relation_joined(ops_test, endpoint_one, endpoint_two)
    except RetryError:
        assert False, "New relation failed to join after 3 minutes."


def new_relation_joined(ops_test: OpsTest, endpoint_one: str, endpoint_two: str) -> bool:
    for rel in ops_test.model.relations:
        endpoints = [f"{endpoint.application_name}:{endpoint.name}" for endpoint in rel.endpoints]
        if endpoint_one in endpoints and endpoint_two in endpoints:
            return True
    return False


def wait_for_relation_removed_between(
    ops_test: OpsTest, endpoint_one: str, endpoint_two: str
) -> None:
    """Wait for relation to be removed before checking if it's waiting or idle.

    Args:
        ops_test: running OpsTest instance
        endpoint_one: one endpoint of the relation. Doesn't matter if it's provider or requirer.
        endpoint_two: the other endpoint of the relation.
    """
    try:
        for attempt in Retrying(stop=stop_after_delay(3 * 60), wait=wait_fixed(3)):
            with attempt:
                assert relation_exited(ops_test, endpoint_one, endpoint_two)
    except RetryError:
        assert False, "Relation failed to exit after 3 minutes."


def relation_exited(ops_test: OpsTest, endpoint_one: str, endpoint_two: str) -> bool:
    """Returns true if the relation between endpoint_one and endpoint_two has been removed."""
    for rel in ops_test.model.relations:
        endpoints = [f"{endpoint.application_name}:{endpoint.name}" for endpoint in rel.endpoints]
        if endpoint_one not in endpoints and endpoint_two not in endpoints:
            return True
    return False


async def scale_application(
    ops_test: OpsTest, application_name: str, scale: int, expected_status="active"
) -> None:
    """Scale a given application to a specific unit count.

    Args:
        ops_test: The ops test framework instance
        application_name: The name of the application
        scale: The number of units to scale to
        expected_status: the expected status of the application
    """
    await ops_test.model.applications[application_name].scale(scale)
    await ops_test.model.wait_for_idle(
        apps=[application_name],
        status=expected_status,
        timeout=1000,
        wait_for_exact_units=scale,
    )


async def deploy_and_relate_application_with_pgbouncer(
    ops_test: OpsTest,
    charm: str,
    application_name: str,
    number_of_units: int,
    channel: str = "stable",
    relation: str = "db",
    status: str = "blocked",
) -> int:
    """Helper function to deploy and relate application with PgBouncer.

    Args:
        ops_test: The ops test framework.
        charm: Charm identifier.
        application_name: The name of the application to deploy.
        number_of_units: The number of units to deploy.
        channel: The channel to use for the charm.
        relation: Name of the PgBouncer relation to relate
            the application to.
        status: The status to wait for in the application (default: blocked).

    Returns:
        the id of the created relation.
    """
    # Deploy application.
    await ops_test.model.deploy(
        charm,
        channel=channel,
        application_name=application_name,
        num_units=number_of_units,
    )
    await ops_test.model.wait_for_idle(
        apps=[application_name],
        status=status,
        raise_on_blocked=False,
        timeout=1000,
    )

    # Relate application to PgBouncer.
    relation = await ops_test.model.relate(f"{application_name}", f"{PGB}:{relation}")
    await ops_test.model.wait_for_idle(
        apps=[application_name],
        status="active",
        raise_on_blocked=False,  # Application that needs a relation is blocked initially.
        raise_on_error=False,
        timeout=1000,
    )

    return relation.id


async def app_name(ops_test: OpsTest, application_name: str = "pgbouncer") -> Optional[str]:
    """Returns the name of the cluster running PgBouncer.

    This is important since not all deployments of the PgBouncer charm have the application name
    "pgbouncer".
    Note: if multiple clusters are running PgBouncer this will return the one first found.
    """
    status = await ops_test.model.get_status()
    for app in ops_test.model.applications:
        if application_name in status["applications"][app]["charm"]:
            return app

    return None


async def check_tls(ops_test: OpsTest, enabled: bool) -> bool:
    """Returns whether TLS is enabled on a related PgBouncer cluster.

    Args:
        ops_test: The ops test framework instance.
        enabled: check if TLS is enabled/disabled.

    Returns:
        Whether TLS is enabled/disabled.
    """
    cleint_name = await app_name(ops_test, CLIENT_APP_NAME)
    unit = ops_test.model.applications[cleint_name].units[0]
    params = {
        "dbname": f"{CLIENT_APP_NAME.replace('-', '_')}_database",
        "relation-name": "database",
        "readonly": False,
    }
    try:
        for attempt in Retrying(stop=stop_after_attempt(10), wait=wait_fixed(3)):
            with attempt:
                action = await unit.run_action("test-tls", **params)
                result = await action.wait()

                tls_enabled = result.results["results"] == "True"
                if enabled != tls_enabled:
                    raise ValueError(f"TLS is{' not' if not tls_enabled else ''} enabled")
                return True
    except RetryError:
        return False


async def get_leader_unit(ops_test: OpsTest, app: str) -> Optional[Unit]:
    leader_unit = None
    for unit in ops_test.model.applications[app].units:
        if await unit.is_leader_from_status():
            leader_unit = unit
            break

    return leader_unit


async def get_data_integrator_credentials(unit: Unit) -> Dict:
    """Helper to run an action on data-integrator to get credentials."""
    return await run_action(unit, "get-credentials")


async def get_status_log(ops_test: OpsTest, unit: Unit) -> str:
    """Helper to get the status log of a unit."""
    _, status_log, _ = await ops_test.juju("show-status-log", unit.name)
    return status_log
