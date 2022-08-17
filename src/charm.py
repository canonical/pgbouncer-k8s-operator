#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed PgBouncer connection pooler."""


import logging
import os
import socket

from charms.pgbouncer_k8s.v0 import pgb
from charms.pgbouncer_k8s.v0.pgb import PgbConfig
from ops.charm import CharmBase, ConfigChangedEvent, PebbleReadyEvent, StartEvent
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import Layer, PathError

from relations.backend_database import BackendDatabaseRequires
from relations.db import DbProvides

logger = logging.getLogger(__name__)

PGB = "pgbouncer"
PG_USER = "postgres"
PGB_DIR = "/var/lib/postgresql/pgbouncer"
INI_PATH = f"{PGB_DIR}/pgbouncer.ini"


class PgBouncerK8sCharm(CharmBase):
    """A class implementing charmed PgBouncer."""

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)

        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.pgbouncer_pebble_ready, self._on_pgbouncer_pebble_ready)

        self.backend = BackendDatabaseRequires(self)
        self.legacy_db_relation = DbProvides(self, admin=False)
        self.legacy_db_admin_relation = DbProvides(self, admin=True)

        self._cores = os.cpu_count()

    # =======================
    #  Charm Lifecycle Hooks
    # =======================

    def _on_start(self, event: StartEvent) -> None:
        """Renders basic PGB config."""
        container = self.unit.get_container(PGB)
        if not container.can_connect():
            logger.debug(
                "pgbouncer config could not be rendered, waiting for container to be available."
            )
            event.defer()
            return

        self.render_pgb_config(PgbConfig(pgb.DEFAULT_CONFIG))

    def _on_config_changed(self, event: ConfigChangedEvent) -> None:
        """Handle changes in configuration."""
        container = self.unit.get_container(PGB)
        if not container.can_connect():
            wait_msg = "waiting for pgbouncer workload container."
            logger.debug(wait_msg)
            self.unit.status = WaitingStatus(wait_msg)
            event.defer()
            return

        try:
            config = self.read_pgb_config()
        except FileNotFoundError as err:
            config_err_msg = f"Unable to read config, error: {err}"
            logger.warning(config_err_msg)
            self.unit.status = WaitingStatus(config_err_msg)
            event.defer()
            return

        config["pgbouncer"]["pool_mode"] = self.config["pool_mode"]
        config.set_max_db_connection_derivatives(
            self.config["max_db_connections"],
            self._cores,
        )

        if config["pgbouncer"]["listen_port"] != self.config["listen_port"]:
            # This emits relation-changed events to every client relation, so only do it when
            # necessary
            self.update_backend_relation_port(self.config["listen_port"])
            config["pgbouncer"]["listen_port"] = self.config["listen_port"]

        self.render_pgb_config(config)

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
                    # -R flag reuses sockets on restart
                    "command": f"pgbouncer -R -v {INI_PATH}",
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
        if self.backend.postgres is None:
            self.unit.status = BlockedStatus("waiting for backend database relation to initialise")

    def _on_pgbouncer_pebble_ready(self, event: PebbleReadyEvent) -> None:
        """Define and start pgbouncer workload."""
        try:
            # Check config is available before running pgbouncer.
            self.read_pgb_config()
        except FileNotFoundError as err:
            # TODO this may need to change to a Blocked or Error status, depending on why the
            # config can't be found.
            config_err_msg = f"Unable to read config, error: {err}"
            logger.warning(config_err_msg)
            self.unit.status = WaitingStatus(config_err_msg)
            event.defer()
            return

        container = event.workload
        pebble_layer = self._pgbouncer_layer()

        container.add_layer(PGB, pebble_layer, combine=True)
        container.autostart()
        self.unit.status = ActiveStatus()

    # =============================
    #  PgBouncer Config Management
    # =============================

    def render_pgb_config(self, config: PgbConfig, reload_pgbouncer=False) -> None:
        """Generate pgbouncer.ini from juju config and deploy it to the container.

        Args:
            config: PgbConfig object containing pgbouncer config.
            reload_pgbouncer: A boolean defining whether or not to reload the pgbouncer application
                in the container. When config files are updated, pgbouncer must be restarted for
                the changes to take effect. However, these config updates can be done in batches,
                minimising the amount of necessary restarts.
        """
        self.push_file(INI_PATH, config.render(), 0o400)
        logger.info("pushed new pgbouncer.ini config file to pgbouncer container")

        if reload_pgbouncer:
            self._reload_pgbouncer()

    def push_file(self, path, file_contents, perms):
        """Pushes file_contents to path, with the given permissions."""
        pgb_container = self.unit.get_container(PGB)
        if not pgb_container.can_connect():
            logger.warning("unable to connect to container")
            self.unit.status = WaitingStatus(
                "Unable to push config to container - container unavailable."
            )
            return

        pgb_container.push(
            path,
            file_contents,
            user=PG_USER,
            permissions=perms,
            make_dirs=True,
        )

    def delete_file(self, path):
        """Deletes the file at `path`."""
        pgb_container = self.unit.get_container(PGB)
        if not pgb_container.can_connect():
            logger.warning("unable to connect to container")
            self.unit.status = WaitingStatus(
                "Unable to delete file from container - container unavailable."
            )
            return

        pgb_container.remove_path(path)

    def read_pgb_config(self) -> PgbConfig:
        """Get config object from pgbouncer.ini file stored on container.

        Returns:
            PgbConfig object containing pgbouncer config.

        Raises:
            FileNotFoundError when the config at INI_PATH isn't available, such as if this is
            called before the charm has started.
        """
        config = self._read_file(INI_PATH)
        return pgb.PgbConfig(config)

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
            logger.error(inaccessible)
            raise FileNotFoundError(inaccessible)

        try:
            file_contents = pgb_container.pull(filepath).read()
        except FileNotFoundError as e:
            raise e
        except PathError as e:
            raise FileNotFoundError(str(e))
        return file_contents

    # =====================
    #  Relation Utilities
    # =====================

    def update_backend_relation_port(self, port):
        """Update ports in backend relations to match updated pgbouncer port.

        TODO this method and the two below it are weird, fix them up
        """
        # Skip updates if backend.postgres doesn't exist yet.
        if not self.backend.postgres:
            return

        for relation in self.model.relations.get("db", []):
            self.legacy_db_relation.update_port(relation, port)

        for relation in self.model.relations.get("db-admin", []):
            self.legacy_db_admin_relation.update_port(relation, port)

    def update_postgres_endpoints(self, reload_pgbouncer):
        """Update postgres endpoints in relation config values."""
        # Skip updates if backend.postgres doesn't exist yet.
        if not self.backend.postgres:
            return

        for relation in self.model.relations.get("db", []):
            self.legacy_db_relation.update_postgres_endpoints(relation, reload_pgbouncer=False)

        for relation in self.model.relations.get("db-admin", []):
            self.legacy_db_admin_relation.update_postgres_endpoints(
                relation, reload_pgbouncer=False
            )

        if reload_pgbouncer:
            self._reload_pgbouncer()

    def remove_postgres_endpoints(self, reload_pgbouncer):
        """Update postgres endpoints in relation config values."""
        # Skip updates if backend.postgres doesn't exist yet.
        if not self.backend.postgres:
            return

        for relation in self.model.relations.get("db", []):
            self.legacy_db_relation.remove_postgres_endpoints(relation, reload_pgbouncer=False)

        for relation in self.model.relations.get("db-admin", []):
            self.legacy_db_admin_relation.remove_postgres_endpoints(
                relation, reload_pgbouncer=False
            )

        if reload_pgbouncer:
            self._reload_pgbouncer()

    @property
    def unit_pod_hostname(self, name="") -> str:
        """Creates the pod hostname from its name."""
        return socket.getfqdn(name)


if __name__ == "__main__":
    main(PgBouncerK8sCharm)
