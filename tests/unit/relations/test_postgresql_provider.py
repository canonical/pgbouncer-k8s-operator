# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import MagicMock, PropertyMock, patch

from ops.testing import Harness

from charm import PgBouncerK8sCharm
from constants import (
    BACKEND_RELATION_NAME,
    DB_ADMIN_RELATION_NAME,
    DB_RELATION_NAME,
    PEER_RELATION_NAME,
)
from lib.charms.pgbouncer_k8s.v0.pgb import (
    DEFAULT_CONFIG,
    PgbConfig,
    parse_dict_to_kv_string,
)

TEST_UNIT = {
    "master": "host=master port=1 dbname=testdatabase",
    "standbys": "host=standby1 port=1 dbname=testdatabase",
}

# TODO write tests for when the current unit is a follower


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
        self.harness.add_relation_unit(self.backend_rel_id, "postgres/0")
        self.harness.add_relation_unit(self.backend_rel_id, self.unit)

    def write_some_tests(self):
        assert False
