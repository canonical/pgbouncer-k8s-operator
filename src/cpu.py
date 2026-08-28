# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Detection of the CPU quota Kubernetes enforces on the pgbouncer container.

Juju turns a `cores`/`cpu-power` constraint into a CPU *limit* on the workload container,
which the kernel enforces as a cgroup quota. Reading that quota from inside the container
needs no Kubernetes API call and no `juju trust`. The charm container has no CPU limit of
its own, so `os.cpu_count()` there reports the whole node.
"""

import logging

from ops import Container
from ops.pebble import Error as PebbleError

logger = logging.getLogger(__name__)

CGROUP_V2_CPU_MAX = "/sys/fs/cgroup/cpu.max"
CGROUP_V1_QUOTA = "/sys/fs/cgroup/cpu/cpu.cfs_quota_us"
CGROUP_V1_PERIOD = "/sys/fs/cgroup/cpu/cpu.cfs_period_us"


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
