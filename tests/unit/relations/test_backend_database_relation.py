# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import MagicMock, patch

from ops.testing import Harness

from charm import PgBouncerK8sCharm

TEST_UNIT = {
    "master": "host=master port=1 dbname=testdatabase",
    "standbys": "host=standby1 port=1 dbname=testdatabase",
}


class TestBackendDatabaseRelation(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(PgBouncerK8sCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

        self.charm = self.harness.charm
        self.relation = self.charm.backend

    @patch("charm.PgBouncerK8sCharm.read_pgb_config")
    @patch("charm.PgBouncerK8sCharm.add_user")
    def test_on_database_created(self, _add_user, _cfg):
        mock_event = MagicMock()
        mock_event.username = "new-user"
        mock_event.password = "new-user-password"

        self.charm.backend._on_database_created(mock_event)

        _add_user.assert_called_with(
            user=mock_event.username,
            cfg=_cfg.return_value,
            password=mock_event.password,
            admin=True,
            reload_pgbouncer=True,
            render_cfg=True,
        )

    @patch("charm.PgBouncerK8sCharm.backend.postgres")
    @patch("charm.PgBouncerK8sCharm.read_pgb_config")
    @patch("charm.PgBouncerK8sCharm.remove_user")
    def test_relation_broken(self, _remove_user, _cfg, _backend):
        _backend.user = "broken-user"
        self.charm.backend._on_relation_broken(MagicMock())

        _remove_user.assert_called_with(
            _backend.user, cfg=_cfg.return_value, reload_pgbouncer=True, render_cfg=True
        )
