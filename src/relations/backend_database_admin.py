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

from charms.pgbouncer_operator.v0 import pgb
from charms.pgbouncer_operator.v0.pgb import PgbConfig
from charms.data_platform_libs.v0.database_requires import DatabaseRequires, DatabaseCreatedEvent
from ops.charm import (
    CharmBase,
    RelationBrokenEvent,
    RelationChangedEvent,
    RelationDepartedEvent,
)
from ops.framework import Object
from ops.model import Unit


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

        self.framework.observe(charm.on[RELATION_NAME].relation_changed, self._on_relation_changed)
        self.framework.observe(charm.on[RELATION_NAME].relation_departed, self._on_relation_departed)
        self.framework.observe(charm.on[RELATION_NAME].relation_broken, self._on_relation_broken)

        self.database = DatabaseRequires(self, relation_name=RELATION_NAME, database_name="postgresql")
        self.charm = charm
        self.framework.observe(self.database.on.database_created, self._on_database_created)

    def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
        config_file = self._render_app_config_file(
            event.username,
            event.password,
            event.endpoints,
        )
        # Start application with rendered configuration
        self._start_application(config_file)
        # Set active status
        self.unit.status = ActiveStatus("received database credentials")

    def _on_relation_changed(self, change_event: RelationChangedEvent):
        """Handle backend-database-admin-relation-changed event.

        Takes leader and standby information from the postgresql leader unit databag and copies it
        into the pgbouncer.ini config, removing redundant standby information along the way.
        """

    def _on_relation_departed(self, departed_event: RelationDepartedEvent):
        """Handle backend-db-admin-relation-departed event.

        Removes unit information from pgbouncer config when a unit is removed.

        TODO since the relation-changed hook updates master and standbys, is this hook still
        relevant? Experiment once integration tests are implemented.
        """

    def _on_relation_broken(self, broken_event: RelationBrokenEvent):
        """Handle backend-db-admin-relation-broken event.

        Removes all traces of this relation from pgbouncer config.
        """
