# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import MagicMock, PropertyMock, patch

from charms.pgbouncer_k8s.v0.pgb import DEFAULT_CONFIG, PGB_DIR, PgbConfig
from ops.testing import Harness

from charm import PgBouncerK8sCharm

BACKEND_RELATION_NAME = "backend-database"


class TestBackendDatabaseRelation(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(PgBouncerK8sCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

        self.charm = self.harness.charm
        self.unit = self.charm.unit.name
        self.backend = self.charm.backend

        # Define a backend relation
        self.rel_id = self.harness.add_relation(BACKEND_RELATION_NAME, "postgres")
        self.harness.add_relation_unit(self.rel_id, "postgres/0")
        self.harness.add_relation_unit(self.rel_id, self.unit)

    @patch("relations.backend_database.BackendDatabaseRequires.get_postgres")
    @patch("charms.pgbouncer_k8s.v0.pgb.generate_password", return_value="pw")
    @patch("relations.backend_database.BackendDatabaseRequires.initialise_auth_function")
    @patch("charm.PgBouncerK8sCharm.push_file")
    @patch("charm.PgBouncerK8sCharm.read_pgb_config", return_value=PgbConfig(DEFAULT_CONFIG))
    @patch("charm.PgBouncerK8sCharm.update_postgres_endpoints")
    def test_on_database_created(
        self, _update_endpoints, _cfg, _push, _init_auth, _gen_pw, _postgres
    ):
        pw = _gen_pw.return_value
        postgres = _postgres.return_value

        mock_event = MagicMock()
        mock_event.username = "mock_user"
        self.backend._on_database_created(mock_event)

        postgres.create_user.assert_called_with(self.backend.auth_user, pw, admin=True)
        _init_auth.assert_called_with(postgres, dbname=self.backend.database.database)
        _push.assert_any_call(
            f"{PGB_DIR}/userlist.txt", f'"{self.backend.auth_user}" "{pw}"', perms=0o777
        )

        cfg = _cfg.return_value
        assert mock_event.username in cfg["pgbouncer"]["admin_users"]
        assert (
            cfg["pgbouncer"]["auth_query"]
            == f"SELECT username, password FROM {self.backend.auth_user}.get_auth($1)"
        )
        assert cfg["pgbouncer"]["auth_file"] == f"{PGB_DIR}/userlist.txt"

        _update_endpoints.assert_called_once()

    @patch(
        "relations.backend_database.BackendDatabaseRequires.postgres", new_callable=PropertyMock
    )
    @patch("charm.PgBouncerK8sCharm.update_postgres_endpoints")
    def test_relation_departed(self, _update_endpoints, _postgres):
        postgres = _postgres.return_value
        depart_event = MagicMock()
        depart_event.departing_unit = self.charm.unit
        self.backend._on_relation_departed(depart_event)

        uninstall_script = open("src/relations/pgbouncer-uninstall.sql", "r").read()

        postgres.connect_to_database.assert_called_with("pgbouncer")
        conn = postgres.connect_to_database().__enter__()
        cursor = conn.cursor().__enter__()
        cursor.execute.assert_called_with(
            uninstall_script.replace("auth_user", self.backend.auth_user)
        )
        conn.close.assert_called()

    @patch(
        "relations.backend_database.BackendDatabaseRequires.postgres", new_callable=PropertyMock
    )
    @patch("charm.PgBouncerK8sCharm.read_pgb_config", return_value=PgbConfig(DEFAULT_CONFIG))
    @patch("charm.PgBouncerK8sCharm.render_pgb_config")
    @patch("charm.PgBouncerK8sCharm.delete_file")
    @patch("charm.PgBouncerK8sCharm.remove_postgres_endpoints")
    def test_relation_broken(self, _remove_endpoints, _delete_file, _render, _cfg, _postgres):
        postgres = _postgres.return_value
        postgres.user = "test_user"
        cfg = _cfg.return_value
        cfg.add_user(postgres.user, admin=True)
        cfg["pgbouncer"]["auth_user"] = "test"
        cfg["pgbouncer"]["auth_query"] = "test"

        self.backend._on_relation_broken(MagicMock())

        assert "test_user" not in cfg["pgbouncer"]
        assert "auth_user" not in cfg["pgbouncer"]
        assert "auth_query" not in cfg["pgbouncer"]

        _render.assert_called_with(cfg)
        _delete_file.assert_called_with(f"{PGB_DIR}/userlist.txt")
        _remove_endpoints.assert_called()

    def test_initialise_auth_function(self):
        install_script = open("src/relations/pgbouncer-install.sql", "r").read()
        postgres = MagicMock()
        dbname = "test-db"

        self.backend.initialise_auth_function(postgres=postgres, dbname=dbname)

        postgres.connect_to_database.assert_called_with(dbname)
        conn = postgres.connect_to_database().__enter__()
        cursor = conn.cursor().__enter__()
        cursor.execute.assert_called_with(
            install_script.replace("auth_user", self.backend.auth_user)
        )
        conn.close.assert_called()
