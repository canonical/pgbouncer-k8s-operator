# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest
from unittest.mock import patch

from charms.pgbouncer_k8s.v0.pgb import DEFAULT_CONFIG, PgbConfig
from ops.model import ActiveStatus, WaitingStatus
from ops.testing import Harness

from charm import INI_PATH, PGB, PgBouncerK8sCharm


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(PgBouncerK8sCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.charm = self.harness.charm

    def test_on_start(self):
        self.charm.on.start.emit()
        pgb_container = self.harness.model.unit.get_container(PGB)

        # assert config is set to default - it gets updated in the config-changed hook fired later
        ini = pgb_container.pull(INI_PATH).read()
        self.assertEqual(ini, PgbConfig(DEFAULT_CONFIG).render())

    @patch("charm.PgBouncerK8sCharm.read_pgb_config", return_value=PgbConfig(DEFAULT_CONFIG))
    @patch("charm.PgBouncerK8sCharm.update_backend_relation_port")
    @patch("ops.model.Container.restart")
    def test_on_config_changed(self, _restart, _update_port, _read):
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
        test_config["pgbouncer"]["listen_port"] = "6464"

        self.harness.update_config(
            {
                "pool_mode": "transaction",
                "max_db_connections": max_db_connections,
                "listen_port": "6464",
            }
        )
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())
        _restart.assert_called()
        _update_port.assert_called()

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
        # emit on install to ensure config file render
        self.harness.charm.on.start.emit()
        initial_plan = self.harness.get_container_pebble_plan(PGB)
        self.assertEqual(initial_plan.to_yaml(), "{}\n")

        expected_plan = {
            "services": {
                PGB: {
                    "summary": "pgbouncer service",
                    "user": "postgres",
                    "command": f"pgbouncer -R -v {INI_PATH}",
                    "startup": "enabled",
                    "override": "replace",
                }
            },
        }
        container = self.harness.model.unit.get_container(PGB)
        self.charm.on.pgbouncer_pebble_ready.emit(container)
        updated_plan = self.harness.get_container_pebble_plan(PGB).to_dict()
        self.assertEqual(expected_plan, updated_plan)

        service = self.harness.model.unit.get_container(PGB).get_service(PGB)
        self.assertTrue(service.is_running())
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    @patch("ops.model.Container.can_connect", return_value=False)
    @patch("charm.PgBouncerK8sCharm._reload_pgbouncer")
    def test_render_pgb_config(self, _reload_pgbouncer, _can_connect):
        cfg = PgbConfig(DEFAULT_CONFIG)

        # Assert we exit early if _can_connect returns false
        _can_connect.return_value = False
        self.charm.render_pgb_config(cfg, reload_pgbouncer=False)
        self.assertIsInstance(self.charm.unit.status, WaitingStatus)
        _reload_pgbouncer.assert_not_called()

        _can_connect.return_value = True
        self.charm.render_pgb_config(cfg, reload_pgbouncer=True)
        _reload_pgbouncer.assert_called()

        pgb_container = self.harness.model.unit.get_container(PGB)
        ini = pgb_container.pull(INI_PATH).read()
        self.assertEqual(cfg.render(), ini)

    def test_read_pgb_config(self):
        test_cfg = PgbConfig(DEFAULT_CONFIG)
        self.charm.render_pgb_config(test_cfg)
        read_cfg = self.charm.read_pgb_config()
        self.assertDictEqual(dict(read_cfg), dict(test_cfg))

    @patch("ops.model.Container.restart")
    def test_reload_pgbouncer(self, _restart):
        self.charm._reload_pgbouncer()
        self.assertIsInstance(self.charm.unit.status, ActiveStatus)
        _restart.assert_called_once()
