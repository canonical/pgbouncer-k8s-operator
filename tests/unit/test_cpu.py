# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest

from ops.testing import ExecResult, Harness

import cpu
from charm import PgBouncerK8sCharm
from constants import PGB


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
