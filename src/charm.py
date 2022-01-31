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
    """An object representing charmed PgBouncer."""

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)

        self._pgbouncer_service = "pgbouncer"
        self._pgbouncer_user = "pgbouncer"
        self._user_list = {
            "juju-admin": None,
        }

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.pgbouncer_pebble_ready, self._on_pgbouncer_pebble_ready)

    def _on_install(self, _) -> None:
        """On install hook."""
        self._user_list["juju-admin"] = self._generate_password()
        self._import_users_from_config()

        self._push_pgbouncer_ini()
        self._push_userlist()

    def _on_config_changed(self, _) -> None:
        """Handle changes in configuration."""
        self._import_users_from_config()

        container = self.unit.get_container("pgbouncer")
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

    def _push_pgbouncer_ini(self) -> None:
        """Generate pgbouncer.ini from juju config and deploy it to the container."""
        pgb_container = self.unit.get_container(self._pgbouncer_service)
        pgbouncer_ini = self._generate_pgbouncer_ini()
        pgb_container.push(
            INI_PATH, pgbouncer_ini, user=self._pgbouncer_user, permissions=0o600, make_dirs=True
        )
        logging.info("pushed new pgbouncer.ini config file to pgbouncer container")

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
admin_users = {",".join(self._user_list.keys())}"""

    def _import_users_from_config(self) -> None:
        """Imports users from juju config and generates passwords when necessary.

        TODO it looks as though multiple types of user exist in pgbouncer config, such as
        stats_users - presumably the details for these users are also stored here. If there are
        users that aren't listed as either admin or stats-only users, would their information be
        available here also?
        """
        for admin_user in self.config["pgb_admin_users"].split(","):
            if admin_user not in self._user_list or self._user_list[admin_user] is None:
                self._user_list[admin_user] = self._generate_password()

    def _push_userlist(self) -> None:
        """Generate userlist.txt from the given userlist, and deploy it to the container."""
        pgb_container = self.unit.get_container(self._pgbouncer_service)
        pgb_container.push(
            USERLIST_PATH,
            self._generate_userlist(),
            user=self._pgbouncer_user,
            make_dirs=True,
        )
        logging.info("pushed new userlist to pgbouncer container")

    def _generate_userlist(self) -> str:
        """Generate userlist.txt from the given dictionary of usernames:passwords."""
        userlist = ""
        for user, password in self._user_list.items():
            userlist += f'"{user}" "{password}"\n'
        return userlist

    def _generate_password(self) -> str:
        """Generates a secure password.

        Returns:
           A random password string.
        """
        choices = string.ascii_letters + string.digits
        password = "".join([secrets.choice(choices) for _ in range(16)])
        return password

    # def _on_update_password_action(self, event):
    #     pass

    def _on_add_user_action(self, event):
        """Event handler for add-admin-user action."""
        user = ""
        if user not in self._user_list or self._user_list[user] is None:
            self._user_list[user] = self._generate_password()
        self._push_user_list(self._user_list)


if __name__ == "__main__":
    main(PgBouncerK8sCharm)
