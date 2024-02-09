# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import patch

from ops.testing import Harness

from charm import PgBouncerK8sCharm
from constants import PEER_RELATION_NAME


class TestPeers(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(PgBouncerK8sCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

        self.togggle_monitoring_patch = patch("charm.PgBouncerK8sCharm.toggle_monitoring_layer")
        self.toggle_monitoring_layer = self.togggle_monitoring_patch.start()

        self.charm = self.harness.charm
        self.app = self.charm.app.name
        self.unit = self.charm.unit.name

        self.rel_id = self.harness.add_relation(PEER_RELATION_NAME, self.charm.app.name)

    def tearDown(self):
        self.togggle_monitoring_patch.stop()
