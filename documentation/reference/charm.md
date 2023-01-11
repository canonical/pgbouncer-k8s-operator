# Charm.py Reference Documentation

This file is the entrypoint for the charm, and contains functions for its basic operation, including its major hooks and file management. This file can be found at [src/charm.py](../../../src/charm.py).

## Hook Handler Flowcharts

These flowcharts detail the control flow of the hooks in this program. Unless otherwise stated, **a hook deferral is always followed by a return**.

### Start Hook

```mermaid
flowchart TD
  hook_fired([start Hook]) --> is_container{ Is container\navailable? }
  is_container -- no --> defer> defer ]
  is_container -- yes --> is_cfg{ Is pgbouncer config\navailable in container or\npeer databag? }
  is_cfg -- no --> is_leader{ Is the current unit Leader? }
  is_cfg -- yes --> render_cfg[ render config, update\nrelations if available ]
  is_leader -- no --> defer_wait> defer:\nwait for leader unit to generate\nconfig and upload to peer databag ]
  is_leader -- yes --> gen_cfg[ generate new config ]
  gen_cfg --> render_cfg
  render_cfg --> rtn(( return ))
```

### PgBouncer Pebble Ready Hook

```mermaid
flowchart TD
  hook_fired([pgbouncer-pebble-ready Hook]) --> is_cfg{Is pgbouncer\nconfig available?}
  is_cfg -- no --> defer>defer]
  is_cfg -- yes --> gen_cfg[Generate pebble config\nand start service]
  gen_cfg --> verify[Verify pgbouncer is\nrunning, and set charm\n status accordingly]
  verify --> rtn([return])
```

#### Config Changed Hook

```mermaid
flowchart TD
  hook_fired([config-changed Hook]) --> is_leader{Is current\nunit leader?}
  is_leader -- no --> rtn([return])
  is_leader -- yes --> is_cfg{Is pgbouncer\nconfig available?}
  is_cfg -- no --> defer>defer]
  is_cfg -- yes --> match_cfg[Modify pgbouncer\nconfig to match\ncharm config]
  match_cfg --> render_cfg[Render config &\nreload pgbouncer]
  render_cfg --> rtn2([return])
```

## Event Flowchart

The following charts detail the expected flow of events for the pgbouncer k8s charm. For more information on charm lifecycles, see [A Charm's Life](https://juju.is/docs/sdk/a-charms-life).

TODO this is likely to be a spaghetti mess

### Charm Startup

Relation events can be fired at any time during startup.

TODO format

```mermaid
flowchart TD
  start([Start charm]) --> start_hook[Run start hook. \nDefers until the workload container is available, and the leader unit has generated config, which is then written to the container filesystem and shared to other units via peer databag.] 
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