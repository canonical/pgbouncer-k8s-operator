# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest
from unittest.mock import Mock, patch

from charms.pgbouncer_operator.v0 import pgb
from ops.model import ActiveStatus, WaitingStatus
from ops.testing import Harness

from charm import INI_PATH, PGB, USERLIST_PATH, PgBouncerK8sCharm


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(PgBouncerK8sCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @patch("charms.pgbouncer_operator.v0.pgb.generate_password", return_value="pw")
    def test_on_install(self, _gen_pw):
        self.harness.charm.on.install.emit()
        pgb_container = self.harness.model.unit.get_container(PGB)

        # assert config is set to default - it gets updated in the config-changed hook fired later
        ini = pgb_container.pull(INI_PATH).read()
        self.assertEqual(ini, pgb.PgbConfig(pgb.DEFAULT_CONFIG).render())

        # Assert userlist is created with the generated password
        userlist = pgb_container.pull(USERLIST_PATH).read()
        self.assertEqual('"juju-admin" "pw"', userlist)
        _gen_pw.assert_called_once()

    @patch("charm.PgBouncerK8sCharm._read_pgb_config", return_value=pgb.PgbConfig(pgb.DEFAULT_CONFIG))
    @patch("ops.model.Container.restart")
    def test_on_config_changed(self, _restart, _read):
        mock_cores = 1
        self.harness.charm._cores = mock_cores
        max_db_connections = 44

        # create default config object and modify it as we expect in the hook.
        test_config = pgb.PgbConfig(pgb.DEFAULT_CONFIG)
        test_config["pgbouncer"]["pool_mode"] = "transaction"
        test_config.set_max_db_connection_derivatives(
            max_db_connections=max_db_connections,
            pgb_instances=mock_cores,
        )

        initial_plan = self.harness.get_container_pebble_plan(PGB).to_dict()
        self.harness.update_config(
            {
                "pool_mode": "transaction",
                "max_db_connections": max_db_connections,
            }
        )
        updated_plan = self.harness.get_container_pebble_plan(PGB).to_dict()
        self.assertNotEqual(initial_plan, updated_plan)
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())
        _restart.assert_called()

        # Test changing charm config propagates to container config file.
        pgb_container = self.harness.model.unit.get_container(PGB)
        container_config = pgb_container.pull(INI_PATH).read()
        self.assertEqual(container_config, test_config.render())

    @patch("ops.model.Container.can_connect", return_value=False)
    @patch("ops.charm.ConfigChangedEvent.defer")
    def test_on_config_changed_container_cant_connect(self, can_connect, defer):
        self.harness.update_config()
        self.assertEqual(
            self.harness.model.unit.status,
            WaitingStatus("waiting for pgbouncer workload container."),
        )
        defer.assert_called()

    def test_on_pgbouncer_pebble_ready(self):
        initial_plan = self.harness.get_container_pebble_plan(PGB)
        self.assertEqual(initial_plan.to_yaml(), "{}\n")

        expected_plan = {
            "services": {
                PGB: {
                    "summary": "pgbouncer service",
                    "user": "postgres",
                    "command": f"pgbouncer {INI_PATH}",
                    "startup": "enabled",
                    "override": "replace",
                }
            },
        }
        container = self.harness.model.unit.get_container(PGB)
        self.harness.charm.on.pgbouncer_pebble_ready.emit(container)
        updated_plan = self.harness.get_container_pebble_plan(PGB).to_dict()
        self.assertEqual(expected_plan, updated_plan)

        service = self.harness.model.unit.get_container(PGB).get_service(PGB)
        self.assertTrue(service.is_running())
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    @patch("charm.PgBouncerK8sCharm._reload_pgbouncer")
    def test_render_pgb_config(self, _reload_pgbouncer):
        cfg = pgb.PgbConfig(pgb.DEFAULT_CONFIG)
        self.harness.charm._render_pgb_config(cfg, reload_pgbouncer=True)
        _reload_pgbouncer.assert_called()

        pgb_container = self.harness.model.unit.get_container(PGB)
        ini = pgb_container.pull(INI_PATH).read()
        self.assertEqual(cfg.render(), ini)

    def test_read_pgb_config(self):
        test_cfg = pgb.PgbConfig(pgb.DEFAULT_CONFIG)
        self.harness.charm._render_pgb_config(test_cfg)
        read_cfg = self.harness.charm._read_pgb_config()
        self.assertDictEqual(dict(read_cfg), dict(test_cfg))

    @patch("charm.PgBouncerK8sCharm._reload_pgbouncer")
    def test_render_userlist(self, _reload_pgbouncer):
        pgb_container = self.harness.model.unit.get_container(PGB)
        self.harness.charm._render_userlist({"test-user": "pw"}, reload_pgbouncer=True)
        _reload_pgbouncer.assert_called()

        userlist = pgb_container.pull(USERLIST_PATH).read()
        self.assertEqual('"test-user" "pw"', userlist)

    def test_read_userlist(self):
        self.harness.charm._render_userlist(userlist={"test-admin": "pass"})
        users = self.harness.charm._read_userlist()
        self.assertDictEqual(users, {"test-admin": "pass"})

    # ===========
    #  UTILITIES
    # ===========

    def get_result(self, event):
        """Get the intended result from a mocked event.

        Effectively this gets whatever is passed into `event.set_results()`, given that event is
        actually a `Mock` object.
        """
        return dict(event.method_calls[0][1][0])
