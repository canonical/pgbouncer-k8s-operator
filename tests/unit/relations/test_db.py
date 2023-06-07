# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import MagicMock, PropertyMock, patch

from charms.pgbouncer_k8s.v0.pgb import (
    DEFAULT_CONFIG,
    PgbConfig,
    parse_dict_to_kv_string,
)
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

        self.togggle_monitoring_patch = patch("charm.PgBouncerK8sCharm.toggle_monitoring_layer")
        self.toggle_monitoring_layer = self.togggle_monitoring_patch.start()

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

    def tearDown(self):
        self.togggle_monitoring_patch.stop()

    def test_correct_admin_perms_set_in_constructor(self):
        assert self.charm.legacy_db_relation.relation_name == "db"
        assert self.charm.legacy_db_relation.admin is False

        assert self.charm.legacy_db_admin_relation.relation_name == "db-admin"
        assert self.charm.legacy_db_admin_relation.admin is True

    @patch("relations.db.DbProvides._check_backend", return_value=True)
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
        _check_backend,
    ):
        self.harness.set_leader(True)

        mock_event = MagicMock()
        mock_event.app.name = "external_test_app"
        mock_event.relation.id = 1

        database = "test_db"
        user = "pgbouncer_k8s_user_1_None"
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
        _init_auth.assert_called_with([database])
        assert user in _read_cfg.return_value["pgbouncer"]["admin_users"]
        _render_cfg.assert_called_with(_read_cfg.return_value, reload_pgbouncer=True)

        for dbag in [relation_data[self.charm.unit], relation_data[self.charm.app]]:
            assert dbag["database"] == database
            assert dbag["user"] == user
            assert dbag["password"] == password

        # Check admin permissions aren't present when we use db_relation
        self.db_relation._on_relation_joined(mock_event)
        _create_user.assert_called_with(user, password, admin=False)

    @patch("relations.db.DbProvides._check_backend", return_value=True)
    @patch(
        "relations.backend_database.BackendDatabaseRequires.postgres", new_callable=PropertyMock
    )
    @patch("relations.db.DbProvides.get_databags", return_value=[{}])
    @patch("relations.db.DbProvides.update_connection_info")
    @patch("relations.db.DbProvides.update_postgres_endpoints")
    @patch("relations.db.DbProvides.update_databags")
    @patch("relations.db.DbProvides.get_allowed_units")
    @patch("relations.db.DbProvides.get_allowed_subnets")
    @patch("relations.db.DbProvides._get_state")
    def test_on_relation_changed(
        self,
        _get_state,
        _allowed_subnets,
        _allowed_units,
        _update_databags,
        _update_postgres_endpoints,
        _update_connection_info,
        _get_databags,
        _backend_postgres,
        _check_backend,
    ):
        self.harness.set_leader()

        database = "test_db"
        user = "test_user"
        password = "test_pw"
        _get_databags.return_value[0] = {
            "database": database,
            "user": user,
            "password": password,
        }

        # Call the function
        event = MagicMock()
        self.db_relation._on_relation_changed(event)

        _update_connection_info.assert_called_with(
            event.relation, self.charm.config["listen_port"]
        )
        _update_postgres_endpoints.assert_called_with(event.relation, reload_pgbouncer=True)
        _update_databags.assert_called_with(
            event.relation,
            {
                "allowed-subnets": _allowed_subnets.return_value,
                "allowed-units": _allowed_units.return_value,
                "version": self.charm.backend.postgres.get_postgresql_version(),
                "host": self.charm.unit_pod_hostname,
                "user": user,
                "password": password,
                "database": database,
                "state": _get_state.return_value,
            },
        )

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

    @patch("relations.db.DbProvides._check_backend", return_value=True)
    @patch("relations.db.DbProvides.get_databags")
    @patch(
        "relations.backend_database.BackendDatabaseRequires.postgres_databag",
        new_callable=PropertyMock,
    )
    @patch(
        "relations.backend_database.BackendDatabaseRequires.get_read_only_endpoints",
        return_value=[],
    )
    @patch("charm.PgBouncerK8sCharm.read_pgb_config")
    @patch("charm.PgBouncerK8sCharm.render_pgb_config")
    def test_update_postgres_endpoints(
        self,
        _render_cfg,
        _read_cfg,
        _read_only_endpoint,
        _pg_databag,
        _get_databags,
        _check_backend,
    ):
        database = "test_db"
        _get_databags.return_value = [{"database": database}]
        _pg_databag.return_value = {"endpoints": "ip:port"}
        cfg = PgbConfig(DEFAULT_CONFIG)
        _read_cfg.side_effect = [cfg, PgbConfig(DEFAULT_CONFIG)]

        relation = MagicMock()
        reload_pgbouncer = False

        self.db_relation.update_postgres_endpoints(relation, reload_pgbouncer=reload_pgbouncer)
        assert database in cfg["databases"].keys()
        assert f"{database}_standby" not in cfg["databases"].keys()

        _render_cfg.assert_called_with(cfg, reload_pgbouncer=reload_pgbouncer)
        _read_only_endpoint.return_value = ["readonly:endpoint"]
        _read_cfg.side_effect = [cfg, PgbConfig(DEFAULT_CONFIG)]

        self.db_relation.update_postgres_endpoints(relation, reload_pgbouncer=reload_pgbouncer)
        assert database in cfg["databases"].keys()
        assert f"{database}_standby" in cfg["databases"].keys()

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

    @patch("relations.db.DbProvides._check_backend", return_value=True)
    @patch("charm.PgBouncerK8sCharm.read_pgb_config", return_value=PgbConfig(DEFAULT_CONFIG))
    @patch("charms.postgresql_k8s.v0.postgresql.PostgreSQL")
    @patch("charms.postgresql_k8s.v0.postgresql.PostgreSQL.delete_user")
    @patch(
        "relations.backend_database.BackendDatabaseRequires.postgres", new_callable=PropertyMock
    )
    @patch("charm.PgBouncerK8sCharm.render_pgb_config")
    @patch("relations.backend_database.BackendDatabaseRequires.remove_auth_function")
    def test_on_relation_broken(
        self,
        _remove_auth,
        _render_cfg,
        _backend_postgres,
        _delete_user,
        _postgres,
        _read,
        _check_backend,
    ):
        """Test that all traces of the given app are removed from pgb config, including user."""
        self.harness.set_leader(True)
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
        databag = {
            "user": username,
            "database": database,
        }
        mock_event.relation.data = {}
        mock_event.relation.data[self.charm.unit] = databag
        mock_event.relation.data[self.charm.app] = databag

        self.db_relation._on_relation_broken(mock_event)

        _delete_user.assert_called_with(username)

        assert database not in [input_cfg["databases"]]
        assert f"{database}_standby" not in [input_cfg["databases"]]
