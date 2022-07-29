# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Postgres db relation hooks & helpers.

This relation uses the pgsql interface, omitting roles and extensions as they are unsupported in
the new postgres charm.

Some example relation data is below. All values are examples, generated in a running test instance.
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┓
┃ category         ┃            keys ┃ pgbouncer-k8s-operator/0                   ┃ finos-waltz/0 ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━┩
│ metadata         │        endpoint │ 'db'                                       │ 'db'          │
│                  │          leader │ True                                       │ True          │
├──────────────────┼─────────────────┼────────────────────────────────────────────┼───────────────┤
│ application data │ allowed-subnets │ 10.152.183.122/32                          │               │
│                  │   allowed-units │ pgbouncer-k8s-operator/0                   │               │
│                  │        database │ waltz                                      │ waltz         │
│                  │            host │ pgbouncer-k8s-operator-0.pgbouncer-k8s-op… │               │
│                  │          master │ host=pgbouncer-k8s-operator-0.pgbouncer-k… │               │
│                  │                 │ dbname=waltz port=6432 user=relation_id_3  │               │
│                  │                 │ password=BjWDKjvZyClvTl4d5VDOK3mH          │               │
│                  │                 │ fallback_application_name=finos-waltz      │               │
│                  │        password │ BjWDKjvZyClvTl4d5VDOK3mH                   │               │
│                  │            port │ 6432                                       │               │
│                  │        standbys │ host=pgbouncer-k8s-operator-0.pgbouncer-k… │               │
│                  │                 │ dbname=waltz port=6432 user=relation_id_3  │               │
│                  │                 │ password=BjWDKjvZyClvTl4d5VDOK3mH          │               │
│                  │                 │ fallback_application_name=finos-waltz      │               │
│                  │           state │ master                                     │               │
│                  │            user │ relation_id_3                              │               │
│                  │         version │ 12.11                                      │               │
│ unit data        │ allowed-subnets │ 10.152.183.122/32                          │               │
│                  │   allowed-units │ pgbouncer-k8s-operator/0                   │               │
│                  │        database │ waltz                                      │ waltz         │
│                  │            host │ pgbouncer-k8s-operator-0.pgbouncer-k8s-op… │               │
│                  │          master │ host=pgbouncer-k8s-operator-0.pgbouncer-k… │               │
│                  │                 │ dbname=waltz port=6432 user=relation_id_3  │               │
│                  │                 │ password=BjWDKjvZyClvTl4d5VDOK3mH          │               │
│                  │                 │ fallback_application_name=finos-waltz      │               │
│                  │        password │ BjWDKjvZyClvTl4d5VDOK3mH                   │               │
│                  │            port │ 6432                                       │               │
│                  │        standbys │ host=pgbouncer-k8s-operator-0.pgbouncer-k… │               │
│                  │                 │ dbname=waltz port=6432 user=relation_id_3  │               │
│                  │                 │ password=BjWDKjvZyClvTl4d5VDOK3mH          │               │
│                  │                 │ fallback_application_name=finos-waltz      │               │
│                  │           state │ master                                     │               │
│                  │            user │ relation_id_3                              │               │
│                  │         version │ 12.11                                      │               │
└──────────────────┴─────────────────┴────────────────────────────────────────────┴───────────────┘
"""

import logging
from typing import Iterable

from charms.pgbouncer_operator.v0 import pgb
from charms.postgresql_k8s.v0.postgresql import (
    PostgreSQLCreateDatabaseError,
    PostgreSQLCreateUserError,
    PostgreSQLDeleteUserError,
)
from ops.charm import (
    CharmBase,
    RelationBrokenEvent,
    RelationChangedEvent,
    RelationDepartedEvent,
    RelationJoinedEvent,
)
from ops.framework import Object
from ops.model import (
    ActiveStatus,
    Application,
    BlockedStatus,
    MaintenanceStatus,
    Relation,
    Unit,
)

logger = logging.getLogger(__name__)


class DbProvides(Object):
    """Defines functionality for the 'provides' side of the 'db' relation.

    Hook events observed:
        - relation-joined
        - relation-changed
        - relation-departed
        - relation-broken
    """

    def __init__(self, charm: CharmBase, admin: bool = False):
        """Constructor for DbProvides object.

        Args:
            charm: the charm for which this relation is provided
            admin: a boolean defining whether or not this relation has admin permissions, switching
                between "db" and "db-admin" relations.
        """
        if admin:
            self.relation_name = "db-admin"
        else:
            self.relation_name = "db"

        super().__init__(charm, self.relation_name)

        self.framework.observe(
            charm.on[self.relation_name].relation_joined, self._on_relation_joined
        )
        self.framework.observe(
            charm.on[self.relation_name].relation_changed, self._on_relation_changed
        )
        self.framework.observe(
            charm.on[self.relation_name].relation_departed, self._on_relation_departed
        )
        self.framework.observe(
            charm.on[self.relation_name].relation_broken, self._on_relation_broken
        )

        self.charm = charm
        self.admin = admin

    def _on_relation_joined(self, join_event: RelationJoinedEvent):
        """Handle db-relation-joined event.

        If the backend relation is fully initialised and available, we generate the proposed
        database and create a user on the postgres charm, and add preliminary data to the databag.
        """
        if not self.charm.unit.is_leader():
            return

        if not self.charm.backend_postgres:
            # We can't relate an app to the backend database without a backend postgres relation
            logger.warning("waiting for backend-database relation to connect")
            join_event.defer()
            return

        logger.info(f"Setting up {self.relation_name} relation")
        logger.warning(
            f"DEPRECATION WARNING - {self.relation_name} is a legacy relation, and will be deprecated in a future release. "
        )

        cfg = self.charm.read_pgb_config()

        relation_data = join_event.relation.data
        pgb_unit_databag = relation_data[self.charm.unit]
        pgb_app_databag = relation_data[self.charm.app]
        remote_app_databag = relation_data[join_event.app]

        # Do not allow apps requesting extensions to be installed.
        if "extensions" in remote_app_databag:
            logger.error(
                "ERROR - `extensions` cannot be requested through relations"
                " - they should be installed through a database charm config in the future"
            )
            self.charm.unit.status = BlockedStatus(
                "bad relation request - remote app requested extensions, which are unsupported."
            )
            return

        database = remote_app_databag.get("database")
        if database is None:
            logger.warning("No database name provided in app databag")
            join_event.defer()
            return

        user = self.generate_username(join_event)
        password = pgb.generate_password()

        # Create user in pgbouncer config
        self.charm.add_user(
            user,
            password=password,
            admin=self.admin,
            cfg=cfg,
            render_cfg=True,
            reload_pgbouncer=True,
        )

        # Create user and database in backend postgresql database
        try:
            init_msg = f"initialising database and user for {self.relation_name} relation"
            self.charm.unit.status = MaintenanceStatus(init_msg)
            logger.info(init_msg)

            self.charm.backend_postgres.create_user(user, password, admin=self.admin)
            self.charm.backend_postgres.create_database(database, user)

            created_msg = f"database and user for {self.relation_name} relation created"
            self.charm.unit.status = ActiveStatus(created_msg)
            logger.info(created_msg)
        except (PostgreSQLCreateDatabaseError, PostgreSQLCreateUserError):
            err_msg = f"failed to create database or user for {self.relation_name}"
            logger.error(err_msg)
            self.charm.unit.status = BlockedStatus(err_msg)
            return

        for databag in [pgb_app_databag, pgb_unit_databag]:
            databag.update(
                {
                    "user": user,
                    "password": password,
                    "database": database,
                }
            )

    def _on_relation_changed(self, change_event: RelationChangedEvent):
        """Handle db-relation-changed event.

        Takes information from the pgbouncer db app relation databag and copies it into the
        pgbouncer.ini config.

        This relation will defer if the backend relation isn't fully available, and if the
        relation_joined hook isn't completed.
        """
        if not self.charm.unit.is_leader():
            return

        if not self.charm.backend_postgres:
            # We can't relate an app to the backend database without a backend postgres relation
            logger.warning("waiting for backend-database relation to connect")
            change_event.defer()
            return

        logger.info(f"changing {self.relation_name} relation - updating config")
        logger.warning(
            f"DEPRECATION WARNING - {self.relation_name} is a legacy relation, and will be deprecated in a future release. "
        )

        pgb_unit_databag = change_event.relation.data[self.charm.unit]
        pgb_app_databag = change_event.relation.data[self.charm.app]

        # No backup values because if pgb_app_databag isn't populated, this relation isn't
        # initialised. This means that the database and user requested in this relation haven't
        # been created, so we defer this event until the databag is populated.
        database = pgb_app_databag.get("database")
        user = pgb_app_databag.get("user")
        password = pgb_app_databag.get("password")

        if None in [database, user, password]:
            logger.warning("relation not initialised - deferring until join_event is complete")
            change_event.defer()
            return

        # In postgres, "endpoints" will only ever have one value. Other databases using the library
        # can have more, but that's not planned for the postgres charm.
        postgres_endpoint = self.charm.backend_relation_app_databag.get("endpoints")
        cfg = self.charm.read_pgb_config()
        cfg["databases"][database] = {
            "host": postgres_endpoint.split(":")[0],
            "dbname": database,
            "port": postgres_endpoint.split(":")[1],
        }
        read_only_endpoint = self._get_read_only_endpoint()
        if read_only_endpoint:
            cfg["databases"][f"{database}_standby"] = {
                "host": read_only_endpoint.split(":")[0],
                "dbname": database,
                "port": read_only_endpoint.split(":")[1],
            }
        # Write config data to charm filesystem
        self.charm._render_pgb_config(cfg, reload_pgbouncer=True)

        dbconnstr = pgb.parse_dict_to_kv_string(
            {
                "host": self.charm.unit_pod_hostname,
                "dbname": database,
                "port": self.charm.config["listen_port"],
                "user": user,
                "password": password,
                "fallback_application_name": self.get_external_app(change_event.relation).name,
            }
        )

        # Populate databags
        for databag in [pgb_app_databag, pgb_unit_databag]:
            updates = {
                "allowed-subnets": self.get_allowed_subnets(change_event.relation),
                "allowed-units": self.get_allowed_units(change_event.relation),
                "host": self.charm.unit_pod_hostname,
                "master": dbconnstr,
                "port": str(self.charm.config["listen_port"]),
                "standbys": dbconnstr,
                "version": self.charm.backend_postgres.get_postgresql_version(),
                "user": user,
                "password": password,
                "database": database,
                "state": self._get_state(dbconnstr),
            }
            databag.update(updates)

    def generate_username(self, event):
        """Generates a username for this relation."""
        return f"relation_id_{event.relation.id}"

    def _get_read_only_endpoint(self):
        """Get a read-only-endpoint from backend relation.

        Though multiple readonly endpoints can be provided by the new backend relation, only one
        can be consumed by this legacy relation.
        """
        read_only_endpoints = self.charm.backend_relation_app_databag.get("read-only-endpoints")
        if read_only_endpoints is None or len(read_only_endpoints) == 0:
            return None
        return read_only_endpoints.split(",")[0]

    def _get_state(self, standbys: str) -> str:
        """Gets the given state for this unit.

        Args:
            standbys: the comma-separated list of postgres standbys

        Returns:
            The described state of this unit. Can be 'standalone', 'master', or 'standby'.
        """
        if standbys == "":
            return "standalone"
        # TODO this doesn't ever return false. Revisit mastery once scaling is sorted, and check
        # replicas return standby.
        elif self.charm.unit.is_leader():
            return "master"
        else:
            return "standby"

    def _on_relation_departed(self, departed_event: RelationDepartedEvent):
        """Handle db-relation-departed event.

        Removes relevant information from pgbouncer config when db relation is removed. This
        function assumes that relation databags are destroyed when the relation itself is removed.
        """
        logger.info("db relation removed - updating config")
        logger.warning(
            f"DEPRECATION WARNING - {self.relation_name} is a legacy relation, and will be deprecated in a future release. "
        )

        app_databag = departed_event.relation.data[self.charm.app]
        unit_databag = departed_event.relation.data[self.charm.unit]

        for databag in [app_databag, unit_databag]:
            databag["allowed-units"] = self.get_allowed_units(departed_event.relation)

    def _on_relation_broken(self, broken_event: RelationBrokenEvent):
        """Handle db-relation-broken event.

        Removes all traces of the given application from the pgbouncer config, and removes relation
        user if its unused by any other relations.

        This doesn't delete any tables so we aren't deleting a user's entire database with one
        command.
        """
        app_databag = broken_event.relation.data[self.charm.app]
        user = app_databag.get("user")
        database = app_databag.get("database")

        if not self.charm.backend_postgres or None in [user, database]:
            # this relation was never created, so wait for it to be initialised before removing
            # everything.
            logger.warning(
                f"backend relation not yet available - deferring {self.relation_name}-relation-broken event."
            )
            broken_event.defer()
            return

        cfg = self.charm.read_pgb_config()

        # delete user
        self.charm.remove_user(user, cfg=cfg, render_cfg=True, reload_pgbouncer=True)
        try:
            if self.charm.backend_postgres:
                # Try to delete user if backend database still exists. If not, postgres has been
                # removed and will handle user deletion in its own relation-broken hook.
                self.charm.backend_postgres.delete_user(user, if_exists=True)
        except PostgreSQLDeleteUserError:
            blockedmsg = f"failed to delete user for {self.relation_name}"
            logger.error(blockedmsg)
            self.charm.unit.status = BlockedStatus(blockedmsg)
            return

        # check database can be deleted from pgb config, and if so, delete it. Database is kept on
        # postgres application because we don't want to delete all user data with one command.
        for relname in ["db", "db-admin"]:
            for relation in self.charm.model.relations.get(relname):
                if relation.id == broken_event.relation.id:
                    continue
                if relation.data.get(self.charm.app, {}).get("database") == database:
                    # There's multiple applications using this database, so don't remove it until
                    # we can guarantee this is the last one.
                    return

        del cfg["databases"][database]
        cfg["databases"].pop(f"{database}_standby")

    def get_allowed_subnets(self, relation: Relation) -> str:
        """Gets the allowed subnets from this relation."""

        def _comma_split(string) -> Iterable[str]:
            if string:
                for substring in string.split(","):
                    substring = substring.strip()
                    if substring:
                        yield substring

        subnets = set()
        for unit, reldata in relation.data.items():
            logger.warning(f"Checking subnets for {unit}")
            if isinstance(unit, Unit) and not unit.name.startswith(self.model.app.name):
                # NB. egress-subnets is not always available.
                subnets.update(set(_comma_split(reldata.get("egress-subnets", ""))))
        return ",".join(sorted(subnets))

    def get_allowed_units(self, relation: Relation) -> str:
        """Gets the external units from this relation that can be allowed into the network."""
        return ",".join(sorted([unit.name for unit in self.get_external_units(relation)]))

    def get_external_units(self, relation: Relation) -> Unit:
        """Gets all units from this relation that aren't owned by this charm."""
        return [
            unit
            for unit in relation.data
            if isinstance(unit, Unit) and not unit.app != self.charm.app
        ]

    def get_external_app(self, relation):
        """Gets external application, as an Application object."""
        for entry in relation.data.keys():
            if isinstance(entry, Application) and entry != self.charm.app:
                return entry
