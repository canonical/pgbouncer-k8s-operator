# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from copy import deepcopy
from unittest.mock import MagicMock, patch

from ops.testing import Harness

from charm import PgBouncerCharm
from lib.charms.pgbouncer_operator.v0 import pgb
from relations.backend_db_admin import STANDBY_PREFIX

TEST_UNIT = {
    "master": "host=master port=1 dbname=testdatabase",
    "standbys": "host=standby1 port=1 dbname=testdatabase",
}


class TestBackendDbAdmin(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(PgBouncerCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

        self.relation = self.harness.charm.legacy_backend_relation

    @patch("charm.PgBouncerCharm._read_pgb_config", return_value=pgb.PgbConfig(pgb.DEFAULT_CONFIG))
    @patch("charm.PgBouncerCharm._render_service_configs")
    def test_on_relation_changed(self, _render, _read):
        """This test exists to check the basics for how the config is expected to change.

        The integration tests for this relation are a more extensive test of this functionality.
        """
        mock_event = MagicMock()
        mock_event.unit = "mock_unit"
        mock_event.relation.data = {"mock_unit": deepcopy(TEST_UNIT)}

        self.relation._on_relation_changed(mock_event)

        # get rendered config from _render, and compare it to expected.
        rendered_cfg = _render.call_args[0][0]
        expected_cfg = pgb.PgbConfig(pgb.DEFAULT_CONFIG)
        expected_cfg["databases"]["pg_master"] = pgb.parse_kv_string_to_dict(TEST_UNIT["master"])
        expected_cfg["databases"][f"{STANDBY_PREFIX}0"] = pgb.parse_kv_string_to_dict(
            TEST_UNIT["standbys"]
        )

        self.assertEqual(expected_cfg.render(), rendered_cfg.render())

        del mock_event.relation.data["mock_unit"]["standbys"]

        self.relation._on_relation_changed(mock_event)

        rendered_cfg = _render.call_args[0][0]
        expected_cfg = pgb.PgbConfig(pgb.DEFAULT_CONFIG)
        expected_cfg["databases"]["pg_master"] = pgb.parse_kv_string_to_dict(TEST_UNIT["master"])
        self.assertEqual(expected_cfg.render(), rendered_cfg.render())
        self.assertNotIn(f"{STANDBY_PREFIX}0", rendered_cfg.keys())

    @patch("charm.PgBouncerCharm._read_pgb_config", return_value=pgb.PgbConfig(pgb.DEFAULT_CONFIG))
    @patch("charm.PgBouncerCharm._render_service_configs")
    def test_on_relation_departed(self, _render, _read):
        """This test exists to check the basics for how the config is expected to change.

        The integration tests for this relation are a more extensive test of this functionality.
        """
        mock_event = MagicMock()
        self.relation._on_relation_departed(mock_event)

        expected_cfg = pgb.PgbConfig(pgb.DEFAULT_CONFIG)
        rendered_cfg = _render.call_args[0][0]
        self.assertEqual(expected_cfg.render(), rendered_cfg.render())
        self.assertNotIn("pg_master", rendered_cfg.keys())
