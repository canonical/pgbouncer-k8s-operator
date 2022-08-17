# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import patch, call

from ops.testing import Harness

from charm import PgBouncerK8sCharm
from lib.charms.pgbouncer_k8s.v0.pgb import (
    PgbConfig
)
from constants import PEER_RELATION_NAME, BACKEND_RELATION_NAME


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

    @patch("charm.PgBouncerK8sCharm.push_file")
    def test_on_peers_changed(self, render_file):
        self.harness.set_leader(True)
        self.harness.on[PEER_RELATION_NAME].relation_changed.emit()
        render_file.assert_not_called()

        self.harness.set_leader(False)
        self.harness.on[PEER_RELATION_NAME].relation_changed.emit()
        calls = [call()]
        render_file.assert_has_calls(calls)

    # TODO test how these interact with the changes to relations.