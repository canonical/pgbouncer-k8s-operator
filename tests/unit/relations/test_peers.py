# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import MagicMock, PropertyMock, patch

from ops.testing import Harness

from charm import PgBouncerK8sCharm
from lib.charms.pgbouncer_k8s.v0.pgb import (
    PgbConfig
)

TEST_UNIT = {
    "master": "host=master port=1 dbname=testdatabase",
    "standbys": "host=standby1 port=1 dbname=testdatabase",
}

BACKEND_RELATION_NAME = "backend-database"
DB_RELATION_NAME = "db"
DB_ADMIN_RELATION_NAME = "db-admin"


class TestDb(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(PgBouncerK8sCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

        self.charm = self.harness.charm
        self.app = self.charm.app.name
        self.unit = self.charm.unit.name

        # Define a backend relation
        self.backend_rel_id = self.harness.add_relation(BACKEND_RELATION_NAME, "postgres")
        self.harness.add_relation_unit(self.backend_rel_id, "postgres/0")
        self.harness.add_relation_unit(self.backend_rel_id, self.unit)

        # TODO scale pgbouncer up to three units

    # TODO test how these interact with the changes to relations.