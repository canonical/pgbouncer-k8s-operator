# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Detection of the CPU allocation provisioned for the pgbouncer container.

PgBouncer is single-threaded, so the charm runs one process per provisioned CPU. The
helpers here read a single source each; `PgBouncerK8sCharm._instance_count` is where they
are tried in order. Note that `os.cpu_count()`, the last resort there, reports the CPUs of
the whole node, ignoring both cgroup quotas and affinity.
"""

import logging

from ops import Container
from ops.pebble import Error as PebbleError

logger = logging.getLogger(__name__)

CGROUP_V2_CPU_MAX = "/sys/fs/cgroup/cpu.max"
CGROUP_V1_QUOTA = "/sys/fs/cgroup/cpu/cpu.cfs_quota_us"
CGROUP_V1_PERIOD = "/sys/fs/cgroup/cpu/cpu.cfs_period_us"

MIN_INSTANCES = 2
MAX_INSTANCES = 4


def parse_quantity(value: str | None) -> float | None:
    """Convert a Kubernetes CPU quantity ("2", "0.5", "1500m") into a number of cores."""
    if not value:
        return None
    try:
        if value.endswith("m"):
            return float(value[:-1]) / 1000
        return float(value)
    except ValueError:
        logger.warning("Unable to parse CPU quantity %r", value)
        return None


def container_cpu_limit(pod, container_name: str) -> float | None:
    """Cores provisioned for a container in the pod spec, or None if it is unconstrained."""
    spec = getattr(pod, "spec", None)
    for container in getattr(spec, "containers", None) or []:
        if container.name != container_name:
            continue
        resources = container.resources
        if resources is None:
            return None
        for quantities in (resources.limits, resources.requests):
            if quantities and (cores := parse_quantity(quantities.get("cpu"))):
                return cores
    return None


def cgroup_cpu_limit(container: Container) -> float | None:
    """Cores enforced on the container by its cgroup, or None if it is unconstrained."""
    if not container.can_connect():
        return None

    if cpu_max := _read_file(container, CGROUP_V2_CPU_MAX):
        quota, _, period = cpu_max.partition(" ")
        return _quota_to_cores(quota, period)

    return _quota_to_cores(
        _read_file(container, CGROUP_V1_QUOTA),
        _read_file(container, CGROUP_V1_PERIOD),
    )


def _read_file(container: Container, path: str) -> str | None:
    """Read a file from the container, or None if it cannot be read."""
    try:
        stdout, _ = container.exec(["cat", path]).wait_output()
    except PebbleError:
        return None
    return stdout.strip()


def _quota_to_cores(quota: str | None, period: str | None) -> float | None:
    """Convert a cgroup quota/period pair into cores, or None if no quota is enforced."""
    try:
        cores = int(quota) / int(period)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return cores if cores > 0 else None
