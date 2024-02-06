# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Postgres client relation hooks & helpers.

Importantly, this relation doesn't handle scaling the same way others do. All PgBouncer nodes are
read/writes, and they expose the read/write nodes of the backend database through the database name
f"{dbname}_readonly".

┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ relation (id: 4) ┃ application                                                                                   ┃ pgbouncer-k8s                                                                                  ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ relation name    │ first-database                                                                                │ database                                                                                       │
│ interface        │ postgresql_client                                                                             │ postgresql_client                                                                              │
│ leader unit      │ 0                                                                                             │ 1                                                                                              │
├──────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────┤
│ application data │ ╭───────────────────────────────────────────────────────────────────────────────────────────╮ │ ╭────────────────────────────────────────────────────────────────────────────────────────────╮ │
│                  │ │                                                                                           │ │ │                                                                                            │ │
│                  │ │  data              {"endpoints":                                                          │ │ │  data                 {"database": "application_first_database", "extra-user-roles":       │ │
│                  │ │                    "pgbouncer-k8s-1.pgbouncer-k8s-endpoints.test-pgbouncer-provider-5l5…  │ │ │                       "CREATEDB,CREATEROLE"}                                               │ │
│                  │ │                    "password": "2LDDKswhH5DdMvjEAZ9igVET", "read-only-endpoints":         │ │ │  endpoints            pgbouncer-k8s-1.pgbouncer-k8s-endpoints.test-pgbouncer-provider-5l…  │ │
│                  │ │                    "pgbouncer-k8s-2.pgbouncer-k8s-endpoints.test-pgbouncer-provider-5l5…  │ │ │  password             2LDDKswhH5DdMvjEAZ9igVET                                             │ │
│                  │ │                    "username": "relation_id_4", "version": "14.5"}                        │ │ │  read-only-endpoints  pgbouncer-k8s-2.pgbouncer-k8s-endpoints.test-pgbouncer-provider-5l…  │ │
│                  │ │  database          application_first_database                                             │ │ │  username             relation_id_4                                                        │ │
│                  │ │  extra-user-roles  CREATEDB,CREATEROLE                                                    │ │ │  version              14.5                                                                 │ │
│                  │ ╰───────────────────────────────────────────────────────────────────────────────────────────╯ │ ╰────────────────────────────────────────────────────────────────────────────────────────────╯ │
│ unit data        │ ╭─ application/0* ─╮ ╭─ application/1 ─╮                                                      │ ╭─ pgbouncer-k8s/0 ─╮ ╭─ pgbouncer-k8s/1* ─╮ ╭─ pgbouncer-k8s/2 ─╮                             │
│                  │ │ <empty>          │ │ <empty>         │                                                      │ │ <empty>           │ │ <empty>            │ │ <empty>           │                             │
│                  │ ╰──────────────────╯ ╰─────────────────╯                                                      │ ╰───────────────────╯ ╰────────────────────╯ ╰───────────────────╯                             │
└──────────────────┴───────────────────────────────────────────────────────────────────────────────────────────────┴────────────────────────────────────────────────────────────────────────────────────────────────┘
"""  # noqa: W505


import logging

from charms.data_platform_libs.v0.data_interfaces import (
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
from ops.charm import CharmBase, RelationBrokenEvent, RelationDepartedEvent
from ops.framework import Object
from ops.model import (
    ActiveStatus,
    Application,
    BlockedStatus,
    MaintenanceStatus,
)

from constants import CLIENT_RELATION_NAME

logger = logging.getLogger(__name__)


class PgBouncerProvider(Object):
    """Defines functionality for the 'provides' side of the 'postgresql-client' relation.

    Hook events observed:
        - database-requested
        - relation-broken
    """

    def __init__(self, charm: CharmBase, relation_name: str = CLIENT_RELATION_NAME) -> None:
        """Constructor for PgbouncerProvider object.

        Args:
            charm: the charm for which this relation is provided
            relation_name: the name of the relation
        """
        super().__init__(charm, relation_name)

        self.charm = charm
        self.relation_name = relation_name
        self.database_provides = DatabaseProvides(self.charm, relation_name=self.relation_name)

        self.framework.observe(
            self.database_provides.on.database_requested, self._on_database_requested
        )
        self.framework.observe(
            charm.on[self.relation_name].relation_departed, self._on_relation_departed
        )
        self.framework.observe(
            charm.on[self.relation_name].relation_broken, self._on_relation_broken
        )

    def _depart_flag(self, relation):
        return f"{self.relation_name}_{relation.id}_departing"

    def _unit_departing(self, relation):
        return self.charm.peers.unit_databag.get(self._depart_flag(relation), None) == "true"

    def _on_database_requested(self, event: DatabaseRequestedEvent) -> None:
        """Handle the client relation-requested event.

        Generate password and handle user and database creation for the related application.

        Deferrals:
            - If backend relation is not fully initialised
        """
        if not self.charm.unit.is_leader():
            return

        if not self.charm.backend.check_backend():
            event.defer()
            return

        # Retrieve the database name and extra user roles using the charm library.
        databases = event.database
        extra_user_roles = event.extra_user_roles or ""
        rel_id = event.relation.id

        # Creates the user and the database for this specific relation.
        user = f"relation_id_{rel_id}"
        logger.debug("generating relation user")
        password = pgb.generate_password()
        try:
            self.charm.backend.postgres.create_user(
                user, password, extra_user_roles=extra_user_roles
            )
            logger.debug("creating database")
            dblist = databases.split(",")
            for database in dblist:
                self.charm.backend.postgres.create_database(database, user)
            # set up auth function
            self.charm.backend.initialise_auth_function(dbs=dblist)
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

        self.charm.render_pgb_config(reload_pgbouncer=True)

        # Share the credentials and updated connection info with the client application.
        self.database_provides.set_credentials(rel_id, user, password)
        # Set the database name
        self.database_provides.set_database(rel_id, databases)
        self.update_connection_info(event.relation)

    def _on_relation_departed(self, event: RelationDepartedEvent) -> None:
        """Check if this relation is being removed, and update databags accordingly.

        If the leader is being removed, we check if this unit is departing. This occurs only on
        relation deletion, so we set a flag for the relation-broken hook to remove the relation.
        When scaling down, we don't set this flag and we just let the newly elected leader take
        control of the pgbouncer config.
        """
        self.update_connection_info(event.relation)

        # This only ever evaluates to true when the relation is being removed - on app scale-down,
        # depart events are only sent to the other application in the relation.
        if event.departing_unit == self.charm.unit:
            self.charm.peers.unit_databag.update({self._depart_flag(event.relation): "true"})

    def _on_relation_broken(self, event: RelationBrokenEvent) -> None:
        """Remove the user created for this relation, and revoke connection permissions."""
        self.update_connection_info(event.relation)
        if not self.charm.backend.check_backend() or not self.charm.unit.is_leader():
            return

        if self._unit_departing(event.relation):
            # This unit is being removed, so don't update the relation.
            self.charm.peers.unit_databag.pop(self._depart_flag(event.relation), None)
            return

        self.charm.render_pgb_config(reload_pgbouncer=True)

        # Delete the user.
        try:
            user = f"relation_id_{event.relation.id}"
            self.charm.backend.postgres.delete_user(user)
        except PostgreSQLDeleteUserError as e:
            logger.exception(e)
            self.charm.unit.status = BlockedStatus(
                f"Failed to delete user during {self.relation_name} relation broken event"
            )
            raise

    def update_connection_info(self, relation):
        """Updates client-facing relation information."""
        # Set the read/write endpoint.
        if not self.charm.unit.is_leader():
            return
        self.charm.unit.status = MaintenanceStatus(
            f"Updating {self.relation_name} relation connection information"
        )
        endpoint = f"{self.charm.leader_hostname}:{self.charm.config['listen_port']}"
        self.database_provides.set_endpoints(relation.id, endpoint)

        self.update_read_only_endpoints()

        # Set the database version.
        if self.charm.backend.check_backend():
            self.database_provides.set_version(
                relation.id, self.charm.backend.postgres.get_postgresql_version()
            )

        self.charm.unit.status = ActiveStatus()

    def update_read_only_endpoints(self, event: DatabaseRequestedEvent = None) -> None:
        """Set the read-only endpoint only if there are replicas."""
        if not self.charm.unit.is_leader():
            return

        # Get the current relation or all the relations if this is triggered by another type of
        # event.
        relations = [event.relation] if event else self.model.relations[self.relation_name]

        port = self.charm.config["listen_port"]
        hostnames = set(self.charm.peers.units_hostnames)
        hostnames.discard(self.charm.peers.leader_hostname)
        for relation in relations:
            self.database_provides.set_read_only_endpoints(
                relation.id,
                ",".join([f"{host}:{port}" for host in hostnames]),
            )

    def get_database(self, relation):
        """Gets database name from relation."""
        return relation.data.get(self.get_external_app(relation)).get("database", None)

    def get_external_app(self, relation):
        """Gets external application, as an Application object.

        Given a relation, this gets the first application object that isn't PGBouncer.

        TODO this is stolen from the db relation - cleanup
        """
        for entry in relation.data.keys():
            if isinstance(entry, Application) and entry != self.charm.app:
                return entry
