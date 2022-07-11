# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Postgres backend-db-admin relation hooks & helpers.

This relation uses the pgsql interface.

Some example relation data is below. The only parts of this we actually need are the "master" and
"standbys" fields. All values are examples taken from a test deployment, and are not definite.

Example with 2 postgresql instances:
TODO add examples
"""

import logging
from typing import List

from charms.data_platform_libs.v0.database_requires import (
    DatabaseCreatedEvent,
    DatabaseRequires,
)
from charms.pgbouncer_operator.v0 import pgb
from charms.pgbouncer_operator.v0.pgb import PgbConfig
from ops.charm import (
    CharmBase,
    RelationBrokenEvent,
    RelationChangedEvent,
    RelationDepartedEvent,
)
from ops.framework import Object
from ops.model import Unit

from lib.charms.data_platform_libs.v0.database_requires import (
    DatabaseCreatedEvent,
    DatabaseEndpointsChangedEvent,
    DatabaseReadOnlyEndpointsChangedEvent,
)

logger = logging.getLogger(__name__)
RELATION_NAME = "backend-database-admin"


class BackendDatabaseAdminRequires(Object):
    """Defines functionality for the 'requires' side of the 'backend-db-admin' relation.

    Hook events observed:
        - relation-changed
        - relation-departed
        - relation-broken
    """

    def __init__(self, charm: CharmBase):
        super().__init__(charm, RELATION_NAME)

        self.charm = charm
        self.database = DatabaseRequires(
            self.charm, relation_name=RELATION_NAME, database_name="postgresql"
        )

        self.framework.observe(self.database.on.database_created, self._on_database_created)
        self.framework.observe(self.database.on.endpoints_changed, self._on_endpoints_changed)
        self.framework.observe(
            self.database.on.read_only_endpoints_changed, self._on_read_only_endpoints_changed
        )

        self.framework.observe(charm.on[RELATION_NAME].relation_broken, self._on_relation_broken)

    def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
        cfg = self.charm._read_pgb_config()
        user = self.generate_username(event, event.relation)
        password = pgb.generate_password()
        # TODO write these data to the databag

        self.charm.blah
        self.charm.

        self.charm.add_user(user, password=password, admin=True, cfg=cfg, reload_pgbouncer=True, render_cfg=True)

    def generate_username(self, event, app_name):
        """Generates a username for this relation."""
        return f"{self.relation_name}_{event.relation.id}_{app_name}".replace('-', '_')

    def _on_endpoints_changed(self, event: DatabaseEndpointsChangedEvent):
        """Handle DatabaseRequires.database_endpoints_changed event.

        This event updates when the primary unit of the backend postgres database changes,
        updating the main postgres replica. This hook updates the locations of each database
        stored on this backend.
        """
        # TODO I want to keep track of how this changes, but if there's a default handler I'm happy
        # to use that

    def _on_read_only_endpoints_changed(self, event: DatabaseReadOnlyEndpointsChangedEvent):
        """Handle DatabaseRequires.database_readonly_endpoints_changed event.

        This event updates when the secondary units of the backend postgres database change,
        updating the spare readonly postgres replicas. This hook updates the locations of each
        database stored on these backend units.
        """
        # TODO I want to keep track of how this changes, but if there's a default handler I'm happy
        # to use that

    def _on_relation_broken(self, broken_event: RelationBrokenEvent):
        """Handle backend-db-admin-relation-broken event.

        Removes all traces of this relation from pgbouncer config.
        """
        user = broken_event.relation.data[self.charm.app].get("username")
        self.charm.remove_user(user, reload_pgbouncer=True)
