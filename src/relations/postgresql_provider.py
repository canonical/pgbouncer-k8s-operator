# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Postgres client relation hooks & helpers."""


import logging

from charms.data_platform_libs.v0.database_provides import (
    DatabaseProvides,
    DatabaseRequestedEvent,
)
from charms.pgbouncer_k8s.v0 import pgb
from charms.postgresql_k8s.v0.postgresql import (
    PostgreSQLCreateDatabaseError,
    PostgreSQLCreateUserError,
    PostgreSQLDeleteUserError,
    PostgreSQLGetPostgreSQLVersionError,
)
from ops.charm import CharmBase, RelationBrokenEvent
from ops.framework import Object
from ops.model import BlockedStatus, WaitingStatus

logger = logging.getLogger(__name__)


"""TODO:
- Add checks for backend relation
- add connections to backend relation
"""


class PostgreSQLProvider(Object):
    """Defines functionality for the 'provides' side of the 'postgresql-client' relation.

    Hook events observed:
        - database-requested
        - relation-broken
    """

    def __init__(self, charm: CharmBase, relation_name: str = "database") -> None:
        """Constructor for PostgreSQLClientProvides object.

        Args:
            charm: the charm for which this relation is provided
            relation_name: the name of the relation
        """
        self.relation_name = relation_name

        super().__init__(charm, self.relation_name)
        self.framework.observe(
            charm.on[self.relation_name].relation_broken, self._on_relation_broken
        )

        self.charm = charm

        # Charm events defined in the database provides charm library.
        self.database_provides = DatabaseProvides(self.charm, relation_name=self.relation_name)
        self.framework.observe(
            self.database_provides.on.database_requested, self._on_database_requested
        )

    def _on_database_requested(self, event: DatabaseRequestedEvent) -> None:
        """Handle the legacy postgresql-client relation changed event.

        Generate password and handle user and database creation for the related application.
        """
        if not self.charm.backend.postgres:
            # We can't relate an app to the backend database without a backend postgres relation
            wait_str = "waiting for backend-database relation to connect"
            logger.warning(wait_str)
            self.charm.unit.status = WaitingStatus(wait_str)
            event.defer()
            return

        if not self.charm.unit.is_leader():
            return

        # Retrieve the database name and extra user roles using the charm library.
        database = event.database
        extra_user_roles = event.extra_user_roles

        try:
            # Creates the user and the database for this specific relation.
            user = f"relation_id_{event.relation.id}"
            password = pgb.generate_password()
            self.charm.backend.postgres.create_user(
                user, password, extra_user_roles=extra_user_roles
            )
            self.charm.peers.add_user(user, password)
            self.charm.backend.postgres.create_database(database, user)

            # Share the credentials with the application.
            self.database_provides.set_credentials(event.relation.id, user, password)

            # Set the read/write endpoint.
            self.database_provides.set_endpoints(
                event.relation.id,
                f"{self.charm.primary_endpoint}:{self.charm.config['listen_port']}",
            )

            # Update the read-only endpoint.
            self.update_read_only_endpoint(event)

            # Set the database version.
            self.database_provides.set_version(
                event.relation.id, self.charm.backend.postgres.get_postgresql_version()
            )
        except (
            PostgreSQLCreateDatabaseError,
            PostgreSQLCreateUserError,
            PostgreSQLGetPostgreSQLVersionError,
        ) as e:
            logger.exception(e)
            self.charm.unit.status = BlockedStatus(
                f"Failed to initialize {self.relation_name} relation"
            )

    def _on_relation_broken(self, event: RelationBrokenEvent) -> None:
        """Remove the user created for this relation."""
        # Check for some conditions before trying to access the PostgreSQL instance.
        if not self.charm.backend.postgres:
            # We can't relate an app to the backend database without a backend postgres relation
            wait_str = "waiting for backend-database relation to connect"
            logger.warning(wait_str)
            self.charm.unit.status = WaitingStatus(wait_str)
            event.defer()
            return

        if not self.charm.unit.is_leader():
            return

        # Delete the user.
        user = f"relation_id_{event.relation.id}"
        try:
            self.charm.postgresql.delete_user(user)
        except PostgreSQLDeleteUserError as e:
            logger.exception(e)
            self.charm.unit.status = BlockedStatus(
                f"Failed to delete user during {self.relation_name} relation broken event"
            )

    def update_read_only_endpoint(self, event: DatabaseRequestedEvent = None) -> None:
        """Set the read-only endpoint only if there are replicas."""
        if not self.charm.unit.is_leader():
            return

        # If there are no replicas, remove the read-only endpoint.
        endpoints = (
            f"{self.charm.replicas_endpoint}:{self.charm.config['listen_port']}"
            if len(self.charm._peers.units) > 0
            else ""
        )

        # Get the current relation or all the relations
        # if this is triggered by another type of event.
        relations = [event.relation] if event else self.model.relations[self.relation_name]

        for relation in relations:
            self.database_provides.set_read_only_endpoints(
                relation.id,
                endpoints,
            )