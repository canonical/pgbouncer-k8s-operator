# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import MagicMock, PropertyMock, patch

from ops.testing import Harness

from charm import PgBouncerK8sCharm
from lib.charms.pgbouncer_k8s.v0.pgb import DEFAULT_CONFIG, PgbConfig
from relations.peers import AUTH_FILE_DATABAG_KEY, CFG_FILE_DATABAG_KEY


class TestPeers(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(PgBouncerK8sCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

        self.charm = self.harness.charm
        self.app = self.charm.app.name
        self.unit = self.charm.unit.name

    @patch("relations.peers.Peers.app_databag", new_callable=PropertyMock)
    @patch("charm.PgBouncerK8sCharm.render_pgb_config")
    @patch("charm.PgBouncerK8sCharm.render_auth_file")
    @patch("charm.PgBouncerK8sCharm.reload_pgbouncer")
    def test_on_peers_changed(
        self, reload_pgbouncer, render_auth_file, render_pgb_config, app_databag
    ):
        databag = {}
        app_databag.return_value = databag

        # We don't want to write anything if we're the leader
        self.harness.set_leader(True)
        self.charm.peers._on_changed(MagicMock())
        render_auth_file.assert_not_called()
        render_pgb_config.assert_not_called()
        reload_pgbouncer.assert_not_called()

        # Don't write anything if nothing is available to write
        self.harness.set_leader(False)
        self.charm.peers._on_changed(MagicMock())
        render_pgb_config.assert_not_called()
        render_auth_file.assert_not_called()
        reload_pgbouncer.assert_not_called()

        # Assert that we're reloading pgb even if we're only changing one thing
        databag[CFG_FILE_DATABAG_KEY] = PgbConfig(DEFAULT_CONFIG).render()
        self.charm.peers._on_changed(MagicMock())
        render_pgb_config.assert_called_once()
        render_auth_file.assert_not_called()
        reload_pgbouncer.assert_called_once()
        render_pgb_config.reset_mock()
        reload_pgbouncer.reset_mock()

        databag[AUTH_FILE_DATABAG_KEY] = '"user" "pass"'
        self.charm.peers._on_changed(MagicMock())
        render_pgb_config.assert_called_once()
        render_auth_file.assert_called_once()
        reload_pgbouncer.assert_called_once()
