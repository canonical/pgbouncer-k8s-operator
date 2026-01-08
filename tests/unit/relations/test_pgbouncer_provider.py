# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import MagicMock, PropertyMock, patch, sentinel

from ops.testing import Harness

from charm import PgBouncerK8sCharm
from constants import BACKEND_RELATION_NAME, CLIENT_RELATION_NAME, PEER_RELATION_NAME


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

    @patch("charm.lightkube")
    @patch("charm.PgBouncerK8sCharm.render_pgb_config")
    @patch(
        "charm.PgBouncerK8sCharm.client_relations",
        new_callable=PropertyMock,
        return_value=sentinel.client_rels,
    )
    @patch("relations.backend_database.BackendDatabaseRequires.check_backend", return_value=True)
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
    @patch("charms.data_platform_libs.v0.data_interfaces.DatabaseProvides.set_read_only_endpoints")
    @patch("charms.data_platform_libs.v0.data_interfaces.DatabaseProvides.set_endpoints")
    @patch("relations.pgbouncer_provider.PgBouncerProvider.get_database", return_value="test-db")
    @patch("charms.data_platform_libs.v0.data_interfaces.DatabaseProvides.set_credentials")
    @patch("charms.data_platform_libs.v0.data_interfaces.DatabaseProvides.set_version")
    @patch(
        "charms.data_platform_libs.v0.data_interfaces.DatabaseProvides.fetch_my_relation_field",
        return_value="test_pass",
    )
    @patch("charm.PgBouncerK8sCharm.set_relation_databases")
    @patch("charm.PgBouncerK8sCharm.generate_relation_databases")
    @patch(
        "charm.PgBouncerK8sCharm.read_write_endpoints",
        new_callable=PropertyMock,
        return_value="host:port",
    )
    @patch(
        "charm.PgBouncerK8sCharm.read_only_endpoints",
        new_callable=PropertyMock,
        return_value="host:port",
    )
    def test_on_database_requested(
        self,
        _read_only_endpoints,
        _read_write_endpoints,
        _gen_rel_dbs,
        _set_rel_dbs,
        _dbp_fetch_my_relation_field,
        _dbp_set_version,
        _dbp_set_credentials,
        _get_database,
        _dbp_set_endpoints,
        _set_read_only_endpoints,
        _password,
        _auth_user,
        _pg_databag,
        _pg,
        _check_backend,
        _,
        _render_pgb_config,
        __,
    ):
        self.harness.set_leader()
        _gen_rel_dbs.return_value = {}

        event = MagicMock()
        rel_id = event.relation.id = self.client_rel_id
        database = event.database = "test-db"
        event.extra_user_roles = "SUPERUSER"
        user = f"relation_id_{rel_id}"
        with self.harness.hooks_disabled():
            self.harness.update_relation_data(rel_id, "application", {"database": "test-db"})
            self.harness.update_relation_data(
                self.peers_rel_id, self.app, {"pgb_dbs_config": "{}"}
            )

        # check we exit immediately if backend doesn't exist.
        _check_backend.return_value = False
        self.client_relation._on_database_requested(event)
        _pg.create_user.assert_not_called()

        _check_backend.return_value = True
        self.client_relation._on_database_requested(event)

        # Verify we've called everything we should
        _pg().create_user.assert_called_with(
            user,
            _password(),
            extra_user_roles=[role.lower() for role in event.extra_user_roles.split(",")]
            + ["relation_access"],
            database="test-db",
        )
        _pg().create_database.assert_called_with(database)
        _dbp_set_credentials.assert_called_with(rel_id, user, _password())
        _dbp_set_version.assert_called_with(rel_id, _pg().get_postgresql_version())
        _dbp_set_endpoints.assert_called_with(rel_id, "host:port")
        _set_read_only_endpoints.assert_called_with(rel_id, "host:port")
        _set_rel_dbs.assert_called_once_with({
            str(rel_id): {"name": "test-db", "legacy": False},
            "*": {"name": "*", "auth_dbname": "test-db", "legacy": False},
        })
        _render_pgb_config.assert_called_once_with()

    @patch("relations.backend_database.BackendDatabaseRequires.check_backend", return_value=True)
    @patch(
        "relations.backend_database.BackendDatabaseRequires.postgres", new_callable=PropertyMock
    )
    @patch("charm.PgBouncerK8sCharm.set_relation_databases")
    @patch("charm.PgBouncerK8sCharm.generate_relation_databases")
    @patch("charm.lightkube")
    def test_on_relation_broken(self, _lightkube, _gen_rel_dbs, _set_rel_dbs, _pg, _check_backend):
        _pg.return_value.get_postgresql_version.return_value = "10"
        _gen_rel_dbs.return_value = {"1": {"name": "test_db", "legacy": False}}
        self.harness.set_leader()

        event = MagicMock()
        rel_id = event.relation.id = 1
        external_app = self.charm.client_relation.get_external_app(event.relation)
        event.relation.app = external_app
        event.relation.data = {external_app: {"database": "test_db"}}
        user = f"relation_id_{rel_id}"

        self.client_relation._on_relation_broken(event)
        _pg().delete_user.assert_called_with(user)

        _set_rel_dbs.assert_called_once_with({})
