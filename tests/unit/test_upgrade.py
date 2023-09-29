# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
import unittest
from unittest.mock import Mock, PropertyMock, patch

import pytest
from charms.data_platform_libs.v0.upgrade import ClusterNotReadyError
from ops.testing import Harness

from charm import PgBouncerK8sCharm


class TestUpgrade(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(PgBouncerK8sCharm)
        self.addCleanup(self.harness.cleanup)
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
        self, _check_pgb_runnig, _set_partition, _app, _, __
    ):
        # PGB is not running
        with pytest.raises(ClusterNotReadyError):
            self.charm.upgrade.pre_upgrade_check()

        _check_pgb_runnig.return_value = True

        # Backend is related but not ready
        with pytest.raises(ClusterNotReadyError):
            self.charm.upgrade.pre_upgrade_check()

    @patch("charm.PgbouncerUpgrade.set_unit_completed")
    @patch("charm.PgbouncerUpgrade._cluster_checks")
    @patch("charm.PgbouncerUpgrade.peer_relation", new_callable=PropertyMock, return_value=None)
    def test_on_pgbouncer_pebble_ready(self, _peer_relation, _cluster_checks, _set_unit_completed):
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

    def test_on_upgrade_changed(self):
        pass

    def test_log_rollback_instructions(self):
        pass

    def test_set_rolling_update_partition(self):
        pass
