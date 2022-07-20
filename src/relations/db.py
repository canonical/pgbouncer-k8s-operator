# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Postgres db relation hooks & helpers.

This relation uses the pgsql interface, omitting roles and extensions as they are unsupported in
the new postgres charm.

Some example relation data is below. All values are examples, generated in a running test instance.
┏━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┓
┃ category  ┃          keys ┃ pgbouncer/25                                      ┃ psql/1 ┃
┡━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━┩
│ metadata  │      endpoint │ 'db'                                              │ 'db'   │
│           │        leader │ True                                              │ True   │
├───────────┼───────────────┼───────────────────────────────────────────────────┼────────┤
│ unit data │ allowed-units │ psql/1                                            │        │
│           │      database │ cli                                               │ cli    │
│           │          host │ 10.101.233.10                                     │        │
│           │        master │ dbname=cli host=10.101.233.10                     │        │
│           │               │ password=jnT4LxNPPrssscxGYmGPy4FKjRNXCn4NL2Y32jqs │        │
│           │               │ port=6432 user=db_85_psql                         │        │
│           │      password │ jnT4LxNPPrssscxGYmGPy4FKjRNXCn4NL2Y32jqs          │        │
│           │          port │ 6432                                              │        │
│           │      standbys │ dbname=cli_standby host=10.101.233.10             │        │
│           │               │ password=jnT4LxNPPrssscxGYmGPy4FKjRNXCn4NL2Y32jqs │        │
│           │               │ port=6432 user=db_85_psql                         │        │
│           │         state │ master                                            │        │
│           │          user │ db_85_psql                                        │        │
│           │       version │ 12                                                │        │
└───────────┴───────────────┴───────────────────────────────────────────────────┴────────┘
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
from ops.model import Relation, Unit

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
        """Handle db-relation-joined event. """

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
        dbs = cfg["databases"]

        relation_data = join_event.relation.data
        pgb_unit_databag = relation_data[self.charm.unit]
        pgb_app_databag = relation_data[self.charm.app]

        external_unit = self.get_external_units(join_event.relation)[0]
        database = pgb_app_databag.get("database", relation_data[external_unit].get("database"))
        if database is None:
            logger.warning("No database name provided")
            join_event.defer()
            return

        # TODO consider replacing database/user sanitisation with sql.Identifier()
        database = database.replace("-", "_")

        user = pgb_app_databag.get("user", self.generate_username(join_event))
        user = user.replace("-", "_")
        password = pgb_app_databag.get("password", pgb.generate_password())

        self.charm.add_user(user, password=password, admin=self.admin, cfg=cfg, render_cfg=False)
        self.charm._render_pgb_config(cfg, reload_pgbouncer=True)

        try:
            self.charm.backend_postgres.create_user(user, password, admin=self.admin)
            self.charm.backend_postgres.create_database(database, user)
        except (PostgreSQLCreateDatabaseError, PostgreSQLCreateUserError):
            logger.error(f"failed to create database or user for {self.relation_name}")
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

        try:
            external_unit = self.get_external_units(change_event.relation)[0]
        except IndexError:
            # In cases where pgbouncer changes the relation, we have no new information to add to
            # the config. Scaling is not yet implemented, and calling this hook from the
            # backend-db-admin relation occurs after the config updates are added.
            logger.info(
                f"no external unit found in {self.relation_name} relation - nothing to change in config, exiting relation hook"
            )
            return
        external_app_name = external_unit.app.name

        # Do not allow apps requesting extensions to be installed.
        # TODO how would these be added into the pgb databags? surely they should be external?
        if "extensions" in pgb_unit_databag or "extensions" in pgb_app_databag:
            logger.error(
                "ERROR - `extensions` cannot be requested through relations"
                " - they should be installed through a database charm config in the future"
            )
            # TODO fail to create relation
            return

        database = pgb_app_databag.get("database")
        if database is None:
            logger.warning("No database name provided")
            change_event.defer()
            return

        # TODO consider replacing database/user sanitisation with sql.Identifier()
        database = database.replace("-", "_")

        user = pgb_app_databag.get("user")
        user = user.replace("-", "_")
        password = pgb_app_databag.get("password")

        # TODO clean this up
        # Get data about primary unit for databags and charm config.
        backend_endpoint = self.charm.backend_relation_app_databag.get("endpoints")
        logger.error(self.charm.backend_relation_app_databag)
        primary_host = backend_endpoint.split(":")[0]
        primary_port = backend_endpoint.split(":")[1]
        primary = {
            "host": primary_host,
            "dbname": database,
            "port": primary_port,
        }
        cfg_entry = self.get_db_cfg_name(database, change_event.relation.id)
        dbs[cfg_entry] = deepcopy(primary)
        primary.update(
            {
                "user": user,
                "password": password,
                "fallback_application_name": external_app_name,
            }
        )

        # Get data about standby units for databags and charm config.
        standbys = self._get_standbys(cfg, external_app_name, cfg_entry, database, user, password)

        # Write config data to charm filesystem
        self.charm._render_pgb_config(cfg, reload_pgbouncer=True)

        # Populate databags
        for databag in [pgb_app_databag, pgb_unit_databag]:
            updates = {
                "allowed-subnets": self.get_allowed_subnets(change_event.relation),
                "allowed-units": self.get_allowed_units(change_event.relation),
                "host": f"http://{primary_host}",
                "master": pgb.parse_dict_to_kv_string(primary),
                "port": primary_port,
                "standbys": standbys,
                "version": "12",
                "user": user,
                "password": password,
                "database": database,
                "state": self._get_state(standbys),
            }
            databag.update(updates)

    def generate_username(self, event):
        """Generates a username for this relation."""
        return f"relation_id_{event.relation.id}"

    def get_db_cfg_name(self, database, id):
        """Generates a unique database name for this relation."""
        return f"{database}_{id}"

    def _get_standbys(self, cfg, app_name, cfg_entry, dbname, user, password):
        dbs = cfg["databases"]

        standbys = []
        for read_only_endpoint in self.charm.backend_relation_app_databag.get(
            "read-only-endpoints"
        ).split(","):
            standby = {
                "host": read_only_endpoint.split(":")[0],
                "dbname": dbname,
                "port": read_only_endpoint.split(":")[1],
            }
            dbs[f"{cfg_entry}_standby"] = deepcopy(standby)

            standby.update(
                {
                    "fallback_application_name": app_name,
                    "user": user,
                    "password": password,
                }
            )
            standbys.append(pgb.parse_dict_to_kv_string(standby))

        return ", ".join(standbys)

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
        cfg_entry = self.get_db_cfg_name(database, broken_event.relation.id)

        del dbs[cfg_entry]
        dbs.pop(f"{cfg_entry}_standby")

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
        return [
            unit
            for unit in relation.data
            if isinstance(unit, Unit) and not unit.name.startswith(self.model.app.name)
        ]
