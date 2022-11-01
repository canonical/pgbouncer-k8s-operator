#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
from multiprocessing import ProcessError
from pathlib import Path
from typing import Dict

import yaml
from charms.pgbouncer_k8s.v0 import pgb
from pytest_operator.plugin import OpsTest
from tenacity import RetryError, Retrying, stop_after_delay, wait_fixed

from constants import AUTH_FILE_PATH, INI_PATH, LOG_PATH

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
PGB = METADATA["name"]
PG = "postgresql-k8s"


def get_backend_relation(ops_test: OpsTest):
    """Gets the backend-database relation used to connect pgbouncer to the backend."""
    return get_joining_relations(ops_test, PGB, PG)[0]


def get_joining_relations(ops_test: OpsTest, app_1: str, app_2: str):
    """Gets every relation in this model that joins app_1 and app_2."""
    relations = []
    for rel in ops_test.model.relations:
        logging.info(rel.data)
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


async def get_backend_user_pass(ops_test, backend_relation):
    pgb_unit = ops_test.model.applications[PGB].units[0]
    backend_databag = await get_app_relation_databag(ops_test, pgb_unit.name, backend_relation.id)
    pgb_user = backend_databag["username"]
    pgb_password = backend_databag["password"]
    return (pgb_user, pgb_password)


async def get_cfg(ops_test: OpsTest, unit_name: str) -> pgb.PgbConfig:
    """Gets pgbouncer config from pgbouncer container."""
    cat = await cat_file_from_unit(ops_test, INI_PATH, unit_name)
    return pgb.PgbConfig(cat)


async def get_pgb_log(ops_test: OpsTest, unit_name) -> str:
    """Gets pgbouncer logs from pgbouncer container."""
    return await cat_file_from_unit(ops_test, LOG_PATH, unit_name)


async def get_userlist(ops_test: OpsTest, unit_name) -> str:
    """Gets pgbouncer logs from pgbouncer container."""
    return await cat_file_from_unit(ops_test, AUTH_FILE_PATH, unit_name)


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
                if new_relation_joined(ops_test, endpoint_one, endpoint_two):
                    break
    except RetryError:
        assert False, "New relation failed to join after 3 minutes."


def new_relation_joined(ops_test: OpsTest, endpoint_one: str, endpoint_two: str) -> bool:
    for rel in ops_test.model.relations:
        endpoints = [endpoint.name for endpoint in rel.endpoints]
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
                if relation_exited(ops_test, endpoint_one, endpoint_two):
                    break
    except RetryError:
        assert False, "Relation failed to exit after 3 minutes."


def relation_exited(ops_test: OpsTest, endpoint_one: str, endpoint_two: str) -> bool:
    """Returns true if the relation between endpoint_one and endpoint_two has been removed."""
    for rel in ops_test.model.relations:
        endpoints = [endpoint.name for endpoint in rel.endpoints]
        if endpoint_one not in endpoints and endpoint_two not in endpoints:
            return True
    return False


async def scale_application(ops_test: OpsTest, application_name: str, scale: int) -> None:
    """Scale a given application to a specific unit count.

    Args:
        ops_test: The ops test framework instance
        application_name: The name of the application
        scale: The number of units to scale to
    """
    await ops_test.model.applications[application_name].scale(scale)
    await ops_test.model.wait_for_idle(
        apps=[application_name],
        status="active",
        timeout=1000,
        wait_for_exact_units=scale,
    )


# TODO update this to match the old one perfectly.
async def build_connection_string(ops_test: OpsTest, readonly: bool = False):
    pgb_unit = ops_test.model.applications[PGB].units[0].name
    pgb_unit_address = await get_unit_address(ops_test, pgb_unit, app_name="pgbouncer-k8s")
    backend_relation = get_backend_relation(ops_test)
    pgb_app_databag = await get_app_relation_databag(
        ops_test, unit_name=pgb_unit, relation_id=backend_relation.id
    )
    user = pgb_app_databag.get("username")
    password = pgb_app_databag.get("password")
    database = json.loads(pgb_app_databag.get("data")).get("database")
    import logging

    logging.info(pgb_app_databag)
    # host = (
    #     client_app_databag.get("read-only-endpoints")
    #     if readonly
    #     else client_app_databag.get("endpoints")
    # )
    return f"dbname='{database}' user='{user}' host='{pgb_unit_address}' password='{password}' connect_timeout=10 port=6432"


async def get_unit_address(ops_test: OpsTest, unit_name: str, app_name: str = None) -> str:
    """Get unit IP address.

    Args:
        ops_test: The ops test framework instance
        unit_name: The name of the unit

    Returns:
        IP address of the unit
    """
    status = await ops_test.model.get_status()
    if not app_name:
        app_name = unit_name.split("/")[0]
    return status["applications"][app_name].units[unit_name]["address"]
