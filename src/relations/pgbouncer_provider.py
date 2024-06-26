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
    Application,
    BlockedStatus,
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

    def external_connectivity(self, event=None) -> bool:
        """Whether any of the relations are marked as external."""
        # New list to avoid modifying the original
        relations = list(self.model.relations[self.relation_name])
        if (
            event
            and type(event) in [RelationBrokenEvent, RelationDepartedEvent]
            and event.relation in relations
        ):
            # Disregard of what has been requested by the client, this relation is being removed
            relations.remove(event.relation)

        # Now, we will return true if any of the relations are marked as external
        return any(
            relation.data.get(relation.app, {}).get("external-node-connectivity", "false")
            == "true"
            for relation in relations
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
        database = event.database
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
            self.charm.backend.postgres.create_database(
                database, user, client_relations=self.charm.client_relations
            )
            # set up auth function
            self.charm.backend.remove_auth_function(dbs=[database])
            self.charm.backend.initialise_auth_function(dbs=[database])
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

        dbs = self.charm.generate_relation_databases()
        dbs[str(event.relation.id)] = {"name": database, "legacy": False}
        roles = extra_user_roles.lower().split(",")
        if "admin" in roles or "superuser" in roles:
            dbs["*"] = {"name": "*", "auth_dbname": database}
        self.charm.set_relation_databases(dbs)

        # Share the credentials and updated connection info with the client application.
        self.database_provides.set_credentials(rel_id, user, password)
        # Set the database name
        self.database_provides.set_database(rel_id, database)

        self.charm.patch_port(self.external_connectivity(event))
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

        dbs = self.charm.get_relation_databases()
        database = dbs.pop(str(event.relation.id), {}).get("name")
        self.charm.set_relation_databases(dbs)

        delete_db = database not in [db["name"] for db in dbs.values()]
        if database and delete_db:
            self.charm.backend.remove_auth_function(dbs=[database])
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
        # Check if we need to close the node port
        self.charm.patch_port(self.external_connectivity(event))

    def update_connection_info(self, relation):
        """Updates client-facing relation information."""
        if not self.charm.unit.is_leader():
            return

        self.update_endpoints(relation)

        # Set the database version.
        if self.charm.backend.check_backend():
            self.database_provides.set_version(
                relation.id, self.charm.backend.postgres.get_postgresql_version()
            )

    def update_endpoints(self, relation=None) -> None:
        """Set the endpoints for the relation."""
        nodeports = self.charm.get_node_ports
        internal_port = self.charm.config["listen_port"]
        internal_hostnames = sorted(set(self.charm.peers.units_hostnames))
        if self.charm.peers.leader_hostname in internal_hostnames:
            internal_hostnames.remove(self.charm.peers.leader_hostname)
        internal_rw = f"{self.charm.leader_hostname}:{self.charm.config['listen_port']}"

        relations = [relation] if relation else self.model.relations[self.relation_name]

        # Set the endpoints for each relation.
        for relation in relations:
            if not relation or not relation.data or not relation.data.get(relation.app):
                # This is a relation that is going away and finds itself in a broken state
                # proceed to the next relation
                continue
            # Read-write endpoint
            if relation.data[relation.app].get("external-node-connectivity", "false") == "true":
                self.database_provides.set_endpoints(relation.id, nodeports["rw"])
                self.database_provides.set_read_only_endpoints(relation.id, nodeports["ro"])
            else:
                self.database_provides.set_endpoints(relation.id, internal_rw)
                self.database_provides.set_read_only_endpoints(
                    relation.id,
                    ",".join([f"{host}:{internal_port}" for host in internal_hostnames]),
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
