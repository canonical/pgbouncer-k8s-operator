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

BACKEND_RELATION_NAME = "backend-database"


class TestBackendDatabaseRelation(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(PgBouncerK8sCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

        self.charm = self.harness.charm
        self.app = self.charm.app.name
        self.unit = self.charm.unit.name
        self.relation = self.charm.backend

        # Define a backend relation
        self.rel_id = self.harness.add_relation(BACKEND_RELATION_NAME, "postgres")
        self.harness.add_relation_unit(self.rel_id, "postgres/0")
        self.harness.add_relation_unit(self.rel_id, self.unit)

    @patch("charm.PgBouncerK8sCharm.read_pgb_config")
    def test_on_database_created(self, _cfg):
        # TODO update to use relations the way Marcelo did
        mock_event = MagicMock()
        mock_event.username = "new-user"
        mock_event.password = "new-user-password"

        self.charm.backend._on_database_created(mock_event)

    def test_relation_departed(self):
        self.charm.backend._on_relation_departed(MagicMock())

    @patch("charm.PgBouncerK8sCharm.read_pgb_config")
    def test_relation_broken(self, _cfg):
        # TODO update to use relations the way Marcelo did
        self.charm.backend._on_relation_broken(MagicMock())

    def test_initialise_auth_function(self):
        install_script = open("src/relations/pgbouncer-install.sql", "r").read()
        postgres = MagicMock()
        dbname = "test-db"

        self.charm.backend.initialise_auth_function(postgres=postgres, dbname=dbname)

        postgres.connect_to_database.assert_called_with(dbname)
        conn = postgres.connect_to_database().__enter__()
        cursor = conn.cursor().__enter__()
        cursor.execute.assert_called_with(
            install_script.replace("auth_user", self.charm.backend.auth_user)
        )
        conn.close.assert_called()
