#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed PgBouncer connection pooler."""

import hashlib
import logging
import secrets
import string
from typing import Dict

from ops.charm import ActionEvent, CharmBase, ConfigChangedEvent, PebbleReadyEvent
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, WaitingStatus
from ops.pebble import Layer, ConnectionError

logger = logging.getLogger(__name__)

INI_PATH = "/etc/pgbouncer/pgbouncer.ini"
USERLIST_PATH = "/etc/pgbouncer/userlist.txt"


class PgBouncerK8sCharm(CharmBase):
    """A class implementing charmed PgBouncer."""

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)

        self._pgbouncer_container = "pgbouncer"
        self._pgbouncer_user = "pgbouncer"

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.pgbouncer_pebble_ready, self._on_pgbouncer_pebble_ready)

        self.framework.observe(self.on.reload_pgbouncer_action, self._on_reload_pgbouncer_action)
        self.framework.observe(self.on.change_password_action, self._on_change_password_action)
        self.framework.observe(self.on.add_user_action, self._on_add_user_action)
        self.framework.observe(self.on.remove_user_action, self._on_remove_user_action)
        self.framework.observe(self.on.get_users_action, self._on_get_users_action)

    # =======================
    #  Charm Lifecycle Hooks
    # =======================

    def _on_install(self, _) -> None:
        """On install hook.

        This imports any users from the juju config, and initialises userlist and pgbouncer.ini
        config files that are essential for pgbouncer to run.
        """
        users = self._get_users_from_charm_config()
        #self._push_container_config(users)

    def _on_config_changed(self, event: ConfigChangedEvent) -> None:
        """Handle changes in configuration."""
        container = self.unit.get_container(self._pgbouncer_container)
        if not container.can_connect():
            self.unit.status = WaitingStatus(
                f"waiting for {self._pgbouncer_container} workload container."
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
            container.add_layer(self._pgbouncer_container, layer, combine=True)
            logging.info(f"Added layer '{self._pgbouncer_container}' to pebble plan")
            container.restart(self._pgbouncer_container)
            logging.info(f"restarted {self._pgbouncer_container} service")
        self.unit.status = ActiveStatus()

    def _pgbouncer_layer(self) -> Layer:
        """Returns a default pebble config layer for the pgbouncer container."""
        return {
            "summary": "pgbouncer layer",
            "description": "pebble config layer for pgbouncer",
            "services": {
                self._pgbouncer_container: {
                    "summary": "pgbouncer service",
                    "user": self._pgbouncer_user,
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
        container.add_layer(self._pgbouncer_container, pebble_layer, combine=True)
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

    def _on_change_password_action(self, event: ActionEvent) -> None:
        """An action to update the password for a specific user.

        Currently passwords are hashed using md5.

        Args:
            event: ActionEvent containing a "username" parameter, defining the user whose password
                will be modified, and a "password" parameter, defining the new password.
        """
        username = event.params["username"]
        # Get users from pgbouncer container and check that the given username doesn't exist.
        users = self._get_userlist_from_container()
        if username not in users.keys():
            event.set_results(
                {
                    "result": f"user {username} does not exist - use the get-users action to list existing users."
                }
            )
            return

        users[username] = self._hash(event.params["password"])
        self._push_container_config(users=users)
        event.set_results({"result": f"password updated for user {username}"})

    def _on_add_user_action(self, event: ActionEvent) -> None:
        """Event handler for add-user action.

        Currently passwords are hashed using md5.

        Args:
            event: ActionEvent containing a "username" parameter, defining the user to be added,
                and a "password" parameter, defining the user's password.
        """
        username = event.params["username"]
        # Get users from pgbouncer container and check that the given username doesn't exist.
        users = self._get_userlist_from_container()
        if username in users.keys():
            event.set_results({"result": f"user {username} already exists"})
            return

        users[username] = self._hash(event.params["password"])
        self._push_container_config(users)
        event.set_results({"result": f"new user {username} added"})

    def _on_remove_user_action(self, event: ActionEvent) -> None:
        """Event handler for remove-user action.

        As of now, this only removes the user from userlist.txt, and not the juju config.
        Therefore, users defined in the juju config are reinstated with a generated password next
        time userlist.txt is generated from local config, causing the user to persist. It remains
        inaccessible due to the new password. To remove this user, it must also be removed from
        the config.

        Args:
            event: ActionEvent containing a "username" parameter, defining the user to be removed.
        """
        username = event.params["username"]
        # Get users from pgbouncer container and check that the given username doesn't exist.
        users = self._get_userlist_from_container()
        if username not in users:
            event.set_results({"result": f"user {username} does not exist"})
            return

        # Remove user from local userlist variable and render updated userlist.txt to container
        del users[username]
        self._push_container_config(users=users)
        event.set_results({"result": f"user {username} removed"})

    def _on_get_users_action(self, event: ActionEvent) -> None:
        """Event handler for get-users action.

        Prints a space-separated list of existing usernames from pgbouncer.ini
        """
        users = self._get_userlist_from_container()
        event.set_results({"result": " ".join(users.keys())})

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

        pgb_container = self.unit.get_container(self._pgbouncer_container)
        pgbouncer_ini = self._generate_pgbouncer_ini(users)

        try:
            # Check that we're not updating this file unnecessarily
            if pgb_container.pull(INI_PATH).read() == pgbouncer_ini:
                logger.info("updated config does not modify existing pgbouncer config")
                return
        except (FileNotFoundError,ConnectionError):
            # There is no existing pgbouncer.ini file, so carry on and add one.
            pass

        pgb_container.push(
            INI_PATH,
            pgbouncer_ini,
            user=self._pgbouncer_user,
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

        return f"""[databases]
{self.config["pgb_databases"]}

[pgbouncer]
listen_port = {self.config["pgb_listen_port"]}
listen_addr = {self.config["pgb_listen_address"]}
auth_type = md5
auth_file = userlist.txt
logfile = pgbouncer.log
pidfile = pgbouncer.pid
admin_users = {",".join(users.keys())}"""

    def _push_userlist(self, users: Dict = None, reload_pgbouncer: bool = False) -> None:
        """Generate userlist.txt from the given userlist dict, and deploy it to the container.

        Args:
            users: a dictionary of usernames and passwords
            reload_pgbouncer: A boolean defining whether or not to reload the pgbouncer application
                in the container. When config files are updated, pgbouncer must be restarted for
                the changes to take effect. However, these config updates can be done in batches,
                minimising the amount of necessary restarts.
        """
        pgb_container = self.unit.get_container(self._pgbouncer_container)
        if users is None:
            users = self._get_userlist_from_container()
        userlist = self._generate_userlist(users)

        try:
            # Check that we're not updating this file unnecessarily
            if pgb_container.pull(USERLIST_PATH).read() == userlist:
                logger.info("updated userlist does not modify existing pgbouncer userlist")
                return
        except (FileNotFoundError,ConnectionError):
            # there is no existing userlist.txt file, so carry on and add one.
            pass

        pgb_container.push(
            USERLIST_PATH,
            userlist,
            user=self._pgbouncer_user,
            permissions=0o600,
            make_dirs=True,
        )
        logging.info("pushed new userlist to pgbouncer container")

        if reload_pgbouncer:
            self._reload_pgbouncer()

    def _generate_userlist(self, users: Dict[str, str]) -> str:
        """Generate userlist.txt from the given dictionary of usernames:passwords.

        Args:
            users: a dictionary of usernames and passwords
        Returns:
            A multiline string, containing each pair of usernames and passwords separated by a
            space, one pair per line.
        """
        return "\n".join([f'"{username}" "{password}"' for username, password in users.items()])

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
                users[admin_user] = self._hash(self._generate_password())
        return users

    def _get_userlist_from_container(self) -> Dict[str, str]:
        """Parses container userlist to a dict.

        This parses the userlist.txt stored on the container into a dictionary of strings, where
        the users are the keys and hashed passwords are the values.

        Returns:
            users: a dictionary of usernames and passwords
        """
        pgb_container = self.unit.get_container(self._pgbouncer_container)
        if not pgb_container.can_connect():
            logger.info("pgbouncer container not accessible, cannot access userlist")
            return {}

        try:
            userlist = pgb_container.pull(USERLIST_PATH).read()
        except FileNotFoundError:
            # There is no existing userlist.txt file, so return an empty dict
            return {}

        parsed_userlist = {}
        for line in userlist.split("\n"):
            if line.strip() == "":
                continue
            # Userlist is formatted "{username}" "{password}""
            username, password = line.replace('"', "").split(" ")
            parsed_userlist[username] = password

        return parsed_userlist

    def _generate_password(self) -> str:
        """Generates a secure password.

        Returns:
            A random 24-character string of letters and numbers.
        """
        choices = string.ascii_letters + string.digits
        return "".join([secrets.choice(choices) for _ in range(24)])

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
