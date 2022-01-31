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
        self._pgbouncer_container = "pgbouncer"
        self._peer_relation = "pgbouncer-replicas"

        self.harness = Harness(PgBouncerK8sCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_on_install(self):
        self.harness.charm._on_install("mock_event")

        pgb_container = self.harness.model.unit.get_container(self._pgbouncer_container)
        ini_path = "/etc/pgbouncer/pgbouncer.ini"
        userlist_path = "/etc/pgbouncer/userlist.txt"

        ini = pgb_container.pull(ini_path).read()
        self.assertEqual(ini, self.harness.charm._generate_pgbouncer_ini())

        userlist = pgb_container.pull(userlist_path).read()
        self.assertEqual(userlist, self.harness.charm._generate_userlist())

    def test_on_config_changed(self):
        self.harness.update_config()
        initial_plan = self.harness.get_container_pebble_plan(self._pgbouncer_container).to_dict()
        self.harness.update_config({"pgb_databases": "db"})
        updated_plan = self.harness.get_container_pebble_plan(self._pgbouncer_container).to_dict()

        self.assertNotEqual(initial_plan, updated_plan)
        placeholder = updated_plan["services"]["pgbouncer"]["environment"]["PGB_DATABASES"]
        self.assertEqual(placeholder, "db")
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    def test_on_pgbouncer_pebble_ready(self):
        self.maxDiff = None
        initial_plan = self.harness.get_container_pebble_plan(self._pgbouncer_container)
        self.assertEqual(initial_plan.to_yaml(), "{}\n")

        expected_plan = {
            "services": {
                "pgbouncer": {
                    "summary": "pgbouncer service",
                    "user": "pgbouncer",
                    "command": "pgbouncer /etc/pgbouncer/pgbouncer.ini",
                    "startup": "enabled",
                    "override": "replace",
                    "environment": {
                        "PGB_DATABASES": "exampledb = host=pg-host port=5432 dbname=exampledb",
                        "PGB_LISTEN_PORT": 6432,
                        "PGB_LISTEN_ADDRESS": "localhost",
                        "PGB_ADMIN_USERS": "juju-admin",
                    },
                }
            },
        }
        container = self.harness.model.unit.get_container(self._pgbouncer_container)
        self.harness.charm.on.pgbouncer_pebble_ready.emit(container)
        updated_plan = self.harness.get_container_pebble_plan(self._pgbouncer_container).to_dict()
        self.assertEqual(expected_plan, updated_plan)

        service = self.harness.model.unit.get_container(self._pgbouncer_container).get_service(
            "pgbouncer"
        )
        self.assertTrue(service.is_running())
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())
