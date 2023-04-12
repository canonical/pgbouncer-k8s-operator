#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed PgBouncer connection pooler."""


import logging
import os
import socket
from typing import Optional

from charms.pgbouncer_k8s.v0 import pgb
from charms.pgbouncer_k8s.v0.pgb import PgbConfig
from charms.postgresql_k8s.v0.postgresql_tls import PostgreSQLTLS
from ops.charm import CharmBase, ConfigChangedEvent, PebbleReadyEvent, StartEvent
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.pebble import ConnectionError, Layer, PathError, ServiceStatus

from constants import (
    AUTH_FILE_PATH,
    CLIENT_RELATION_NAME,
    INI_PATH,
    PEER_RELATION_NAME,
    PG_GROUP,
    PG_USER,
    PGB,
    PGB_DIR,
    TLS_CA_FILE,
    TLS_CERT_FILE,
    TLS_KEY_FILE,
)
from relations.backend_database import BackendDatabaseRequires
from relations.db import DbProvides
from relations.peers import Peers
from relations.pgbouncer_provider import PgBouncerProvider

logger = logging.getLogger(__name__)


class PgBouncerK8sCharm(CharmBase):
    """A class implementing charmed PgBouncer."""

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)

        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.pgbouncer_pebble_ready, self._on_pgbouncer_pebble_ready)
        self.framework.observe(self.on.update_status, self._on_update_status)

        self.peers = Peers(self)
        self.backend = BackendDatabaseRequires(self)
        self.client_relation = PgBouncerProvider(self)
        self.legacy_db_relation = DbProvides(self, admin=False)
        self.legacy_db_admin_relation = DbProvides(self, admin=True)
        self.tls = PostgreSQLTLS(self, PEER_RELATION_NAME, [self.unit_pod_hostname])

        self._cores = os.cpu_count()
        self._services = [
            {
                "name": f"{PGB}_{service_id}",
                "id": service_id,
                "dir": f"{PGB_DIR}/instance_{service_id}",
                "ini_path": f"{PGB_DIR}/instance_{service_id}/pgbouncer.ini",
            }
            for service_id in range(self._cores)
        ]

    # =======================
    #  Charm Lifecycle Hooks
    # =======================

    def _on_start(self, event: StartEvent) -> None:
        """Renders basic PGB config.

        Deferrals:
            - If pgbouncer container cannot connect, since this makes rendering config impossible.
            - If config is unavailable in filesystem or peer databag, and this unit isn't the
              leader, and therefore can't generate a default config.
            - When we try and update relation endpoints, and pebble throws an error, implying that
              it hasn't started yet.
        """
        container = self.unit.get_container(PGB)
        if not container.can_connect():
            logger.debug("pgbouncer container unavailable, deferring start hook...")
            event.defer()
            return

        config = None
        try:
            # Try and get pgb config. If it only exists in the peer databag, pull it and write it
            # to filesystem.
            config = self.read_pgb_config()
        except FileNotFoundError:
            config = self.peers.get_cfg()

        if not config:
            if self.unit.is_leader():
                # If there's no config in the container or the peer databag, the leader creates a
                # default
                config = PgbConfig(pgb.DEFAULT_CONFIG)
            else:
                # follower units wait for the leader to define a config.
                event.defer()
                return

        # Initialise filesystem - _push_file()'s make_dirs option sets the permissions for those
        # dirs to root, so we build them ourselves to control permissions.
        for service in self._services:
            if not container.exists(service["dir"]):
                container.make_dir(
                    service["dir"],
                    make_parents=True,
                    user=PG_USER,
                    group=PG_USER,
                    permissions=0o700,
                )

        self.render_pgb_config(config)

        try:
            # Update postgres endpoints in config to match the current state of the charm.
            self.update_postgres_endpoints(reload_pgbouncer=True)
        except ConnectionError:
            # pebble_ready hook not fired yet, so defer.
            event.defer()

    @property
    def version(self) -> str:
        """Returns the version Pgbouncer."""
        container = self.unit.get_container(PGB)
        if container.can_connect():
            try:
                output, _ = container.exec(
                    ["pgbouncer", "--version"], user=PG_USER, group=PG_USER
                ).wait_output()
                if output:
                    return output.split("\n")[0].split(" ")[1]
            except Exception:
                logger.exception("Unable to get Pgbouncer version")
                return ""
        return ""

    def _on_pgbouncer_pebble_ready(self, event: PebbleReadyEvent) -> None:
        """Define and start pgbouncer workload.

        Deferrals:
            - If pgbouncer config is not available in container filesystem, ensuring this fires
              after start hook. This is likely unnecessary, and these hooks could be merged.
            - If checking pgb running raises an error, implying that the pgbouncer services are not
              yet accessible in the container.
            - If the unit is waiting for certificates to be issued
        """
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

        tls_enabled = all(self.tls.get_tls_files())
        if self.model.relations.get("certificates", []) and not tls_enabled:
            logger.debug(
                "pgbouncer_pebble_ready: Deferring as certificates files are not yet populated for existing certificates relation"
            )
            self.unit.status = WaitingStatus("Waiting for certificates")
            event.defer()
            return
        # in case of pod restart
        elif tls_enabled:
            self.push_tls_files_to_workload(False)

        container = event.workload
        pebble_layer = self._pgbouncer_layer()
        container.add_layer(PGB, pebble_layer, combine=True)
        container.autostart()

        try:
            if self.check_pgb_running():
                self.unit.status = ActiveStatus()
        except ConnectionError:
            not_running = "pgbouncer not running"
            logger.error(not_running)
            self.unit.status = WaitingStatus(not_running)
            event.defer()

        self.unit.set_workload_version(self.version)

    def _on_config_changed(self, event: ConfigChangedEvent) -> None:
        """Handle changes in configuration.

        Deferrals:
            - If pgb config is unavailable
            - If reloading the pgbouncer pebble service throws a ConnectionError (Implying that
              the pebble service is not yet ready)
        """
        if not self.unit.is_leader():
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
            self.update_client_connection_info(self.config["listen_port"])
            config["pgbouncer"]["listen_port"] = self.config["listen_port"]

        self.render_pgb_config(config)
        try:
            if self.check_pgb_running():
                self.reload_pgbouncer()
        except ConnectionError:
            event.defer()

    def _pgbouncer_layer(self) -> Layer:
        """Returns a default pebble config layer for the pgbouncer container.

        Since PgBouncer is single-threaded, we auto-generate multiple pgbouncer services to make
        use of all the available cpu cores on a unit. This necessitates that we have separate
        directories for each instance, since otherwise pidfiles and logfiles will conflict. Ports
        are reused by setting "so_reuseport=1" in the pgbouncer config. This is enabled by default
        in pgb.DEFAULT_CONFIG.

        When viewing logs (including exporting them to COS), use the pebble service logs, rather
        than viewing individual logfiles.

        Returns:
            A pebble configuration layer for as many charm services as there are available CPU
            cores
        """
        pebble_services = {}
        for service in self._services:
            pebble_services[service["name"]] = {
                "summary": f"pgbouncer service {service['id']}",
                "user": PG_USER,
                "group": PG_GROUP,
                # -R flag reuses sockets on restart
                "command": f"pgbouncer -R {service['ini_path']}",
                "startup": "enabled",
                "override": "replace",
            }

        return {
            "summary": "pgbouncer layer",
            "description": "pebble config layer for pgbouncer",
            "services": pebble_services,
        }

    def _on_update_status(self, _) -> None:
        """Update Status hook.

        Sets BlockedStatus if we have no backend database; if we can't connect to a backend, this
        charm serves no purpose.
        """
        self.update_status()

        self.peers.update_leader()

        # Update relation connection information. This is necessary because we don't receive any
        # information when the leader is removed, but we still need to have up-to-date connection
        # information in all the relation databags.
        self.update_client_connection_info()

    def update_status(self):
        """Health check to update pgbouncer status based on charm state."""
        if self.backend.postgres is None:
            self.unit.status = BlockedStatus("waiting for backend database relation to initialise")
            return

        if not self.backend.ready:
            self.unit.status = BlockedStatus("backend database relation not ready")
            return

        try:
            if self.check_pgb_running():
                self.unit.status = ActiveStatus()
        except ConnectionError:
            not_running = "pgbouncer not running"
            logger.error(not_running)
            self.unit.status = WaitingStatus(not_running)

    def reload_pgbouncer(self) -> None:
        """Reloads pgbouncer application.

        Pgbouncer will not apply configuration changes without reloading, so this must be called
        after each time config files are changed.

        Raises:
            ops.pebble.ConnectionError if pgb service isn't accessible
        """
        logger.info("reloading pgbouncer application")

        pgb_container = self.unit.get_container(PGB)
        pebble_services = pgb_container.get_services()
        for service in self._services:
            if service["name"] not in pebble_services.keys():
                # pebble_ready event hasn't fired so pgbouncer has not been added to pebble config
                raise ConnectionError
            pgb_container.restart(service["name"])

        self.check_pgb_running()

    def check_pgb_running(self):
        """Checks that pgbouncer pebble service is running, and updates status accordingly."""
        pgb_container_unavailable = "PgBouncer container currently unavailable"
        pgb_container = self.unit.get_container(PGB)
        if not pgb_container.can_connect():
            self.unit.status = BlockedStatus(pgb_container_unavailable)
            logger.error(pgb_container_unavailable)
            return False

        pebble_services = pgb_container.get_services()
        for service in self._services:
            if service["name"] not in pebble_services.keys():
                # pebble_ready event hasn't fired so pgbouncer layer has not been added to pebble
                raise ConnectionError
            pgb_service_status = pgb_container.get_services().get(service["name"]).current
            if pgb_service_status != ServiceStatus.ACTIVE:
                pgb_not_running = f"PgBouncer service {service['name']} not running: service status = {pgb_service_status}"
                self.unit.status = BlockedStatus(pgb_not_running)
                logger.error(pgb_not_running)
                return False

        return True

    def get_hostname_by_unit(self, unit_name: str) -> str:
        """Create a DNS name for a PgBouncer unit.

        Args:
            unit_name: the juju unit name, e.g. "pgbouncer-k8s/1".

        Returns:
            A string representing the hostname of the PgBouncer unit.
        """
        unit_id = unit_name.split("/")[1]
        return f"{self.app.name}-{unit_id}.{self.app.name}-endpoints"

    def get_secret(self, scope: str, key: str) -> Optional[str]:
        """Get secret from the secret storage."""
        return self.peers.get_secret(scope, key)

    def set_secret(self, scope: str, key: str, value: Optional[str]) -> None:
        """Set secret from the secret storage."""
        self.peers.set_secret(scope, key, value)

    def push_tls_files_to_workload(self, update_config: bool = True) -> None:
        """Uploads TLS files to the workload container."""
        key, ca, cert = self.tls.get_tls_files()
        if key is not None:
            self.push_file(
                f"{PGB_DIR}/{TLS_KEY_FILE}",
                key,
                0o400,
            )
        if ca is not None:
            self.push_file(
                f"{PGB_DIR}/{TLS_CA_FILE}",
                ca,
                0o400,
            )
        if cert is not None:
            self.push_file(
                f"{PGB_DIR}/{TLS_CERT_FILE}",
                cert,
                0o400,
            )
        if update_config:
            self.update_config()

    def update_config(self) -> None:
        """Updates PgBouncer config file based on the existence of the TLS files."""
        try:
            config = self.read_pgb_config()
        except FileNotFoundError as err:
            logger.warning(f"update_config: Unable to read config, error: {err}")
            return

        if all(self.tls.get_tls_files()):
            config["pgbouncer"]["client_tls_key_file"] = f"{PGB_DIR}/{TLS_KEY_FILE}"
            config["pgbouncer"]["client_tls_ca_file"] = f"{PGB_DIR}/{TLS_CA_FILE}"
            config["pgbouncer"]["client_tls_cert_file"] = f"{PGB_DIR}/{TLS_CERT_FILE}"
            config["pgbouncer"]["client_tls_sslmode"] = "prefer"
        else:
            # cleanup tls keys if present
            config["pgbouncer"].pop("client_tls_key_file", None)
            config["pgbouncer"].pop("client_tls_cert_file", None)
            config["pgbouncer"].pop("client_tls_ca_file", None)
            config["pgbouncer"].pop("client_tls_sslmode", None)
        self.render_pgb_config(config, True)

    # =============================
    #  File Management
    #  TODO: extract into new file
    # =============================

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
            group=PG_USER,
            permissions=perms,
            make_dirs=True,
        )

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
            FileNotFoundError when the config can't be found at INI_PATH, such as if this is called
            before the charm has started.
        """
        return pgb.PgbConfig(self._read_file(INI_PATH))

    def render_pgb_config(self, config: PgbConfig, reload_pgbouncer=False) -> None:
        """Generate pgbouncer.ini from juju config and deploy it to the container.

        Every time the config is rendered, `peers.update_cfg` is called. This updates the config in
        the peer databag if this unit is the leader, propagating the config file to all units,
        which will then update their local config, so each unit isn't figuring out its own config
        constantly. This is valuable because the leader unit is the only unit that can read app
        databags, so this information would have to be propagated to peers anyway. Therefore, it's
        most convenient to have a single source of truth for the whole config.

        Args:
            config: PgbConfig object containing pgbouncer config.
            reload_pgbouncer: A boolean defining whether or not to reload the pgbouncer application
                in the container. When config files are updated, pgbouncer must be restarted for
                the changes to take effect. However, these config updates can be done in batches,
                minimising the amount of necessary restarts.
        """
        try:
            if config == self.read_pgb_config():
                # Skip updating config if it's exactly the same as the existing config.
                return
        except FileNotFoundError:
            # config doesn't exist on local filesystem, so update it.
            pass

        self.peers.update_cfg(config)

        perm = 0o400
        for service in self._services:
            s_config = pgb.PgbConfig(config)
            s_config[PGB]["unix_socket_dir"] = service["dir"]
            s_config[PGB]["logfile"] = f"{service['dir']}/pgbouncer.log"
            s_config[PGB]["pidfile"] = f"{service['dir']}/pgbouncer.pid"
            self.push_file(service["ini_path"], s_config.render(), perm)
        self.push_file(INI_PATH, config.render(), perm)
        logger.info("pushed new pgbouncer.ini config files to pgbouncer container")

        if reload_pgbouncer:
            self.reload_pgbouncer()

    def read_auth_file(self) -> str:
        """Gets the auth file from the pgbouncer container filesystem."""
        return self._read_file(AUTH_FILE_PATH)

    def render_auth_file(self, auth_file: str, reload_pgbouncer=False):
        """Renders the given auth_file to the correct location."""
        self.push_file(AUTH_FILE_PATH, auth_file, 0o400)
        logger.info("pushed new auth file to pgbouncer container")

        self.peers.update_auth_file(auth_file)

        if reload_pgbouncer:
            self.reload_pgbouncer()

    # =====================
    #  Relation Utilities
    # =====================

    def update_client_connection_info(self, port: Optional[str] = None):
        """Update connection info in client relations.

        TODO rename
        """
        # Skip updates if backend.postgres doesn't exist yet.
        if not self.backend.postgres:
            return
        # if not self.backend.postgres.ready:
        #     return

        if not port:
            port = self.config["listen_port"]

        for relation in self.model.relations.get("db", []):
            self.legacy_db_relation.update_connection_info(relation, port)

        for relation in self.model.relations.get("db-admin", []):
            self.legacy_db_admin_relation.update_connection_info(relation, port)

        for relation in self.model.relations.get(CLIENT_RELATION_NAME, []):
            self.client_relation.update_connection_info(relation)

    def update_postgres_endpoints(self, reload_pgbouncer=False):
        """Update postgres endpoints in relation config values.

        TODO rename

        Raises:
            ops.pebble.ConnectionError if we can't connect to the pebble container.
        """
        # Skip updates if backend.postgres doesn't exist yet.
        if not self.backend.postgres or not self.unit.is_leader():
            return

        for relation in self.model.relations.get("db", []):
            self.legacy_db_relation.update_postgres_endpoints(relation, reload_pgbouncer=False)

        for relation in self.model.relations.get("db-admin", []):
            self.legacy_db_admin_relation.update_postgres_endpoints(
                relation, reload_pgbouncer=False
            )

        for relation in self.model.relations.get(CLIENT_RELATION_NAME, []):
            self.client_relation.update_postgres_endpoints(relation, reload_pgbouncer=False)

        if reload_pgbouncer:
            self.reload_pgbouncer()

    @property
    def unit_pod_hostname(self, name="") -> str:
        """Creates the pod hostname from its name."""
        return socket.getfqdn(name)

    @property
    def leader_hostname(self) -> str:
        """Gets leader hostname."""
        return self.peers.leader_hostname


if __name__ == "__main__":
    main(PgBouncerK8sCharm)
