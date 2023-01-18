# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest
from unittest.mock import call, patch

from charms.pgbouncer_k8s.v0.pgb import DEFAULT_CONFIG, PgbConfig
from ops.model import ActiveStatus, WaitingStatus
from ops.testing import Harness

from charm import PgBouncerK8sCharm
from constants import BACKEND_RELATION_NAME, INI_PATH, PGB


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(PgBouncerK8sCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin_with_initial_hooks()
        self.charm = self.harness.charm

    @patch("ops.model.Container.make_dir")
    def test_on_start(self, _mkdir):
        self.harness.add_relation(BACKEND_RELATION_NAME, "postgres")
        self.harness.set_leader(True)
        self.charm.on.start.emit()
        pgb_container = self.harness.model.unit.get_container(PGB)

        # assert config is set to default - it gets updated in the config-changed hook fired later
        ini = pgb_container.pull(INI_PATH).read()
        self.assertEqual(ini, PgbConfig(DEFAULT_CONFIG).render())

    @patch("charm.PgBouncerK8sCharm.update_client_connection_info")
    @patch("charm.PgBouncerK8sCharm.reload_pgbouncer")
    @patch("ops.model.Container.make_dir")
    @patch("charm.PgBouncerK8sCharm.check_pgb_running")
    def test_on_config_changed(self, _check_pgb_running, _mkdir, _reload, _update_connection_info):
        self.harness.add_relation(BACKEND_RELATION_NAME, "postgres")
        self.harness.set_leader(True)
        self.charm.on.start.emit()
        self.harness.update_config()

        mock_cores = 1
        self.charm._cores = mock_cores
        max_db_connections = 535

        # create default config object and modify it as we expect in the hook.
        test_config = PgbConfig(DEFAULT_CONFIG)
        test_config["pgbouncer"]["pool_mode"] = "transaction"
        test_config.set_max_db_connection_derivatives(
            max_db_connections=max_db_connections,
            pgb_instances=mock_cores,
        )
        test_config["pgbouncer"]["listen_port"] = 6464

        self.harness.update_config(
            {
                "pool_mode": "transaction",
                "max_db_connections": max_db_connections,
                "listen_port": 6464,
            }
        )
        _reload.assert_called()
        _update_connection_info.assert_called()
        _check_pgb_running.assert_called()

        # Test changing charm config propagates to container config file.
        pgb_container = self.harness.model.unit.get_container(PGB)
        container_config = pgb_container.pull(INI_PATH).read()
        self.assertEqual(container_config, test_config.render())

    @patch("ops.model.Container.can_connect", return_value=False)
    @patch("ops.charm.ConfigChangedEvent.defer")
    def test_on_config_changed_container_cant_connect(self, can_connect, defer):
        self.harness.add_relation(BACKEND_RELATION_NAME, "postgres")
        self.harness.set_leader(True)
        self.harness.update_config()
        self.assertIsInstance(
            self.harness.model.unit.status,
            WaitingStatus,
        )
        defer.assert_called()

    def test_pgbouncer_layer(self):
        layer = self.charm._pgbouncer_layer()
        assert len(layer["services"]) == self.charm._cores

    @patch("ops.model.Container.make_dir")
    def test_on_pgbouncer_pebble_ready(self, _mkdir):
        self.harness.add_relation(BACKEND_RELATION_NAME, "postgres")
        self.harness.set_leader(True)
        # emit on start to ensure config file render
        self.charm.on.start.emit()
        initial_plan = self.harness.get_container_pebble_plan(PGB)
        self.assertEqual(initial_plan.to_yaml(), "{}\n")

        container = self.harness.model.unit.get_container(PGB)
        self.charm.on.pgbouncer_pebble_ready.emit(container)
        for service in self.charm._services:
            container_service = self.harness.model.unit.get_container(PGB).get_service(
                service["name"]
            )
            self.assertTrue(container_service.is_running())
        self.assertIsInstance(self.harness.model.unit.status, ActiveStatus)

    @patch("ops.model.Container.can_connect", return_value=False)
    @patch("charm.PgBouncerK8sCharm.reload_pgbouncer")
    def test_render_pgb_config(self, reload_pgbouncer, _can_connect):
        cfg = PgbConfig(DEFAULT_CONFIG)

        # Assert we exit early if _can_connect returns false
        _can_connect.return_value = False
        self.charm.render_pgb_config(cfg, reload_pgbouncer=False)
        self.assertIsInstance(self.charm.unit.status, WaitingStatus)
        reload_pgbouncer.assert_not_called()

        _can_connect.return_value = True
        self.charm.render_pgb_config(cfg, reload_pgbouncer=True)
        reload_pgbouncer.assert_called()

        pgb_container = self.harness.model.unit.get_container(PGB)
        ini = pgb_container.pull(INI_PATH).read()
        self.assertEqual(cfg.render(), ini)

    def test_read_pgb_config(self):
        test_cfg = PgbConfig(DEFAULT_CONFIG)
        self.charm.render_pgb_config(test_cfg)
        read_cfg = self.charm.read_pgb_config()
        self.assertEqual(PgbConfig(read_cfg).render(), test_cfg.render())

    @patch("ops.model.Container.make_dir")
    @patch("ops.model.Container.restart")
    def test_reload_pgbouncer(self, _restart, _mkdir):
        self.harness.add_relation(BACKEND_RELATION_NAME, "postgres")
        self.harness.set_leader(True)
        # necessary hooks before we can check reloads
        self.charm.on.start.emit()
        container = self.harness.model.unit.get_container(PGB)
        self.charm.on.pgbouncer_pebble_ready.emit(container)

        self.charm.reload_pgbouncer()
        self.assertIsInstance(self.charm.unit.status, ActiveStatus)
        calls = [call(service["name"]) for service in self.charm._services]
        _restart.assert_has_calls(calls)
