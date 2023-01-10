# Charm.py Reference Documentation

This file is the entrypoint for the charm, and contains functions for its basic operation, including its major hooks and file management. This file can be found at [src/charm.py](../../../src/charm.py).

## Event Flowchart

The following charts detail the expected flow of events for the pgbouncer k8s charm. TODO

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
