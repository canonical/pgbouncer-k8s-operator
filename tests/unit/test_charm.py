# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import logging
import math
import unittest
from unittest.mock import Mock, PropertyMock, call, patch

import pytest
from jinja2 import Template
from ops.model import RelationDataTypeError
from ops.testing import Harness
from parameterized import parameterized

from charm import PgBouncerK8sCharm
from constants import (
    AUTH_FILE_PATH,
    BACKEND_RELATION_NAME,
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
        root = self.harness.get_filesystem_root(PGB)
        (root / "etc" / "logrotate.d").mkdir(parents=True, exist_ok=True)
        (root / "var" / "lib" / "pgbouncer").mkdir(parents=True, exist_ok=True)
        (root / "var" / "log" / "pgbouncer").mkdir(parents=True, exist_ok=True)
        self.harness.handle_exec(
            PGB, ["pgbouncer", "--version"], result="PGB 1.16.1\nOther things"
        )
        self.harness.begin_with_initial_hooks()
        self.charm = self.harness.charm

        self.rel_id = self.harness.model.relations[PEER_RELATION_NAME][0].id

    @pytest.fixture
    def use_caplog(self, caplog):
        self._caplog = caplog

    @patch("charm.PgBouncerK8sCharm.patch_port")
    @patch("charm.PgBouncerK8sCharm.update_client_connection_info")
    @patch("charm.PgBouncerK8sCharm.render_pgb_config")
    @patch("charm.PgBouncerK8sCharm.reload_pgbouncer")
    @patch("charm.PgBouncerK8sCharm.check_pgb_running")
    def test_on_config_changed(
        self,
        _check_pgb_running,
        _reload,
        _render,
        _update_connection_info,
        _,
    ):
        self.harness.add_relation(BACKEND_RELATION_NAME, "postgres")
        self.harness.set_leader(True)
        container = self.harness.model.unit.get_container(PGB)
        self.charm.on.pgbouncer_pebble_ready.emit(container)
        _reload.reset_mock()

        mock_cores = 1
        self.charm._cores = mock_cores
        max_db_connections = 535

        self.harness.update_config({
            "pool_mode": "transaction",
            "max_db_connections": max_db_connections,
            "listen_port": 6464,
        })
        _reload.assert_called_once_with()
        _reload.assert_called_once_with()
        _update_connection_info.assert_called_with(6464)
        _check_pgb_running.assert_called_once_with()

    @patch(
        "charm.PgBouncerK8sCharm.is_container_ready", new_callable=PropertyMock, return_value=False
    )
    @patch("ops.charm.ConfigChangedEvent.defer")
    def test_on_config_changed_container_cant_connect(self, can_connect, defer):
        self.harness.add_relation(BACKEND_RELATION_NAME, "postgres")
        self.harness.set_leader(True)
        self.harness.update_config()
        defer.assert_called()

    def test_pgbouncer_layer(self):
        layer = self.charm._pgbouncer_layer()
        assert len(layer.services) == self.charm._cores + 2

    @patch("charm.PgBouncerK8sCharm.patch_port")
    @patch("charm.PgBouncerK8sCharm.update_status")
    @patch("charm.PgBouncerK8sCharm.render_pgb_config")
    def test_on_pgbouncer_pebble_ready(self, _render, _update_status, _):
        self.harness.add_relation(BACKEND_RELATION_NAME, "postgres")
        self.harness.set_leader(True)

        container = self.harness.model.unit.get_container(PGB)
        self.charm.on.pgbouncer_pebble_ready.emit(container)
        for service in self.charm._services:
            container_service = self.harness.model.unit.get_container(PGB).get_service(
                service["name"]
            )
            self.assertTrue(container_service.is_running())
        _update_status.assert_called_once_with()
        _render.assert_called_once_with()

    @patch("charm.PgBouncerK8sCharm.patch_port")
    @patch("charm.PgBouncerK8sCharm.update_status")
    @patch("charm.PgBouncerK8sCharm.push_tls_files_to_workload")
    @patch("charm.PgBouncerK8sCharm.render_pgb_config")
    @patch("charm.PostgreSQLTLS.get_tls_files")
    def test_on_pgbouncer_pebble_ready_ensure_tls_files(
        self, get_tls_files, _render, push_tls_files_to_workload, _update_status, _
    ):
        get_tls_files.return_value = ("key", "ca", "cert")

        self.harness.add_relation(BACKEND_RELATION_NAME, "postgres")
        self.harness.add_relation("certificates", "tls_op")
        self.harness.set_leader(True)
        # emit on start to ensure config file render
        self.charm.on.start.emit()

        container = self.harness.model.unit.get_container(PGB)
        self.charm.on.pgbouncer_pebble_ready.emit(container)

        get_tls_files.assert_called_once_with()
        push_tls_files_to_workload.assert_called_once_with(False)
        _update_status.assert_called_once_with()
        _render.assert_called_once_with()

    @patch("ops.model.Container.can_connect", return_value=False)
    @patch(
        "relations.backend_database.DatabaseRequires.fetch_relation_field",
        return_value="BACKNEND_USER",
    )
    @patch(
        "charm.BackendDatabaseRequires.relation", new_callable=PropertyMock, return_value=Mock()
    )
    @patch(
        "charm.BackendDatabaseRequires.postgres_databag",
        new_callable=PropertyMock,
        return_value={"endpoints": "HOST:PORT", "read-only-endpoints": "HOST2:PORT"},
    )
    @patch("charm.PgBouncerK8sCharm.get_relation_databases")
    @patch("charm.PgBouncerK8sCharm.push_file")
    @patch("charm.PgBouncerK8sCharm.reload_pgbouncer")
    def test_render_pgb_config(
        self,
        _reload_pgbouncer,
        _push_file,
        _get_dbs,
        _postgres_databag,
        _backend_rel,
        _,
        _can_connect,
    ):
        _get_dbs.return_value = {
            "1": {"name": "first_test", "legacy": True},
            "2": {"name": "second_test", "legacy": False},
        }

        # Assert we exit early if _can_connect returns false
        _can_connect.return_value = False
        self.charm.render_pgb_config(reload_pgbouncer=False)
        _reload_pgbouncer.assert_not_called()

        with open("templates/pgb_config.j2") as file:
            template = Template(file.read())
        _can_connect.return_value = True
        self.charm.render_pgb_config(reload_pgbouncer=True)
        _reload_pgbouncer.assert_called()
        effective_db_connections = 100 / self.charm._cores
        default_pool_size = math.ceil(effective_db_connections / 2)
        min_pool_size = math.ceil(effective_db_connections / 4)
        reserve_pool_size = math.ceil(effective_db_connections / 4)
        expected_databases = {
            "first_test": {
                "host": "HOST",
                "dbname": "first_test",
                "port": "PORT",
                "auth_user": "pgbouncer_auth_BACKNEND_USER",
            },
            "first_test_readonly": {
                "host": "HOST2",
                "dbname": "first_test",
                "port": "PORT",
                "auth_user": "pgbouncer_auth_BACKNEND_USER",
            },
            "first_test_standby": {
                "host": "HOST2",
                "dbname": "first_test",
                "port": "PORT",
                "auth_user": "pgbouncer_auth_BACKNEND_USER",
            },
            "second_test": {
                "host": "HOST",
                "dbname": "second_test",
                "port": "PORT",
                "auth_user": "pgbouncer_auth_BACKNEND_USER",
            },
            "second_test_readonly": {
                "host": "HOST2",
                "dbname": "second_test",
                "port": "PORT",
                "auth_user": "pgbouncer_auth_BACKNEND_USER",
            },
        }
        for i in range(self.charm._cores):
            expected_content = template.render(
                databases=expected_databases,
                socket_dir=f"/var/lib/pgbouncer/instance_{i}",
                log_file=f"/var/log/pgbouncer/instance_{i}/pgbouncer.log",
                pid_file=f"/var/lib/pgbouncer/instance_{i}/pgbouncer.pid",
                listen_port=6432,
                pool_mode="session",
                max_db_connections=100,
                default_pool_size=default_pool_size,
                min_pool_size=min_pool_size,
                reserve_pool_size=reserve_pool_size,
                stats_user="pgbouncer_stats_pgbouncer_k8s",
                auth_query="SELECT username, password FROM pgbouncer_auth_BACKNEND_USER.get_auth($1)",
                auth_file=AUTH_FILE_PATH,
                enable_tls=False,
            )
            _push_file.assert_any_call(
                f"/var/lib/pgbouncer/instance_{i}/pgbouncer.ini", expected_content, 0o400
            )
        _push_file.reset_mock()
        _reload_pgbouncer.reset_mock()

        # test constant pool sizes with unlimited connections and no ro endpoints
        with self.harness.hooks_disabled():
            self.harness.update_config({
                "max_db_connections": 0,
            })
        del expected_databases["first_test_readonly"]
        del expected_databases["first_test_standby"]
        del expected_databases["second_test_readonly"]

        del _postgres_databag.return_value["read-only-endpoints"]

        self.charm.render_pgb_config()

        assert not _reload_pgbouncer.called
        for i in range(self.charm._cores):
            expected_content = template.render(
                databases=expected_databases,
                socket_dir=f"/var/lib/pgbouncer/instance_{i}",
                log_file=f"/var/log/pgbouncer/instance_{i}/pgbouncer.log",
                pid_file=f"/var/lib/pgbouncer/instance_{i}/pgbouncer.pid",
                listen_port=6432,
                pool_mode="session",
                max_db_connections=0,
                default_pool_size=20,
                min_pool_size=10,
                reserve_pool_size=10,
                stats_user="pgbouncer_stats_pgbouncer_k8s",
                auth_query="SELECT username, password FROM pgbouncer_auth_BACKNEND_USER.get_auth($1)",
                auth_file=AUTH_FILE_PATH,
                enable_tls=False,
            )
            _push_file.assert_any_call(
                f"/var/lib/pgbouncer/instance_{i}/pgbouncer.ini", expected_content, 0o400
            )

    @patch("charm.PgBouncerK8sCharm.push_file")
    @patch("charm.PgBouncerK8sCharm.reload_pgbouncer")
    def test_render_auth_file(self, _reload_pgbouncer, _push_file):
        self.charm.render_auth_file("test", reload_pgbouncer=False)

        _reload_pgbouncer.assert_not_called()
        _push_file.assert_called_once_with(AUTH_FILE_PATH, "test", 0o400)
        _reload_pgbouncer.reset_mock()

        # Test reload
        self.charm.render_auth_file("test", reload_pgbouncer=True)
        _reload_pgbouncer.assert_called_once_with()

    @patch("charm.Peers.app_databag", new_callable=PropertyMock, return_value={})
    @patch("charm.PgBouncerK8sCharm.get_secret")
    def test_get_relation_databases_legacy_data(self, _get_secret, _):
        """Test that legacy data will be parsed if new one is not set."""
        self.harness.set_leader(False)
        _get_secret.return_value = """
        [databases]
        test_db = host_cfg
        test_db_standby = host_cfg
        other_db = other_cfg
        """
        result = self.charm.get_relation_databases()
        assert result == {
            "1": {"legacy": False, "name": "test_db"},
            "2": {"legacy": False, "name": "other_db"},
        }
        _get_secret.assert_called_once_with("app", "cfg_file")

        # Get empty dict if no config is set
        _get_secret.return_value = None
        assert self.charm.get_relation_databases() == {}

        # Get empty dict if exception
        _get_secret.return_value = 1
        assert self.charm.get_relation_databases() == {}

        # Get empty dict if no databases
        _get_secret.return_value = """
        [other]
        test_db = host_cfg
        test_db_standby = host_cfg
        other_db = other_cfg
        """
        assert self.charm.get_relation_databases() == {}

    @patch("charm.PgBouncerK8sCharm.get_relation_databases", return_value={"some": "values"})
    def test_generate_relation_databases_not_leader(self, _):
        self.harness.set_leader(False)

        assert self.charm.generate_relation_databases() == {}

    @patch("charm.PgBouncerK8sCharm.patch_port")
    @patch("charm.PgBouncerK8sCharm.check_pgb_running")
    @patch("charm.PgBouncerK8sCharm.render_pgb_config")
    @patch("ops.model.Container.restart")
    def test_reload_pgbouncer(self, _restart, _check_pgb_running, _, __):
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

    @parameterized.expand([("app", "monitoring-password"), ("unit", "csr")])
    @patch("charm.JujuVersion.has_secrets", new_callable=PropertyMock, return_value=True)
    def test_get_secret_secrets(self, scope, field, _):
        with self.harness.hooks_disabled():
            self.harness.set_leader()

        assert self.charm.get_secret(scope, field) is None
        self.charm.set_secret(scope, field, "test")
        assert self.charm.get_secret(scope, field) == "test"

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
        # App has to be leader, unit can be eithe
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

        with self.assertRaises((RelationDataTypeError, TypeError)):
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
        with self._caplog.at_level(logging.DEBUG):
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

    @pytest.mark.usefixtures("use_caplog")
    @patch("charm.JujuVersion.has_secrets", new_callable=PropertyMock, return_value=True)
    def test_delete_existing_password_secrets(self, _):
        """NOTE: currently ops.testing seems to allow for non-leader to remove secrets too!"""
        with self.harness.hooks_disabled():
            self.harness.set_leader(True)
        self.harness.charm.set_secret("app", "monitoring-password", "somepw")
        self.harness.charm.remove_secret("app", "monitoring-password")
        assert self.harness.charm.get_secret("app", "monitoring-password") is None

        with self.harness.hooks_disabled():
            self.harness.set_leader(False)
        self.harness.charm.set_secret("unit", "csr", "somesecret")
        self.harness.charm.remove_secret("unit", "csr")
        assert self.harness.charm.get_secret("unit", "csr") is None

        with self.harness.hooks_disabled():
            self.harness.set_leader(True)
        with self._caplog.at_level(logging.DEBUG):
            self.harness.charm.remove_secret("app", "monitoring-password")
            assert (
                "Non-existing secret monitoring-password was attempted to be removed."
                in self._caplog.text
            )

            self.harness.charm.remove_secret("unit", "csr")
            assert "Non-existing secret csr was attempted to be removed." in self._caplog.text

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
        self.harness.update_relation_data(self.rel_id, entity.name, {"monitoring_password": "bla"})
        assert self.harness.charm.get_secret(scope, "monitoring_password") == "bla"

        # Reset new secret
        self.harness.charm.set_secret(scope, "monitoring-password", "blablabla")
        assert self.harness.charm.model.get_secret(
            label=f"{PEER_RELATION_NAME}.pgbouncer-k8s.{scope}"
        )
        assert self.harness.charm.get_secret(scope, "monitoring-password") == "blablabla"
        assert "monitoring-password" not in self.harness.get_relation_data(
            self.rel_id, getattr(self.charm, scope).name
        )

    @parameterized.expand([("app", True), ("unit", True), ("unit", False)])
    @patch("charm.JujuVersion.has_secrets", new_callable=PropertyMock, return_value=True)
    def test_migration_from_single_secret(self, scope, is_leader, _):
        """Check if we're moving on to use secrets when live upgrade from databag to Secrets usage."""
        # App has to be leader, unit can be either
        with self.harness.hooks_disabled():
            self.harness.set_leader(is_leader)

        secret = self.harness.charm.app.add_secret({"monitoring-password": "bla"})

        # Getting current password
        entity = getattr(self.charm, scope)
        self.harness.update_relation_data(
            self.rel_id, entity.name, {SECRET_INTERNAL_LABEL: secret.id}
        )
        assert self.harness.charm.get_secret(scope, "monitoring-password") == "bla"

        # Reset new secret
        # Only the leader can set app secret content.
        with self.harness.hooks_disabled():
            self.harness.set_leader(True)
        self.harness.charm.set_secret(scope, "monitoring-password", "blablabla")
        with self.harness.hooks_disabled():
            self.harness.set_leader(is_leader)
        assert self.harness.charm.model.get_secret(
            label=f"{PEER_RELATION_NAME}.pgbouncer-k8s.{scope}"
        )
        assert self.harness.charm.get_secret(scope, "monitoring-password") == "blablabla"
        assert SECRET_INTERNAL_LABEL not in self.harness.get_relation_data(
            self.rel_id, getattr(self.charm, scope).name
        )
