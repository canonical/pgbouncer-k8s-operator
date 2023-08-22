# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Pgbouncer pgb-peers relation hooks & helpers.

This relation is primarily used for inter-unit communication through its databags, such as sharing
networking information, or leader units handing down config to followers.

Example:
-----------------------------------------------------------------------------------------------------------------------
│relation (id: 2)  │pgbouncer-k8s                                                                                     │
-----------------------------------------------------------------------------------------------------------------------
│ relation name    │ pgb-peers                                                                                        │
│ interface        │ pgb_peers                                                                                        │
│ leader unit      │ 0                                                                                                │
│ type             │ peer                                                                                             │
-----------------------------------------------------------------------------------------------------------------------
│ application data │ ╭──────────────────────────────────────────────────────────────────────────────────────────────╮ │
│                  │ │                                                                                              │ │
│                  │ │  auth_file        "pgbouncer_auth_relation_id_3" "md5aad46d9afbcc8c8248d254d567b577c1"       │ │
│                  │ │  cfg_file                                                                                    │ │
│                  │ │                   application_first_database =                                               │ │
│                  │ │                   host=postgresql-k8s-primary.test-pgbouncer-provider-gnrj.svc.cluster.loc…  │ │
│                  │ │                   dbname=application_first_database port=5432                                │ │
│                  │ │                   auth_user=pgbouncer_auth_relation_id_3                                     │ │
│                  │ │                   application_first_database_readonly =                                      │ │
│                  │ │                   host=postgresql-k8s-replicas.test-pgbouncer-provider-gnrj.svc.cluster.lo…  │ │
│                  │ │                   dbname=application_first_database port=5432                                │ │
│                  │ │                   auth_user=pgbouncer_auth_relation_id_3                                     │ │
│                  │ │                                                                                              │ │
│                  │ │                                                                                              │ │
│                  │ │                   listen_addr = *                                                            │ │
│                  │ │                   listen_port = 6432                                                         │ │
│                  │ │                   logfile = /var/lib/postgresql/pgbouncer/pgbouncer.log                      │ │
│                  │ │                   pidfile = /var/lib/postgresql/pgbouncer/pgbouncer.pid                      │ │
│                  │ │                   admin_users = relation_id_3                                                │ │
│                  │ │                   stats_users =                                                              │ │
│                  │ │                   auth_type = md5                                                            │ │
│                  │ │                   user = postgres                                                            │ │
│                  │ │                   max_client_conn = 10000                                                    │ │
│                  │ │                   ignore_startup_parameters = extra_float_digits                             │ │
│                  │ │                   server_tls_sslmode = prefer                                                │ │
│                  │ │                   so_reuseport = 1                                                           │ │
│                  │ │                   unix_socket_dir = /var/lib/postgresql/pgbouncer                            │ │
│                  │ │                   pool_mode = session                                                        │ │
│                  │ │                   max_db_connections = 100                                                   │ │
│                  │ │                   default_pool_size = 13                                                     │ │
│                  │ │                   min_pool_size = 7                                                          │ │
│                  │ │                   reserve_pool_size = 7                                                      │ │
│                  │ │                   auth_query = SELECT username, password FROM                                │ │
│                  │ │                   pgbouncer_auth_relation_id_3.get_auth($1)                                  │ │
│                  │ │                   auth_file = /var/lib/postgresql/pgbouncer/userlist.txt                     │ │
│                  │ │                                                                                              │ │
│                  │ │                                                                                              │ │
│                  │ │  leader_hostname  pgbouncer-k8s-0.pgbouncer-k8s-endpoints.test-pgbouncer-provider-gnrj.svc…  │ │
│                  │ │  relation_id_4    Z4OtFCe6r5HG6mk1XuR6LkwZ                                                   │ │
│                  │ ╰──────────────────────────────────────────────────────────────────────────────────────────────╯ │
│ unit data        │ ╭─ pgbouncer-k8s/0* ─╮ ╭─ pgbouncer-k8s/1 ─╮ ╭─ pgbouncer-k8s/2 ─╮                               │
│                  │ │ <empty>            │ │ <empty>           │ │ <empty>           │                               │
│                  │ ╰────────────────────╯ ╰───────────────────╯ ╰───────────────────╯                               │
-----------------------------------------------------------------------------------------------------------------------

"""  # noqa: W505

import logging
from typing import Optional, Set

from charms.pgbouncer_k8s.v0.pgb import PgbConfig
from ops.charm import CharmBase, HookEvent, RelationCreatedEvent
from ops.framework import Object
from ops.model import MaintenanceStatus, Relation, Unit
from ops.pebble import ChangeError, ConnectionError

from constants import APP_SCOPE, AUTH_FILE_DATABAG_KEY, PEER_RELATION_NAME

CFG_FILE_DATABAG_KEY = "cfg_file"
ADDRESS_KEY = "private-address"
LEADER_ADDRESS_KEY = "leader_hostname"


logger = logging.getLogger(__name__)


class Peers(Object):
    """Defines functionality for the pgbouncer peer relation.

    The data created in this relation allows the pgbouncer charm to connect to the postgres charm.

    Hook events observed:
        - relation-created
        - relation-joined
        - relation-changed
    """

    def __init__(self, charm: CharmBase):
        super().__init__(charm, PEER_RELATION_NAME)

        self.charm = charm

        self.framework.observe(charm.on[PEER_RELATION_NAME].relation_created, self._on_created)
        self.framework.observe(charm.on[PEER_RELATION_NAME].relation_joined, self._on_changed)
        self.framework.observe(charm.on[PEER_RELATION_NAME].relation_changed, self._on_changed)
        self.framework.observe(charm.on.secret_changed, self._on_changed)
        self.framework.observe(charm.on.secret_remove, self._on_changed)
        self.framework.observe(charm.on[PEER_RELATION_NAME].relation_departed, self._on_departed)
        self.framework.observe(charm.on.leader_elected, self._on_leader_elected)

    @property
    def relation(self) -> Relation:
        """Returns the relations in this model , or None if peer is not initialised."""
        return self.charm.model.get_relation(PEER_RELATION_NAME)

    @property
    def app_databag(self):
        """Returns the app databag for the Peer relation."""
        if not self.relation:
            return None
        return self.relation.data[self.charm.app]

    @property
    def unit_databag(self):
        """Returns this unit's databag for the Peer relation."""
        if not self.relation:
            return None
        return self.relation.data[self.charm.unit]

    @property
    def units_hostnames(self) -> Set[str]:
        """Fetch current set of peers hostnames.

        Returns:
            A set of peers addresses (strings).
        """
        units_hostnames = {self._get_unit_hostname(unit) for unit in self.relation.units}
        units_hostnames.discard(None)
        units_hostnames.discard(self.leader_hostname)
        units_hostnames.add(self.charm.unit_pod_hostname)
        return units_hostnames

    @property
    def leader_hostname(self) -> str:
        """Gets the hostname of the leader unit."""
        return self.app_databag.get(LEADER_ADDRESS_KEY, None)

    @property
    def leader_unit(self) -> Unit:
        """Gets the leader unit."""
        for unit in self.relation.units:
            if self._get_unit_hostname(unit) == self.leader_hostname:
                return unit

    def _get_unit_hostname(self, unit: Unit) -> Optional[str]:
        """Get the hostname of a specific unit."""
        # Check if host is current host.
        if unit == self.charm.unit:
            return self.charm.unit_pod_hostname
        # Check if host is a peer.
        elif unit in self.relation.data:
            return str(self.relation.data[unit].get(ADDRESS_KEY))
        # Return None if the unit is not a peer neither the current unit.
        else:
            return None

    def _on_created(self, event: RelationCreatedEvent):
        """Updates unit databag with address key, and if this unit is leader, add config data.

        Defers:
            - If config is unavailable
        """
        self.unit_databag[ADDRESS_KEY] = self.charm.unit_pod_hostname
        if not self.charm.unit.is_leader():
            return

        try:
            cfg = self.charm.read_pgb_config()
            self.update_cfg(cfg)
        except FileNotFoundError:
            # If there's no config, the charm start hook hasn't fired yet, so defer until it's
            # available.
            event.defer()
            return

        if self.charm.backend.ready:
            # The backend relation creates the userlist, so only upload userlist to databag if
            # backend relation is initialised. If not, it'll be added when that relation first
            # writes it to the container, so no need to add it now.
            self.update_auth_file(self.charm.read_auth_file())

    def _on_changed(self, event: HookEvent):
        """If the current unit is a follower, write updated config and auth files to filesystem.

        Every time the pgbouncer config is changed, update_cfg is called. This updates the leader's
        config file in the peer databag, which propagates the config to the follower units. In this
        function, we check for that updated config and render it to the container.

        Deferrals:
            - If pgbouncer config is unavailable
            - If pgbouncer container is unavailable.
        """
        self.unit_databag.update({ADDRESS_KEY: self.charm.unit_pod_hostname})
        self.charm.update_client_connection_info()

        if self.charm.unit.is_leader():
            try:
                cfg = self.charm.read_pgb_config()
            except FileNotFoundError:
                # If there's no config, the charm start hook hasn't fired yet, so defer until it's
                # available.
                event.defer()
                return

            self.update_cfg(cfg)
            self.update_leader()
            return

        if cfg := self.get_cfg():
            self.charm.render_pgb_config(PgbConfig(cfg))

        if auth_file := self.charm.get_secret(APP_SCOPE, AUTH_FILE_DATABAG_KEY):
            self.charm.render_auth_file(auth_file)

        if cfg is not None or auth_file is not None:
            try:
                # raises an error if this is fired before on_pebble_ready.
                self.charm.reload_pgbouncer()
                self.charm.toggle_monitoring_layer(self.charm.backend.ready)
            except (ConnectionError, ChangeError):
                logger.error(
                    "failed to reload pgbouncer - deferring change_event and waiting for pebble."
                )
                event.defer()

    def _on_departed(self, event):
        self.update_leader()
        self.charm.update_client_connection_info()
        if event.departing_unit == self.leader_unit:
            self.charm.unit.status = MaintenanceStatus(
                "Leader unit removed - waiting for leader_elected event"
            )

    def _on_leader_elected(self, _):
        self.update_leader()
        self.charm.update_client_connection_info()

    def update_leader(self):
        """Updates leader hostname in peer databag to match this unit if it's the leader."""
        if self.charm.unit.is_leader():
            self.app_databag[LEADER_ADDRESS_KEY] = self.charm.unit_pod_hostname

    def update_cfg(self, cfg: PgbConfig) -> None:
        """Writes cfg to app databag if leader.

        Called every time a unit tries to write config. This creates a peer-relation-changed event,
        meaning that the follower units will receive config updates when the leader adds them.

        Args:
            cfg: the config file to be sent to the databag. Will be rendered to a string
            automatically.
        """
        if not self.charm.unit.is_leader() or not self.relation:
            return

        self.charm.set_secret(APP_SCOPE, CFG_FILE_DATABAG_KEY, cfg.render())
        logger.debug("updated config file in peer databag")

    def get_cfg(self) -> PgbConfig:
        """Retrieves the pgbouncer config from the peer databag."""
        if cfg := self.charm.get_secret(APP_SCOPE, CFG_FILE_DATABAG_KEY):
            return PgbConfig(cfg)
        else:
            return None

    def update_auth_file(self, auth_file: str) -> None:
        """Writes auth_file to app databag if leader."""
        if not self.charm.unit.is_leader() or not self.relation:
            return

        self.charm.set_secret(APP_SCOPE, AUTH_FILE_DATABAG_KEY, auth_file)
        logger.debug("updated auth file in peer databag")

    def add_user(self, username: str, password: str):
        """Adds user to app databag."""
        if not self.charm.unit.is_leader():
            return

        self.charm.set_secret(APP_SCOPE, username, password)

    def remove_user(self, username: str):
        """Removes user from app databag."""
        if not self.charm.unit.is_leader():
            return

        self.charm.set_secret(APP_SCOPE, username, None)
