# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import logging
import unittest
from unittest.mock import PropertyMock, call, patch

import pytest
from charms.pgbouncer_k8s.v0.pgb import DEFAULT_CONFIG, PgbConfig
from ops.model import RelationDataTypeError, WaitingStatus
from ops.testing import Harness
from parameterized import parameterized

from charm import PgBouncerK8sCharm
from constants import (
    BACKEND_RELATION_NAME,
    INI_PATH,
    PEER_RELATION_NAME,
    PGB,
    SECRET_INTERNAL_LABEL,
)


class TestCharm(unittest.TestCase):
    def setUp(self):
        backend_ready_patch = patch(
            "relations.backend_database.BackendDatabaseRequires.ready",
            new_callable=PropertyMock,
            return_value=True,
        )
        backend_ready_patch.start()

        self.harness = Harness(PgBouncerK8sCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin_with_initial_hooks()
        self.charm = self.harness.charm
        self.harness.model.unit.get_container(PGB).make_dir("/etc/logrotate.d", make_parents=True)

        self.rel_id = self.harness.model.relations[PEER_RELATION_NAME][0].id

    @pytest.fixture
    def use_caplog(self, caplog):
        self._caplog = caplog

    @patch("charm.PgBouncerK8sCharm._patch_port")
    @patch("charm.PgBouncerK8sCharm.read_pgb_config")
    @patch("charm.PgBouncerK8sCharm.push_file")
    @patch("charm.PgBouncerK8sCharm.update_client_connection_info")
    @patch("charm.PgBouncerK8sCharm.reload_pgbouncer")
    @patch("ops.model.Container.make_dir")
    @patch("charm.PgBouncerK8sCharm.check_pgb_running")
    def test_on_config_changed(
        self,
        _check_pgb_running,
        _mkdir,
        _reload,
        _update_connection_info,
        _push_file,
        _read_pgb_config,
        _,
    ):
        self.harness.add_relation(BACKEND_RELATION_NAME, "postgres")
        _read_pgb_config.side_effect = lambda: PgbConfig(DEFAULT_CONFIG)
        self.harness.set_leader(True)
        container = self.harness.model.unit.get_container(PGB)
        self.charm.on.pgbouncer_pebble_ready.emit(container)

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
        _reload.assert_called_once_with()
        _update_connection_info.assert_called_with(6464)
        _check_pgb_running.assert_called_once_with()
        _push_file.assert_called_with(
            "/var/lib/pgbouncer/pgbouncer.ini", test_config.render(), 0o400
        )

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
        assert len(layer.services) == self.charm._cores + 2

    @patch("charm.PgBouncerK8sCharm._patch_port")
    @patch("charm.PgBouncerK8sCharm.update_status")
    @patch("ops.model.Container.exec")
    @patch("ops.model.Container.make_dir")
    def test_on_pgbouncer_pebble_ready(self, _mkdir, _exec, _update_status, _):
        _exec.return_value.wait_output.return_value = ("PGB 1.16.1\nOther things", "")
        self.harness.add_relation(BACKEND_RELATION_NAME, "postgres")
        self.harness.set_leader(True)
        initial_plan = self.harness.get_container_pebble_plan(PGB)
        self.assertEqual(initial_plan.to_yaml(), "{}\n")

        container = self.harness.model.unit.get_container(PGB)
        self.charm.on.pgbouncer_pebble_ready.emit(container)
        for service in self.charm._services:
            container_service = self.harness.model.unit.get_container(PGB).get_service(
                service["name"]
            )
            self.assertTrue(container_service.is_running())
        _update_status.assert_called_once_with()

    @patch("charm.PostgreSQLTLS.get_tls_files")
    @patch("ops.model.Container.make_dir")
    def test_on_pgbouncer_pebble_ready_defer_tls(self, _mkdir, get_tls_files):
        get_tls_files.return_value = (None, None, None)

        self.harness.add_relation(BACKEND_RELATION_NAME, "postgres")
        self.harness.add_relation("certificates", "tls_op")
        self.harness.set_leader(True)
        # emit on start to ensure config file render
        self.charm.on.start.emit()
        initial_plan = self.harness.get_container_pebble_plan(PGB)
        self.assertEqual(initial_plan.to_yaml(), "{}\n")

        container = self.harness.model.unit.get_container(PGB)
        self.charm.on.pgbouncer_pebble_ready.emit(container)

        assert not len(self.harness.model.unit.get_container(PGB).get_services())
        get_tls_files.assert_called_once_with()
        self.assertIsInstance(self.harness.model.unit.status, WaitingStatus)
        self.assertEqual(self.harness.model.unit.status.message, "Waiting for certificates")

    @patch("charm.PgBouncerK8sCharm._patch_port")
    @patch("charm.PgBouncerK8sCharm.update_status")
    @patch("ops.model.Container.exec")
    @patch("charm.PgBouncerK8sCharm.push_tls_files_to_workload")
    @patch("charm.PostgreSQLTLS.get_tls_files")
    @patch("ops.model.Container.make_dir")
    def test_on_pgbouncer_pebble_ready_ensure_tls_files(
        self, _mkdir, get_tls_files, push_tls_files_to_workload, _exec, _update_status, _
    ):
        _exec.return_value.wait_output.return_value = ("", "")
        get_tls_files.return_value = ("key", "ca", "cert")

        self.harness.add_relation(BACKEND_RELATION_NAME, "postgres")
        self.harness.add_relation("certificates", "tls_op")
        self.harness.set_leader(True)
        # emit on start to ensure config file render
        self.charm.on.start.emit()
        initial_plan = self.harness.get_container_pebble_plan(PGB)
        self.assertEqual(initial_plan.to_yaml(), "{}\n")

        container = self.harness.model.unit.get_container(PGB)
        self.charm.on.pgbouncer_pebble_ready.emit(container)

        get_tls_files.assert_called_once_with()
        push_tls_files_to_workload.assert_called_once_with(False)
        _update_status.assert_called_once_with()

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

    @patch("charm.PgBouncerK8sCharm._patch_port")
    @patch("charm.PgBouncerK8sCharm.check_pgb_running")
    @patch("ops.model.Container.exec")
    @patch("ops.model.Container.make_dir")
    @patch("ops.model.Container.restart")
    def test_reload_pgbouncer(self, _restart, _mkdir, _exec, _check_pgb_running, _):
        self.harness.add_relation(BACKEND_RELATION_NAME, "postgres")
        self.harness.set_leader(True)
        # necessary hooks before we can check reloads
        self.charm.on.start.emit()
        container = self.harness.model.unit.get_container(PGB)
        self.charm.on.pgbouncer_pebble_ready.emit(container)

        self.charm.reload_pgbouncer()
        _check_pgb_running.assert_called_once_with()
        calls = [call(service["name"]) for service in self.charm._services]
        _restart.assert_has_calls(calls)

    @patch("charm.PgBouncerK8sCharm.render_pgb_config")
    @patch("charm.PgBouncerK8sCharm.read_pgb_config")
    @patch("charm.PostgreSQLTLS.get_tls_files")
    def test_update_config_enable_tls(self, get_tls_files, read_pgb_config, render_pgb_config):
        get_tls_files.return_value = ("key", "ca", "cert")
        read_pgb_config.return_value = {"pgbouncer": {}}

        self.charm.update_config()

        get_tls_files.assert_called_once_with()
        read_pgb_config.assert_called_once_with()
        render_pgb_config.assert_called_once_with(read_pgb_config.return_value, True)
        self.assertEqual(
            read_pgb_config.return_value["pgbouncer"],
            {
                "client_tls_ca_file": "/var/lib/pgbouncer/ca.pem",
                "client_tls_cert_file": "/var/lib/pgbouncer/cert.pem",
                "client_tls_key_file": "/var/lib/pgbouncer/key.pem",
                "client_tls_sslmode": "prefer",
            },
        )

    @patch("charm.PgBouncerK8sCharm.render_pgb_config")
    @patch("charm.PgBouncerK8sCharm.read_pgb_config")
    @patch("charm.PostgreSQLTLS.get_tls_files")
    def test_update_config_disable_tls(self, get_tls_files, read_pgb_config, render_pgb_config):
        get_tls_files.return_value = (None, None, None)
        read_pgb_config.return_value = {
            "pgbouncer": {
                "client_tls_ca_file": "/var/lib/postgresql/pgbouncer/ca.pem",
                "client_tls_cert_file": "/var/lib/postgresql/pgbouncer/cert.pem",
                "client_tls_key_file": "/var/lib/postgresql/pgbouncer/key.pem",
                "client_tls_sslmode": "prefer",
            }
        }

        self.charm.update_config()

        get_tls_files.assert_called_once_with()
        read_pgb_config.assert_called_once_with()
        render_pgb_config.assert_called_once_with(read_pgb_config.return_value, True)
        self.assertEqual(read_pgb_config.return_value["pgbouncer"], {})

    @patch("charm.PgBouncerK8sCharm.render_pgb_config")
    @patch("charm.PgBouncerK8sCharm.read_pgb_config")
    @patch("charm.PostgreSQLTLS.get_tls_files")
    def test_update_config_no_config(self, get_tls_files, read_pgb_config, render_pgb_config):
        read_pgb_config.side_effect = FileNotFoundError

        self.charm.update_config()

        read_pgb_config.assert_called_once_with()
        get_tls_files.assert_not_called()
        render_pgb_config.assert_not_called()

    @patch("charm.PgBouncerK8sCharm.push_file")
    @patch("charm.PgBouncerK8sCharm.update_config")
    @patch("charm.PostgreSQLTLS.get_tls_files")
    def test_push_tls_files_to_workload_enabled_tls(self, get_tls_files, update_config, push_file):
        get_tls_files.return_value = ("key", "ca", "cert")

        self.charm.push_tls_files_to_workload()

        get_tls_files.assert_called_once_with()
        update_config.assert_called_once_with()
        assert push_file.call_count == 3
        push_file.assert_any_call("/var/lib/pgbouncer/key.pem", "key", 0o400)
        push_file.assert_any_call("/var/lib/pgbouncer/ca.pem", "ca", 0o400)
        push_file.assert_any_call("/var/lib/pgbouncer/cert.pem", "cert", 0o400)

    @patch("charm.PgBouncerK8sCharm.push_file")
    @patch("charm.PgBouncerK8sCharm.update_config")
    @patch("charm.PostgreSQLTLS.get_tls_files")
    def test_push_tls_files_to_workload_disabled_tls(
        self, get_tls_files, update_config, push_file
    ):
        get_tls_files.return_value = (None, None, None)

        self.charm.push_tls_files_to_workload(False)

        get_tls_files.assert_called_once_with()
        update_config.assert_not_called()
        push_file.assert_not_called()

    #
    # Secrets
    #

    def test_scope_obj(self):
        assert self.charm._scope_obj("app") == self.charm.framework.model.app
        assert self.charm._scope_obj("unit") == self.charm.framework.model.unit
        assert self.charm._scope_obj("test") is None

    def test_get_secret(self):
        # App level changes require leader privileges
        with self.harness.hooks_disabled():
            self.harness.set_leader()
        # Test application scope.
        assert self.charm.get_secret("app", "password") is None
        self.harness.update_relation_data(
            self.rel_id, self.charm.app.name, {"password": "test-password"}
        )
        assert self.charm.get_secret("app", "password") == "test-password"

        # Unit level changes don't require leader privileges
        with self.harness.hooks_disabled():
            self.harness.set_leader(False)
        # Test unit scope.
        assert self.charm.get_secret("unit", "password") is None
        self.harness.update_relation_data(
            self.rel_id, self.charm.unit.name, {"password": "test-password"}
        )
        assert self.charm.get_secret("unit", "password") == "test-password"

    @parameterized.expand([("app"), ("unit")])
    @patch("charm.JujuVersion.has_secrets", new_callable=PropertyMock, return_value=True)
    def test_get_secret_secrets(self, scope, _):
        with self.harness.hooks_disabled():
            self.harness.set_leader()

        assert self.charm.get_secret(scope, "operator-password") is None
        self.charm.set_secret(scope, "operator-password", "test-password")
        assert self.charm.get_secret(scope, "operator-password") == "test-password"

    def test_set_secret(self):
        with self.harness.hooks_disabled():
            self.harness.set_leader()

        # Test application scope.
        assert "password" not in self.harness.get_relation_data(self.rel_id, self.charm.app.name)
        self.charm.set_secret("app", "password", "test-password")
        assert (
            self.harness.get_relation_data(self.rel_id, self.charm.app.name)["password"]
            == "test-password"
        )
        self.charm.set_secret("app", "password", None)
        assert "password" not in self.harness.get_relation_data(self.rel_id, self.charm.app.name)

        # Test unit scope.
        assert "password" not in self.harness.get_relation_data(self.rel_id, self.charm.unit.name)
        self.charm.set_secret("unit", "password", "test-password")
        assert (
            self.harness.get_relation_data(self.rel_id, self.charm.unit.name)["password"]
            == "test-password"
        )
        self.charm.set_secret("unit", "password", None)
        assert "password" not in self.harness.get_relation_data(self.rel_id, self.charm.unit.name)

        with self.assertRaises(RuntimeError):
            self.charm.set_secret("test", "password", "test")

    @parameterized.expand([("app", True), ("unit", True), ("unit", False)])
    @patch("charm.JujuVersion.has_secrets", new_callable=PropertyMock, return_value=True)
    def test_set_reset_new_secret(self, scope, is_leader, _):
        """NOTE: currently ops.testing seems to allow for non-leader to set secrets too!"""
        # App has to be leader, unit can be either
        with self.harness.hooks_disabled():
            self.harness.set_leader(is_leader)
        # Getting current password
        self.harness.charm.set_secret(scope, "new-secret", "bla")
        assert self.harness.charm.get_secret(scope, "new-secret") == "bla"

        # Reset new secret
        self.harness.charm.set_secret(scope, "new-secret", "blablabla")
        assert self.harness.charm.get_secret(scope, "new-secret") == "blablabla"

        # Set another new secret
        self.harness.charm.set_secret(scope, "new-secret2", "blablabla")
        assert self.harness.charm.get_secret(scope, "new-secret2") == "blablabla"

    @parameterized.expand([("app", True), ("unit", True), ("unit", False)])
    @patch("charm.JujuVersion.has_secrets", new_callable=PropertyMock, return_value=True)
    def test_invalid_secret(self, scope, is_leader, _):
        # App has to be leader, unit can be either
        with self.harness.hooks_disabled():
            self.harness.set_leader(is_leader)

        with self.assertRaises(RelationDataTypeError):
            self.harness.charm.set_secret(scope, "somekey", 1)

        self.harness.charm.set_secret(scope, "somekey", "")
        assert self.harness.charm.get_secret(scope, "somekey") is None

    @pytest.mark.usefixtures("use_caplog")
    def test_delete_password(self):
        """NOTE: currently ops.testing seems to allow for non-leader to remove secrets too!"""
        with self.harness.hooks_disabled():
            self.harness.set_leader(True)
        self.harness.update_relation_data(
            self.rel_id, self.charm.app.name, {"replication": "somepw"}
        )
        self.harness.charm.remove_secret("app", "replication")
        assert self.harness.charm.get_secret("app", "replication") is None

        with self.harness.hooks_disabled():
            self.harness.set_leader(False)
        self.harness.update_relation_data(
            self.rel_id, self.charm.unit.name, {"somekey": "somevalue"}
        )
        self.harness.charm.remove_secret("unit", "somekey")
        assert self.harness.charm.get_secret("unit", "somekey") is None

        with self.harness.hooks_disabled():
            self.harness.set_leader(True)
        with self._caplog.at_level(logging.ERROR):
            self.harness.charm.remove_secret("app", "replication")
            assert (
                "Non-existing field 'replication' was attempted to be removed" in self._caplog.text
            )

            self.harness.charm.remove_secret("unit", "somekey")
            assert "Non-existing field 'somekey' was attempted to be removed" in self._caplog.text

            self.harness.charm.remove_secret("app", "non-existing-secret")
            assert (
                "Non-existing field 'non-existing-secret' was attempted to be removed"
                in self._caplog.text
            )

            self.harness.charm.remove_secret("unit", "non-existing-secret")
            assert (
                "Non-existing field 'non-existing-secret' was attempted to be removed"
                in self._caplog.text
            )

    @patch("charm.JujuVersion.has_secrets", new_callable=PropertyMock, return_value=True)
    @pytest.mark.usefixtures("use_caplog")
    def test_delete_existing_password_secrets(self, _):
        """NOTE: currently ops.testing seems to allow for non-leader to remove secrets too!"""
        with self.harness.hooks_disabled():
            self.harness.set_leader(True)
        self.harness.charm.set_secret("app", "operator-password", "somepw")
        self.harness.charm.remove_secret("app", "operator-password")
        assert self.harness.charm.get_secret("app", "operator-password") is None

        with self.harness.hooks_disabled():
            self.harness.set_leader(False)
        self.harness.charm.set_secret("unit", "operator-password", "somesecret")
        self.harness.charm.remove_secret("unit", "operator-password")
        assert self.harness.charm.get_secret("unit", "operator-password") is None

        with self.harness.hooks_disabled():
            self.harness.set_leader(True)
        with self._caplog.at_level(logging.ERROR):
            self.harness.charm.remove_secret("app", "operator-password")
            assert (
                "Non-existing secret operator-password was attempted to be removed."
                in self._caplog.text
            )

            self.harness.charm.remove_secret("unit", "operator-password")
            assert (
                "Non-existing secret operator-password was attempted to be removed."
                in self._caplog.text
            )

            self.harness.charm.remove_secret("app", "non-existing-secret")
            assert (
                "Non-existing field 'non-existing-secret' was attempted to be removed"
                in self._caplog.text
            )

            self.harness.charm.remove_secret("unit", "non-existing-secret")
            assert (
                "Non-existing field 'non-existing-secret' was attempted to be removed"
                in self._caplog.text
            )

    @parameterized.expand([("app", True), ("unit", True), ("unit", False)])
    @patch("charm.JujuVersion.has_secrets", new_callable=PropertyMock, return_value=True)
    def test_migration_from_databag(self, scope, is_leader, _):
        """Check if we're moving on to use secrets when live upgrade from databag to Secrets usage."""
        # App has to be leader, unit can be either
        with self.harness.hooks_disabled():
            self.harness.set_leader(is_leader)

        # Getting current password
        entity = getattr(self.charm, scope)
        self.harness.update_relation_data(self.rel_id, entity.name, {"operator-password": "bla"})
        assert self.harness.charm.get_secret(scope, "operator-password") == "bla"

        # Reset new secret
        self.harness.charm.set_secret(scope, "operator-password", "blablabla")
        assert self.harness.charm.model.get_secret(label=f"pgbouncer-k8s.{scope}")
        assert self.harness.charm.get_secret(scope, "operator-password") == "blablabla"
        assert "operator-password" not in self.harness.get_relation_data(
            self.rel_id, getattr(self.charm, scope).name
        )

    @parameterized.expand([("app", True), ("unit", True), ("unit", False)])
    @patch("charm.JujuVersion.has_secrets", new_callable=PropertyMock, return_value=True)
    def test_migration_from_single_secret(self, scope, is_leader, _):
        """Check if we're moving on to use secrets when live upgrade from databag to Secrets usage."""
        # App has to be leader, unit can be either
        with self.harness.hooks_disabled():
            self.harness.set_leader(is_leader)

        secret = self.harness.charm.app.add_secret({"operator-password": "bla"})

        # Getting current password
        entity = getattr(self.charm, scope)
        self.harness.update_relation_data(
            self.rel_id, entity.name, {SECRET_INTERNAL_LABEL: secret.id}
        )
        assert self.harness.charm.get_secret(scope, "operator-password") == "bla"

        # Reset new secret
        # Only the leader can set app secret content.

        with self.harness.hooks_disabled():
            self.harness.set_leader(True)
        self.harness.charm.set_secret(scope, "operator-password", "blablabla")
        with self.harness.hooks_disabled():
            self.harness.set_leader(is_leader)

        assert self.harness.charm.model.get_secret(label=f"pgbouncer-k8s.{scope}")
        assert self.harness.charm.get_secret(scope, "operator-password") == "blablabla"
        assert SECRET_INTERNAL_LABEL not in self.harness.get_relation_data(
            self.rel_id, getattr(self.charm, scope).name
        )
