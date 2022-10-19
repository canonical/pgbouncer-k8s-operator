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
from ops.model import Application, BlockedStatus, WaitingStatus

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
        """Handle the client relation-requested event.

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
            return

        # set up auth function
        self.charm.backend.initialise_auth_function(dbname=database)

        # Create user in pgbouncer config
        cfg = self.charm.read_pgb_config()
        cfg.add_user(user, admin=True if "SUPERUSER" in extra_user_roles else False)

        # Update endpoints

        # In postgres, "endpoints" will only ever have one value. Other databases using the library
        # can have more, but that's not planned for the postgres charm.
        postgres_endpoint = self.charm.backend.postgres_databag.get("endpoints")
        cfg = self.charm.read_pgb_config()
        cfg["databases"][database] = {
            "host": postgres_endpoint.split(":")[0],
            "dbname": database,
            "port": postgres_endpoint.split(":")[1],
            "auth_user": self.charm.backend.auth_user,
        }

        # TODO should postgres scaling be handled by this relation? Ideally, in future (after pgb
        # version 1.17, therefore after the snap) this entry will point to multiple endpoints,
        # which will be automatically load balanced by default. Incidentally, this _standby suffix
        # should therefore be removed.
        read_only_endpoint = self._get_read_only_endpoint()
        if read_only_endpoint:
            cfg["databases"][f"{database}_standby"] = {
                "host": read_only_endpoint.split(":")[0],
                "dbname": database,
                "port": read_only_endpoint.split(":")[1],
                "auth_user": self.charm.backend.auth_user,
            }
        else:
            cfg["databases"].pop(f"{database}_standby", None)
        # Write config data to charm filesystem
        self.charm.render_pgb_config(cfg, reload_pgbouncer=True)

    def _on_relation_broken(self, event: RelationBrokenEvent) -> None:
        """Remove the user created for this relation, and revoke connection permissions."""
        if not self.charm.backend.postgres:
            # We can't relate an app to the backend database without a backend postgres relation
            wait_str = "waiting for backend-database relation to connect"
            logger.warning(wait_str)
            self.charm.unit.status = WaitingStatus(wait_str)
            event.defer()
            return

        if not self.charm.unit.is_leader():
            return

        cfg = self.charm.read_pgb_config()
        database = event.relation.data[self.get_external_app(event.relation)].get("database")
        cfg["databases"].pop(database, None)
        cfg["databases"].pop(f"{database}_standby", None)
        user = f"relation_id_{event.relation.id}"
        cfg.remove_user(user)
        self.charm.render_pgb_config(cfg, reload_pgbouncer=True)

        # Delete the user.
        try:
            self.charm.backend.postgres.delete_user(user)
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

    def _get_read_only_endpoint(self):
        """Get a read-only-endpoint from backend relation.

        Though multiple readonly endpoints can be provided by the new backend relation, only one
        can be consumed by this legacy relation.

        TODO this is copy-pasted from the db relation, clean it up a bit.
        """
        read_only_endpoints = self.charm.backend.postgres_databag.get("read-only-endpoints")
        if read_only_endpoints is None or len(read_only_endpoints) == 0:
            return None
        return read_only_endpoints.split(",")[0]

    def get_external_app(self, relation):
        """Gets external application, as an Application object.

        TODO this is stolen from the db relation - cleanup
        """
        for entry in relation.data.keys():
            if isinstance(entry, Application) and entry != self.charm.app:
                return entry
