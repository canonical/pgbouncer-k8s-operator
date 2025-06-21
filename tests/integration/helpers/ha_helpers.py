# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import psycopg2
import requests
from lightkube.core.client import Client
from lightkube.resources.core_v1 import Pod
from pytest_operator.plugin import OpsTest
from tenacity import (
    Retrying,
    stop_after_delay,
    wait_fixed,
)

from .helpers import CLIENT_APP_NAME


async def get_password(ops_test: OpsTest, app: str, down_unit: str | None = None) -> str:
    """Use the charm action to retrieve the password from provided application.

    Returns:
        string with the password stored on the peer relation databag.
    """
    # Can retrieve from any unit running unit, so we pick the first.
    for unit in ops_test.model.applications[app].units:
        if unit.name != down_unit:
            unit_name = unit.name
            break
    action = await ops_test.model.units.get(unit_name).run_action("get-password")
    action = await action.wait()
    return action.results["password"]


def get_patroni_cluster(unit_ip: str) -> dict[str, str]:
    resp = requests.get(f"http://{unit_ip}:8008/cluster")
    return resp.json()


def get_member_lag(cluster: dict, member_name: str) -> int:
    """Return the lag of a specific member."""
    for member in cluster["members"]:
        if member["name"] == member_name.replace("/", "-"):
            return member.get("lag", 0)
    return 0


async def check_writes(ops_test) -> int:
    """Gets the total writes from the test charm and compares to the writes from db."""
    total_expected_writes = await stop_continuous_writes(ops_test)
    actual_writes, max_number_written = await count_writes(ops_test)
    for member, count in actual_writes.items():
        assert count == max_number_written[member], (
            f"{member}: writes to the db were missed: count of actual writes ({count}) on {member} different from the max number written ({max_number_written[member]})."
        )
        assert total_expected_writes == count, f"{member}: writes to the db were missed."
    return total_expected_writes


async def are_writes_increasing(ops_test, down_unit: str | None = None) -> None:
    """Verify new writes are continuing by counting the number of writes."""
    writes, _ = await count_writes(ops_test, down_unit=down_unit)
    for member, count in writes.items():
        for attempt in Retrying(stop=stop_after_delay(60 * 3), wait=wait_fixed(3), reraise=True):
            with attempt:
                more_writes, _ = await count_writes(ops_test, down_unit=down_unit)
                assert more_writes[member] > count, (
                    f"{member}: writes not continuing to DB (current writes: {more_writes[member]} - previous writes: {count})"
                )


async def count_writes(
    ops_test: OpsTest, down_unit: str | None = None
) -> tuple[dict[str, int], dict[str, int]]:
    """Count the number of writes in the database."""
    app = "postgresql-k8s"
    password = await get_password(ops_test, app=app, down_unit=down_unit)
    status = await ops_test.model.get_status()
    for unit_name, unit in status["applications"][app]["units"].items():
        if unit_name != down_unit:
            cluster = get_patroni_cluster(unit["address"])
            break

    count = {}
    maximum = {}
    for member in cluster["members"]:
        if member["role"] != "replica" and member["host"].split(".")[0] != (
            down_unit or ""
        ).replace("/", "-"):
            host = member["host"]

            # Translate the service hostname to an IP address.
            model = ops_test.model.info
            client = Client(namespace=model.name)
            service = client.get(Pod, name=host.split(".")[0])
            ip = service.status.podIP

            connection_string = (
                f"dbname='{CLIENT_APP_NAME.replace('-', '_')}_database' user='operator'"
                f" host='{ip}' password='{password}' connect_timeout=10"
            )

            with psycopg2.connect(connection_string) as connection, connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(number), MAX(number) FROM continuous_writes;")
                results = cursor.fetchone()
                count[member["name"]] = results[0]
                maximum[member["name"]] = results[1]
            connection.close()
    return count, maximum


async def start_continuous_writes(
    ops_test: OpsTest, app: str, test_app: str = CLIENT_APP_NAME
) -> None:
    """Start continuous writes to PostgreSQL."""
    # Start the process by relating the application to the database or
    # by calling the action if the relation already exists.
    relations = [
        relation
        for relation in ops_test.model.applications[app].relations
        if not relation.is_peer
        and f"{relation.requires.application_name}:{relation.requires.name}"
        == f"{test_app}:database"
    ]
    if not relations:
        await ops_test.model.relate(app, f"{test_app}:database")
        await ops_test.model.wait_for_idle(status="active", timeout=1000)
    else:
        action = (
            await ops_test.model.applications[test_app]
            .units[0]
            .run_action("start-continuous-writes")
        )
        await action.wait()
    for attempt in Retrying(stop=stop_after_delay(60 * 5), wait=wait_fixed(3), reraise=True):
        with attempt:
            action = (
                await ops_test.model.applications[test_app]
                .units[0]
                .run_action("start-continuous-writes")
            )
            await action.wait()
            assert action.results["result"] == "True", "Unable to create continuous_writes table"


async def stop_continuous_writes(ops_test: OpsTest, test_app: str = CLIENT_APP_NAME) -> int:
    """Stops continuous writes to PostgreSQL and returns the last written value."""
    action = await ops_test.model.units.get(f"{test_app}/0").run_action("stop-continuous-writes")
    action = await action.wait()
    return int(action.results["writes"])
