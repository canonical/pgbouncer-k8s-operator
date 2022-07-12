# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from copy import deepcopy
from unittest.mock import MagicMock, patch

from ops.testing import Harness

from charm import PgBouncerK8sCharm
from lib.charms.pgbouncer_operator.v0.pgb import DEFAULT_CONFIG, PgbConfig

TEST_UNIT = {
    "master": "host=master port=1 dbname=testdatabase",
    "standbys": "host=standby1 port=1 dbname=testdatabase",
}


class TestBackendDbAdmin(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(PgBouncerK8sCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

        self.charm = self.harness.charm
        self.relation = self.charm.backend_relation

    @patch("charm.PgBouncerK8sCharm.add_user")
    def test_on_database_created(self, _add_user):
        mock_event = MagicMock()
        user = "new-user"
        password = "new-user-password"
        mock_event.relation.data = {self.charm.app: {"username": user, "password": password}}
        self.charm.backend._on_database_created(mock_event)
        _add_user.assert_called_with(user, password=password, admin=True, reload_pgbouncer=True, render_cfg = True)


    @patch("charm.PgBouncerK8sCharm.remove_user")
    def test_relation_broken(self, _remove_user):
        mock_event = MagicMock()
        user = "broken-user"
        password = "broken-user-password"
        mock_event.relation.data = {self.charm.app: {"username": user, "password": password}}
        self.charm.backend._on_relation_broken(mock_event)
        _remove_user.assert_called_with(user, reload_pgbouncer=True, render_cfg = True)
