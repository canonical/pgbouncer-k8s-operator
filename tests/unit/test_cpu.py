# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest

from lightkube.models.core_v1 import Container, PodSpec, ResourceRequirements
from lightkube.resources.core_v1 import Pod
from ops.testing import ExecResult, Harness
from parameterized import parameterized

import cpu
from charm import PgBouncerK8sCharm
from constants import PGB


def _pod(resources: ResourceRequirements | None, name: str = PGB) -> Pod:
    return Pod(spec=PodSpec(containers=[Container(name=name, resources=resources)]))


class TestParseQuantity(unittest.TestCase):
    @parameterized.expand([
        ("2", 2.0),
        ("1", 1.0),
        ("0.5", 0.5),
        ("1500m", 1.5),
        ("500m", 0.5),
        ("100m", 0.1),
    ])
    def test_parses_kubernetes_cpu_quantities(self, value, expected):
        self.assertAlmostEqual(cpu.parse_quantity(value), expected)

    @parameterized.expand([("",), ("abc",), ("m",), ("1.5.2",), ("max",)])
    def test_returns_none_for_unparseable_values(self, value):
        self.assertIsNone(cpu.parse_quantity(value))


class TestContainerCpuLimit(unittest.TestCase):
    def test_prefers_the_cpu_limit(self):
        pod = _pod(ResourceRequirements(limits={"cpu": "2"}, requests={"cpu": "1"}))
        self.assertEqual(cpu.container_cpu_limit(pod, PGB), 2.0)

    def test_falls_back_to_the_cpu_request_when_no_limit_is_set(self):
        pod = _pod(ResourceRequirements(requests={"cpu": "1500m"}))
        self.assertEqual(cpu.container_cpu_limit(pod, PGB), 1.5)

    def test_falls_back_to_the_cpu_request_when_limits_omit_cpu(self):
        pod = _pod(ResourceRequirements(limits={"memory": "1Gi"}, requests={"cpu": "2"}))
        self.assertEqual(cpu.container_cpu_limit(pod, PGB), 2.0)

    def test_returns_none_when_the_container_has_no_resources(self):
        self.assertIsNone(cpu.container_cpu_limit(_pod(None), PGB))

    def test_returns_none_when_neither_limit_nor_request_sets_cpu(self):
        pod = _pod(ResourceRequirements(limits={"memory": "1Gi"}))
        self.assertIsNone(cpu.container_cpu_limit(pod, PGB))

    def test_ignores_other_containers_in_the_pod(self):
        pod = _pod(ResourceRequirements(limits={"cpu": "8"}), name="charm")
        self.assertIsNone(cpu.container_cpu_limit(pod, PGB))

    def test_returns_none_when_the_pod_has_no_spec(self):
        self.assertIsNone(cpu.container_cpu_limit(Pod(), PGB))


class TestCgroupCpuLimit(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(PgBouncerK8sCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.container = self.harness.charm.unit.get_container(PGB)

    def _handle(self, path, result):
        self.harness.handle_exec(PGB, ["cat", path], result=result)

    def test_reads_the_quota_from_cgroup_v2(self):
        self.harness.set_can_connect(PGB, True)
        self._handle(cpu.CGROUP_V2_CPU_MAX, "200000 100000\n")
        self.assertEqual(cpu.cgroup_cpu_limit(self.container), 2.0)

    def test_returns_none_when_cgroup_v2_reports_no_quota(self):
        self.harness.set_can_connect(PGB, True)
        self._handle(cpu.CGROUP_V2_CPU_MAX, "max 100000\n")
        self.assertIsNone(cpu.cgroup_cpu_limit(self.container))

    def test_falls_back_to_cgroup_v1_when_v2_is_absent(self):
        self.harness.set_can_connect(PGB, True)
        self._handle(cpu.CGROUP_V2_CPU_MAX, ExecResult(exit_code=1, stderr="No such file"))
        self._handle(cpu.CGROUP_V1_QUOTA, "150000\n")
        self._handle(cpu.CGROUP_V1_PERIOD, "100000\n")
        self.assertEqual(cpu.cgroup_cpu_limit(self.container), 1.5)

    def test_returns_none_when_cgroup_v1_quota_is_unset(self):
        self.harness.set_can_connect(PGB, True)
        self._handle(cpu.CGROUP_V2_CPU_MAX, ExecResult(exit_code=1, stderr="No such file"))
        self._handle(cpu.CGROUP_V1_QUOTA, "-1\n")
        self._handle(cpu.CGROUP_V1_PERIOD, "100000\n")
        self.assertIsNone(cpu.cgroup_cpu_limit(self.container))

    def test_returns_none_when_no_cgroup_file_can_be_read(self):
        self.harness.set_can_connect(PGB, True)
        self.harness.handle_exec(PGB, ["cat"], result=ExecResult(exit_code=1, stderr="nope"))
        self.assertIsNone(cpu.cgroup_cpu_limit(self.container))

    def test_returns_none_when_the_container_is_unreachable(self):
        self.harness.set_can_connect(PGB, False)
        self.assertIsNone(cpu.cgroup_cpu_limit(self.container))
