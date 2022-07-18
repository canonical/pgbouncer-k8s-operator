# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper functions for pgbouncer integration tests."""

import logging

from charms.pgbouncer_operator.v0 import pgb
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

INI_PATH = f"{pgb.PGB_DIR}/pgbouncer.ini"


async def cat_from(unit, path: str) -> str:
    """Pull the content of a file from one unit.

    Args:
        unit: the Juju unit instance.
        path: the path of the file to get the contents from.

    Returns:
        the entire content of the file.
    """
    action = await unit.run(f"cat {path}")
    return action.results.get("Stdout", None)


async def get_cfg(unit) -> pgb.PgbConfig:
    """Get primary config file from a unit.

    Returns:
        pgb.PgbConfig: primary config object from the given unit
    """
    cfg_str = await cat_from(unit, INI_PATH)
    return pgb.PgbConfig(cfg_str)


async def get_unit_address(ops_test: OpsTest, application_name: str, unit_name: str) -> str:
    """Get unit IP address.

    Args:
        ops_test: The ops test framework instance
        application_name: The name of the application
        unit_name: The name of the unit

    Returns:
        IP address of the unit
    """
    status = await ops_test.model.get_status()
    return status["applications"][application_name].units[unit_name]["address"]


async def get_unit_cores(unit: str) -> int:
    """Get the number of CPU cores available on the given unit.

    Since PgBouncer is single-threaded, the charm automatically creates one instance of pgbouncer
    per CPU core on a given unit. Therefore, the number of cores is the expected number of
    pgbouncer instances.

    Args:
        unit: the juju unit instance
    Returns:
        The number of cores on the unit.
    """
    get_cores_from_unit = await unit.run('python3 -c "import os; print(os.cpu_count())"')
    cores = get_cores_from_unit.results.get("Stdout")
    return int(cores)


async def get_running_instances(unit: str, service: str) -> int:
    """Returns the number of running instances of the given service.

    Uses `ps` to find the number of instances of a given service.

    Args:
        unit: the juju unit running the service
        service: a string that can be used to grep for the intended service.

    Returns:
        an integer defining the number of running instances.
    """
    get_running_instances = await unit.run(f"ps aux | grep {service}")
    ps_output = get_running_instances.results.get("Stdout")
    num_of_ps_lines = len(ps_output.split("\n"))
    # one extra for grep process, and one for a blank line at the end
    return num_of_ps_lines - 2
