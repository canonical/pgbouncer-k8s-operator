#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed PgBouncer connection pooler."""


import logging
import os
from typing import Dict

from charms.pgbouncer_operator.v0 import pgb
from charms.pgbouncer_operator.v0.pgb import PgbConfig
from charms.postgresql_k8s.v0.postgresql import PostgreSQL
from ops.charm import CharmBase, ConfigChangedEvent, InstallEvent, PebbleReadyEvent
from ops.framework import StoredState
from ops.main import main
from ops.model import (
    ActiveStatus,
    Application,
    BlockedStatus,
    MaintenanceStatus,
    Relation,
    WaitingStatus,
)
from ops.pebble import Layer, PathError

from relations.backend_database import RELATION_NAME as BACKEND_RELATION_NAME
from relations.backend_database import BackendDatabaseRequires
from relations.db import DbProvides

logger = logging.getLogger(__name__)

PGB = "pgbouncer"
PG_USER = "postgres"
PGB_DIR = "/var/lib/postgresql/pgbouncer"
INI_PATH = f"{PGB_DIR}/pgbouncer.ini"
USERLIST_PATH = f"{PGB_DIR}/userlist.txt"


class PgBouncerK8sCharm(CharmBase):
    """A class implementing charmed PgBouncer."""

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.pgbouncer_pebble_ready, self._on_pgbouncer_pebble_ready)

        self.backend = BackendDatabaseRequires(self)
        self.legacy_db_relation = DbProvides(self, admin=False)
        self.legacy_db_admin_relation = DbProvides(self, admin=True)

        self._cores = os.cpu_count()

    # =======================
    #  Charm Lifecycle Hooks
    # =======================

    def _on_install(self, event: InstallEvent) -> None:
        """On install hook.

        This imports any users from the juju config, and initialises userlist and pgbouncer.ini
        config files that are essential for pgbouncer to run.
        """
        container = self.unit.get_container(PGB)
        if not container.can_connect():
            logger.debug(
                "pgbouncer config could not be rendered, waiting for container to be available."
            )
            event.defer()
            return

        # Initialise pgbouncer.ini config files from defaults set in charm lib.
        config = PgbConfig(pgb.DEFAULT_CONFIG)
        self._render_pgb_config(config)

        # Initialise userlist, generating passwords for initial users. All config files use the
        # same userlist, so we only need one.
        self._render_userlist(pgb.initialise_userlist_from_ini(config))

    def _on_config_changed(self, event: ConfigChangedEvent) -> None:
        """Handle changes in configuration."""
        container = self.unit.get_container(PGB)
        if not container.can_connect():
            self.unit.status = WaitingStatus("waiting for pgbouncer workload container.")
            event.defer()
            return

        try:
            config = self.read_pgb_config()
        except FileNotFoundError:
            self.unit.status = WaitingStatus("waiting for pgbouncer install hook to finish")
            event.defer()
            return

        config["pgbouncer"]["pool_mode"] = self.config["pool_mode"]
        config.set_max_db_connection_derivatives(
            self.config["max_db_connections"],
            self._cores,
        )
        self._render_pgb_config(config)

        # Create an updated pebble layer for the pgbouncer container, and apply it if there are
        # any changes.
        layer = self._pgbouncer_layer()
        services = container.get_plan().to_dict().get("services", {})
        if services != layer["services"]:
            container.add_layer(PGB, layer, combine=True)
            logging.info("Added layer 'pgbouncer' to pebble plan")
            container.restart(PGB)
            logging.info(f"restarted {PGB} service")
        self.unit.status = ActiveStatus()

    def _pgbouncer_layer(self) -> Layer:
        """Returns a default pebble config layer for the pgbouncer container.

        TODO auto-generate multiple pgbouncer services to make use of available cpu cores on unit.

        Returns:
            A pebble configuration layer for charm services.
        """
        return {
            "summary": "pgbouncer layer",
            "description": "pebble config layer for pgbouncer",
            "services": {
                PGB: {
                    "summary": "pgbouncer service",
                    "user": PG_USER,
                    "command": f"pgbouncer {INI_PATH}",
                    "startup": "enabled",
                    "override": "replace",
                }
            },
        }

    def _on_update_status(self, _) -> None:
        """Update Status hook.

        Sets BlockedStatus if we have no backend database; if we can't connect to a backend, this
        charm serves no purpose.

        TODO verify pgbouncer is actually running in this hook
        """
        if not self.backend_relation:
            self.unit.status = BlockedStatus("waiting for backend database relation")

    def _on_pgbouncer_pebble_ready(self, event: PebbleReadyEvent) -> None:
        """Define and start pgbouncer workload."""
        container = event.workload
        pebble_layer = self._pgbouncer_layer()
        container.add_layer(PGB, pebble_layer, combine=True)
        container.autostart()
        self.unit.status = ActiveStatus()

    # ===================================
    #  PgBouncer-Specific Utilities
    # ===================================

    def _render_pgb_config(self, config: PgbConfig, reload_pgbouncer=False) -> None:
        """Generate pgbouncer.ini from juju config and deploy it to the container.

        Args:
            config: PgbConfig object containing pgbouncer config.
            reload_pgbouncer: A boolean defining whether or not to reload the pgbouncer application
                in the container. When config files are updated, pgbouncer must be restarted for
                the changes to take effect. However, these config updates can be done in batches,
                minimising the amount of necessary restarts.
        """
        pgb_container = self.unit.get_container(PGB)
        if not pgb_container.can_connect():
            self.unit.status = WaitingStatus(
                "Unable to push config to container - container unavailable."
            )
            return

        pgb_container.push(
            INI_PATH,
            config.render(),
            user=PG_USER,
            permissions=0o600,
            make_dirs=True,
        )
        logging.info("pushed new pgbouncer.ini config file to pgbouncer container")

        if reload_pgbouncer:
            self._reload_pgbouncer()

    def read_pgb_config(self) -> PgbConfig:
        """Get config object from pgbouncer.ini file stored on container.

        Returns:
            PgbConfig object containing pgbouncer config.

        Raises:
            FileNotFoundError when the config at INI_PATH isn't available, such as if this is
            called before the charm has finished installing.
        """
        try:
            config = self._read_file(INI_PATH)
            return pgb.PgbConfig(config)
        except FileNotFoundError as e:
            logger.error("pgbouncer config not found")
            raise e

    def _render_userlist(self, userlist: Dict, reload_pgbouncer: bool = False) -> None:
        """Generate userlist.txt from the given userlist dict, and deploy it to the container.

        Args:
            userlist: a dictionary of usernames and passwords
            reload_pgbouncer: A boolean defining whether or not to reload the pgbouncer application
                in the container. When config files are updated, pgbouncer must be restarted for
                the changes to take effect. However, these config updates can be done in batches,
                minimising the amount of necessary restarts.
        """
        pgb_container = self.unit.get_container(PGB)
        if not pgb_container.can_connect():
            self.unit.status = WaitingStatus(
                "Unable to push config to container - container unavailable."
            )
            return

        pgb_container.push(
            USERLIST_PATH,
            pgb.generate_userlist(userlist),
            user=PG_USER,
            permissions=0o600,
            make_dirs=True,
        )
        logging.info("pushed new userlist to pgbouncer container")

        if reload_pgbouncer:
            self._reload_pgbouncer()

    def _read_userlist(self) -> Dict[str, str]:
        """Reads userlist.txt into a dictionary of strings."""
        return pgb.parse_userlist(self._read_file(USERLIST_PATH))

    def _reload_pgbouncer(self) -> None:
        """Reloads pgbouncer application.

        Pgbouncer will not apply configuration changes without reloading, so this must be called
        after each time config files are changed.
        """
        self.unit.status = MaintenanceStatus("Reloading Pgbouncer")
        logger.info("reloading pgbouncer application")
        pgb_container = self.unit.get_container(PGB)
        pgb_container.restart(PGB)
        self.unit.status = ActiveStatus("PgBouncer Reloaded")

    # =================
    #  User Management
    # =================

    def add_user(
        self,
        user: str,
        cfg: PgbConfig,
        password: str = None,
        admin: bool = False,
        stats: bool = False,
        reload_pgbouncer: bool = False,
        render_cfg: bool = False,
    ):
        """Adds a user.

        Users are added to userlist.txt and pgbouncer.ini config files

        Args:
            user: the username for the intended user
            cfg: A PgbConfig object. Modified during this method.
            password: intended password for the user
            admin: whether or not the user has admin permissions
            stats: whether or not the user has stats permissions
            reload_pgbouncer: whether or not to restart pgbouncer after changing config. Must be
                restarted for changes to take effect.
            render_cfg: whether or not to render config

        Raises:
            FileNotFoundError when userlist cannot be found.
        """
        userlist = self._read_userlist()

        # Userlist is key-value dict of users and passwords.
        if not password:
            password = pgb.generate_password()

        # Return early if user and password are already set to the correct values
        if userlist.get(user) == password:
            return

        userlist[user] = password
        self._render_userlist(userlist)

        if admin and (user not in cfg[PGB]["admin_users"]):
            cfg[PGB]["admin_users"].append(user)
        if stats and (user not in cfg[PGB]["stats_users"]):
            cfg[PGB]["stats_users"].append(user)

        if render_cfg:
            self._render_pgb_config(cfg, reload_pgbouncer)

    def remove_user(
        self,
        user: str,
        cfg: PgbConfig,
        reload_pgbouncer: bool = False,
        render_cfg: bool = False,
    ):
        """Removes a user from config files.

        Args:
            user: the username for the intended user.
            cfg: A PgbConfig object. Modified during this method.
            reload_pgbouncer: whether or not to restart pgbouncer after changing config. Must be
                restarted for changes to take effect.
            render_cfg: whether or not to render config

        Raises:
            FileNotFoundError when userlist can't be found.
        """
        userlist = self._read_userlist()

        if user in userlist.keys():
            del userlist[user]
            self._render_userlist(userlist)

        if user in cfg[PGB]["admin_users"]:
            cfg[PGB]["admin_users"].remove(user)
        if user in cfg[PGB]["stats_users"]:
            cfg[PGB]["stats_users"].remove(user)

        if render_cfg:
            self._render_pgb_config(cfg, reload_pgbouncer)

    # =====================
    #  K8s Charm Utilities
    # =====================

    def _read_file(self, filepath: str) -> str:
        """Reads file from pgbouncer container as a string.

        Args:
            filepath: the filepath to be read

        Returns:
            A string containing the file located at the given filepath.

        Raises:
            FileNotFoundError: if there is no file at the given path.
        """
        pgb_container = self.unit.get_container(PGB)
        if not pgb_container.can_connect():
            inaccessible = f"pgbouncer container not accessible, cannot find {filepath}"
            logger.info(inaccessible)
            raise FileNotFoundError(inaccessible)

        try:
            file_contents = pgb_container.pull(filepath).read()
        except FileNotFoundError as e:
            raise e
        except PathError as e:
            raise FileNotFoundError(str(e))
        return file_contents

    @property
    def backend_relation(self) -> Relation:
        """Returns the relation to the postgresql backend.

        Returns:
            Relation object for the backend relation.
        """
        backend_relation = self.model.get_relation(BACKEND_RELATION_NAME)
        if not backend_relation:
            return None
        else:
            return backend_relation

    @property
    def backend_relation_app_databag(self) -> Dict:
        """Wrapper around accessing the remote application databag for the backend relation."""
        backend_relation = self.backend_relation
        if not backend_relation:
            return None

        # Since we can trigger db-relation-changed on backend-changed,
        for entry in backend_relation.data:
            if isinstance(entry, Application) and entry != self.app:
                return self.backend_relation.data[entry]

    @property
    def backend_postgres(self) -> PostgreSQL:
        """Returns PostgreSQL representation of backend database, as defined in relation."""
        backend_relation = self.backend_relation
        if not backend_relation:
            return None

        backend_data = backend_relation.data[backend_relation.app]
        host = backend_data.get("endpoints").split(":")[0]
        user = backend_data.get("username")
        password = backend_data.get("password")
        database = backend_relation.data[self.app].get("database")

        return PostgreSQL(host=host, user=user, password=password, database=database)


if __name__ == "__main__":
    main(PgBouncerK8sCharm)
