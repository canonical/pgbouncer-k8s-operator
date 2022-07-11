# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from copy import deepcopy
from unittest.mock import MagicMock, patch

from ops.testing import Harness

from charm import PgBouncerK8sCharm
from lib.charms.pgbouncer_operator.v0 import pgb
from relations.backend_db_admin import STANDBY_PREFIX

TEST_UNIT = {
    "master": "host=master port=1 dbname=testdatabase",
    "standbys": "host=standby1 port=1 dbname=testdatabase",
}


class TestBackendDbAdmin(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(PgBouncerK8sCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

        self.relation = self.harness.charm.backend_relation
