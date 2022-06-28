# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Postgres backend-db-admin relation hooks & helpers.

This relation uses the pgsql interface.

Some example relation data is below. The only parts of this we actually need are the "master" and
"standbys" fields. All values are examples taken from a test deployment, and are not definite.

Example with 2 postgresql instances:
┏━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ category  ┃            keys ┃ pgbouncer-operator/23 ┃ postgresql/4                          ┃
┡━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ metadata  │        endpoint │ 'backend-db-admin'    │ 'db-admin'                            │
│           │          leader │ True                  │ True                                  │
├───────────┼─────────────────┼───────────────────────┼───────────────────────────────────────┤
│ unit data │ allowed-subnets │                       │ 10.101.233.152/32                     │
│           │   allowed-units │                       │ pgbouncer-operator/23                 │
│           │        database │                       │ pgbouncer-operator                    │
│           │            host │                       │ 10.101.233.241                        │
│           │          master │                       │ dbname=pgbouncer-operator             │
│           │                 │                       │ host=10.101.233.241                   │
│           │                 │                       │ password=zWRHxMgqZBPcLPh5VXCfGyjJj4c7 │
│           │                 │                       │ cP2qjnwdj port=5432                   │
│           │                 │                       │ user=jujuadmin_pgbouncer-operator     │
│           │        password │                       │ zWRHxMgqZBPcLPh5VXCfGyjJj4c7cP2qjnwdj │
│           │            port │                       │ 5432                                  │
│           │        standbys │                       │ dbname=pgbouncer-operator             │
│           │                 │                       │ host=10.101.233.169                   │
│           │                 │                       │ password=zWRHxMgqZBPcLPh5VXCfGyjJj4c7 │
│           │                 │                       │ cP2qjnwdj port=5432                   │
│           │                 │                       │ user=jujuadmin_pgbouncer-operator     │
│           │           state │                       │ master                                │
│           │            user │                       │ jujuadmin_pgbouncer-operator          │
│           │         version │                       │ 12                                    │
└───────────┴─────────────────┴───────────────────────┴───────────────────────────────────────┘
If there were multiple standbys, they would be separated by a newline character.


Example with 1 postgresql instance:
┏━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ category  ┃            keys ┃ pgbouncer-operator/23 ┃ postgresql/4                          ┃
┡━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ metadata  │        endpoint │ 'backend-db-admin'    │ 'db-admin'                            │
│           │          leader │ True                  │ True                                  │
├───────────┼─────────────────┼───────────────────────┼───────────────────────────────────────┤
│ unit data │ allowed-subnets │                       │ 10.101.233.152/32                     │
│           │   allowed-units │                       │ pgbouncer-operator/23                 │
│           │        database │                       │ pgbouncer-operator                    │
│           │            host │                       │ 10.101.233.241                        │
│           │          master │                       │ dbname=pgbouncer-operator             │
│           │                 │                       │ host=10.101.233.241                   │
│           │                 │                       │ password=zWRHxMgqZBPcLPh5VXCfGyjJj4c7 │
│           │                 │                       │ cP2qjnwdj port=5432                   │
│           │                 │                       │ user=jujuadmin_pgbouncer-operator     │
│           │        password │                       │ zWRHxMgqZBPcLPh5VXCfGyjJj4c7cP2qjnwdj │
│           │            port │                       │ 5432                                  │
│           │           state │                       │ standalone                            │
│           │            user │                       │ jujuadmin_pgbouncer-operator          │
│           │         version │                       │ 12                                    │
└───────────┴─────────────────┴───────────────────────┴───────────────────────────────────────┘

"""

import logging
from typing import List

from charms.pgbouncer_operator.v0 import pgb
from charms.pgbouncer_operator.v0.pgb import PgbConfig
from ops.charm import (
    CharmBase,
    RelationBrokenEvent,
    RelationChangedEvent,
    RelationDepartedEvent,
)
from ops.framework import Object
from ops.model import Unit

logger = logging.getLogger(__name__)

RELATION_ID = "backend-db-admin"
STANDBY_PREFIX = "pgb_postgres_standby_"


class BackendDbAdminRequires(Object):
    """Defines functionality for the 'requires' side of the 'backend-db-admin' relation.

    Hook events observed:
        - relation-changed
        - relation-departed
        - relation-broken
    """

    def __init__(self, charm: CharmBase):
        super().__init__(charm, RELATION_ID)

        self.framework.observe(charm.on[RELATION_ID].relation_changed, self._on_relation_changed)
        self.framework.observe(charm.on[RELATION_ID].relation_departed, self._on_relation_departed)
        self.framework.observe(charm.on[RELATION_ID].relation_broken, self._on_relation_broken)

        self.charm = charm

    def _on_relation_changed(self, change_event: RelationChangedEvent):
        """Handle backend-db-admin-relation-changed event.

        Takes master and standby information from the postgresql leader unit databag and copies it
        into the pgbouncer.ini config, removing redundant standby information along the way.
        """
        logger.info("database change detected - updating config")
        logger.warning(
            "DEPRECATION WARNING - backend-db-admin is a legacy relation, and will be deprecated in a future release. "
        )

        postgres_data = change_event.relation.data[change_event.unit]

        cfg = self.charm._read_pgb_config()
        dbs = cfg["databases"]

        if postgres_data.get("master"):
            dbs["pg_master"] = pgb.parse_kv_string_to_dict(postgres_data.get("master"))
        else:
            logger.info("waiting for postgres charm to correctly populate relation data")
            change_event.defer()
            return

        standbys_str = postgres_data.get("standbys")
        standbys = standbys_str.split("\n") if standbys_str else []

        self._update_standbys(cfg, standbys)

        self.charm._render_pgb_config(cfg, reload_pgbouncer=True)

    def _on_relation_departed(self, departed_event: RelationDepartedEvent):
        """Handle backend-db-admin-relation-departed event.

        Removes unit information from pgbouncer config when a unit is removed.
        """
        logger.info("backend database removed - updating config")
        logger.warning(
            "DEPRECATION WARNING - backend-db-admin is a legacy relation, and will be deprecated in a future release. "
        )

        cfg = self.charm._read_pgb_config()

        # Iterate through relation data to get the postgresql unit. Relation data keys are one Unit
        # and one Application for each side of the relation.
        event_data = {}
        for relation_entity, entity_data in departed_event.relation.data.items():
            if isinstance(relation_entity, Unit) and relation_entity is not self.charm.unit:
                event_data = entity_data
                break

        standbys = event_data.get("standbys")
        standbys = standbys.split("\n") if standbys else []

        self._update_standbys(cfg, standbys)

        self.charm._render_pgb_config(cfg, reload_pgbouncer=True)

    def _update_standbys(self, cfg: PgbConfig, standbys: List[str]):
        """Updates standby list to match new relation data."""
        dbs = cfg["databases"]

        standby_names = []
        for idx, standby in enumerate(standbys):
            standby_name = f"{STANDBY_PREFIX}{idx}"
            standby_names.append(standby_name)
            dbs[standby_name] = pgb.parse_kv_string_to_dict(standby)

        # Remove old standby information
        for db in list(dbs.keys()):
            if db[:21] == STANDBY_PREFIX and db not in standby_names:
                del dbs[db]

        return cfg

    def _on_relation_broken(self, broken_event: RelationBrokenEvent):
        """Handle backend-db-admin-relation-broken event.

        Removes all traces of this relation from pgbouncer config.
        """
        logger.info("backend database removed - updating config")
        logger.warning(
            "DEPRECATION WARNING - backend-db-admin is a legacy relation, and will be deprecated in a future release. "
        )

        cfg = self.charm._read_pgb_config()
        dbs = cfg["databases"]

        dbs.pop("pg_master", None)

        for db in list(dbs.keys()):
            # Remove all standbys
            if db[:21] == STANDBY_PREFIX:
                del dbs[db]

        self.charm._render_pgb_config(cfg, reload_pgbouncer=True)
