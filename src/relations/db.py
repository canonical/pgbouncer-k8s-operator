# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Postgres db relation hooks & helpers.

This relation uses the pgsql interface, omitting roles and extensions as they are unsupported in
the new postgres charm.

Some example relation data is below. All values are examples, generated in a running test instance.
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┓
┃ category         ┃            keys ┃ pgbouncer-k8s-operator/0                                ┃ finos-waltz/0 ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━┩
│ metadata         │        endpoint │ 'db'                                                    │ 'db'          │
│                  │          leader │ True                                                    │ True          │
├──────────────────┼─────────────────┼─────────────────────────────────────────────────────────┼───────────────┤
│ application data │ allowed-subnets │ 10.152.183.22/32                                        │               │
│                  │   allowed-units │ finos-waltz/0                                           │               │
│                  │        database │ waltz                                                   │ waltz         │
│                  │            host │ pgbouncer-k8s-operator-0.pgbouncer-k8s-operator-endpoi… │               │
│                  │          master │ host=pgbouncer-k8s-operator-0.pgbouncer-k8s-operator-e… │               │
│                  │                 │ dbname=waltz port=6432 user=relation_id_3               │               │
│                  │                 │ password=ZFz5RnH7hyvTpgu1wE0O9uoi                       │               │
│                  │                 │ fallback_application_name=finos-waltz                   │               │
│                  │        password │ ZFz5RnH7hyvTpgu1wE0O9uoi                                │               │
│                  │            port │ 5432                                                    │               │
│                  │        standbys │ host=pgbouncer-k8s-operator-0.pgbouncer-k8s-operator-e… │               │
│                  │                 │ dbname=waltz port=6432                                  │               │
│                  │                 │ fallback_application_name=finos-waltz                   │               │
│                  │                 │ user=relation_id_3 password=ZFz5RnH7hyvTpgu1wE0O9uoi    │               │
│                  │           state │ master                                                  │               │
│                  │            user │ relation_id_3                                           │               │
│                  │         version │ 12                                                      │               │
│ unit data        │ allowed-subnets │ 10.152.183.22/32                                        │               │
│                  │   allowed-units │ finos-waltz/0                                           │               │
│                  │        database │ waltz                                                   │ waltz         │
│                  │            host │ pgbouncer-k8s-operator-0.pgbouncer-k8s-operator-endpoi… │               │
│                  │          master │ host=pgbouncer-k8s-operator-0.pgbouncer-k8s-operator-e… │               │
│                  │                 │ dbname=waltz port=6432 user=relation_id_3               │               │
│                  │                 │ password=ZFz5RnH7hyvTpgu1wE0O9uoi                       │               │
│                  │                 │ fallback_application_name=finos-waltz                   │               │
│                  │        password │ ZFz5RnH7hyvTpgu1wE0O9uoi                                │               │
│                  │            port │ 5432                                                    │               │
│                  │        standbys │ host=pgbouncer-k8s-operator-0.pgbouncer-k8s-operator-e… │               │
│                  │                 │ dbname=waltz port=6432                                  │               │
│                  │                 │ fallback_application_name=finos-waltz                   │               │
│                  │                 │ user=relation_id_3 password=ZFz5RnH7hyvTpgu1wE0O9uoi    │               │
│                  │           state │ master                                                  │               │
│                  │            user │ relation_id_3                                           │               │
│                  │         version │ 12                                                      │               │
└──────────────────┴─────────────────┴─────────────────────────────────────────────────────────┴───────────────┘
wrf@wrf-canonical:~/src/pgbouncer-k8s-operator$

"""

import logging
from copy import deepcopy
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
from ops.model import Application, Relation, Unit

logger = logging.getLogger(__name__)


class DbProvides(Object):
    """Defines functionality for the 'provides' side of the 'db' relation.

    Hook events observed:
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
        """Handle db-relation-joined event."""
        if not self.charm.unit.is_leader():
            return

        if not self.charm.backend_relation:
            # We can't relate an app to the backend database without a backend postgres relation
            logger.warning("waiting for backend-database relation")
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
            # TODO fail to create relation
            return

        database = remote_app_databag.get("database")
        if database is None:
            logger.warning("No database name provided")
            join_event.defer()
            return

        user = self.generate_username(join_event)
        password = pgb.generate_password()

        self.charm.add_user(
            user,
            password=password,
            admin=self.admin,
            cfg=cfg,
            render_cfg=True,
            reload_pgbouncer=True,
        )

        try:
            self.charm.backend_postgres.create_user(user, password, admin=self.admin)
            self.charm.backend_postgres.create_database(database, user)
        except (PostgreSQLCreateDatabaseError, PostgreSQLCreateUserError):
            logger.error(f"failed to create database or user for {self.relation_name}")
            join_event.defer()
            return

        for databag in [pgb_app_databag, pgb_unit_databag]:
            updates = {
                "user": user,
                "password": password,
                "database": database,
            }
            databag.update(updates)

    def _on_relation_changed(self, change_event: RelationChangedEvent):
        """Handle db-relation-changed event.

        Takes information from the db relation databag and copies it into the pgbouncer.ini
        config.
        """
        if not self.charm.unit.is_leader():
            return

        if not self.charm.backend_relation:
            # We can't relate an app to the backend database without a backend postgres relation
            logger.warning("waiting for backend-database relation")
            change_event.defer()
            return

        logger.info(f"changing {self.relation_name} relation - updating config")
        logger.warning(
            f"DEPRECATION WARNING - {self.relation_name} is a legacy relation, and will be deprecated in a future release. "
        )

        cfg = self.charm.read_pgb_config()
        dbs = cfg["databases"]

        relation_data = change_event.relation.data
        pgb_unit_databag = relation_data[self.charm.unit]
        pgb_app_databag = relation_data[self.charm.app]
        # TODO Delete, this was used to get a backup database name but it shouldn't be used.
        remote_app_databag = relation_data[change_event.app]

        external_app_name = self.get_external_app(change_event.relation).name

        database = pgb_app_databag.get("database")
        user = pgb_app_databag.get("user")
        password = pgb_app_databag.get("password")

        if None in [database, user, password]:
            logger.warning("relation not initialised - deferring until join_event is complete")
            change_event.defer()
            return

        backend_endpoint = self.charm.backend_relation_app_databag.get("endpoints")
        if backend_endpoint == None:
            # Sometimes postgres can create relation data without endpoints, so we defer until they
            # show up.
            change_event.defer()
            return

        primary_host = backend_endpoint.split(":")[0]
        primary_port = backend_endpoint.split(":")[1]
        primary = {
            "host": primary_host,
            "dbname": database,
            "port": primary_port,
        }
        dbs[database] = deepcopy(primary)
        primary.update(
            {
                "host": self.charm.unit_pod_hostname,
                "port": cfg["pgbouncer"]["listen_port"],
                "user": user,
                "password": password,
                "fallback_application_name": external_app_name,
            }
        )

        # Get data about standby units for databags and charm config.
        standbys = self._get_standby(cfg, external_app_name, database, user, password)

        # Write config data to charm filesystem
        logger.error(cfg)
        self.charm._render_pgb_config(cfg, reload_pgbouncer=True)

        # Populate databags
        for databag in [pgb_app_databag, pgb_unit_databag]:
            updates = {
                "allowed-subnets": self.get_allowed_subnets(change_event.relation),
                "allowed-units": self.get_allowed_units(change_event.relation),
                "host": self.charm.unit_pod_hostname,
                "master": pgb.parse_dict_to_kv_string(primary),
                "port": cfg["pgbouncer"]["listen_port"],
                "standbys": standbys,
                "version": self.charm.backend_postgres.get_postgresql_version(),
                "user": user,
                "password": password,
                "database": database,
                "state": self._get_state(standbys),
            }
            logger.error(updates)
            databag.update(updates)

    def generate_username(self, event):
        """Generates a username for this relation."""
        return f"relation_id_{event.relation.id}"

    def get_db_cfg_name(self, database, id):
        """Generates a unique database name for this relation."""
        return f"{database}_{id}"

    def _get_standby(self, cfg, app_name, dbname, user, password):
        dbs = cfg["databases"]

        read_only_endpoints = self.charm.backend_relation_app_databag.get("read-only-endpoints")
        if read_only_endpoints is None or len(read_only_endpoints) == 0:
            return None
        read_only_endpoint = read_only_endpoints.split(",")[0]

        dbs[f"{dbname}_standby"] = {
            "host": read_only_endpoint.split(":")[0],
            "dbname": dbname,
            "port": read_only_endpoint.split(":")[1],
        }

        return pgb.parse_dict_to_kv_string({
            "host": self.charm.unit_pod_hostname,
            "dbname": dbname,
            "port": cfg["pgbouncer"]["listen_port"],
            "fallback_application_name": app_name,
            "user": user,
            "password": password,
        })

    def _get_state(self, standbys: str) -> str:
        """Gets the given state for this unit.

        Args:
            standbys: the comma-separated list of postgres standbys

        Returns:
            The described state of this unit. Can be 'standalone', 'master', or 'standby'.
        """
        if standbys == "":
            return "standalone"
        elif self.charm.unit.is_leader():
            return "master"
        else:
            return "standby"

    def _on_relation_departed(self, departed_event: RelationDepartedEvent):
        """Handle db-relation-departed event.

        Removes relevant information from pgbouncer config when db relation is removed. This
        function assumes that relation databags are destroyed when the relation itself is removed.

        This doesn't delete users or tables, following the design of the legacy charm.
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

        Removes all traces of the given application from the pgbouncer config.
        """
        app_databag = broken_event.relation.data[self.charm.app]

        cfg = self.charm.read_pgb_config()
        dbs = cfg["databases"]
        user = app_databag["user"]
        database = app_databag["database"]

        duplicate = False
        logging.error(self.charm.model.relations)
        for relname in ["db", "db-admin"]:
            logging.error(self.charm.model.relations.get(relname))
            for relation in self.charm.model.relations.get(relname):
                logging.error(relation)
                if relation.data.get("database") == database:
                    duplicate = True

        if not duplicate:
            del dbs[database]
            dbs.pop(f"{database}_standby")

        self.charm.remove_user(user, cfg=cfg, render_cfg=True, reload_pgbouncer=True)

        try:
            self.charm.backend_postgres.delete_user(user, if_exists=True)
        except PostgreSQLDeleteUserError:
            logger.error(f"failed to delete user for {self.relation_name}")
            return

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
        # TODO switch if line for unit.app != self.charm.app
        return [
            unit
            for unit in relation.data
            if isinstance(unit, Unit) and not unit.name.startswith(self.model.app.name)
        ]

    def get_external_app(self, relation):
        """Gets external application, as an Application object.

        # External app != event.app
        #"""
        for entry in relation.data.keys():
            if isinstance(entry, Application) and entry != self.charm.app:
                return entry
