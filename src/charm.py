#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed PgBouncer connection pooler."""


import logging
import os
from typing import Dict

from charms.pgbouncer_operator.v0 import pgb
from ops.charm import CharmBase, ConfigChangedEvent, PebbleReadyEvent
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import Layer

from relations.backend_db_admin import RELATION_ID as LEGACY_BACKEND_RELATION_ID
from relations.backend_db_admin import BackendDbAdminRequires

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

        self.legacy_backend_relation = BackendDbAdminRequires(self)

        self._cores = os.cpu_count()

    # =======================
    #  Charm Lifecycle Hooks
    # =======================

    def _on_install(self, _) -> None:
        """On install hook.

        This imports any users from the juju config, and initialises userlist and pgbouncer.ini
        config files that are essential for pgbouncer to run.
        """
        # Initialise pgbouncer.ini config files from defaults set in charm lib.
        config = pgb.PgbConfig(pgb.DEFAULT_CONFIG)
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

        config = self._read_pgb_config()
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

    def _render_pgb_config(self, config: pgb.PgbConfig, reload_pgbouncer=False) -> None:
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

    def _read_pgb_config(self) -> pgb.PgbConfig:
        """Get config object from pgbouncer.ini file stored on container.

        Returns:
            PgbConfig object containing pgbouncer config.
        """
        try:
            config = self._read_file(INI_PATH)
            return pgb.PgbConfig(config)
        except FileNotFoundError:
            logger.error("pgbouncer config not found")

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
        return file_contents


if __name__ == "__main__":
    main(PgBouncerK8sCharm)
