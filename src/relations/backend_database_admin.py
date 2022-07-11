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

        config_file = self._render_app_config_file(
            event.username,
            event.password,
            event.endpoints,
        )

    def _on_endpoints_changed(self, event: DatabaseEndpointsChangedEvent):
        """Handle DatabaseRequires.database_endpoints_changed event.

        This event updates when the primary unit of the backend postgres database changes,
        updating the main postgres replica. This hook updates the locations of each database
        stored on this backend.
        """

    def _on_read_only_endpoints_changed(self, event: DatabaseReadOnlyEndpointsChangedEvent):
        """Handle DatabaseRequires.database_readonly_endpoints_changed event.

        This event updates when the secondary units of the backend postgres database change,
        updating the spare readonly postgres replicas. This hook updates the locations of each
        database stored on these backend units.
        """

    def _on_relation_broken(self, broken_event: RelationBrokenEvent):
        """Handle backend-db-admin-relation-broken event.

        Removes all traces of this relation from pgbouncer config.
        """
