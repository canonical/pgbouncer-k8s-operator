# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import MagicMock, patch

from ops.testing import Harness

from charm import PgBouncerK8sCharm
from constants import BACKEND_RELATION_NAME, CLIENT_RELATION_NAME, PEER_RELATION_NAME


class TestPgbouncerProvider(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(PgBouncerK8sCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

        self.charm = self.harness.charm
        self.app = self.charm.app.name
        self.unit = self.charm.unit.name
        self.backend = self.charm.backend
        self.client_relation = self.charm.client_relation

        # Define a peer relation
        self.peers_rel_id = self.harness.add_relation(PEER_RELATION_NAME, "pgbouncer-k8s")
        self.harness.add_relation_unit(self.peers_rel_id, self.unit)

        # Define a backend relation
        self.backend_rel_id = self.harness.add_relation(BACKEND_RELATION_NAME, "postgres-k8s")
        self.harness.add_relation_unit(self.backend_rel_id, "postgres-k8s/0")

        # Define a pgbouncer provider relation
        self.client_rel_id = self.harness.add_relation(CLIENT_RELATION_NAME, "application")
        self.harness.add_relation_unit(self.client_rel_id, "application/0")

    @patch("charms.data_platform_libs.v0.data_interfaces.DatabaseProvides.set_read_only_endpoints")
    def test_update_read_only_endpoints(self, _set_read_only_endpoints):
        self.harness.set_leader()
        event = MagicMock()
        self.client_relation.update_read_only_endpoints(event)
        _set_read_only_endpoints.assert_called()
