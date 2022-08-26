# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Pgbouncer pgb-peers relation hooks & helpers.

Example:
                                                  relation data v0.3
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ relation (id: 0) ┃ pgbouncer-k8s                                                                                    ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ relation name    │ pgb-peers                                                                                        │
│ interface        │ pgb_peers                                                                                        │
│ leader unit      │ 1                                                                                                │
│ type             │ peer                                                                                             │
├──────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ application data │ ╭──────────────────────────────────────────────────────────────────────────────────────────────╮ │
│                  │ │                                                                                              │ │
│                  │ │  auth_file                                "pgbouncer_auth_relation_id_2"                     │ │
│                  │ │                                           "md558cfafb042867ba28d809ec3ff73534f"              │ │
│                  │ │  cfg_file                                                                                    │ │
│                  │ │                                                                                              │ │
│                  │ │                                                                                              │ │
│                  │ │                                           listen_addr = *                                    │ │
│                  │ │                                           listen_port = 6432                                 │ │
│                  │ │                                           logfile =                                          │ │
│                  │ │                                           /var/lib/postgresql/pgbouncer/pgbouncer.log        │ │
│                  │ │                                           pidfile =                                          │ │
│                  │ │                                           /var/lib/postgresql/pgbouncer/pgbouncer.pid        │ │
│                  │ │                                           admin_users =                                      │ │
│                  │ │                                           stats_users =                                      │ │
│                  │ │                                           auth_type = md5                                    │ │
│                  │ │                                           user = postgres                                    │ │
│                  │ │                                           max_client_conn = 10000                            │ │
│                  │ │                                           ignore_startup_parameters = extra_float_digits     │ │
│                  │ │                                           so_reuseport = 1                                   │ │
│                  │ │                                           unix_socket_dir = /var/lib/postgresql/pgbouncer    │ │
│                  │ │                                           pool_mode = session                                │ │
│                  │ │                                           max_db_connections = 100                           │ │
│                  │ │                                           default_pool_size = 13                             │ │
│                  │ │                                           min_pool_size = 7                                  │ │
│                  │ │                                           reserve_pool_size = 7                              │ │
│                  │ │                                           auth_file =                                        │ │
│                  │ │                                           /var/lib/postgresql/pgbouncer/userlist.txt         │ │
│                  │ │                                                                                              │ │
│                  │ │                                                                                              │ │
│                  │ │  pgbouncer_k8s_user_id_3_test_peers_xz5n  DHj1tJXAcrQzSUNc4eVlWf18                           │ │
│                  │ ╰──────────────────────────────────────────────────────────────────────────────────────────────╯ │
│ unit data        │ ╭─ pgbouncer-k8s/0 ─╮ ╭─ pgbouncer-k8s/1* ─╮                                                     │
│                  │ │ <empty>           │ │ <empty>            │                                                     │
│                  │ ╰───────────────────╯ ╰────────────────────╯                                                     │
└──────────────────┴──────────────────────────────────────────────────────────────────────────────────────────────────┘

"""

import logging

from charms.pgbouncer_k8s.v0.pgb import PgbConfig
from ops.charm import CharmBase, RelationChangedEvent, RelationCreatedEvent
from ops.framework import Object

RELATION_NAME = "pgb-peers"
CFG_FILE_DATABAG_KEY = "cfg_file"
AUTH_FILE_DATABAG_KEY = "auth_file"


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
        super().__init__(charm, RELATION_NAME)

        self.charm = charm

        self.framework.observe(charm.on[RELATION_NAME].relation_created, self._on_created)
        self.framework.observe(charm.on[RELATION_NAME].relation_joined, self._on_changed)
        self.framework.observe(charm.on[RELATION_NAME].relation_changed, self._on_changed)

    @property
    def peer_databag(self):
        """Returns the app databag for the Peer relation."""
        peer_relation = self.model.get_relation(RELATION_NAME)
        if peer_relation is None:
            return None
        return peer_relation.data[self.charm.app]

    def _on_created(self, event: RelationCreatedEvent):
        if not self.charm.unit.is_leader():
            return

        try:
            cfg = self.charm.read_pgb_config()
        except FileNotFoundError:
            # If there's no config, the charm start hook hasn't fired yet, so defer until it's
            # available.
            event.defer()
            return

        self.update_cfg(cfg)

        try:
            if self.charm.backend:
                # update userlist only if backend relation exists.
                self.update_auth_file(self.charm.read_auth_file())
        except FileNotFoundError:
            # Auth files will be added to the databag once they're available
            pass

    def _on_changed(self, event: RelationChangedEvent):
        """If the current unit is a follower, write updated config and auth files to filesystem."""
        if self.charm.unit.is_leader():
            try:
                cfg = self.charm.read_pgb_config()
            except FileNotFoundError:
                # If there's no config, the charm start hook hasn't fired yet, so defer until it's
                # available.
                event.defer()
                return

            self.update_cfg(cfg)
            return

        if cfg := self.peer_databag.get(CFG_FILE_DATABAG_KEY):
            self.charm.render_pgb_config(PgbConfig(cfg))

        if auth_file := self.peer_databag.get(AUTH_FILE_DATABAG_KEY):
            self.charm.render_auth_file(auth_file)

        if cfg is not None or auth_file is not None:
            self.charm.reload_pgbouncer()

    def update_cfg(self, cfg: PgbConfig) -> None:
        """Writes cfg to app databag if leader."""
        if not self.charm.unit.is_leader():
            return

        if self.peer_databag is None:
            # peer relation not yet initialised
            # TODO fail louder
            return

        self.peer_databag[CFG_FILE_DATABAG_KEY] = cfg.render()
        logger.debug("updated config file in peer databag")

    def get_cfg(self) -> PgbConfig:
        """Retrieves the pgbouncer config from the peer databag."""
        if self.peer_databag is None:
            return None

        if cfg := self.peer_databag.get(CFG_FILE_DATABAG_KEY):
            return PgbConfig(cfg)
        else:
            return None

    def update_auth_file(self, auth_file: str) -> None:
        """Writes auth_file to app databag if leader."""
        if not self.charm.unit.is_leader():
            return

        if self.peer_databag is None:
            # peer relation not yet initialised
            # TODO fail louder
            return

        self.peer_databag[AUTH_FILE_DATABAG_KEY] = auth_file
        logger.debug("updated auth file in peer databag")
