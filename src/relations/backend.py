# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Postgres backend-db-admin relation hooks & helpers.

This relation uses the pgsql interface.

Some example relation data is below. The only parts of this we actually need are the "master" and
"standbys" fields. All values are examples taken from a test deployment, and are not definite.

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

from charms.data_platform_libs.v0.database_requires import (
    DatabaseCreatedEvent,
    DatabaseRequires,
)
from ops.charm import CharmBase, RelationBrokenEvent
from ops.framework import Object

RELATION_NAME = "backend-database-admin"


class BackendRequires(Object):
    """Defines functionality for the 'requires' side of the 'backend' relation.

    Hook events observed:
        - relation-changed
        - relation-departed
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
        """Handle backend-database-created event.

        Accesses user and password generated by the postgres charm and adds a user.
        """
        cfg = self.charm.read_pgb_config()
        self.charm.add_user(
            user=event.username,
            cfg=cfg,
            password=event.password,
            admin=True,
            reload_pgbouncer=True,
            render_cfg=True,
        )

    def _on_relation_broken(self, event: RelationBrokenEvent):
        """Handle backend-relation-broken event.

        Removes all traces of this relation from pgbouncer config.
        """
        cfg = self.charm.read_pgb_config()
        user = self.charm.backend_postgres.user
        self.charm.remove_user(user, cfg=cfg, reload_pgbouncer=True, render_cfg=True)
