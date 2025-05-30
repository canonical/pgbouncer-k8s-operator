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
│                  │ │  pgb_dbs_config   '{"1": {"name": "db_name", "legacy": false}}'                              │ │
│                  │ │  leader_hostname  pgbouncer-k8s-0.pgbouncer-k8s-endpoints.test-pgbouncer-provider-gnrj.svc…  │ │
│                  │ │  relation_id_4    Z4OtFCe6r5HG6mk1XuR6LkwZ                                                   │ │
│                  │ ╰──────────────────────────────────────────────────────────────────────────────────────────────╯ │
│ unit data        │ ╭─ pgbouncer-k8s/0* ─╮ ╭─ pgbouncer-k8s/1 ─╮ ╭─ pgbouncer-k8s/2 ─╮                               │
│                  │ │ <empty>            │ │ <empty>           │ │ <empty>           │                               │
│                  │ ╰────────────────────╯ ╰───────────────────╯ ╰───────────────────╯                               │
-----------------------------------------------------------------------------------------------------------------------

"""

import logging
from hashlib import shake_128

from ops.charm import CharmBase, HookEvent, RelationCreatedEvent
from ops.framework import Object
from ops.model import Relation, Unit

from constants import APP_SCOPE, PEER_RELATION_NAME, UNIT_SCOPE, Scopes

ADDRESS_KEY = "private-address"


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
        self.framework.observe(charm.on[PEER_RELATION_NAME].relation_departed, self._on_departed)
        self.framework.observe(charm.on.leader_elected, self._on_leader_elected)

    @property
    def relation(self) -> Relation:
        """Returns the relations in this model , or None if peer is not initialised."""
        return self.charm.model.get_relation(PEER_RELATION_NAME)

    def scoped_peer_data(self, scope: Scopes) -> dict | None:
        """Returns peer data based on scope."""
        if scope == APP_SCOPE:
            return self.app_databag
        elif scope == UNIT_SCOPE:
            return self.unit_databag

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

    def _get_unit_hostname(self, unit: Unit) -> str | None:
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

        if not self.charm.is_container_ready:
            logger.debug("_on_peer_changed defer: container unavailable")
            event.defer()
            return

        pgb_dbs_hash = shake_128(self.app_databag.get("pgb_dbs_config", "{}").encode()).hexdigest(
            16
        )
        self.charm.render_pgb_config()
        self.charm.toggle_monitoring_layer(self.charm.backend.ready)
        self.unit_databag["pgb_dbs"] = pgb_dbs_hash

        if self.charm.unit.is_leader() and self.charm.configuration_check():
            self.charm.client_relation.update_endpoints()

    def _on_departed(self, event):
        self.charm.update_client_connection_info()
        if self.charm.unit.is_leader():
            self.charm.client_relation.update_endpoints()

    def _on_leader_elected(self, _):
        self.charm.update_client_connection_info()
