# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest
from unittest.mock import patch

from charms.pgbouncer_k8s_operator.v0.pgb import DEFAULT_CONFIG, PgbConfig
from ops.model import ActiveStatus, WaitingStatus
from ops.testing import Harness

from charm import INI_PATH, PGB, USERLIST_PATH, PgBouncerK8sCharm


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(PgBouncerK8sCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.charm = self.harness.charm

    @patch("charms.pgbouncer_k8s_operator.v0.pgb.generate_password", return_value="pw")
    def test_on_install(self, _gen_pw):
        self.charm.on.install.emit()
        pgb_container = self.harness.model.unit.get_container(PGB)

        # assert config is set to default - it gets updated in the config-changed hook fired later
        ini = pgb_container.pull(INI_PATH).read()
        self.assertEqual(ini, PgbConfig(DEFAULT_CONFIG).render())

        # Assert userlist is created with the generated password
        userlist = pgb_container.pull(USERLIST_PATH).read()
        self.assertEqual('"juju_admin" "pw"', userlist)
        _gen_pw.assert_called_once()

    @patch("charm.PgBouncerK8sCharm.read_pgb_config", return_value=PgbConfig(DEFAULT_CONFIG))
    @patch("charm.PgBouncerK8sCharm.trigger_db_relations")
    @patch("ops.model.Container.restart")
    def test_on_config_changed(self, _restart, _trigger_db_relations, _read):
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
        _trigger_db_relations.assert_called()

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
        self.harness.charm.on.install.emit()
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
        self.charm._render_pgb_config(cfg, reload_pgbouncer=True)
        self.assertIsInstance(self.charm.unit.status, WaitingStatus)
        _reload_pgbouncer.assert_not_called()

        _can_connect.return_value = True
        self.charm._render_pgb_config(cfg, reload_pgbouncer=True)
        _reload_pgbouncer.assert_called()

        pgb_container = self.harness.model.unit.get_container(PGB)
        ini = pgb_container.pull(INI_PATH).read()
        self.assertEqual(cfg.render(), ini)

    def testread_pgb_config(self):
        test_cfg = PgbConfig(DEFAULT_CONFIG)
        self.charm._render_pgb_config(test_cfg)
        read_cfg = self.charm.read_pgb_config()
        self.assertDictEqual(dict(read_cfg), dict(test_cfg))

    @patch("ops.model.Container.can_connect")
    @patch("charm.PgBouncerK8sCharm._reload_pgbouncer")
    def test_render_userlist(self, _reload_pgbouncer, _can_connect):
        cfg = PgbConfig(DEFAULT_CONFIG)

        # Assert we exit early if _can_connect returns false
        _can_connect.return_value = False
        self.charm._render_userlist(cfg, reload_pgbouncer=True)
        self.assertIsInstance(self.charm.unit.status, WaitingStatus)
        _reload_pgbouncer.assert_not_called()

        _can_connect.return_value = True
        pgb_container = self.harness.model.unit.get_container(PGB)
        self.charm._render_userlist({"test-user": "pw"}, reload_pgbouncer=True)
        _reload_pgbouncer.assert_called()

        userlist = pgb_container.pull(USERLIST_PATH).read()
        self.assertEqual('"test-user" "pw"', userlist)

    @patch("ops.model.Container.restart")
    def test_reload_pgbouncer(self, _restart):
        self.charm._reload_pgbouncer()
        self.assertIsInstance(self.charm.unit.status, ActiveStatus)
        _restart.assert_called_once()

    @patch("charms.pgbouncer_k8s_operator.v0.pgb.generate_password", return_value="default-pass")
    @patch("charm.PgBouncerK8sCharm._read_userlist", return_value={})
    @patch("charm.PgBouncerK8sCharm.read_pgb_config", return_value=PgbConfig(DEFAULT_CONFIG))
    @patch("charm.PgBouncerK8sCharm._render_userlist")
    @patch("charm.PgBouncerK8sCharm._render_pgb_config")
    def test_add_user(self, _render_cfg, _render_userlist, _read_cfg, _read_userlist, _gen_pw):
        default_admins = DEFAULT_CONFIG[PGB]["admin_users"]
        default_stats = DEFAULT_CONFIG[PGB]["stats_users"]
        cfg = PgbConfig(DEFAULT_CONFIG)

        # If user already exists, assert we aren't recreating them.
        _read_userlist.return_value = {"test-user": "test-pass"}
        self.charm.add_user(user="test-user", cfg=cfg, password="test-pass")
        _render_userlist.assert_not_called()
        _read_userlist.reset_mock()

        # Test defaults
        self.charm.add_user(user="test-user", cfg=cfg)
        _render_userlist.assert_called_with({"test-user": "default-pass"})
        _render_cfg.assert_not_called()
        assert cfg[PGB].get("admin_users") == default_admins
        # No stats_users by default
        assert cfg[PGB].get("stats_users") == default_stats
        _read_userlist.reset_mock()
        _render_userlist.reset_mock()

        # Test everything else
        max_cfg = PgbConfig(DEFAULT_CONFIG)
        self.charm.add_user(
            user="max-test",
            password="max-pw",
            cfg=max_cfg,
            admin=True,
            stats=True,
            reload_pgbouncer=True,
            render_cfg=True,
        )
        _render_userlist.assert_called_with({"test-user": "default-pass", "max-test": "max-pw"})
        assert max_cfg[PGB].get("admin_users") == default_admins + ["max-test"]
        assert max_cfg[PGB].get("stats_users") == default_stats + ["max-test"]
        _render_cfg.assert_called_with(max_cfg, True)

        # Test we can't duplicate stats or admin users
        self.charm.add_user(
            user="max-test", password="max-pw", cfg=max_cfg, admin=True, stats=True
        )
        assert max_cfg[PGB].get("admin_users") == default_admins + ["max-test"]
        assert max_cfg[PGB].get("stats_users") == default_stats + ["max-test"]

    @patch("charm.PgBouncerK8sCharm._read_userlist", return_value={"test_user": ""})
    @patch("charm.PgBouncerK8sCharm.read_pgb_config", return_value=PgbConfig(DEFAULT_CONFIG))
    @patch("charm.PgBouncerK8sCharm._render_userlist")
    @patch("charm.PgBouncerK8sCharm._render_pgb_config")
    def test_remove_user(self, _render_cfg, _render_userlist, _read_cfg, _read_userlist):
        user = "test_user"
        cfg = PgbConfig(DEFAULT_CONFIG)
        cfg[PGB]["admin_users"].append(user)
        cfg[PGB]["stats_users"].append(user)
        admin_users = list(cfg[PGB]["admin_users"])
        stats_users = list(cfg[PGB]["stats_users"])

        # try to remove user that doesn't exist
        self.charm.remove_user("nonexistent-user", cfg=cfg)
        _render_userlist.assert_not_called()
        assert cfg[PGB]["admin_users"] == admin_users
        assert cfg[PGB]["stats_users"] == stats_users

        # remove user that does exist
        self.charm.remove_user(user, cfg=cfg, render_cfg=True, reload_pgbouncer=True)
        assert user not in cfg[PGB]["admin_users"]
        assert user not in cfg[PGB]["stats_users"]
        _render_userlist.assert_called_with({})
        _render_cfg.assert_called_with(cfg, True)
