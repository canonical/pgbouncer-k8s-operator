# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import MagicMock, PropertyMock, patch

from ops.testing import Harness

from charm import PgBouncerK8sCharm
from lib.charms.pgbouncer_k8s.v0.pgb import (
    DEFAULT_CONFIG,
    PgbConfig,
    parse_dict_to_kv_string,
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
        self.backend = self.charm.backend
        self.db_relation = self.charm.legacy_db_relation
        self.db_admin_relation = self.charm.legacy_db_admin_relation

        # TODO update mocks now we're using the mock harness
        # Define a backend relation
        self.backend_rel_id = self.harness.add_relation(BACKEND_RELATION_NAME, "postgres")
        self.harness.add_relation_unit(self.backend_rel_id, "postgres/0")
        self.harness.add_relation_unit(self.backend_rel_id, self.unit)

        # Define a db relation
        self.db_rel_id = self.harness.add_relation(DB_RELATION_NAME, "postgres")
        self.harness.add_relation_unit(self.db_rel_id, "client/0")
        self.harness.add_relation_unit(self.db_rel_id, self.unit)

        # Define a db-admin relation
        self.db_admin_rel_id = self.harness.add_relation(DB_ADMIN_RELATION_NAME, "postgres")
        self.harness.add_relation_unit(self.db_admin_rel_id, "admin_client/0")
        self.harness.add_relation_unit(self.db_admin_rel_id, self.unit)

    def test_correct_admin_perms_set_in_constructor(self):
        assert self.charm.legacy_db_relation.relation_name == "db"
        assert self.charm.legacy_db_relation.admin is False

        assert self.charm.legacy_db_admin_relation.relation_name == "db-admin"
        assert self.charm.legacy_db_admin_relation.admin is True

    @patch(
        "relations.backend_database.BackendDatabaseRequires.postgres", new_callable=PropertyMock
    )
    @patch("charm.PgBouncerK8sCharm.read_pgb_config", return_value=PgbConfig(DEFAULT_CONFIG))
    @patch("charms.pgbouncer_k8s.v0.pgb.generate_password", return_value="test_pass")
    @patch("charms.postgresql_k8s.v0.postgresql.PostgreSQL")
    @patch("charms.postgresql_k8s.v0.postgresql.PostgreSQL.create_user")
    @patch("charms.postgresql_k8s.v0.postgresql.PostgreSQL.create_database")
    @patch("relations.backend_database.BackendDatabaseRequires.initialise_auth_function")
    @patch("charm.PgBouncerK8sCharm.render_pgb_config")
    def test_on_relation_joined(
        self,
        _render_cfg,
        _init_auth,
        _create_database,
        _create_user,
        _postgres,
        _gen_pw,
        _read_cfg,
        _backend_pg,
    ):
        self.harness.set_leader(True)

        mock_event = MagicMock()
        mock_event.app.name = "external_test_app"
        mock_event.relation.id = 1

        database = "test_db"
        user = "pgbouncer_k8s_user_id_1_None"
        password = _gen_pw.return_value

        relation_data = mock_event.relation.data = {}
        relation_data[self.charm.unit] = {}
        relation_data[self.charm.app] = {}
        relation_data[mock_event.app] = {"database": database}
        _backend_pg.return_value = _postgres
        _postgres.create_user = _create_user
        _postgres.create_database = _create_database

        self.db_admin_relation._on_relation_joined(mock_event)

        _create_user.assert_called_with(user, password, admin=True)
        _create_database.assert_called_with(database, user)
        _init_auth.assert_called_with(dbname=database)
        assert user in _read_cfg.return_value["pgbouncer"]["admin_users"]
        _render_cfg.assert_called_with(_read_cfg.return_value, reload_pgbouncer=True)

        for dbag in [relation_data[self.charm.unit], relation_data[self.charm.app]]:
            assert dbag["database"] == database
            assert dbag["user"] == user
            assert dbag["password"] == password

        # Check admin permissions aren't present when we use db_relation
        self.db_relation._on_relation_joined(mock_event)
        _create_user.assert_called_with(user, password, admin=False)

    @patch(
        "relations.backend_database.BackendDatabaseRequires.app_databag", new_callable=PropertyMock
    )
    @patch(
        "relations.backend_database.BackendDatabaseRequires.postgres", new_callable=PropertyMock
    )
    @patch("charm.PgBouncerK8sCharm.read_pgb_config", return_value=PgbConfig(DEFAULT_CONFIG))
    @patch(
        "charm.PgBouncerK8sCharm.unit_pod_hostname",
        new_callable=PropertyMock,
        return_value="test-host",
    )
    @patch("relations.db.DbProvides.get_external_app")
    @patch("relations.db.DbProvides.get_allowed_units", return_value="test_allowed_unit")
    @patch("relations.db.DbProvides.get_allowed_subnets", return_value="test_allowed_subnet")
    @patch("relations.db.DbProvides._get_state", return_value="test-state")
    @patch("charm.PgBouncerK8sCharm.render_pgb_config")
    @patch("charms.postgresql_k8s.v0.postgresql.PostgreSQL")
    def test_on_relation_changed(
        self,
        _postgres,
        _render_cfg,
        _state,
        _allowed_subnets,
        _allowed_units,
        _external_app,
        _hostname,
        _read_cfg,
        _backend_postgres,
        _backend_dbag,
    ):
        # Ensure event doesn't defer too early
        self.harness.set_leader(True)

        # set up mocks
        _read_cfg.return_value["databases"]["test_db"] = {
            "host": "test-host",
            "dbname": "external_test_unit",
            "port": "test_port",
            "user": "test_user",
            "password": "test_pass",
            "fallback_application_name": "external_test_unit",
        }

        mock_event = MagicMock()
        relation_data = mock_event.relation.data = {}
        pgb_unit_databag = relation_data[self.db_relation.charm.unit] = {}
        database = "test_db"
        user = "test_user"
        password = "test_pw"
        pgb_app_databag = relation_data[self.charm.app] = {
            "database": database,
            "user": user,
            "password": password,
        }

        external_app = _external_app.return_value
        relation_data[external_app] = {}
        external_app.name = "external_test_app"

        _backend_postgres.return_value = _postgres
        _postgres.get_postgresql_version.return_value = "12"

        # Call the function
        self.db_relation._on_relation_changed(mock_event)

        # evaluate output
        dbconnstr = parse_dict_to_kv_string(
            {
                "host": self.charm.unit_pod_hostname,
                "dbname": database,
                "port": self.charm.config["listen_port"],
                "user": user,
                "password": password,
                "fallback_application_name": external_app.name,
            }
        )

        for databag in [pgb_app_databag, pgb_unit_databag]:
            assert databag["allowed-subnets"] == _allowed_subnets.return_value
            assert databag["allowed-units"] == _allowed_units.return_value
            assert databag["host"] == _hostname.return_value
            assert databag["master"] == dbconnstr
            assert databag["port"] == str(self.charm.config["listen_port"])
            assert databag["standbys"] == dbconnstr
            assert databag["version"] == "12"
            assert databag["user"] == user
            assert databag["password"] == password
            assert databag["database"] == database

        assert pgb_unit_databag["state"] == _state.return_value

        _render_cfg.assert_called_with(_read_cfg.return_value, reload_pgbouncer=True)

    @patch("relations.db.DbProvides.get_allowed_units", return_value="test_string")
    def test_on_relation_departed(self, _get_units):
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

    @patch("charm.PgBouncerK8sCharm.read_pgb_config", return_value=PgbConfig(DEFAULT_CONFIG))
    @patch("charms.postgresql_k8s.v0.postgresql.PostgreSQL")
    @patch("charms.postgresql_k8s.v0.postgresql.PostgreSQL.delete_user")
    @patch(
        "relations.backend_database.BackendDatabaseRequires.postgres", new_callable=PropertyMock
    )
    @patch("charm.PgBouncerK8sCharm.render_pgb_config")
    def test_on_relation_broken(
        self, _render_cfg, _backend_postgres, _delete_user, _postgres, _read
    ):
        """Test that all traces of the given app are removed from pgb config, including user."""
        database = "test_db"
        username = "test_user"
        _backend_postgres.return_value = _postgres
        _postgres.delete_user = _delete_user

        input_cfg = PgbConfig(DEFAULT_CONFIG)
        input_cfg["databases"]["some_other_db"] = {"dbname": "pgb_postgres_standby_0"}
        input_cfg["databases"][database] = {"dbname": f"{database}"}
        input_cfg["databases"][f"{database}_standby"] = {"dbname": f"{database}"}
        _read.return_value = input_cfg

        mock_event = MagicMock()
        app_databag = {
            "user": username,
            "database": database,
        }
        mock_event.relation.data = {}
        mock_event.relation.data[self.charm.app] = app_databag

        self.db_relation._on_relation_broken(mock_event)

        _delete_user.assert_called_with(username, if_exists=True)

        assert database not in [input_cfg["databases"]]
        assert f"{database}_standby" not in [input_cfg["databases"]]
