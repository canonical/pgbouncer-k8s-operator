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
