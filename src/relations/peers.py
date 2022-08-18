# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Pgbouncer pgb-peers relation hooks & helpers.

Example:
TODO example docs
"""

import logging

from charms.pgbouncer_k8s.v0.pgb import PgbConfig
from ops.charm import CharmBase, RelationChangedEvent
from ops.framework import Object
# TODO consider writing a PgbConfig.json() function
import json

RELATION_NAME = "pgb-peers"
CFG_FILE_DATABAG_KEY = "cfg_file"
AUTH_FILE_DATABAG_KEY = "auth_file"


logger = logging.getLogger(__name__)


class Peers(Object):
    """Defines functionality for the pgbouncer peer relation.

    The data created in this relation allows the pgbouncer charm to connect to the postgres charm.

    Hook events observed:
        - relation-changed

    TODO swapping config files around isn't really going to cut it. I need to swap the relevant
    variables around, and nothing else, and let the update_endpoints hooks sort out the nuances.
    """

    def __init__(self, charm: CharmBase):
        super().__init__(charm, RELATION_NAME)

        self.charm = charm

        self.framework.observe(charm.on[RELATION_NAME].relation_changed, self._on_peers_changed)

    @property
    def app_databag(self):
        """Returns the app databag for the Peer relation."""
        peer_relation = self.model.get_relation(RELATION_NAME)
        if peer_relation is None:
            return None
        return peer_relation.data[self.charm.app]

    def _on_peers_changed(self, _):
        """If the current unit is a follower, write updated config and auth files to filesystem."""
        if self.charm.unit.is_leader():
            return

        if cfg := self.app_databag.get(CFG_FILE_DATABAG_KEY):
            self.charm.render_pgb_config(PgbConfig(cfg))

        if auth_file := self.app_databag.get(AUTH_FILE_DATABAG_KEY):
            self.charm.render_auth_file(auth_file)

        self.charm.update_postgres_endpoints()

        if cfg is not None or auth_file is not None:
            self.charm.reload_pgbouncer()

    def update_cfg(self, cfg: PgbConfig) -> None:
        """Writes cfg to app databag if leader."""
        if not self.charm.unit.is_leader():
            return

        if self.app_databag is None:
            # peer relation not yet initialised
            return

        self.app_databag[CFG_FILE_DATABAG_KEY] = json.loads(dict(cfg))

    def update_auth_file(self, auth_file: str) -> None:
        """Writes auth_file to app databag if leader."""
        if not self.charm.unit.is_leader():
            return

        if self.app_databag is None:
            # peer relation not yet initialised
            return

        self.app_databag[AUTH_FILE_DATABAG_KEY] = auth_file
