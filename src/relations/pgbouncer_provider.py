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
"""

import logging
from hashlib import shake_128

from charms.data_platform_libs.v0.data_interfaces import (
    DatabaseProvides,
    DatabaseRequestedEvent,
)
from charms.pgbouncer_k8s.v0 import pgb
from charms.postgresql_k8s.v0.postgresql import (
    PERMISSIONS_GROUP_ADMIN,
)
from charms.postgresql_k8s.v0.postgresql import PostgreSQL as PostgreSQLv0
from ops.charm import CharmBase, RelationBrokenEvent, RelationDepartedEvent
from ops.framework import Object
from ops.model import Application, BlockedStatus
from single_kernel_postgresql.utils.postgresql import (
    ACCESS_GROUP_RELATION,
    PostgreSQLCreateDatabaseError,
    PostgreSQLCreateUserError,
    PostgreSQLDeleteUserError,
    PostgreSQLEnableDisableExtensionError,
    PostgreSQLGetPostgreSQLVersionError,
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

    @staticmethod
    def sanitize_extra_roles(extra_roles: str | None) -> list[str]:
        """Standardize and sanitize user extra-roles."""
        if extra_roles is None:
            return []

        return [role.lower() for role in extra_roles.split(",")]

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

        if not self.charm.backend.check_backend() or not self.charm.read_write_endpoints:
            event.defer()
            return

        # Retrieve the database name and extra user roles using the charm library.
        database = event.database
        rel_id = event.relation.id

        # Make sure that certain groups are not in the list
        extra_user_roles = self.sanitize_extra_roles(event.extra_user_roles)
        extra_user_roles.append(ACCESS_GROUP_RELATION)

        dbs = self.charm.generate_relation_databases()
        dbs[str(rel_id)] = {"name": database, "legacy": False}
        if (
            PERMISSIONS_GROUP_ADMIN in extra_user_roles
            or "superuser" in extra_user_roles
            or "createdb" in extra_user_roles
            or "charmed_admin" in extra_user_roles
            or "charmed_backup" in extra_user_roles
            or "charmed_databases_owner" in extra_user_roles
            or "charmed_dba" in extra_user_roles
            or "charmed_dml" in extra_user_roles
            or "charmed_read" in extra_user_roles
            or "charmed_stats" in extra_user_roles
        ):
            dbs["*"] = {"name": "*", "auth_dbname": database, "legacy": False}

        self.charm.set_relation_databases(dbs)

        pgb_dbs_hash = shake_128(
            self.charm.peers.app_databag["pgb_dbs_config"].encode()
        ).hexdigest(16)
        for key in self.charm.peers.relation.data:
            # We skip the leader so we don't have to wait on the defer
            if (
                key != self.charm.app
                and key != self.charm.unit
                and self.charm.peers.relation.data[key].get("pgb_dbs", "") != pgb_dbs_hash
            ):
                logger.debug("Not all units have synced configuration")
                event.defer()
                return

        # Creates the user and the database for this specific relation.
        user = f"relation_id_{rel_id}"
        logger.debug("generating relation user")
        password = pgb.generate_password()
        try:
            if isinstance(self.charm.backend.postgres, PostgreSQLv0):
                self.charm.backend.postgres.create_user(
                    user, password, extra_user_roles=extra_user_roles
                )
                logger.debug("creating database")
                self.charm.backend.postgres.create_database(
                    database, user, client_relations=self.charm.client_relations
                )
            else:
                logger.debug("creating database")
                self.charm.backend.postgres.create_database(database)
                self.charm.backend.postgres.create_user(
                    user, password, extra_user_roles=extra_user_roles, database=database
                )
            # set up auth function
            self.charm.backend.remove_auth_function(dbs=[database])
            self.charm.backend.initialise_auth_function(dbs=[database])
        except (
            PostgreSQLCreateDatabaseError,
            PostgreSQLCreateUserError,
            PostgreSQLGetPostgreSQLVersionError,
            PostgreSQLEnableDisableExtensionError,
        ) as e:
            self.charm.unit.status = BlockedStatus(
                e.message
                if (
                    isinstance(e, PostgreSQLCreateDatabaseError)
                    or isinstance(e, PostgreSQLCreateUserError)
                )
                and e.message is not None
                else f"Failed to initialize relation {self.relation_name}"
            )
            return

        self.charm.render_pgb_config()

        self.charm.backend.sync_hba(user)

        # Share the credentials and updated connection info with the client application.
        self.database_provides.set_credentials(rel_id, user, password)
        # Set the database name
        self.database_provides.set_database(rel_id, database)
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
        if event.departing_unit == self.charm.unit and self.charm.peers.unit_databag:
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

    def update_connection_info(self, relation):
        """Updates client-facing relation information."""
        if not self.charm.unit.is_leader() or not self.charm.configuration_check():
            return

        self.update_endpoints(relation)

        # Set the database version.
        if (
            self.database_provides.fetch_relation_field(relation.id, "database")
            and self.charm.backend.check_backend()
        ):
            self.database_provides.set_version(
                relation.id, self.charm.backend.postgres.get_postgresql_version(current_host=False)
            )

    def update_endpoints(self, relation=None) -> None:
        """Set the endpoints for the relation."""
        relations = [relation] if relation else self.model.relations[self.relation_name]

        key, ca, cert = self.charm.tls.get_tls_files()
        if all((key, ca, cert)):
            tls_flag = "True"
            tls_ca = ca
        else:
            tls_flag = "False"
            tls_ca = ""
        # Set the endpoints for each relation.
        for relation in relations:
            if not relation or not relation.data or not relation.data.get(relation.app):
                # This is a relation that is going away and finds itself in a broken state
                # proceed to the next relation
                continue
            user = f"relation_id_{relation.id}"
            database = self.database_provides.fetch_relation_field(relation.id, "database")
            password = self.database_provides.fetch_my_relation_field(relation.id, "password")
            if not database or not password:
                return

            self.database_provides.set_tls(relation.id, tls_flag)
            self.database_provides.set_tls_ca(relation.id, tls_ca)
            self.database_provides.set_endpoints(relation.id, self.charm.read_write_endpoints)
            self.database_provides.set_read_only_endpoints(
                relation.id, self.charm.read_only_endpoints
            )
            self.database_provides.set_uris(
                relation.id,
                f"postgresql://{user}:{password}@{self.charm.read_write_endpoints}/{database}",
            )
            # Make sure that the URI will be a secret
            if (
                secret_fields := self.database_provides.fetch_relation_field(
                    relation.id, "requested-secrets"
                )
            ) and "read-only-uris" in secret_fields:
                self.database_provides.set_read_only_uris(
                    relation.id,
                    f"postgresql://{user}:{password}@{self.charm.read_write_endpoints}/{database}_readonly",
                )

    def get_database(self, relation):
        """Gets database name from relation."""
        return relation.data.get(self.get_external_app(relation)).get("database", None)

    def get_external_app(self, relation):
        """Gets external application, as an Application object.

        Given a relation, this gets the first application object that isn't PGBouncer.

        TODO this is stolen from the db relation - cleanup
        """
        for entry in relation.data:
            if isinstance(entry, Application) and entry != self.charm.app:
                return entry
