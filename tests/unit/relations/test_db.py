# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import MagicMock, patch

from charms.pgbouncer_k8s.v0.pgb import parse_dict_to_kv_string
from ops.testing import Harness

from charm import PgBouncerK8sCharm
from constants import (
    BACKEND_RELATION_NAME,
    DB_ADMIN_RELATION_NAME,
    DB_RELATION_NAME,
    PEER_RELATION_NAME,
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
        self.harness.add_relation_unit(self.backend_rel_id, "postgres-k8s/0")

        # Define a db relation
        self.db_rel_id = self.harness.add_relation(DB_RELATION_NAME, "client_app")
        self.harness.add_relation_unit(self.db_rel_id, "client_app/0")

        # Define a db-admin relation
        self.db_admin_rel_id = self.harness.add_relation(DB_ADMIN_RELATION_NAME, "admin_client")
        self.harness.add_relation_unit(self.db_admin_rel_id, "admin_client/0")

    def test_correct_admin_perms_set_in_constructor(self):
        assert self.charm.legacy_db_relation.relation_name == "db"
        assert self.charm.legacy_db_relation.admin is False

        assert self.charm.legacy_db_admin_relation.relation_name == "db-admin"
        assert self.charm.legacy_db_admin_relation.admin is True

    @patch("relations.db.DbProvides.get_databags", return_value=[{}])
    @patch("relations.db.DbProvides.get_external_app")
    @patch("relations.db.DbProvides.update_databags")
    def test_update_connection_info(self, _update_databags, _get_external_app, _get_databags):
        relation = MagicMock()
        database = "test_db"
        user = "test_user"
        password = "test_pw"
        port = "5555"

        _get_databags.return_value[0] = {
            "database": database,
            "user": user,
            "password": password,
        }

        master_dbconnstr = {
            "host": self.charm.peers.leader_hostname,
            "dbname": database,
            "port": port,
            "user": user,
            "password": password,
            "fallback_application_name": _get_external_app().name,
        }

        standby_hostnames = self.charm.peers.units_hostnames - {self.charm.peers.leader_hostname}
        if len(standby_hostnames) > 0:
            standby_hostname = standby_hostnames.pop()
            standby_dbconnstr = dict(master_dbconnstr)
            standby_dbconnstr.update({"host": standby_hostname, "dbname": f"{database}_standby"})

        self.db_relation.update_connection_info(relation, port)
        _update_databags.assert_called_with(
            relation,
            {
                "master": parse_dict_to_kv_string(master_dbconnstr),
                "port": port,
                "host": self.charm.unit_pod_hostname,
                "standbys": parse_dict_to_kv_string(standby_dbconnstr),
            },
        )

    @patch("relations.db.DbProvides.get_allowed_units", return_value="test_string")
    def test_on_relation_departed(self, _get_units):
        self.harness.set_leader(True)
        mock_event = MagicMock()
        mock_event.relation.data = {
            self.charm.app: {"allowed-units": "app"},
            self.charm.unit: {"allowed-units": "unit"},
        }
        self.db_relation._on_relation_departed(mock_event)

        app_databag = mock_event.relation.data[self.charm.app]
        unit_databag = mock_event.relation.data[self.charm.unit]

        expected_app_databag = {"allowed-units": "test_string"}
        expected_unit_databag = {"allowed-units": "test_string"}

        self.assertDictEqual(app_databag, expected_app_databag)
        self.assertDictEqual(unit_databag, expected_unit_databag)
