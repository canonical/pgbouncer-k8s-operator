# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import MagicMock, patch

from ops.testing import Harness

from charm import PgBouncerK8sCharm
from constants import BACKEND_STANDBY_PREFIX
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

    @patch("charm.PgBouncerCharm._read_pgb_config", return_value=PgbConfig(DEFAULT_CONFIG))
    @patch("ops.charm.EventBase.defer")
    @patch("relations.db.DbProvides.get_external_units", return_value=[MagicMock()])
    def test_on_relation_changed_early_returns(self, _get_units, _defer, _read_cfg):
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
        mock_event.relation.data[_get_units.return_value[0]] = {"database": None}

        _read_cfg.return_value["databases"]["pg_master"] = {"test": "value"}
        self.db_relation._on_relation_changed(mock_event)
        _defer.assert_called_once()

    @patch("charm.PgBouncerCharm.backend_postgres")
    @patch("charm.PgBouncerCharm._read_pgb_config", return_value=PgbConfig(DEFAULT_CONFIG))
    @patch("relations.db.DbProvides.get_external_units", return_value=[MagicMock()])
    @patch("relations.db.DbProvides.get_allowed_units", return_value="test_allowed_unit")
    @patch("relations.db.DbProvides.get_allowed_subnets", return_value="test_allowed_subnet")
    @patch("relations.db.DbProvides._get_postgres_standbys", return_value="test_postgres_standbys")
    @patch("charms.pgbouncer_operator.v0.pgb.generate_password", return_value="test_pass")
    @patch("relations.db.DbProvides.generate_username", return_value="test_user")
    @patch("ops.charm.EventBase.defer")
    @patch("relations.db.DbProvides._get_state", return_value="test-state")
    @patch("charm.PgBouncerCharm.add_user")
    @patch("charm.PgBouncerCharm._render_service_configs")
    def test_instantiate_new_relation_on_relation_changed(
        self,
        _render_cfg,
        _add_user,
        _state,
        _defer,
        _username,
        _pass,
        _standbys,
        _allowed_subnets,
        _allowed_units,
        _external_units,
        _read_cfg,
        _backend,
    ):
        """Test we can access database, user, and password data from the same relation easily."""
        # Ensure event doesn't defer too early
        self.harness.set_leader(True)

        master_host = "test-host"
        master_port = "test-port"
        _read_cfg.return_value["databases"]["pg_master"] = {
            "host": master_host,
            "port": master_port,
        }
        external_unit = _external_units.return_value[0]

        mock_event = MagicMock()
        mock_event.defer = _defer
        relation_data = mock_event.relation.data = {}
        pgb_unit_databag = relation_data[self.db_admin_relation.charm.unit] = {}
        pgb_app_databag = relation_data[self.charm.app] = {}

        relation_data[external_unit] = {}
        external_unit.app.name = None

        self.db_relation._on_relation_changed(mock_event)
        _defer.assert_called_once()
        _defer.reset_mock()

        external_unit.app.name = "external_test_unit"
        relation_data[external_unit] = {"database": "test_database_name"}

        self.db_relation._on_relation_changed(mock_event)
        _defer.assert_not_called()

        database = "test_database_name"
        user = _username.return_value
        password = _pass.return_value

        expected_primary = {
            "host": master_host,
            "dbname": database,
            "port": master_port,
            "user": user,
            "password": password,
            "fallback_application_name": external_unit.app.name,
        }

        for databag in [pgb_app_databag, pgb_unit_databag]:
            assert databag["allowed-subnets"] == _allowed_subnets.return_value
            assert databag["allowed-units"] == _allowed_units.return_value
            assert databag["host"] == f"http://{master_host}"
            assert databag["master"] == parse_dict_to_kv_string(expected_primary)
            assert databag["port"] == master_port
            assert databag["standbys"] == _standbys.return_value
            assert databag["version"] == "12"
            assert databag["user"] == user
            assert databag["password"] == password
            assert databag["database"] == database

        assert pgb_unit_databag["state"] == _state.return_value

        _add_user.assert_called_with(
            user, password, admin=False, cfg=_read_cfg.return_value, render_cfg=False
        )
        _render_cfg.assert_called_with(_read_cfg.return_value, reload_pgbouncer=True)

    @patch("charm.PgBouncerCharm.backend_postgres")
    @patch("charm.PgBouncerCharm._read_pgb_config", return_value=PgbConfig(DEFAULT_CONFIG))
    @patch("relations.db.DbProvides.get_external_units", return_value=[MagicMock()])
    @patch("relations.db.DbProvides.get_allowed_units", return_value="test_allowed_unit")
    @patch("relations.db.DbProvides.get_allowed_subnets", return_value="test_allowed_subnet")
    @patch("relations.db.DbProvides._get_postgres_standbys", return_value="test-postgres-standbys")
    @patch("relations.db.DbProvides._get_state", return_value="test-state")
    @patch("charm.PgBouncerCharm.add_user")
    @patch("charm.PgBouncerCharm._render_service_configs")
    def test_update_existing_relation_on_relation_changed(
        self,
        _render_cfg,
        _add_user,
        _state,
        _standbys,
        _allowed_subnets,
        _allowed_units,
        _external_units,
        _read_cfg,
        _backend,
    ):
        # Ensure event doesn't defer too early
        self.harness.set_leader(True)

        # set up mocks
        master_host = "test-host"
        master_port = "test-port"
        _read_cfg.return_value["databases"]["pg_master"] = {
            "host": master_host,
            "port": master_port,
        }
        _read_cfg.return_value["databases"]["test_db"] = {
            "host": "test-host",
            "dbname": "external_test_unit",
            "port": "test_port",
            "user": "test_user",
            "password": "test_pass",
            "fallback_application_name": "external_test_unit",
        }

        external_unit = _external_units.return_value[0]

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

        relation_data[external_unit] = {}
        external_unit.app.name = "external_test_unit"

        # Call the function
        self.db_relation._on_relation_changed(mock_event)

        # evaluate output
        expected_primary = {
            "host": master_host,
            "dbname": database,
            "port": master_port,
            "user": user,
            "password": password,
            "fallback_application_name": external_unit.app.name,
        }

        for databag in [pgb_app_databag, pgb_unit_databag]:
            assert databag["allowed-subnets"] == _allowed_subnets.return_value
            assert databag["allowed-units"] == _allowed_units.return_value
            assert databag["host"] == f"http://{master_host}"
            assert databag["master"] == parse_dict_to_kv_string(expected_primary)
            assert databag["port"] == master_port
            assert databag["standbys"] == _standbys.return_value
            assert databag["version"] == "12"
            assert databag["user"] == user
            assert databag["password"] == password
            assert databag["database"] == database

        assert pgb_unit_databag["state"] == _state.return_value

        _add_user.assert_called_with(
            user, password, admin=False, cfg=_read_cfg.return_value, render_cfg=False
        )
        _render_cfg.assert_called_with(_read_cfg.return_value, reload_pgbouncer=True)

    @patch("charm.PgBouncerCharm.backend_postgres")
    @patch("charm.PgBouncerCharm._read_pgb_config", return_value=PgbConfig(DEFAULT_CONFIG))
    @patch("relations.db.DbProvides.get_external_units", return_value=[MagicMock()])
    @patch("relations.db.DbProvides.get_allowed_units", return_value="test_allowed_unit")
    @patch("relations.db.DbProvides.get_allowed_subnets", return_value="test_allowed_subnet")
    @patch("relations.db.DbProvides._get_postgres_standbys", return_value="test-postgres-standbys")
    @patch("relations.db.DbProvides._get_state", return_value="test-state")
    @patch("charm.PgBouncerCharm.add_user")
    @patch("charm.PgBouncerCharm._render_service_configs")
    def test_admin_user_generated_with_correct_admin_permissions(
        self,
        _render_cfg,
        _add_user,
        _state,
        _standbys,
        _allowed_subnets,
        _allowed_units,
        _external_units,
        _read_cfg,
        _backend,
    ):
        self.harness.set_leader(True)
        _read_cfg.return_value["databases"]["pg_master"] = {
            "host": "test-host",
            "port": "test-port",
        }

        mock_event = MagicMock()
        relation_data = mock_event.relation.data = {}
        database = "test_db"
        user = "test_user"
        password = "test_pw"

        relation_data[self.db_relation.charm.unit] = {}
        relation_data[self.charm.app] = {
            "database": database,
            "user": user,
            "password": password,
        }
        external_unit = _external_units.return_value[0]
        relation_data[external_unit] = {}
        external_unit.app.name = "external_test_unit"

        self.db_admin_relation._on_relation_changed(mock_event)

        _add_user.assert_called_with(
            user, password, admin=True, cfg=_read_cfg.return_value, render_cfg=False
        )

    def test_get_postgres_standbys(self):
        cfg = PgbConfig(DEFAULT_CONFIG)
        cfg["databases"]["not_a_standby"] = {"dbname": "not_a_standby"}
        cfg["databases"]["pg_master"] = {"dbname": "pg_master", "host": "test"}
        cfg["databases"][BACKEND_STANDBY_PREFIX] = {
            "dbname": BACKEND_STANDBY_PREFIX,
            "host": "standby_host",
            "port": "standby_port",
        }
        cfg["databases"][f"{BACKEND_STANDBY_PREFIX}0"] = {
            "dbname": f"{BACKEND_STANDBY_PREFIX}0",
            "host": "standby_host",
            "port": "standby_port",
        }
        cfg["databases"][f"not_a_standby{BACKEND_STANDBY_PREFIX}"] = {
            "dbname": f"not_a_standby{BACKEND_STANDBY_PREFIX}",
            "host": "test",
            "port": "port_test",
        }

        app = "app_name"
        db_name = "db_name"
        user = "user"
        pw = "pw"
        standbys = self.db_relation._get_standbys(cfg, app, db_name, user, pw)

        assert "not_a_standby" not in standbys
        assert "pg_master" not in standbys

        standby_list = standbys.split(", ")
        assert len(standby_list) == 2

        for standby in standby_list:
            standby_dict = parse_kv_string_to_dict(standby)
            assert standby_dict.get("dbname") == db_name
            assert standby_dict.get("host") == "standby_host"
            assert standby_dict.get("port") == "standby_port"
            assert standby_dict.get("user") == user
            assert standby_dict.get("password") == pw
            assert standby_dict.get("fallback_application_name") == app

    @patch("relations.db.DbProvides.get_allowed_units", return_value="test_string")
    def test_on_relation_departed(self, _get_units):
        mock_event = MagicMock()
        mock_event.relation.data = {
            self.charm.app: {"allowed-units": "blah"},
            self.charm.unit: {"allowed-units": "blahh"},
        }
        self.db_relation._on_relation_departed(mock_event)

        app_databag = mock_event.relation.data[self.charm.app]
        unit_databag = mock_event.relation.data[self.charm.unit]

        expected_app_databag = {"allowed-units": "test_string"}
        expected_unit_databag = {"allowed-units": "test_string"}

        self.assertDictEqual(app_databag, expected_app_databag)
        self.assertDictEqual(unit_databag, expected_unit_databag)

    @patch("charm.PgBouncerCharm._read_pgb_config", return_value=PgbConfig(DEFAULT_CONFIG))
    @patch("charm.PgBouncerCharm.remove_user")
    @patch("charm.PgBouncerCharm._render_service_configs")
    def test_on_relation_broken(self, _render, _remove_user, _read):
        """Test that all traces of the given app are removed from pgb config, including user."""
        test_dbname = "test_db"
        test_user = "test_user"

        input_cfg = PgbConfig(DEFAULT_CONFIG)
        input_cfg["databases"]["pg_master"] = {"dbname": "pg_master"}
        input_cfg["databases"]["pgb_postgres_standby_0"] = {"dbname": "pgb_postgres_standby_0"}
        input_cfg["databases"]["pgb_postgres_standby_555"] = {"dbname": "pgb_postgres_standby_555"}
        input_cfg["databases"][f"{test_dbname}"] = {"dbname": f"{test_dbname}"}
        input_cfg["databases"][f"{test_dbname}_standby_0"] = {"dbname": f"{test_dbname}_standby_0"}
        input_cfg["databases"][f"{test_dbname}_standby_1"] = {"dbname": f"{test_dbname}_standby_1"}
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
