#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed PgBouncer connection pooler."""

import logging
import secrets
import string

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
        self._users = {}

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.pgbouncer_pebble_ready, self._on_pgbouncer_pebble_ready)

        self.framework.observe(self.on.reload_pgbouncer_action, self._on_reload_pgbouncer_action)
        self.framework.observe(self.on.update_password_action, self._on_update_password_action)
        self.framework.observe(self.on.add_user_action, self._on_add_user_action)
        self.framework.observe(self.on.remove_user_action, self._on_remove_user_action)
        self.framework.observe(self.on.get_users_action, self._on_get_users_action)

    def _on_install(self, _) -> None:
        """On install hook.

        This initialises the juju-admin user with a random password, imports any other users in the
        juju config, and pushes the necessary config files to the container.
        """
        self._import_users_from_config()
        self._update_local_config()

    def _on_config_changed(self, _) -> None:
        """Handle changes in configuration."""
        self._import_users_from_config()
        self._update_local_config()

        container = self.unit.get_container(self._pgbouncer_service)
        layer = self._pgbouncer_layer()
        if container.can_connect():
            services = container.get_plan().to_dict().get("services", {})
            if services != layer["services"]:
                container.add_layer(self._pgbouncer_service, layer, combine=True)
                logging.info("Added layer 'pgbouncer' to pebble plan")
                container.restart(self._pgbouncer_service)
                logging.info("restarted pgbouncer service")
            self.unit.status = ActiveStatus()
        else:
            self.unit.status = WaitingStatus("waiting for pebble in pgbouncer workload container.")

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

    def _update_local_config(self) -> None:
        """Updates config files stored on pgbouncer container.

        Updates userlist.txt and pgbouncer.ini config files, reloading pgbouncer application once
        updated.
        """
        self._push_userlist()
        self._push_pgbouncer_ini(reload_pgbouncer=True)

    def _push_pgbouncer_ini(self, reload_pgbouncer=False) -> None:
        """Generate pgbouncer.ini from juju config and deploy it to the container.

        TODO verify if pgbouncer has to restart to implement changes
        """
        pgb_container = self.unit.get_container(self._pgbouncer_service)
        pgbouncer_ini = self._generate_pgbouncer_ini()

        try:
            # Check that we're not updating this file unnecessarily
            if pgb_container.pull(INI_PATH).read() == pgbouncer_ini:
                logger.info("updated config does not modify existing pgbouncer config")
                return
        except FileNotFoundError:
            # there is no existing pgbouncer.ini file, so carry on and add one.
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

    def _generate_pgbouncer_ini(self) -> str:
        """Generate pgbouncer.ini from config.

        This is a basic stub method, and will be updated in future to generate more complex
        pgbouncer.ini files in a more sophisticated way.

        TODO compare to real-world pgbouncer.ini files and devise a more sophisticated way of
        generating them.  look at the previous charm's implementation of this, since that's not
        likely to have changed.
        TODO evaluate other user types
        """
        return f"""[databases]
{self.config["pgb_databases"]}

[pgbouncer]
listen_port = {self.config["pgb_listen_port"]}
listen_addr = {self.config["pgb_listen_address"]}
auth_type = md5
auth_file = userlist.txt
logfile = pgbouncer.log
pidfile = pgbouncer.pid
admin_users = {",".join(self._users.keys())}"""

    def _import_users_from_config(self) -> None:
        """Imports users from juju config and generates passwords when necessary.

        TODO it looks as though multiple types of user exist in pgbouncer config, such as
        stats_users - presumably the details for these users are also stored here. If there are
        users that aren't listed as either admin or stats-only users, would their information be
        available here also?
        """
        self._users = {}
        for admin_user in self.config["pgb_admin_users"].split(","):
            if admin_user.strip() == "":
                continue
            if admin_user not in self._users or self._users[admin_user] is None:
                self._users[admin_user] = self._generate_password()

    def _push_userlist(self, reload_pgbouncer=False) -> None:
        """Generate userlist.txt from the given userlist, and deploy it to the container.

        TODO verify if pgbouncer has to restart to implement changes
        """
        pgb_container = self.unit.get_container(self._pgbouncer_service)
        userlist = self._generate_userlist()

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

    def _generate_userlist(self) -> str:
        """Generate userlist.txt from the given dictionary of usernames:passwords."""
        return "\n".join(
            [f'"{username}" "{password}"' for username, password in self._users.items()]
        )

    def _generate_password(self) -> str:
        """Generates a secure password.

        Returns:
           A random 24-character password string.
        """
        choices = string.ascii_letters + string.digits
        return "".join([secrets.choice(choices) for _ in range(24)])

    def _reload_pgbouncer(self) -> None:
        """Reloads pgbouncer application.

        Pgbouncer will not apply configuration changes without reloading, so this must be called
        after each time config files are changed.
        """
        logger.info("reloading pgbouncer application")
        pass

    def _on_reload_pgbouncer_action(self, event) -> None:
        self._reload_pgbouncer()
        event.set_results({"result": "pgbouncer has restarted"})

    def _on_update_password_action(self, event) -> None:
        """An action to update the password for a specific user.

        TODO implement password encryption at this stage, before anything is ever stored.
        """
        username = event.params["username"]
        password = event.params["password"]
        if username not in self._users:
            event.set_results(
                {
                    "result": f"user {username} does not exist - use the get-users action to list existing users."
                }
            )
            return
        self._users[username] = password
        self._update_local_config()
        event.set_results({"result": f"password updated for user {username}"})

    def _on_add_user_action(self, event) -> None:
        """Event handler for add-user action.

        TODO implement password encryption at this stage, before anything is ever stored.
        """
        username = event.params["username"]
        if username in self._users:
            event.set_results({"result": f"user {username} already exists"})
            return

        try:
            password = event.params["password"]
        except KeyError:
            password = self._generate_password()
            logger.info(
                "no password supplied when adding new user - a password will be randomly generated"
            )

        self._users[username] = password
        self._update_local_config()
        event.set_results({"result": f"new user {username} added"})

    def _on_remove_user_action(self, event) -> None:
        """Event handler for remove-user action."""
        username = event.params["username"]
        if username not in self._users:
            event.set_results({"result": f"user {username} does not exist"})
            return

        del self._users[username]
        self._update_local_config()
        event.set_results({"result": f"user {username} removed"})

    def _on_get_users_action(self, event) -> None:
        """Event handler for get-users action."""
        event.set_results({"result": " ".join(self._users.keys())})


if __name__ == "__main__":
    main(PgBouncerK8sCharm)
