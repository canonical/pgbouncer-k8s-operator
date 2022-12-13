# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import MagicMock, PropertyMock, patch

from ops.testing import Harness

from charm import PgBouncerK8sCharm
from constants import BACKEND_RELATION_NAME, CLIENT_RELATION_NAME, PEER_RELATION_NAME
from lib.charms.pgbouncer_k8s.v0.pgb import DEFAULT_CONFIG, PgbConfig


class TestPgbouncerProvider(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(PgBouncerK8sCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

        self.charm = self.harness.charm
        self.app = self.charm.app.name
        self.unit = self.charm.unit.name
        self.backend = self.charm.backend
        self.client_relation = self.charm.client_relation

        # Define a peer relation
        self.peers_rel_id = self.harness.add_relation(PEER_RELATION_NAME, "pgbouncer-k8s")
        self.harness.add_relation_unit(self.peers_rel_id, self.unit)

        # Define a backend relation
        self.backend_rel_id = self.harness.add_relation(BACKEND_RELATION_NAME, "postgres-k8s")
        self.harness.add_relation_unit(self.backend_rel_id, "postgres-k8s/0")

        # Define a pgbouncer provider relation
        self.client_rel_id = self.harness.add_relation(CLIENT_RELATION_NAME, "application")
        self.harness.add_relation_unit(self.client_rel_id, "application/0")

    @patch("relations.pgbouncer_provider.PgBouncerProvider._check_backend")
    @patch(
        "relations.backend_database.BackendDatabaseRequires.postgres", new_callable=PropertyMock
    )
    @patch(
        "relations.backend_database.BackendDatabaseRequires.postgres_databag",
        new_callable=PropertyMock,
        return_value={"endpoints": "test:endpoint"},
    )
    @patch(
        "relations.backend_database.BackendDatabaseRequires.auth_user",
        new_callable=PropertyMock,
        return_value="test_auth_user",
    )
    @patch("charms.pgbouncer_k8s.v0.pgb.generate_password", return_value="test_pass")
    @patch("relations.pgbouncer_provider.PgBouncerProvider.update_read_only_endpoints")
    @patch("relations.pgbouncer_provider.PgBouncerProvider.get_database", return_value="test-db")
    @patch("charms.data_platform_libs.v0.database_provides.DatabaseProvides.set_credentials")
    @patch("charms.data_platform_libs.v0.database_provides.DatabaseProvides.set_endpoints")
    @patch("charms.data_platform_libs.v0.database_provides.DatabaseProvides.set_version")
    @patch("charm.PgBouncerK8sCharm.read_pgb_config", return_value=PgbConfig(DEFAULT_CONFIG))
    @patch("charm.PgBouncerK8sCharm.render_pgb_config")
    def test_on_database_requested(
        self,
        _render_cfg,
        _cfg,
        _dbp_set_version,
        _dbp_set_endpoints,
        _dbp_set_credentials,
        _get_database,
        _update_read_only_endpoints,
        _password,
        _auth_user,
        _pg_databag,
        _pg,
        _check_backend,
    ):
        self.harness.set_leader()

        event = MagicMock()
        rel_id = event.relation.id = 1
        database = event.database = "test-db"
        event.extra_user_roles = "SUPERUSER"
        user = f"relation_id_{rel_id}"

        # check we exit immediately if backend doesn't exist.
        _check_backend.return_value = False
        self.client_relation._on_database_requested(event)
        _pg.create_user.assert_not_called()

        _check_backend.return_value = True
        self.client_relation._on_database_requested(event)

        # Verify we've called everything we should
        _pg().create_user.assert_called_with(
            user, _password(), extra_user_roles=event.extra_user_roles
        )
        _pg().create_database.assert_called_with(database, user)
        assert self.charm.peers.get_secret("app", user) == _password()
        _dbp_set_credentials.assert_called_with(rel_id, user, _password())
        _dbp_set_version.assert_called_with(rel_id, _pg().get_postgresql_version())
        _dbp_set_endpoints.assert_called_with(
            rel_id, f"{self.charm.leader_hostname}:{self.charm.config['listen_port']}"
        )
        _update_read_only_endpoints.assert_called()
        _render_cfg.assert_called_with(_cfg(), reload_pgbouncer=True)

        # Verify config contains what we want
        postgres_endpoint = self.charm.backend.postgres_databag.get("endpoints")
        assert _cfg()["databases"][database] == {
            "host": postgres_endpoint.split(":")[0],
            "dbname": database,
            "port": postgres_endpoint.split(":")[1],
            "auth_user": self.charm.backend.auth_user,
        }
        assert not _cfg()["databases"].get(f"{database}_readonly")

        # test cfg with scaled pg
        _pg_databag.return_value["read-only-endpoints"] = "r_test:endpoint"
        self.client_relation._on_database_requested(event)
        postgres_endpoint = self.charm.backend.postgres_databag.get("endpoints")
        assert _cfg()["databases"][database] == {
            "host": postgres_endpoint.split(":")[0],
            "dbname": database,
            "port": postgres_endpoint.split(":")[1],
            "auth_user": self.charm.backend.auth_user,
        }
        read_only_endpoints = self.charm.backend.get_read_only_endpoints()
        r_hosts = ",".join([host.split(":")[0] for host in read_only_endpoints])
        assert _cfg()["databases"][f"{database}_readonly"] == {
            "host": r_hosts,
            "dbname": database,
            "port": next(iter(read_only_endpoints)).split(":")[1],
            "auth_user": self.charm.backend.auth_user,
        }

    @patch("relations.pgbouncer_provider.PgBouncerProvider._check_backend")
    @patch(
        "relations.backend_database.BackendDatabaseRequires.postgres", new_callable=PropertyMock
    )
    @patch("charm.PgBouncerK8sCharm.read_pgb_config", return_value=PgbConfig(DEFAULT_CONFIG))
    @patch("charm.PgBouncerK8sCharm.render_pgb_config")
    def test_on_relation_broken(self, _render_cfg, _cfg, _pg, _check_backend):
        _pg.return_value.get_postgresql_version.return_value = "10"
        self.harness.set_leader()

        event = MagicMock()
        rel_id = event.relation.id = 1
        external_app = self.charm.client_relation.get_external_app(event.relation)
        event.relation.data = {external_app: {"database": "test_db"}}
        database = event.relation.data[external_app]["database"]
        user = f"relation_id_{rel_id}"

        _cfg.return_value["databases"][database] = {
            "host": "host",
            "dbname": database,
            "port": "1111",
            "auth_user": self.charm.backend.auth_user,
        }
        _cfg.return_value["databases"][f"{database}_readonly"] = {
            "host": "host2",
            "dbname": database,
            "port": "1111",
            "auth_user": self.charm.backend.auth_user,
        }
        _cfg.return_value["pgbouncer"]["admin_users"].add(user)
        _cfg.return_value["pgbouncer"]["stats_users"].add(user)

        _check_backend.return_value = True
        self.client_relation._on_relation_broken(event)
        _cfg.assert_called()
        assert user not in _cfg()["pgbouncer"]["admin_users"]
        assert user not in _cfg()["pgbouncer"]["stats_users"]
        assert not _cfg()["databases"].get(database)
        assert not _cfg()["databases"].get(f"{database}_readonly")
        _render_cfg.assert_called_with(_cfg(), reload_pgbouncer=True)
        _pg().delete_user.assert_called_with(user)

        # Test again without readonly node
        _cfg.return_value["databases"][database] = {
            "host": "host",
            "dbname": database,
            "port": "1111",
            "auth_user": self.charm.backend.auth_user,
        }
        self.client_relation._on_relation_broken(event)
        assert not _cfg()["databases"].get(database)
        assert not _cfg()["databases"].get(f"{database}_readonly")

    @patch(
        "charms.data_platform_libs.v0.database_provides.DatabaseProvides.set_read_only_endpoints"
    )
    def test_update_read_only_endpoints(self, _set_read_only_endpoints):
        self.harness.set_leader()
        event = MagicMock()
        self.client_relation.update_read_only_endpoints(event)
        _set_read_only_endpoints.assert_called()
