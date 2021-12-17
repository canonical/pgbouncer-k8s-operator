# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest

from ops.model import ActiveStatus
from ops.testing import Harness

from charm import PgBouncerK8sCharm


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(PgBouncerK8sCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_pgbouncer_pebble_ready(self):
        initial_plan = self.harness.get_container_pebble_plan("pgbouncer")
        self.assertEqual(initial_plan.to_yaml(), "{}\n")

        expected_plan = {
            "services": {
                "pgbouncer": {
                    "summary": "pgbouncer service",
                    "user": "pgbouncer",
                    "command": "pgbouncer /etc/pgbouncer/pgbouncer.ini",
                    "startup": "enabled",
                    "override": "replace",
                }
            },
        }
        container = self.harness.model.unit.get_container("pgbouncer")
        self.harness.charm.on.pgbouncer_pebble_ready.emit(container)
        updated_plan = self.harness.get_container_pebble_plan("pgbouncer").to_dict()
        self.assertEqual(expected_plan, updated_plan)

        service = self.harness.model.unit.get_container("pgbouncer").get_service("pgbouncer")
        self.assertTrue(service.is_running())
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())
