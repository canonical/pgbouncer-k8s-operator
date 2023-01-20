# Charm.py Reference Documentation

This file is the entrypoint for the charm, and contains functions for its basic operation, including its major hooks and file management. This file can be found at [src/charm.py](../../../src/charm.py).

## Event Flow

The following charts detail the expected flow of events for the pgbouncer k8s charm. For more information on charm lifecycles, see [A Charm's Life](https://juju.is/docs/sdk/a-charms-life).

### Charm Startup

Relation events can be fired at any time during startup, but they're generally expected by the charm to run after start and pebble_ready hooks. The "golden path" in the flowchart below is shown by the bold lines.

```mermaid
flowchart TD
  start([Start Charm]) ==> start_hook
  start --> peer_relation_created
  start_hook[Run start hook. \nDefers until the workload container\nis available, and the leader unit\n has generated config, which is\nthen written to the container\nfilesystem and shared to other units\nvia peer databag.]
  start_hook ==> pebble_ready[Run pgbouncer-pebble-ready hook.\nDefers until config has been\nwritten to container filesystem.\n Writes pebble config to pgbouncer\ncontainer, which in turn starts\npgbouncer services.]
  pebble_ready -. deferral .-> start_hook
  pebble_ready ==> begin([Begin charm operation])
  pebble_ready --> backend_database_relation_created
  pebble_ready --> client_relation_created
  backend_database_relation_created[Backend relation can be\ncreated, but won't be\ninitialised unil pgbouncer\nservices are running]
  backend_database_relation_created -. deferral .-> pebble_ready
    peer_relation_created[Peer relation created by default on\nstartup. Defers config upload until config\nexists, and defers auth file upload\nuntil backend relation exists]
  peer_relation_created -. deferral .-> start_hook
  peer_relation_created -. deferral .-> backend_database_relation_created
  client_relation_created[Client relations can be\ncreated, but won't be\ninitialised until pgbouncer\nservices are running and\nbackend database is initialised]
  client_relation_created -. deferral .-> backend_database_relation_created
  client_relation_created -. deferral .-> pebble_ready
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
  exists([Charm is running])--> leader_deleted[Leader unit is deleted]
  leader_deleted --> relation_remove_leader[All relations add unit-departing\n flag to unit databag, and \n update connection information]
  relation_remove_leader -.-> leader_elected[leader_elected hook fires after\nan indeterminate amount of time]
  leader_elected --> update_leader[Update leader address in peer databag, and\n update connection information in relation databags]
  update_leader --> continue([Continue normal \n charm operation])
```

## Hook Handler Flowcharts

These flowcharts detail the control flow of individual hook handlers in this program. Unless otherwise stated, **a hook deferral is always followed by a return**.

### Start Hook

```mermaid
flowchart TD
  hook_fired([start Hook]) --> is_container{ Is container\navailable? }
  is_container -- no --> defer> defer ]
  is_container -- yes --> is_cfg{ Is pgbouncer config\navailable in container or\npeer databag? }
  is_cfg -- no --> is_leader{ Is the current\nunit Leader? }
  is_cfg -- yes --> make_dirs[Create directory\nstructure for charm]
  is_leader -- no --> defer_wait> defer:\nwait for leader unit to generate\nconfig and upload to peer databag ]
  is_leader -- yes --> gen_cfg[ generate new config ]
  gen_cfg --> make_dirs
  make_dirs --> render_cfg[ render config, update\nrelations if available ]
  render_cfg --> rtn(( return ))
```

### PgBouncer Pebble Ready Hook

```mermaid
flowchart TD
  hook_fired([pgbouncer-pebble-ready Hook]) --> is_cfg{Is pgbouncer\nconfig available?}
  is_cfg -- no --> defer>defer]
  is_cfg -- yes --> gen_cfg[Generate pebble config and\nstart pgbouncer services]
  gen_cfg --> verify[Verify pgbouncer services\nare running, and set\ncharm status accordingly]
  verify --> rtn([return])
```

### Config Changed Hook

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

### Update Status Hook

```mermaid
flowchart TD
  hook_fired([update-status Hook]) --> is_backend_ready{Is backend\ndatabase ready?}
  is_backend_ready -- no --> set_blocked[Set Blocked\nstatus]
  is_backend_ready -- yes --> is_running{Is pgbouncer\nrunning?}
  is_running -- yes --> set_active[Set Active\n Status]
  is_running -- no --> set_waiting[Set Waiting\nStatus]
  set_blocked --> update_leader[Update leader in\nPeer Relation\nDatabag.]
  set_active --> update_leader
  set_waiting --> update_leader
  update_leader --> update_relations[Update peer data\n in relation databags]
  update_relations --> return([Return])
```
