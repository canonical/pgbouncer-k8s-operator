# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Pgbouncer backend-database relation hooks & helpers.

This relation expects that usernames and passwords are generated and provided by the PostgreSQL
charm.

Some example relation data is below. The only parts of this we actually need are the "endpoints"
and "read-only-endpoints" fields. All values are examples taken from a test deployment, and are
not definite.

Example:
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ category         ┃             keys ┃ pgbouncer-k8s-o… ┃ postgresql-k8s/0 ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ metadata         │         endpoint │ 'backend-databa… │ 'database'       │
│                  │           leader │ True             │ True             │
├──────────────────┼──────────────────┼──────────────────┼──────────────────┤
│ application data │             data │ {"endpoints":    │ {"database":     │
│                  │                  │ "postgresql-k8s… │ "postgresql",    │
│                  │                  │ "password":      │ "extra-user-rol… │
│                  │                  │ "18cqKCp19xOPBh… │ "SUPERUSER"}     │
│                  │                  │ "read-only-endp… │                  │
│                  │                  │ "postgresql-k8s… │                  │
│                  │                  │ "username":      │                  │
│                  │                  │ "relation_id_18… │                  │
│                  │                  │ "version":       │                  │
│                  │                  │ "12.9"}          │                  │
│                  │         database │ pgbouncer        │                  │
│                  │        endpoints │                  │ postgresql-k8s-… │
│                  │ extra-user-roles │ SUPERUSER        │                  │
│                  │         password │                  │ 18cqKCp19xOPBhk9 │
│                  │ read-only-endpo… │                  │ postgresql-k8s-… │
│                  │         username │                  │ relation_id_18   │
│                  │          version │                  │ 12.9             │
└──────────────────┴──────────────────┴──────────────────┴──────────────────┘
"""

import logging
from typing import Dict

import psycopg2
from charms.data_platform_libs.v0.database_requires import (
    DatabaseCreatedEvent,
    DatabaseRequires,
)
from charms.pgbouncer_k8s.v0 import pgb
from charms.postgresql_k8s.v0.postgresql import PostgreSQL
from ops.charm import CharmBase, RelationDepartedEvent, RelationBrokenEvent
from ops.framework import Object
from ops.model import Application, BlockedStatus, Relation

RELATION_NAME = "backend-database"
PGB_DIR = "/var/lib/postgresql/pgbouncer"
PGB_DB = "pgbouncer"
USERLIST_PATH = f"{PGB_DIR}/userlist.txt"


logger = logging.getLogger(__name__)


class BackendDatabaseRequires(Object):
    """Defines functionality for the 'requires' side of the 'backend-database' relation.

    The data created in this relation allows the pgbouncer charm to connect to the postgres charm.

    Hook events observed:
        - database-created
        - database-endpoints-changed
        - database-read-only-endpoints-changed
        - relation-departed
        - relation-broken
    """

    def __init__(self, charm: CharmBase):
        super().__init__(charm, RELATION_NAME)

        self.charm = charm
        self.database = DatabaseRequires(
            self.charm,
            relation_name=RELATION_NAME,
            database_name=PGB_DB,
            extra_user_roles="SUPERUSER",
        )

        self.framework.observe(self.database.on.database_created, self._on_database_created)
        self.framework.observe(self.database.on.endpoints_changed, self._on_endpoints_changed)
        self.framework.observe(
            self.database.on.read_only_endpoints_changed, self._on_endpoints_changed
        )
        self.framework.observe(charm.on[RELATION_NAME].relation_broken, self._on_relation_broken)

    def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
        """Handle backend-database-database-created event.

        Accesses user and password generated by the postgres charm and adds a user.
        """
        logger.info("initialising postgres and pgbouncer relations")
        if not self.charm.unit.is_leader():
            return

        if self.postgres is None:
            event.defer()
            logging.error("deferring database-created hook - postgres database not ready")
            return

        plaintext_password = pgb.generate_password()
        # create authentication user on postgres database, so we can authenticate other users
        # later on
        self.postgres.create_user(self.auth_user, plaintext_password, admin=True)
        self.initialise_auth_function(dbname=self.database.database)

        hashed_password = pgb.get_hashed_password(self.auth_user, plaintext_password)
        self.charm.push_file(
            f"{PGB_DIR}/userlist.txt", f'"{self.auth_user}" "{hashed_password}"', perms=0o400
        )
        cfg = self.charm.read_pgb_config()
        # adds user to pgb config
        cfg.add_user(user=event.username, admin=True)
        cfg["pgbouncer"][
            "auth_query"
        ] = f"SELECT username, password FROM {self.auth_user}.get_auth($1)"
        cfg["pgbouncer"]["auth_file"] = f"{PGB_DIR}/userlist.txt"
        self.charm.render_pgb_config(cfg)

        self.charm.update_postgres_endpoints(reload_pgbouncer=True)

    def _on_endpoints_changed(self, _):
        self.charm.update_postgres_endpoints(reload_pgbouncer=True)

    def _on_relation_departed(self, event: RelationDepartedEvent):
        """Runs pgbouncer-uninstall.sql and removes auth user.

        pgbouncer-uninstall doesn't actually uninstall anything - it actually removes permissions
        for the auth user.
        """
        if event.departing_unit != self.charm.unit or not self.charm.unit.is_leader():
            return

        logger.info("removing auth user")

        uninstall_script = open("src/relations/sql/pgbouncer-uninstall.sql", "r").read()

        try:
            with self.postgres.connect_to_database(PGB_DB) as conn, conn.cursor() as cursor:
                cursor.execute(uninstall_script.replace("auth_user", self.auth_user))
            conn.close()
        except psycopg2.Error:
            self.charm.unit.status = BlockedStatus(
                "failed to remove auth user when disconnecting from postgres application."
            )
            return

        self.postgres.delete_user(self.auth_user)

        logger.info("auth user removed")

    def _on_relation_broken(self, event: RelationBrokenEvent):
        """Handle backend-database-relation-broken event.

        Removes all traces of this relation from pgbouncer config.
        """
        try:
            cfg = self.charm.read_pgb_config()
        except FileNotFoundError:
            event.defer()
            return

        cfg.remove_user(self.postgres.user)
        cfg["pgbouncer"].pop("auth_user", None)
        cfg["pgbouncer"].pop("auth_query", None)
        self.charm.render_pgb_config(cfg)

        self.charm.delete_file(f"{PGB_DIR}/userlist.txt")

    def initialise_auth_function(self, dbname=PGB_DB):
        """Runs an SQL script to initialise the auth function.

        This function must run in every database for authentication to work correctly, and assumes
        self.postgres is set up correctly.

        Args:
            dbname: the name of the database to connect to.

        Raises:
            psycopg2.Error if self.postgres isn't usable.
        """
        logger.info("initialising auth function")

        install_script = open("src/relations/sql/pgbouncer-install.sql", "r").read()

        with self.postgres.connect_to_database(dbname) as conn, conn.cursor() as cursor:
            cursor.execute(install_script.replace("auth_user", self.auth_user))
        conn.close()
        logger.info("auth function initialised")

    @property
    def relation(self) -> Relation:
        """Relation object for postgres backend-database relation."""
        backend_relation = self.model.get_relation(RELATION_NAME)
        if not backend_relation:
            return None
        else:
            return backend_relation

    @property
    def postgres(self) -> PostgreSQL:
        """Returns PostgreSQL representation of backend database, as defined in relation.

        Returns None if backend relation is not fully initialised.
        """
        if not self.relation:
            return None

        databag = self.postgres_databag
        endpoint = databag.get("endpoints")
        user = databag.get("username")
        password = databag.get("password")
        database = self.database.database

        if None in [endpoint, user, password, database]:
            return None

        return PostgreSQL(
            host=endpoint.split(":")[0], user=user, password=password, database=database
        )

    @property
    def auth_user(self):
        """Username for auth_user."""
        username = self.postgres_databag.get("username")
        if username is None:
            return None

        return f"pgbouncer_auth_{username}"

    @property
    def postgres_databag(self) -> Dict:
        """Wrapper around accessing the remote application databag for the backend relation.

        Returns None if relation is none.

        Since we can trigger db-relation-changed on backend-changed, we need to be able to easily
        access the backend app relation databag.
        """
        if self.relation:
            for key, databag in self.relation.data.items():
                if isinstance(key, Application) and key != self.charm.app:
                    return databag
        return None
