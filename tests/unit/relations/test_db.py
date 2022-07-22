# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import MagicMock, PropertyMock, patch

from charms.postgresql_k8s.v0.postgresql import PostgreSQL
from ops.testing import Harness

from charm import PgBouncerK8sCharm
from lib.charms.pgbouncer_operator.v0.pgb import (
    DEFAULT_CONFIG,
    PgbConfig,
    parse_dict_to_kv_string,
    parse_kv_string_to_dict,
)

TEST_UNIT = {
    "master": "host=master port=1 dbname=testdatabase",
    "standbys": "host=standby1 port=1 dbname=testdatabase",
}


class TestDb(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(PgBouncerK8sCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

        self.charm = self.harness.charm
        self.db_relation = self.charm.legacy_db_relation
        self.db_admin_relation = self.charm.legacy_db_admin_relation

    def test_correct_admin_perms_set_in_constructor(self):
        assert self.charm.legacy_db_relation.relation_name == "db"
        assert self.charm.legacy_db_relation.admin is False

        assert self.charm.legacy_db_admin_relation.relation_name == "db-admin"
        assert self.charm.legacy_db_admin_relation.admin is True

    @patch("charm.PgBouncerK8sCharm.read_pgb_config", return_value=PgbConfig(DEFAULT_CONFIG))
    @patch("ops.charm.EventBase.defer")
    @patch("relations.db.DbProvides.get_external_app")
    def test_on_relation_changed_early_returns(self, _get_app, _defer, _read_cfg):
        """Validate the various cases where we want _on_relation_changed to return early."""
        mock_event = MagicMock()
        mock_event.defer = _defer

        # changed-hook returns early if charm is not leader
        self.db_relation._on_relation_changed(mock_event)
        _read_cfg.assert_not_called()

        # changed-hook returns early if charm cfg[databases][pg_master] doesn't exist
        self.harness.set_leader(True)
        self.db_relation._on_relation_changed(mock_event)
        _defer.assert_called_once()
        _defer.reset_mock()

        # changed-hook returns early if relation data doesn't contain a database name
        mock_event.relation.data = {}
        mock_event.relation.data[self.db_admin_relation.charm.unit] = None
        mock_event.relation.data[self.charm.app] = {"database": None}
        mock_event.relation.data[_get_app] = {"database": None}

        _read_cfg.return_value["databases"]["pg_master"] = {"test": "value"}
        self.db_relation._on_relation_changed(mock_event)
        _defer.assert_called_once()

    @patch("charm.PgBouncerK8sCharm.backend_relation", new_callable=PropertyMock)
    @patch("charm.PgBouncerK8sCharm.read_pgb_config", return_value=PgbConfig(DEFAULT_CONFIG))
    @patch("charms.pgbouncer_operator.v0.pgb.generate_password", return_value="test_pass")
    @patch("charm.PgBouncerK8sCharm.add_user")
    @patch("charms.postgresql_k8s.v0.postgresql.PostgreSQL.create_user")
    @patch("charms.postgresql_k8s.v0.postgresql.PostgreSQL.create_database")
    @patch("charm.PgBouncerK8sCharm._render_pgb_config")
    def test_on_relation_joined(
        self,
        _render_cfg,
        _create_database,
        _create_user,
        _add_user,
        _gen_pw,
        _read_cfg,
        _backend,
    ):
        self.harness.set_leader(True)

        mock_event = MagicMock()
        mock_event.unit = MagicMock()
        mock_event.app = MagicMock()
        mock_event.app.name = "external_test_app"
        mock_event.relation.id = 1
        database = "test_db"

        relation_data = mock_event.relation.data = {}
        relation_data[self.charm.unit] = {}
        relation_data[self.charm.app] = {}
        relation_data[mock_event.unit] = {"database": database}

        user = f"relation_id_{mock_event.relation.id}"
        password = _gen_pw.return_value

        self.db_admin_relation._on_relation_joined(mock_event)

        _add_user.assert_called_with(
            user,
            password=password,
            admin=True,
            cfg=_read_cfg.return_value,
            render_cfg=True,
            reload_pgbouncer=True,
        )
        _create_user.assert_called_with(user, password, admin=True)
        _create_database.assert_called_with(database, user)

        for dbag in [relation_data[self.charm.unit], relation_data[self.charm.app]]:
            assert dbag["database"] == database
            assert dbag["user"] == user
            assert dbag["password"] == password

        self.db_relation._on_relation_joined(mock_event)
        _create_user.assert_called_with(user, password, admin=False)
        _create_database.assert_called_with(database, user)

        _add_user.assert_called_with(
            user,
            password=password,
            admin=False,
            cfg=_read_cfg.return_value,
            render_cfg=True,
            reload_pgbouncer=True,
        )

    @patch("charm.PgBouncerK8sCharm.backend_relation", new_callable=PropertyMock)
    @patch("charm.PgBouncerK8sCharm.backend_postgres", new_callable=PropertyMock)
    @patch("charm.PgBouncerK8sCharm.read_pgb_config", return_value=PgbConfig(DEFAULT_CONFIG))
    @patch("relations.db.DbProvides.get_external_app")
    @patch("relations.db.DbProvides.get_allowed_units", return_value="test_allowed_unit")
    @patch("relations.db.DbProvides.get_allowed_subnets", return_value="test_allowed_subnet")
    @patch("relations.db.DbProvides._get_standbys", return_value="test-postgres-standbys")
    @patch("relations.db.DbProvides._get_state", return_value="test-state")
    @patch("charm.PgBouncerK8sCharm._render_pgb_config")
    def test_on_relation_changed(
        self,
        _render_cfg,
        _state,
        _standbys,
        _allowed_subnets,
        _allowed_units,
        _external_app,
        _read_cfg,
        _backend_postgres,
        _backend_relation,
    ):
        # Ensure event doesn't defer too early
        self.harness.set_leader(True)

        # set up mocks
        primary_host = "test-host"
        primary_port = "test-port"
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

        _backend_postgres.return_value = PostgreSQL(
            host=f"{primary_host}:{primary_port}", user=user, password=password, database=database
        )

        # Call the function
        self.db_relation._on_relation_changed(mock_event)

        # evaluate output
        expected_primary = {
            "host": primary_host,
            "dbname": database,
            "port": primary_port,
            "user": user,
            "password": password,
            "fallback_application_name": external_app.name,
        }

        for databag in [pgb_app_databag, pgb_unit_databag]:
            assert databag["allowed-subnets"] == _allowed_subnets.return_value
            assert databag["allowed-units"] == _allowed_units.return_value
            assert databag["host"] == f"http://{primary_host}"
            assert databag["master"] == parse_dict_to_kv_string(expected_primary)
            assert databag["port"] == primary_port
            assert databag["standbys"] == _standbys.return_value
            assert databag["version"] == "12"
            assert databag["user"] == user
            assert databag["password"] == password
            assert databag["database"] == database

        assert pgb_unit_databag["state"] == _state.return_value

        _render_cfg.assert_called_with(_read_cfg.return_value, reload_pgbouncer=True)

    @patch("charm.PgBouncerK8sCharm.backend_relation_app_databag", new_callable=PropertyMock)
    @patch("charm.PgBouncerK8sCharm.backend_relation", new_callable=PropertyMock)
    def test_get_standbys(self, backend_relation, backend_databag):
        backend_data = {"read-only-endpoints": "host1:port1,host2:port2"}
        self.charm.backend_relation.data = {self.charm.backend_relation.app: backend_data}

        cfg = PgbConfig(DEFAULT_CONFIG)
        app = "app_name"
        cfg_entry = "db_app"
        db_name = "dbname"
        user = "user"
        pw = "pw"

        standbys = self.db_relation._get_standbys(cfg, app, cfg_entry, db_name, user, pw)
        standby_list = standbys.split(", ")

        assert len(standby_list) == 2

        assert cfg["databases"][f"{cfg_entry}_standby"] == {
            "host": "host2",
            "dbname": db_name,
            "port": "port2",
        }

        for standby in standby_list:
            standby_dict = parse_kv_string_to_dict(standby)
            assert standby_dict.get("dbname") == db_name
            assert standby_dict.get("user") == user
            assert standby_dict.get("password") == pw
            assert standby_dict.get("fallback_application_name") == app
            assert "host" in standby_dict.get("host")
            assert "port" in standby_dict.get("port")

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
    @patch("charm.PgBouncerK8sCharm.remove_user")
    @patch("charm.PgBouncerK8sCharm._render_pgb_config")
    def test_on_relation_broken(self, _render, _remove_user, _read):
        """Test that all traces of the given app are removed from pgb config, including user."""
        test_dbname = "test_db"
        test_user = "test_user"

        input_cfg = PgbConfig(DEFAULT_CONFIG)
        input_cfg["databases"]["pgb_postgres_standby_0"] = {"dbname": "pgb_postgres_standby_0"}
        input_cfg["databases"]["pgb_postgres_standby_555"] = {"dbname": "pgb_postgres_standby_555"}
        input_cfg["databases"][f"{test_dbname}"] = {"dbname": f"{test_dbname}"}
        input_cfg["databases"][f"{test_dbname}_standby"] = {"dbname": f"{test_dbname}_standby_0"}
        _read.return_value = input_cfg

        mock_event = MagicMock()
        app_databag = {
            "user": test_user,
            "database": test_dbname,
        }
        mock_event.relation.data = {}
        mock_event.relation.data[self.charm.app] = app_databag
        self.db_relation._on_relation_broken(mock_event)

        broken_cfg = PgbConfig(_render.call_args[0][0])
        for backend_dbname in ["pg_master", "pgb_postgres_standby_0", "pgb_postgres_standby_555"]:
            assert backend_dbname in broken_cfg["databases"].keys()

        for dbname in [f"{test_dbname}", f"{test_dbname}_standby_0", f"{test_dbname}_standby_1"]:
            assert dbname not in broken_cfg["databases"].keys()

        _remove_user.assert_called_with(test_user, cfg=input_cfg, render_cfg=False)
