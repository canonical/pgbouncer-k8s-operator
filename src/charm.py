#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed PgBouncer connection pooler."""

import hashlib
import logging
import secrets
import string
from typing import Dict

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, WaitingStatus
from ops.pebble import Layer

logger = logging.getLogger(__name__)

INI_PATH = "/etc/pgbouncer/pgbouncer.ini"
USERLIST_PATH = "/etc/pgbouncer/userlist.txt"


class PgBouncerK8sCharm(CharmBase):
    """A class implementing charmed PgBouncer."""

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)

        self._pgbouncer_service = "pgbouncer"
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

        This imports any users from the juju config, and pushes the necessary config files to the
        container.
        """
        users = self._get_users_from_charm_config(users={})
        self._push_container_config(users)

    def _on_config_changed(self, _) -> None:
        """Handle changes in configuration."""
        # Handle any user changes that may have been created through config.
        users = self._get_userlist_from_container()
        users = self._get_users_from_charm_config(users=users)
        self._push_container_config(users)

        container = self.unit.get_container(self._pgbouncer_service)
        layer = self._pgbouncer_layer()

        if not container.can_connect():
            self.unit.status = WaitingStatus("waiting for pebble in pgbouncer workload container.")
            return

        services = container.get_plan().to_dict().get("services", {})
        if services != layer["services"]:
            container.add_layer(self._pgbouncer_service, layer, combine=True)
            logging.info("Added layer 'pgbouncer' to pebble plan")
            container.restart(self._pgbouncer_service)
            logging.info("restarted pgbouncer service")
        self.unit.status = ActiveStatus()

    def _pgbouncer_layer(self) -> Layer:
        """Returns a default pebble config layer for the pgbouncer container."""
        return {
            "summary": "pgbouncer layer",
            "description": "pebble config layer for pgbouncer",
            "services": {
                self._pgbouncer_service: {
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

    def _on_pgbouncer_pebble_ready(self, event) -> None:
        """Define and start pgbouncer workload."""
        container = event.workload
        pebble_layer = self._pgbouncer_layer()
        container.add_layer(self._pgbouncer_service, pebble_layer, combine=True)
        container.autostart()
        self.unit.status = ActiveStatus()

    # ====================
    #  Charm Action Hooks
    # ====================

    def _on_reload_pgbouncer_action(self, event) -> None:
        """An action to explicitly reload pgbouncer.

        TODO implement function stub
        """
        self._reload_pgbouncer()
        event.set_results({"result": "pgbouncer has restarted"})

    def _on_change_password_action(self, event) -> None:
        """An action to update the password for a specific user.

        TODO implement password encryption at this stage, before anything is stored.
        TODO verify passwords are valid
        """
        username = event.params["username"]
        users = self._get_userlist_from_container()
        if username not in users:
            event.set_results(
                {
                    "result": f"user {username} does not exist - use the get-users action to list existing users."
                }
            )
            return
        hash = hashlib.md5(event.params["password"].encode())
        users[username] = hash.hexdigest()
        self._push_container_config(users=users)
        event.set_results({"result": f"password updated for user {username}"})

    def _on_add_user_action(self, event) -> None:
        """Event handler for add-user action.

        TODO implement password encryption at this stage, before anything is ever stored.
        TODO verify passwords are valid
        """
        users = self._get_userlist_from_container()
        username = event.params["username"]
        if username in users:
            event.set_results({"result": f"user {username} already exists"})
            return

        hash = hashlib.md5(event.params["password"].encode())
        users[username] = hash.hexdigest()
        self._push_container_config(users=users)
        event.set_results({"result": f"new user {username} added"})

    def _on_remove_user_action(self, event) -> None:
        """Event handler for remove-user action.

        TODO This only removes the user from userlist.txt, and not from the juju config. Do we need
        to keep a list of users that have been deleted so they aren't re-added when the config
        updates? The password is updated, so the user is inaccessible, but it's still messy. The
        other option is to entirely remove user management from the charm config, since we can't
        edit that from charm code. Passwords still have to be configured manually using the action,
        and we can't add users to the charm config, so using the config isn't a perfect solution.
        This should use Juju Secrets once available.
        """
        users = self._get_userlist_from_container()
        username = event.params["username"]
        if username not in users:
            event.set_results({"result": f"user {username} does not exist"})
            return

        del users[username]
        self._push_container_config(users=users)
        event.set_results({"result": f"user {username} removed"})

    def _on_get_users_action(self, event) -> None:
        """Event handler for get-users action.

        Prints a space-separated list of existing usernames from pgbouncer.ini
        TODO until user deletion is more effective, we could also read users in from charm config
        and alert the charm admin to the existence of users that must be removed manually.
        """
        users = self._get_userlist_from_container()
        event.set_results({"result": " ".join(users.keys())})

    # ===================================
    #  User management support functions
    # ===================================

    def _push_container_config(self, users=None) -> None:
        """Updates config files stored on pgbouncer container and reloads application.

        Updates userlist.txt and pgbouncer.ini config files, reloading pgbouncer application once
        updated.

        Params:
            users: a dictionary of usernames and passwords
        """
        if users is None:
            users = self._get_userlist_from_container()
        else:
            self._push_userlist(users)

        self._push_pgbouncer_ini(users, reload_pgbouncer=True)

    def _push_pgbouncer_ini(self, users=None, reload_pgbouncer=False) -> None:
        """Generate pgbouncer.ini from juju config and deploy it to the container.

        Params:
            users: a dictionary of usernames and passwords
            reload_pgbouncer: A boolean defining whether or not to reload the pgbouncer application
                in the container. When config files are updated, pgbouncer must be restarted for
                the changes to take effect. However, these config updates can be done in batches,
                minimising the amount of necessary restarts.
        """
        if users is None:
            users = self._get_userlist_from_container()

        pgb_container = self.unit.get_container(self._pgbouncer_service)
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
            user=self._pgbouncer_user,
            permissions=0o600,
            make_dirs=True,
        )
        logging.info("pushed new pgbouncer.ini config file to pgbouncer container")

        if reload_pgbouncer:
            self._reload_pgbouncer()

    def _generate_pgbouncer_ini(self, users=None) -> str:
        """Generate pgbouncer.ini from config.

        This is a basic stub method, and will be updated in future to generate more complex
        pgbouncer.ini files in a more sophisticated way.

        TODO compare to real-world pgbouncer.ini files and devise a more sophisticated way of
        generating them. Look at the previous charm's implementation of this.
        TODO evaluate other user types, such as stat_users etc
        TODO define/parse databases based on relation to postgres - does it need to be an exposed
        config option?

        Params:
            users: a dictionary of usernames and passwords
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

    def _push_userlist(self, users=None, reload_pgbouncer=False) -> None:
        """Generate userlist.txt from the given userlist dict, and deploy it to the container.

        Params:
            users: a dictionary of usernames and passwords
            reload_pgbouncer: A boolean defining whether or not to reload the pgbouncer application
                in the container. When config files are updated, pgbouncer must be restarted for
                the changes to take effect. However, these config updates can be done in batches,
                minimising the amount of necessary restarts.
        """
        pgb_container = self.unit.get_container(self._pgbouncer_service)
        if users is None:
            users = self._get_userlist_from_container()
        userlist = self._generate_userlist(users)

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
            user=self._pgbouncer_user,
            permissions=0o600,
            make_dirs=True,
        )
        logging.info("pushed new userlist to pgbouncer container")

        if reload_pgbouncer:
            self._reload_pgbouncer()

    def _generate_userlist(self, users: Dict[str, str]) -> str:
        """Generate userlist.txt from the given dictionary of usernames:passwords.

        Params:
            users: a dictionary of usernames and passwords
        Returns:
            A multiline string, containing each pair of usernames and passwords separated by a
            space, one pair per line.
        """
        return "\n".join([f'"{username}" "{password}"' for username, password in users.items()])

    def _get_users_from_charm_config(self, users: Dict[str, str]) -> Dict[str, str]:
        """Imports users from charm config and generates passwords when necessary.

        TODO it looks as though multiple types of user exist in pgbouncer config, such as
        stats_users - presumably the details for these users are also stored here. If there are
        users that aren't listed as either admin or stats-only users, would their information be
        available here also?

        Params:
            users: an existing dictionary of usernames and passwords
        Returns:
            the `users` dictionary, with usernames from charm config and corresponding generated
            passwords appended.
        """
        for admin_user in self.config["pgb_admin_users"].split(","):
            # TODO add username validation
            if admin_user not in users or users[admin_user] is None:
                hash = hashlib.md5(self._generate_password().encode())
                users[admin_user] = hash.hexdigest()
        return users

    def _get_userlist_from_container(self) -> Dict[str, str]:
        """Parses container userlist to a dict, for use in charm.

        This parses the userlist.txt stored on the container into a dictionary of strings

        Returns:
            users: a dictionary of usernames and passwords
        """
        pgb_container = self.unit.get_container(self._pgbouncer_service)
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
