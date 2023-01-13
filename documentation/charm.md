# Charm Reference docs

TODO merge these into the other reference docs once they're merged.

## Event Flowchart

The following charts detail the expected flow of events for the pgbouncer k8s charm. For more information on charm lifecycles, see [A Charm's Life](https://juju.is/docs/sdk/a-charms-life).

### Charm Startup

Relation events can be fired at any time during startup.

TODO format

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
  exists([Charm is running fine])
```
