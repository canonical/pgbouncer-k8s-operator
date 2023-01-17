# Charm Reference docs

TODO merge these into the other reference docs once they're merged.

## Event Flowchart

The following charts detail the expected flow of events for the pgbouncer k8s charm. For more information on charm lifecycles, see [A Charm's Life](https://juju.is/docs/sdk/a-charms-life).

### Charm Startup

Relation events can be fired at any time during startup.

TODO this is an unreadable mess

```mermaid
flowchart TD
  start_hook[Run start hook. \nDefers until the workload container\nis available, and the leader unit\n has generated config, which is\nthen written to the container\nfilesystem and shared to other units\nvia peer databag.]
  start_hook --> pebble_ready[Run pgbouncer-pebble-ready hook.\nDefers until config has been\nwritten to container filesystem.\n Writes pebble config to pgbouncer\ncontainer, which in turn starts\npgbouncer services.]
  pebble_ready -- deferral --> start_hook
  pebble_ready --> begin([Begin charm operation])
  backend_database_relation_created[Backend relation can be\ncreated, but won't be\ninitialised unil pgbouncer\nservices are running]
  backend_database_relation_created -- deferral --> pebble_ready
    peer_relation_created[Peer relation created by default on\nstartup. Defers config upload until config\nexists, and defers auth file upload\nuntil backend relation exists]
  peer_relation_created -- deferral --> start_hook
  peer_relation_created -- deferral --> backend_database_relation_created
  client_relation_created[Client relations can be\ncreated, but won't be\ninitialised until pgbouncer\nservices are running and\nbackend database is initialised]
  client_relation_created -- deferral --> backend_database_relation_created
  client_relation_created -- deferral --> pebble_ready
```

### Config updates

```mermaid
flowchart TD
  exists([Charm is running]) --> config_changed[Charm config is changed,\nfiring Config-changed hook]
  exists --> relation_changed[Backend or client\nrelation updates,\ntriggering changes in\npgbouncer config] --> update_cfg
  config_changed --> update_cfg[Leader updates config locally\nand in peer databag, causing a \n peer-relation-changed event]
  update_cfg --> peer_changed[Follower units update\nconfig from peer databag]
  update_cfg --> reload_pgb[Reload\npgbouncer]
  peer_changed --> reload_pgb
  reload_pgb --> continue([Charm continues running])
```

### Leader Updates

```mermaid
flowchart TD
  exists([Charm is running])--> leader_deleted[Leader unit \n is deleted]
  leader_deleted --> client_relation_remove_leader
  leader_deleted --> legacy_client_relation_remove_leader
  leader_deleted --> peer_relation_remove_leader[Update peer databag\nto inform other\nunits that leader\nis departing]
  peer_relation_remove_leader --> wait_for_elect[Wait for leader_elected hook]
  wait_for_elect -.-> leader_elected[leader_elected hook fires]
  leader_elected --> client_relation_update_leader
  leader_elected --> legacy_client_relation_update_leader
  leader_elected --> peer_relation_update_leader[Update leader address\n in peer databag,\nand update connection\ninformation]
  client_relation_update_leader --> continue
  legacy_client_relation_update_leader --> continue
  peer_relation_update_leader --> continue([Continue normal \n charm operation.])
```
