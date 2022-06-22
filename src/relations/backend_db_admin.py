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

from charms.pgbouncer_operator.v0 import pgb
from ops.charm import CharmBase, RelationChangedEvent, RelationDepartedEvent
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
    """

    def __init__(self, charm: CharmBase):
        super().__init__(charm, RELATION_ID)

        self.framework.observe(charm.on[RELATION_ID].relation_changed, self._on_relation_changed)
        self.framework.observe(charm.on[RELATION_ID].relation_departed, self._on_relation_departed)

        self.charm = charm

    def _on_relation_changed(self, change_event: RelationChangedEvent):
        """Handle backend-db-admin-relation-changed event.

        Takes master and standby information from the postgresql leader unit databag and copies it
        into the pgbouncer.ini config, removing redundant standby information along the way.
        """
        logger.info("database change detected - updating config")
        logger.info(
            "DEPRECATION WARNING - backend-db-admin is a legacy relation, and will be deprecated in a future release. "
        )

        event_data = change_event.relation.data
        pg_data = event_data[change_event.unit]

        cfg = self.charm._read_pgb_config()
        dbs = cfg["databases"]

        # Test that relation data contains everything we need
        if pg_data.get("master"):
            dbs["pg_master"] = pgb.parse_kv_string_to_dict(pg_data.get("master"))

        # update standbys
        standbys_str = pg_data.get("standbys")
        standby_data = standbys_str.split("\n") if standbys_str else []
        standby_names = []

        for idx, standby in enumerate(standby_data):
            standby_name = f"{STANDBY_PREFIX}{idx}"
            standby_names.append(standby_name)
            dbs[standby_name] = pgb.parse_kv_string_to_dict(standby)

        # Remove old standby information
        for db in list(dbs.keys()):
            if db[:21] == STANDBY_PREFIX and db not in standby_names:
                del dbs[db]

        self.charm._render_service_configs(cfg, reload_pgbouncer=True)

    def _on_relation_departed(self, departed_event: RelationDepartedEvent):
        """Handle backend-db-admin-relation-departed event.

        Removes master and standby information from pgbouncer config when backend-db-admin relation
        is removed.
        """
        logger.info("backend database removed - updating config")
        logger.info(
            "DEPRECATION WARNING - backend-db-admin is a legacy relation, and will be deprecated in a future release. "
        )

        cfg = self.charm._read_pgb_config()
        cfg["databases"].pop("pg_master", None)

        # Get postgres leader unit from relation data through iteration. Using departed_event.unit
        # appears to pick a unit at random, and relation data is not copied over to
        # departed_event.app, so we do this instead.
        event_data = {}
        for key, value in departed_event.relation.data.items():
            if isinstance(key, Unit) and key is not self.charm.unit:
                event_data = value
                break

        standbys = event_data.get("standbys")
        standbys = standbys.split("\n") if standbys else []

        for idx, _ in enumerate(standbys):
            cfg["databases"].pop(f"{STANDBY_PREFIX}{idx}", None)

        self.charm._render_service_configs(cfg, reload_pgbouncer=True)
