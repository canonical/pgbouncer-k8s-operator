# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Pgbouncer pgb-peers relation hooks & helpers.

Example:
TODO example docs
"""

import logging

from charms.pgbouncer_k8s.v0.pgb import PgbConfig
from ops.charm import CharmBase, RelationChangedEvent, RelationCreatedEvent
from ops.framework import Object
import json

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
            # self.charm.update_postgres_endpoints(reload_pgbouncer=True)
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

    def update_auth_file(self, auth_file: str) -> None:
        """Writes auth_file to app databag if leader."""
        if not self.charm.unit.is_leader():
            return

        if self.peer_databag is None:
            # peer relation not yet initialised
            # TODO fail louder
            return

        self.peer_databag[AUTH_FILE_DATABAG_KEY] = auth_file

    def get_password(self, username: str) -> str:
        return self.users.get(username)

    def store_user(self, username: str, password: str):
        users = self.users
        users[username] = password
        self.peer_databag["users"] = users

    @property
    def users(self):
        """Property to access the "users" field of this relation databag.

        This field is used to store the
        """
        if users := self.peer_databag.get("users"):
            return json.loads(users)
        else:
            return {}
