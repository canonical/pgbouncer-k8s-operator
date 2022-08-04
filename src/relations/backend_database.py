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
│                  │         database │ postgresql       │                  │
│                  │        endpoints │                  │ postgresql-k8s-… │
│                  │ extra-user-roles │ SUPERUSER        │                  │
│                  │         password │                  │ 18cqKCp19xOPBhk9 │
│                  │ read-only-endpo… │                  │ postgresql-k8s-… │
│                  │         username │                  │ relation_id_18   │
│                  │          version │                  │ 12.9             │
└──────────────────┴──────────────────┴──────────────────┴──────────────────┘
"""

import logging

from charms.data_platform_libs.v0.database_requires import (
    DatabaseCreatedEvent,
    DatabaseEndpointsChangedEvent,
    DatabaseReadOnlyEndpointsChangedEvent,
    DatabaseRequires,
)
from charms.pgbouncer_operator.v0 import pgb
from ops.charm import CharmBase, RelationBrokenEvent
from ops.framework import Object

RELATION_NAME = "backend-database"
PGB_DIR = "/var/lib/postgresql/pgbouncer"
USERLIST_PATH = f"{PGB_DIR}/userlist.txt"


logger = logging.getLogger(__name__)


class BackendDatabaseRequires(Object):
    """Defines functionality for the 'requires' side of the 'backend-database' relation.

    The data created in this relation allows the pgbouncer charm to connect to the postgres charm.

    Hook events observed:
        - database-created
        - database-endpoints-changed
        - database-read-only-endpoints-changed
        - relation-broken
    """

    def __init__(self, charm: CharmBase):
        super().__init__(charm, RELATION_NAME)

        self.charm = charm
        self.database = DatabaseRequires(
            self.charm,
            relation_name=RELATION_NAME,
            database_name="postgresql",
            extra_user_roles="SUPERUSER",
        )

        self.framework.observe(self.database.on.database_created, self._on_database_created)
        self.framework.observe(charm.on[RELATION_NAME].relation_broken, self._on_relation_broken)

    def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
        """Handle backend-database-database-created event.

        Accesses user and password generated by the postgres charm and adds a user.
        """
        logger.info("initialising postgres and pgbouncer relations")
        cfg = self.charm.read_pgb_config()
        cfg.add_user(user=event.username, admin=True)
        # TODO maybe don't reload if we're updating endpoints
        self.charm._render_pgb_config(cfg, reload_pgbouncer=True)

        self.init_auth_user()

        # TODO this doesn't do anything yet. Get endpoints from relation
        self.charm.update_postgres_endpoints()

    def _on_endpoints_changed(self, event: DatabaseEndpointsChangedEvent):
        # TODO this doesn't do anything yet. Get endpoints from relation
        self.charm.update_postgres_endpoints()

    def _on_read_only_endpoints_changed(self, event: DatabaseReadOnlyEndpointsChangedEvent):
        # TODO this doesn't do anything yet. Get endpoints from relation
        self.charm.update_postgres_endpoints()

    def _on_relation_broken(self, event: RelationBrokenEvent):
        """Handle backend-database-relation-broken event.

        Removes all traces of this relation from pgbouncer config.
        """
        # from pdb import set_trace; set_trace()
        self.remove_auth_user()

        cfg = self.charm.read_pgb_config()
        cfg.remove_user(self.charm.backend_postgres.user)
        # TODO maybe don't reload if we're updating endpoints
        self.charm._render_pgb_config(cfg, reload_pgbouncer=True)

        # TODO this doesn't update the endpoints yet, because they're only updated when this
        # hook ends.
        self.charm.update_postgres_endpoints()

    def init_auth_user(self):
        logger.info("initialising auth user")
        with self.charm.backend_postgres.connect_to_database() as conn, conn.cursor() as cursor:
            # TODO prepend a unique username to this file
            sql_file = open("src/relations/pgbouncer-install.sql", "r")
            cursor.execute(sql_file.read())
        conn.close()
        logger.info("auth user created")

        cfg = self.charm.read_pgb_config()
        cfg["pgbouncer"][
            "auth_user"
        ] = "pgbouncer"  # defined in src/relations/pgbouncer-install.sql
        cfg["pgbouncer"]["auth_query"] = "SELECT username, password FROM pgbouncer.get_auth($1)"
        self.charm._render_pgb_config(cfg, reload_pgbouncer=True)

    def remove_auth_user(self):
        # TODO this part has to run before postgresql relation-broken hook
        # logger.info("removing auth user")
        # with self.charm.backend_postgres.connect_to_database() as conn, conn.cursor() as cursor:
        #     # TODO prepend a unique username to this file
        #     sql_file = open("src/relations/pgbouncer-uninstall.sql", "r")
        #     cursor.execute(sql_file.read())
        # conn.close()
        # logger.info("auth user removed")

        cfg = self.charm.read_pgb_config()
        # TODO pop these instead.
        del cfg["pgbouncer"]["auth_user"]
        del cfg["pgbouncer"]["auth_query"]
        self.charm._render_pgb_config(cfg, reload_pgbouncer=True)
