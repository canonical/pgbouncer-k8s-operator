# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import PropertyMock, patch

from ops.testing import Harness

from charm import PgBouncerK8sCharm
from constants import BACKEND_RELATION_NAME, PEER_RELATION_NAME


class TestDb(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(PgBouncerK8sCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

        self.charm = self.harness.charm
        self.app = self.charm.app.name
        self.unit = self.charm.unit.name
        self.backend = self.charm.backend
        self.db_relation = self.charm.legacy_db_relation
        self.db_admin_relation = self.charm.legacy_db_admin_relation

        # Define a peer relation
        self.peers_rel_id = self.harness.add_relation(PEER_RELATION_NAME, "pgbouncer-k8s")
        self.harness.add_relation_unit(self.peers_rel_id, self.unit)

        # Define a backend relation
        self.backend_rel_id = self.harness.add_relation(BACKEND_RELATION_NAME, "postgres-k8s")
        self.harness.add_relation_unit(self.backend_rel_id, "postgres-k8s/0")

    @patch(
        "relations.backend_database.BackendDatabaseRequires.postgres", new_callable=PropertyMock
    )
    @patch("charms.data_platform_libs.v0.database_provides.DatabaseRequestedEvent.defer")
    def test_on_database_requested(self, _backend_postgres, _defer):
        _backend_postgres.return_value = False

        # _defer.assert_called()

        _backend_postgres.return_value = True

        # _defer.assert_not_called()

    # def test_on_relation_broken(self):
    #     assert False

    # def test_update_read_only_endpoint(self):
    #     assert False
