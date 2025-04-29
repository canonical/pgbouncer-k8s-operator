# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, PropertyMock, patch

from ops.testing import Harness

from charm import PgBouncerK8sCharm
from constants import BACKEND_RELATION_NAME, PEER_RELATION_NAME


class TestPeers(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(PgBouncerK8sCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

        self.togggle_monitoring_patch = patch("charm.PgBouncerK8sCharm.toggle_monitoring_layer")
        self.toggle_monitoring_layer = self.togggle_monitoring_patch.start()

        self.charm = self.harness.charm
        self.app = self.charm.app.name
        self.unit = self.charm.unit.name

        self.rel_id = self.harness.add_relation(PEER_RELATION_NAME, self.charm.app.name)

    def tearDown(self):
        self.togggle_monitoring_patch.stop()

    @patch(
        "charm.PgBouncerK8sCharm.is_container_ready", new_callable=PropertyMock, return_value=True
    )
    @patch("charm.PgBouncerK8sCharm.render_pgb_config")
    @patch("charm.PgBouncerK8sCharm.toggle_monitoring_layer")
    def test_on_peers_changed(
        self, toggle_monitoring_layer, render_pgb_config, is_container_ready
    ):
        self.harness.add_relation(BACKEND_RELATION_NAME, "postgres")
        self.charm.peers._on_changed(Mock())
        render_pgb_config.assert_called_once_with()
        toggle_monitoring_layer.assert_called_once_with(False)
        render_pgb_config.reset_mock()
        toggle_monitoring_layer.reset_mock()

        # Event will be deferred if the container is not ready
        is_container_ready.return_value = False
        event = Mock()
        self.charm.peers._on_changed(event)
        event.defer.assert_called_once_with()
        assert not render_pgb_config.called
        assert not toggle_monitoring_layer.called
