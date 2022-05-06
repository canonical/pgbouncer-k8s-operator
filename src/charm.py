#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed PgBouncer connection pooler."""

import hashlib
import logging
import secrets
import string
from typing import Dict

from charms.pgbouncer_operator.v0 import pgb
from ops.charm import ActionEvent, CharmBase, ConfigChangedEvent, PebbleReadyEvent
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, WaitingStatus
from ops.pebble import Layer

logger = logging.getLogger(__name__)

PGB = "pgbouncer"
PGB_USER = PGB
PGB_DIR = "/etc/pgbouncer"
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

        self.framework.observe(self.on.reload_pgbouncer_action, self._on_reload_pgbouncer_action)

    # =======================
    #  Charm Lifecycle Hooks
    # =======================

    def _on_install(self, _) -> None:
        """On install hook.

        This imports any users from the juju config, and initialises userlist and pgbouncer.ini
        config files that are essential for pgbouncer to run.
        """
        users = self._get_users_from_charm_config()
        self._push_container_config(users)

    def _on_config_changed(self, event: ConfigChangedEvent) -> None:
        """Handle changes in configuration."""
        container = self.unit.get_container(PGB)
        if not container.can_connect():
            self.unit.status = WaitingStatus(
                f"waiting for pgbouncer workload container."
            )
            event.defer()
            return

        # Handle any user changes that may have been created through charm config.
        users = self._get_userlist_from_container()
        users = self._get_users_from_charm_config(users)
        self._push_container_config(users)

        # Create an updated pebble layer for the pgbouncer container, and apply it if there are
        # any changes.
        layer = self._pgbouncer_layer()
        services = container.get_plan().to_dict().get("services", {})
        if services != layer["services"]:
            container.add_layer(PGB, layer, combine=True)
            logging.info(f"Added layer 'pgbouncer' to pebble plan")
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
                    "user": PGB_USER,
                    "command": f"pgbouncer {INI_PATH}",
                    "startup": "enabled",
                    "override": "replace",
                    "environment": {
                        "PGB_DATABASES": self.config["pgb_databases"],
                        "PGB_LISTEN_PORT": self.config["pgb_listen_port"],
                        "PGB_LISTEN_ADDRESS": self.config["pgb_listen_address"],
                        "PGB_ADMIN_USERS": self.config["pgb_admin_users"],
                    },
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

    # ====================
    #  Charm Action Hooks
    # ====================

    def _on_reload_pgbouncer_action(self, event: ActionEvent) -> None:
        """An action to explicitly reload pgbouncer application.

        It should be made obvious to the user that this does not restart the container nor the
        charm - it *only* restarts the application itself.
        """
        self._reload_pgbouncer()
        event.set_results({"result": "pgbouncer application has restarted"})

    # ===================================
    #  User management support functions
    # ===================================

    def _push_container_config(self, users: Dict[str, str] = None) -> None:
        """Updates config files stored on pgbouncer container and reloads application.

        Updates userlist.txt and pgbouncer.ini config files, reloading pgbouncer application once
        updated.

        Args:
            users: a dictionary of usernames and passwords
        """
        if users is None:
            users = self._get_userlist_from_container()
        else:
            self._push_userlist(users)

        self._push_pgbouncer_ini(users, reload_pgbouncer=True)

    def _push_pgbouncer_ini(self, users: Dict[str, str] = None, reload_pgbouncer=False) -> None:
        """Generate pgbouncer.ini from juju config and deploy it to the container.

        Args:
            users: a dictionary of usernames and passwords
            reload_pgbouncer: A boolean defining whether or not to reload the pgbouncer application
                in the container. When config files are updated, pgbouncer must be restarted for
                the changes to take effect. However, these config updates can be done in batches,
                minimising the amount of necessary restarts.
        """
        if users is None:
            users = self._get_userlist_from_container()

        pgb_container = self.unit.get_container(PGB)
        pgbouncer_ini = self._generate_pgbouncer_ini(users)

        try:
            # Check that we're not updating this file unnecessarily
            if pgb_container.pull(INI_PATH).read() == pgbouncer_ini:
                logger.info("updated config does not modify existing pgbouncer config")
                return
        except FileNotFoundError:
            # There is no existing pgbouncer.ini file, so carry on and add one.
            pass

        pgb_container.push(
            INI_PATH,
            pgbouncer_ini,
            user=PGB_USER,
            permissions=0o600,
            make_dirs=True,
        )
        logging.info("pushed new pgbouncer.ini config file to pgbouncer container")

        if reload_pgbouncer:
            self._reload_pgbouncer()

    def _generate_pgbouncer_ini(self, users: Dict = None) -> str:
        """Generate pgbouncer.ini from config.

        This is a basic stub method, and will be updated in future to generate more complex
        pgbouncer.ini files in a more sophisticated way.

        Args:
            users: a dictionary of usernames and passwords
        Returns:
            A multiline string defining a valid pgbouncer.ini file
        """
        if users is None:
            users = self._get_userlist_from_container()

        cfg = pgb.PgbConfig(pgb.DEFAULT_CONFIG)
        cfg[PGB]["admin_users"] = ",".join(users.keys())
        cfg[PGB]["listen_port"] = str(self.config["pgb_listen_port"])
        cfg[PGB]["listen_addr"] = self.config["pgb_listen_address"]
        return cfg.render()

    def _push_userlist(self, users: Dict = None, reload_pgbouncer: bool = False) -> None:
        """Generate userlist.txt from the given userlist dict, and deploy it to the container.

        Args:
            users: a dictionary of usernames and passwords
            reload_pgbouncer: A boolean defining whether or not to reload the pgbouncer application
                in the container. When config files are updated, pgbouncer must be restarted for
                the changes to take effect. However, these config updates can be done in batches,
                minimising the amount of necessary restarts.
        """
        pgb_container = self.unit.get_container(PGB)
        if users is None:
            users = self._get_userlist_from_container()
        userlist = pgb.generate_userlist(users)

        try:
            # Check that we're not updating this file unnecessarily
            if pgb_container.pull(USERLIST_PATH).read() == userlist:
                logger.info("updated userlist does not modify existing pgbouncer userlist")
                return
        except FileNotFoundError:
            # there is no existing userlist.txt file, so carry on and add one.
            pass

        pgb_container.push(
            USERLIST_PATH,
            userlist,
            user=PGB_USER,
            permissions=0o600,
            make_dirs=True,
        )
        logging.info("pushed new userlist to pgbouncer container")

        if reload_pgbouncer:
            self._reload_pgbouncer()

    def _get_users_from_charm_config(self, users: Dict[str, str] = {}) -> Dict[str, str]:
        """Imports users from charm config and generates passwords when necessary.

        When generated, passwords are hashed using md5.

        Args:
            users: an existing dictionary of usernames and passwords
        Returns:
            the `users` dictionary, with usernames from charm config and corresponding generated
            passwords appended.
        """
        for admin_user in self.config["pgb_admin_users"].split(","):
            if admin_user not in users or users[admin_user] is None:
                users[admin_user] = self._hash(pgb.generate_password())
        return users

    def _get_userlist_from_container(self) -> Dict[str, str]:
        """Parses container userlist to a dict.

        This parses the userlist.txt stored on the container into a dictionary of strings, where
        the users are the keys and hashed passwords are the values.

        Returns:
            users: a dictionary of usernames and passwords
        """
        pgb_container = self.unit.get_container(PGB)
        if not pgb_container.can_connect():
            logger.info("pgbouncer container not accessible, cannot access userlist")
            return {}

        try:
            userlist = pgb_container.pull(USERLIST_PATH).read()
        except FileNotFoundError:
            # There is no existing userlist.txt file, so return an empty dict
            return {}
        return pgb.parse_userlist(userlist)

    def _hash(self, string: str) -> str:
        """Returns a hash of the given string.

        Currently only implements md5
        """
        return hashlib.md5(string.encode()).hexdigest()

    # =================================================
    #  PgBouncer service management / health functions
    # =================================================

    def _reload_pgbouncer(self) -> None:
        """Reloads pgbouncer application.

        Pgbouncer will not apply configuration changes without reloading, so this must be called
        after each time config files are changed.
        TODO implement function stub
        """
        logger.info("reloading pgbouncer application")
        pass


if __name__ == "__main__":
    main(PgBouncerK8sCharm)
