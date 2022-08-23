# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Postgres db relation hooks & helpers.

This relation uses the pgsql interface, omitting roles and extensions as they are unsupported in
the new postgres charm.

Some example relation data is below. All values are examples, generated in a running test instance.
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┓
┃ category         ┃            keys ┃ pgbouncer-k8s/0                            ┃ finos-waltz/0 ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━┩
│ metadata         │        endpoint │ 'db'                                       │ 'db'          │
│                  │          leader │ True                                       │ True          │
├──────────────────┼─────────────────┼────────────────────────────────────────────┼───────────────┤
│ application data │ allowed-subnets │ 10.152.183.122/32                          │               │
│                  │   allowed-units │ pgbouncer-k8s/0                            │               │
│                  │        database │ waltz                                      │ waltz         │
│                  │            host │ pgbouncer-k8s-0.pgbouncer-k8s-op…          │               │
│                  │          master │ host=pgbouncer-k8s-0.pgbouncer-k…          │               │
│                  │                 │ dbname=waltz port=6432 user=relation_id_3  │               │
│                  │                 │ password=BjWDKjvZyClvTl4d5VDOK3mH          │               │
│                  │                 │ fallback_application_name=finos-waltz      │               │
│                  │        password │ BjWDKjvZyClvTl4d5VDOK3mH                   │               │
│                  │            port │ 6432                                       │               │
│                  │        standbys │ host=pgbouncer-k8s-0.pgbouncer-k…          │               │
│                  │                 │ dbname=waltz port=6432 user=relation_id_3  │               │
│                  │                 │ password=BjWDKjvZyClvTl4d5VDOK3mH          │               │
│                  │                 │ fallback_application_name=finos-waltz      │               │
│                  │           state │ master                                     │               │
│                  │            user │ relation_id_3                              │               │
│                  │         version │ 12.11                                      │               │
│ unit data        │ allowed-subnets │ 10.152.183.122/32                          │               │
│                  │   allowed-units │ pgbouncer-k8s/0                            │               │
│                  │        database │ waltz                                      │ waltz         │
│                  │            host │ pgbouncer-k8s-0.pgbouncer-k8s-op…          │               │
│                  │          master │ host=pgbouncer-k8s-0.pgbouncer-k…          │               │
│                  │                 │ dbname=waltz port=6432 user=relation_id_3  │               │
│                  │                 │ password=BjWDKjvZyClvTl4d5VDOK3mH          │               │
│                  │                 │ fallback_application_name=finos-waltz      │               │
│                  │        password │ BjWDKjvZyClvTl4d5VDOK3mH                   │               │
│                  │            port │ 6432                                       │               │
│                  │        standbys │ host=pgbouncer-k8s-0.pgbouncer-k…          │               │
│                  │                 │ dbname=waltz port=6432 user=relation_id_3  │               │
│                  │                 │ password=BjWDKjvZyClvTl4d5VDOK3mH          │               │
│                  │                 │ fallback_application_name=finos-waltz      │               │
│                  │           state │ master                                     │               │
│                  │            user │ relation_id_3                              │               │
│                  │         version │ 12.11                                      │               │
└──────────────────┴─────────────────┴────────────────────────────────────────────┴───────────────┘
"""

import logging
from typing import Dict, Iterable

from charms.pgbouncer_k8s.v0 import pgb
from charms.postgresql_k8s.v0.postgresql import (
    PostgreSQLCreateDatabaseError,
    PostgreSQLCreateUserError,
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
    WaitingStatus,
)

logger = logging.getLogger(__name__)


class RelationNotInitialisedError(Exception):
    """An error to be raised if the relation is not initialised."""


class DbProvides(Object):
    """Defines functionality for the 'provides' side of the 'db' relation.

    This relation connects to client applications, providing database services in an identical way
    to the same relation in the PostgreSQL charm, to the point where they should be
    indistinguishable to the client app.

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
        if not self.charm.backend.postgres:
            # We can't relate an app to the backend database without a backend postgres relation
            wait_str = "waiting for backend-database relation to connect"
            logger.warning(wait_str)
            self.charm.unit.status = WaitingStatus(wait_str)
            join_event.defer()
            return

        try:
            cfg = self.charm.read_pgb_config()
        except FileNotFoundError:
            wait_str = "waiting for pgbouncer to start"
            logger.warning(wait_str)
            self.charm.unit.status = WaitingStatus(wait_str)
            join_event.defer()
            return

        logger.info(f"Setting up {self.relation_name} relation")
        logger.warning(
            f"DEPRECATION WARNING - {self.relation_name} is a legacy relation, and will be deprecated in a future release. "
        )

        remote_app_databag = join_event.relation.data[join_event.app]

        # Do not allow apps requesting extensions to be installed.
        if "extensions" in remote_app_databag:
            logger.error(
                "ERROR - `extensions` cannot be requested through relations"
                " - they should be installed through a database charm config in the future"
            )
            self.charm.unit.status = BlockedStatus(
                "bad relation request - remote app requested extensions, which are unsupported. Please remove this relation."
            )
            return

        database = remote_app_databag.get("database")
        if database is None:
            logger.warning("No database name provided in app databag")
            join_event.defer()
            return

        self.update_databag(
            join_event.relation,
            {
                "user": user,
                "password": password,
                "database": database,
            },
        )

        if not self.charm.unit.is_leader():
            return

        user = self._generate_username(join_event)
        password = pgb.generate_password()

        # Create user and database in backend postgresql database
        try:
            init_msg = f"initialising database and user for {self.relation_name} relation"
            self.charm.unit.status = MaintenanceStatus(init_msg)
            logger.info(init_msg)

            self.charm.backend.postgres.create_user(user, password, admin=self.admin)
            self.charm.backend.postgres.create_database(database, user)

            created_msg = f"database and user for {self.relation_name} relation created"
            self.charm.unit.status = ActiveStatus(created_msg)
            logger.info(created_msg)
        except (PostgreSQLCreateDatabaseError, PostgreSQLCreateUserError):
            err_msg = f"failed to create database or user for {self.relation_name}"
            logger.error(err_msg)
            self.charm.unit.status = BlockedStatus(err_msg)
            return

        # set up auth function
        self.charm.backend.initialise_auth_function(dbname=database)

        # Create user in pgbouncer config
        cfg = self.charm.read_pgb_config()
        cfg.add_user(user, admin=self.admin)
        self.charm.render_pgb_config(cfg, reload_pgbouncer=True)

    def _on_relation_changed(self, change_event: RelationChangedEvent):
        """Handle db-relation-changed event.

        Takes information from the pgbouncer db app relation databag and copies it into the
        pgbouncer.ini config.

        This relation will defer if the backend relation isn't fully available, and if the
        relation_joined hook isn't completed.
        """
        if not self.charm.backend.postgres:
            # We can't relate an app to the backend database without a backend postgres relation
            wait_str = "waiting for backend-database relation to connect"
            logger.warning(wait_str)
            self.charm.unit.status = WaitingStatus(wait_str)
            change_event.defer()
            return

        logger.warning(
            f"DEPRECATION WARNING - {self.relation_name} is a legacy relation, and will be deprecated in a future release. "
        )

        # No backup values because if databag isn't populated, this relation isn't initialised.
        # This means that the database and user requested in this relation haven't been created,
        # so we defer this event until the databag is populated.
        databag = self.get_databags(change_event.relation)[0]
        database = databag.get("database")
        user = databag.get("user")
        password = databag.get("password")

        if None in [database, user, password]:
            logger.warning(
                "relation not fully initialised - deferring until join_event is complete"
            )
            change_event.defer()
            return

        self.update_port(change_event.relation, self.charm.config["listen_port"])
        self.update_postgres_endpoints(change_event.relation, reload_pgbouncer=True)
        self.update_databag(
            change_event.relation,
            {
                "allowed-subnets": self.get_allowed_subnets(change_event.relation),
                "allowed-units": self.get_allowed_units(change_event.relation),
                "version": self.charm.backend.postgres.get_postgresql_version(),
                "host": self.charm.unit_pod_hostname,
                "user": user,
                "password": password,
                "database": database,
                "state": self._get_state(),
            },
        )

    def update_port(self, relation: Relation, port: str):
        """Updates databag to match new port."""
        databag = self.get_databags(relation)[0]
        database = databag.get("database")
        user = databag.get("user")
        password = databag.get("password")

        if None in [database, user, password]:
            logger.warning("relation not fully initialised - skipping port update")
            return

        dbconnstr = pgb.parse_dict_to_kv_string(
            {
                "host": self.charm.unit_pod_hostname,
                "dbname": database,
                "port": port,
                "user": user,
                "password": password,
                "fallback_application_name": self.get_external_app(relation).name,
            }
        )
        self.update_databag(
            relation,
            {
                "master": dbconnstr,
                "port": str(port),
                "standbys": dbconnstr,
            },
        )

    def update_postgres_endpoints(self, relation: Relation, reload_pgbouncer: bool = False):
        """Updates postgres replicas."""
        database = self.get_databags(relation)[0].get("database")
        if database is None:
            logger.warning("relation not fully initialised - skipping postgres endpoint update")
            return

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
        self.charm.render_pgb_config(cfg, reload_pgbouncer=reload_pgbouncer)

    def _on_relation_departed(self, departed_event: RelationDepartedEvent):
        """Handle db-relation-departed event.

        Removes relevant information from pgbouncer config when db relation is removed. This
        function assumes that relation databags are destroyed when the relation itself is removed.
        """
        logger.info("db relation removed - updating config")
        logger.warning(
            f"DEPRECATION WARNING - {self.relation_name} is a legacy relation, and will be deprecated in a future release. "
        )

        self.update_databag({"allowed-units": self.get_allowed_units(departed_event.relation)})

    def _on_relation_broken(self, broken_event: RelationBrokenEvent):
        """Handle db-relation-broken event.

        Removes all traces of the given application from the pgbouncer config, and removes relation
        user if its unused by any other relations.

        This doesn't delete any tables so we aren't deleting a user's entire database with one
        command.
        """
        databag = self.get_databags(broken_event.relation)[0]
        user = databag.get("user")
        database = databag.get("database")

        if not self.charm.backend.postgres or None in [user, database]:
            # this relation was never created, so wait for it to be initialised before removing
            # everything.
            logger.warning(
                f"backend relation not yet available - deferring {self.relation_name}-relation-broken event."
            )
            broken_event.defer()
            return

        cfg = self.charm.read_pgb_config()

        # check database can be deleted from pgb config, and if so, delete it. Database is kept on
        # postgres application because we don't want to delete all user data with one command.
        delete_db = True
        for relname in ["db", "db-admin"]:
            for relation in self.model.relations.get(relname, []):
                if relation.id == broken_event.relation.id:
                    continue
                if relation.data[self.charm.app].get("database") == database:
                    # There's multiple applications using this database, so don't remove it until
                    # we can guarantee this is the last one.
                    delete_db = False
                    break
        if delete_db:
            del cfg["databases"][database]
            cfg["databases"].pop(f"{database}_standby", None)

        cfg.remove_user(user)
        self.charm.render_pgb_config(cfg, reload_pgbouncer=True)
        if self.charm.unit.is_leader():
            self.charm.backend.postgres.delete_user(user)

    def update_databag(self, relation, updates: Dict[str, str]):
        """Updates databag with the given dict."""
        # Databag entries can only be strings
        for key, item in updates.items():
            updates[key] = str(item)

        for databag in self.get_databags(relation):
            databag.update(updates)

    def _generate_username(self, event):
        """Generates a unique username for this relation."""
        app_name = self.charm.app.name
        relation_id = event.relation.id
        model_name = self.model.name
        return f"{app_name}_user_id_{relation_id}_{model_name}".replace("-", "_")

    def get_databags(self, relation):
        """Returns available databags for the given relation"""
        databags = [relation.data[self.charm.unit]]
        if self.charm.unit.is_leader():
            databags.append(relation.data[self.charm.app])
        return databags

    def _get_read_only_endpoint(self):
        """Get a read-only-endpoint from backend relation.

        Though multiple readonly endpoints can be provided by the new backend relation, only one
        can be consumed by this legacy relation.
        """
        read_only_endpoints = self.charm.backend.postgres_databag.get("read-only-endpoints")
        if read_only_endpoints is None or len(read_only_endpoints) == 0:
            return None
        return read_only_endpoints.split(",")[0]

    def _get_state(self) -> str:
        """Gets the given state for this unit.

        Args:
            standbys: the comma-separated list of postgres standbys

        Returns:
            The described state of this unit. Can be 'standalone', 'master', or 'standby'.
        """
        if self.charm.unit.is_leader():
            return "master"
        else:
            return "standby"

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
        return ",".join(
            sorted(
                [
                    unit.name
                    for unit in relation.data
                    if isinstance(unit, Unit) and not unit.app != self.charm.app
                ]
            )
        )

    def get_external_app(self, relation):
        """Gets external application, as an Application object."""
        for entry in relation.data.keys():
            if isinstance(entry, Application) and entry != self.charm.app:
                return entry
