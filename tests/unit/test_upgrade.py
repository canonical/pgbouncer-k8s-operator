# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
import unittest
from unittest.mock import Mock, PropertyMock, patch

import pytest
from charms.data_platform_libs.v0.upgrade import ClusterNotReadyError, KubernetesClientError
from lightkube.resources.apps_v1 import StatefulSet
from ops.testing import Harness

from charm import PgBouncerK8sCharm
from constants import PGB
from tests.unit.helpers import _FakeApiError


class TestUpgrade(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(PgBouncerK8sCharm)
        self.addCleanup(self.harness.cleanup)
        root = self.harness.get_filesystem_root(PGB)
        (root / "etc" / "logrotate.d").mkdir(parents=True, exist_ok=True)
        (root / "var" / "lib" / "pgbouncer").mkdir(parents=True, exist_ok=True)
        (root / "var" / "log" / "pgbouncer").mkdir(parents=True, exist_ok=True)
        self.harness.begin_with_initial_hooks()
        self.charm = self.harness.charm

    @patch("charm.PgBouncerK8sCharm.app", new_callable=PropertyMock)
    @patch("charm.PgbouncerUpgrade._set_rolling_update_partition")
    @patch("charm.PgBouncerK8sCharm.check_pgb_running")
    def test_pre_upgrade_check(self, _check_pgb_runnig, _set_partition, _app):
        _app.return_value.planned_units.return_value = 3

        self.charm.upgrade.pre_upgrade_check()

        _check_pgb_runnig.assert_called_once_with()
        _set_partition.assert_called_once_with(2)

    @patch("charm.BackendDatabaseRequires.ready", new_callable=PropertyMock, return_value=False)
    @patch("charm.BackendDatabaseRequires.postgres", new_callable=PropertyMock, return_value=True)
    @patch("charm.PgBouncerK8sCharm.app", new_callable=PropertyMock)
    @patch("charm.PgbouncerUpgrade._set_rolling_update_partition")
    @patch("charm.PgBouncerK8sCharm.check_pgb_running", return_value=False)
    def test_pre_upgrade_check_cluster_not_ready(
        self, _check_pgb_runnig: Mock, _set_partition: Mock, _app: Mock, _, _backend_ready: Mock
    ):
        _app.return_value.planned_units.return_value = 3

        # PGB is not running
        with pytest.raises(ClusterNotReadyError):
            self.charm.upgrade.pre_upgrade_check()

        _check_pgb_runnig.return_value = True

        # Backend is related but not ready
        with pytest.raises(ClusterNotReadyError):
            self.charm.upgrade.pre_upgrade_check()

        # Failed patching
        _backend_ready.return_value = True
        _set_partition.side_effect = KubernetesClientError("test", "test")

        with pytest.raises(ClusterNotReadyError):
            self.charm.upgrade.pre_upgrade_check()

        _set_partition.assert_called_once_with(2)

    @patch("charm.PgBouncerK8sCharm.reconcile_k8s_service")
    @patch("charm.PgbouncerUpgrade.set_unit_completed")
    @patch("charm.PgbouncerUpgrade._cluster_checks")
    @patch("charm.PgbouncerUpgrade.peer_relation", new_callable=PropertyMock, return_value=None)
    def test_on_pgbouncer_pebble_ready(
        self,
        _peer_relation: Mock,
        _cluster_checks: Mock,
        _set_unit_completed: Mock,
        _reconcile_k8s_service: Mock,
    ):
        event = Mock()

        # Defer if no peers
        self.charm.upgrade._on_pgbouncer_pebble_ready(event)

        event.defer.assert_called_once_with()
        event.defer.reset_mock()

        # Early exit if status is not updating
        _peer_relation.return_value = Mock()
        _peer_relation.return_value.data = {self.charm.unit: {"state": "testing"}}

        self.charm.upgrade._on_pgbouncer_pebble_ready(event)

        assert event.defer.called is False

        # Run checks if unit is upgrading
        _peer_relation.return_value.data = {self.charm.unit: {"state": "upgrading"}}

        self.charm.upgrade._on_pgbouncer_pebble_ready(event)

        _cluster_checks.assert_called_once_with()
        _set_unit_completed.assert_called_once_with()
        assert event.defer.called is False

        # Defer if checks fail
        _cluster_checks.side_effect = ClusterNotReadyError("test", "test")

        self.charm.upgrade._on_pgbouncer_pebble_ready(event)

        event.defer.assert_called_once_with()

        # Will try to repatch the nodeport service
        self.harness.set_leader(True)
        _cluster_checks.side_effect = None

        self.charm.upgrade._on_pgbouncer_pebble_ready(event)

        _reconcile_k8s_service.assert_called_once_with()

    @patch("charm.PgBouncerK8sCharm.check_pgb_running", return_value=True)
    @patch("charm.PgBouncerK8sCharm.update_config")
    @patch("charm.PgbouncerUpgrade.peer_relation", new_callable=PropertyMock, return_value=None)
    def test_on_upgrade_changed(self, _peer_relation: Mock, _update_config: Mock, _):
        # Early exit when no peer
        self.charm.upgrade._on_upgrade_changed(None)

        assert _update_config.called is False

        # update_config called
        _peer_relation.return_value = Mock()
        _peer_relation.return_value.data = {self.charm.unit: {"state": "testing"}}

        self.charm.upgrade._on_upgrade_changed(None)

        _update_config.assert_called_once_with()

    @patch("upgrade.logger.info")
    def test_log_rollback_instructions(self, _logger: Mock):
        self.charm.upgrade.log_rollback_instructions()

        assert _logger.call_count == 2
        _logger.assert_any_call(
            "Run `juju refresh --revision <previous-revision> pgbouncer-k8s` to initiate the rollback"
        )
        _logger.assert_any_call(
            "and `juju run-action pgbouncerl-k8s/leader resume-upgrade` to resume the rollback"
        )

    @patch("upgrade.Client")
    def test_set_rolling_update_partition(self, _k8s_client: Mock):
        self.charm.upgrade._set_rolling_update_partition(1)

        _k8s_client.return_value.patch.assert_called_once_with(
            StatefulSet,
            name="pgbouncer-k8s",
            namespace=None,
            obj={"spec": {"updateStrategy": {"rollingUpdate": {"partition": 1}}}},
        )

    @patch("upgrade.Client")
    def test_set_rolling_update_partition_api_error(self, _k8s_client: Mock):
        _k8s_client.return_value.patch.side_effect = _FakeApiError

        with pytest.raises(KubernetesClientError):
            self.charm.upgrade._set_rolling_update_partition(1)

    @patch(
        "relations.backend_database.BackendDatabaseRequires.stats_user",
        new_callable=PropertyMock,
        return_value="stats_user",
    )
    @patch("charm.PgBouncerK8sCharm.set_secret")
    @patch("charm.PgBouncerK8sCharm.get_secret", return_value=None)
    def test_handle_md5_monitoring_auth(self, _get_secret, _set_secret, _):
        self.harness.set_leader(True)

        # Early exit if no secret
        self.charm.upgrade._handle_md5_monitoring_auth()
        _set_secret.assert_not_called()

        # Up to date
        _get_secret.return_value = '"auth_user" "cred"\n"stats_user" "other cred"'
        self.charm.upgrade._handle_md5_monitoring_auth()
        _set_secret.assert_not_called()

        # Remove md5 hash
        _get_secret.side_effect = ['"auth_user" "cred"\n"stats_user" "md5aabb"', "other cred"]
        self.charm.upgrade._handle_md5_monitoring_auth()
        _set_secret.assert_called_once_with(
            "app", "auth_file", '"auth_user" "cred"\n"stats_user" "other cred"'
        )
