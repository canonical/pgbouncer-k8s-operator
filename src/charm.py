#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed PgBouncer connection pooler."""

import logging

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, ModelError, WaitingStatus
from ops.pebble import Layer

logger = logging.getLogger(__name__)


class PgBouncerK8sCharm(CharmBase):
    """An object representing charmed PgBouncer.

    Could this run in the same pod as the postgres charm?
    """

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)

        self._pgbouncer_service = "pgbouncer"
        self._pgbouncer_user = "pgbouncer"

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.pgbouncer_pebble_ready, self._on_pgbouncer_pebble_ready)

    def _on_install(self, _):
        """On install hook.

        Considering the container should already have everything pgbouncer needs to run, this hook
        only needs to replace the pgbouncer.ini and userlist.txt files with sensible defaults.

        TODO replace static defaults with ones generated at runtime. userlist.txt could also be
            replaced with a string.
        """
        pgb_container = self.unit.get_container(self._pgbouncer_service)
        try:
            pgb_ini_path = self.model.resources.fetch("default-ini")
        except ModelError:
            self.unit.status = BlockedStatus(
                "Unable to fetch default pgbouncer.ini file - please upload a valid file manually."
            )
            return

        try:
            userlist_path = self.model.resources.fetch("default-userlist")
        except ModelError:
            self.unit.status = BlockedStatus(
                "Unable to fetch default userlist.txt file - please upload a valid file manually."
            )
            return

        with open(pgb_ini_path, "r") as default_ini:
            pgb_container.push(
                "/etc/pgbouncer/pgbouncer.ini", default_ini, user=self._pgbouncer_user
            )
        with open(userlist_path, "r") as default_userlist:
            pgb_container.push(
                "/etc/pgbouncer/userlist.txt", default_userlist, user=self._pgbouncer_user
            )

    def _on_config_changed(self, _):
        """Handle changes in configuration.

        TODO Currently this hook immediately replaces any changes with the default pgbouncer
            config. Update to merge new config options where necessary.
        """
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
                    "command": "pgbouncer /etc/pgbouncer/pgbouncer.ini",
                    "startup": "enabled",
                    "override": "replace",
                }
            },
        }

    def _on_pgbouncer_pebble_ready(self, event):
        """Define and start pgbouncer workload."""
        container = event.workload
        pebble_layer = self._pgbouncer_layer()
        container.add_layer(self._pgbouncer_service, pebble_layer, combine=True)
        container.autostart()
        self.unit.status = ActiveStatus()

    def _on_update_ini_action(self, event):
        """Action allowing a user to update pgbouncer.ini from a local file on the juju host.

        NB this function is an in-progress stub.
        """
        pgb_container = self.unit.get_container(self._pgbouncer_service)
        # TODO get this from event
        pgbouncer_ini = ""
        logfile = pgb_container.push(
            "/etc/pgbouncer/pgbouncer.ini", pgbouncer_ini, user=self._pgbouncer_user
        )
        # TODO update config
        logger.info(logfile)
        event.set_results({"result": "pushed pgbouncer.ini"})


if __name__ == "__main__":
    main(PgBouncerK8sCharm)
