# Charm Reference docs

TODO merge these into the other reference docs once they're merged.

## Event Flowchart

The following charts detail the expected flow of events for the pgbouncer k8s charm. For more information on charm lifecycles, see [A Charm's Life](https://juju.is/docs/sdk/a-charms-life).

### Charm Startup

Relation events can be fired at any time during startup.

TODO format

```mermaid
flowchart TD
  start([Start charm]) --> start_hook[Run start hook. \nDefers until the workload container is available,and the leader unit has generated config, which is then written to the container filesystem and shared to other units via peer databag.]
  start_hook --> pebble_ready[Run pgbouncer-pebble-ready hook.\nDefers until config has been written to container filesystem. Writes pebble config to pgbouncer container, which in turn starts pgbouncer services.]
  pebble_ready -- deferral --> start_hook
  pebble_ready --> begin([Begin charm operation])
  backend_database_relation_created[Backend relation can be created, but won't be initialised unil pgbouncer services are running]
  backend_database_relation_created -- deferral --> pebble_ready
  client_relation_created[Client relations can be created, but won't be initialised until pgbouncer services are running and backend database is initialised]
  client_relation_created -- deferral --> pebble_ready
  client_relation_created -- deferral --> backend_database_relation_created
  peer_relation_created[Peer relation created by default on startup\ndefers config upload until config exists, and defers auth file upload until backend relation exists]
  peer_relation_created -- deferral --> start_hook
  peer_relation_created -- deferral --> backend_database_relation_created
```

### Config updates

```mermaid
flowchart TD
  exists([Charm is running fine])
```
