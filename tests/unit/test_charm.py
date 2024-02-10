# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import logging
import unittest
from unittest.mock import PropertyMock, patch

import pytest
from ops.model import RelationDataTypeError
from ops.testing import Harness
from parameterized import parameterized

from charm import PgBouncerK8sCharm
from constants import (
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
        self.harness.begin_with_initial_hooks()
        self.charm = self.harness.charm

        self.rel_id = self.harness.model.relations[PEER_RELATION_NAME][0].id

    @pytest.fixture
    def use_caplog(self, caplog):
        self._caplog = caplog

    def test_pgbouncer_layer(self):
        layer = self.charm._pgbouncer_layer()
        assert len(layer.services) == self.charm._cores + 2

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
