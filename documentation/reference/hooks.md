# Hooks

This reference documentation details the flow of each hook handler function.

### Appendix A: Charm Lifecycle Flowcharts

These flowcharts detail the control flow of the hooks in this program. Unless otherwise stated, **a hook deferral is always followed by a return**.

TODO:

- Copy the relevant hook flowcharts into relation documentation, along with the expected relation interface.

#### Start Hook

file: [src/charm.py](https://github.com/canonical/pgbouncer-k8s-operator/blob/main/src/charm.py)

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

#### PgBouncer Pebble Ready Hook

file: [src/charm.py](https://github.com/canonical/pgbouncer-k8s-operator/blob/main/src/charm.py)

```mermaid
flowchart TD
  hook_fired([pgbouncer-pebble-ready Hook]) --> is_cfg{Is pgbouncer\nconfig available?}
  is_cfg -- no --> defer>defer]
  is_cfg -- yes --> gen_cfg[Generate pebble config\nand start service]
  gen_cfg --> verify[Verify pgbouncer is\nrunning, and set charm\n status accordingly]
  verify --> rtn([return])
```

#### Config Changed Hook

file: [src/charm.py](https://github.com/canonical/pgbouncer-k8s-operator/blob/main/src/charm.py)

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

#### Peer Relation Created Hook

file: [src/relations/peers.py](https://github.com/canonical/pgbouncer-k8s-operator/blob/main/src/relations/peers.py)

```mermaid
flowchart TD
  hook_fired([peer-relation-created Hook]) --> save_hostname[Save unit hostname\n in unit databag]
  save_hostname --> is_leader{Is current\nunit leader?}
  is_leader -- no --> rtn([return])
  is_leader -- yes --> is_cfg{Is pgbouncer\nconfig available?}
  is_cfg -- no --> defer>defer]
  is_cfg -- yes --> is_backend_ready{Is backend\ndatabase ready?}
  is_backend_ready -- no --> defer2>defer]
  is_backend_ready -- yes --> update_auth[Add auth file to\npeer databag]
  update_auth --> rtn2([return])
```

#### Peer Relation Changed Hook

file: [src/relations/peers.py](https://github.com/canonical/pgbouncer-k8s-operator/blob/main/src/relations/peers.py)

```mermaid
flowchart TD
  hook_fired([peer-relation-changed Hook]) --> save_hostname[Save unit hostname\n in unit databag]
  save_hostname --> update_relations[Update peer data\n in relation databags]
  update_relations --> is_leader{Is current\nunit leader?}
  is_leader -- yes --> is_cfg{Is local pgbouncer\nconfig available?}
  is_cfg -- no --> defer>defer]
  is_cfg -- yes --> update_cfg[Update pgbouncer config\nand leader hostname\n in app databag]
  update_cfg --> rtn([return])
  is_leader -- no --> is_cfg_in_databag{Is a valid config\nfile in the\napp databag?}
  is_cfg_in_databag -- yes --> save_cfg[Save config from\napplication databag]
  is_cfg_in_databag -- no --> is_auth_in_databag{Is a valid auth\nfile in the\napp databag?}
  save_cfg --> is_auth_in_databag
  is_auth_in_databag -- yes --> save_auth[Save auth file from\napplication databag]
  is_auth_in_databag -- no --> reload[if auth file or\n config have changed,\nreload pgbouncer]
  save_auth --> reload
  reload --> rtn2([return])
```

#### Backend Database Created Hook

file: [src/relations/backend_database.py](https://github.com/canonical/pgbouncer-k8s-operator/blob/main/src/relations/backend_database.py)

```mermaid
flowchart TD
  hook_fired([backend-database-requested Hook]) --> is_leader{Is current\nunit leader?}
  is_leader -- no --> rtn([return])
  is_leader -- yes --> is_running{Is pgbouncer\nrunning?}
  is_running -- no --> rtn3([return])
  is_running -- yes --> is_backend_ready{is backend database ready,\nand has pgbouncer been\nprovided with the\nnecessary relation data?}
  is_backend_ready -- no --> defer>defer]
  is_backend_ready -- yes --> generate_user[Generate username & password]
  generate_user --> create_auth_func[create auth function on postgres]
  create_auth_func --> save_auth_data[update pgbouncer config, and save\nauth data to container and peer databag]
  save_auth_data --> update_relations[update postgres endpoints in client relations]
  update_relations --> update_status[update charm status]
  update_status --> rtn2([return])
```

#### Backend Database Departed Hook

file: [src/relations/backend_database.py](https://github.com/canonical/pgbouncer-k8s-operator/blob/main/src/relations/backend_database.py)

```mermaid
flowchart TD
  hook_fired([backend-database-relation-departed Hook]) --> update_info[update relation connection information]
  update_info --> is_this_unit_departing{Is this unit the\ndeparting unit?}
  is_this_unit_departing -- yes --> tell_peers[update unit databag to tell\npeers this unit is departing]
  tell_peers --> rtn([return])
  is_this_unit_departing -- no --> is_leader{is this unit the\nleader, and is\nit departing}
  is_leader -- no --> rtn2([return])
  is_leader -- yes --> scale_down{Is this application\nscaling down,\nbut not to 0?}
  scale_down -- no --> rtn3([return])
  scale_down -- yes --> remove_auth[Remove auth function, and \n delete auth user]
  remove_auth --> rtn4([return])
```

#### Backend Database Broken Hook

file: [src/relations/backend_database.py](https://github.com/canonical/pgbouncer-k8s-operator/blob/main/src/relations/backend_database.py)

```mermaid
flowchart TD
  hook_fired([backend-database-relation-broken Hook]) --> check_depart{Is this unit not\nthe leader, or is the\nrelation_departing flag\n in the unit databag?}
  check_depart -- yes --> rtn([return])
  check_depart -- no --> is_cfg{Is pgbouncer\nconfig available?}
  is_cfg -- no --> defer>defer]
  is_cfg -- yes --> remove_auth[Remove authentication\ninformation from\npgbouncer config]
  remove_auth --> rtn2([return])
```

#### Database Requested Hook

file: [src/relations/pgbouncer_provider.py](https://github.com/canonical/pgbouncer-k8s-operator/blob/main/src/relations/pgbouncer_provider.py)

TODO

```mermaid
flowchart TD
  hook_fired([database-requested Hook])
```

#### Database Relation Departed Hook

file: [src/relations/pgbouncer_provider.py](https://github.com/canonical/pgbouncer-k8s-operator/blob/main/src/relations/pgbouncer_provider.py)

TODO

```mermaid
flowchart TD
  hook_fired([database-relation-departed Hook])
```


#### Database Relation Broken Hook

file: [src/relations/pgbouncer_provider.py](https://github.com/canonical/pgbouncer-k8s-operator/blob/main/src/relations/pgbouncer_provider.py)

TODO

```mermaid
flowchart TD
  hook_fired([database-relation-broken Hook])
```

#### db And db-admin Relation Joined Hook

file: [src/relations/db.py](https://github.com/canonical/pgbouncer-k8s-operator/blob/main/src/relations/db.py)

`db` and `db-admin` relations share the same logic. `db` has been used in this documentation, but they're interchangeable.

TODO

```mermaid
flowchart TD
  hook_fired([db-relation-joined Hook]) --> is_backend_ready{Is backend\ndatabase ready?}
  is_backend_ready -- no --> defer>defer]
  is_backend_ready -- yes --> is_cfg{Is pgbouncer\nconfig available?}
  is_cfg -- no --> defer2>defer]
  is_cfg -- yes --> extension_requested{Has the remote\napplication requested\nextensions?}
  extension_requested -- yes --> defer3>defer\nThis charm\ncurrently doesn't\nsupport extensions]
  extension_requested -- no --> get_data[Get database from databag\nand generate username]
  get_data --> is_leader{is this unit\nthe leader}
  is_leader -- no --> is_pw_in_databag{Is password in \n peer databag?}
  is_pw_in_databag -- no --> defer4>defer]
  is_pw_in_databag -- yes --> store_data[Store username,\npassword, and database\n in client relation databags]
  is_leader -- yes --> gen_pw[Generate password and\nstore in peer databag]
  gen_pw --> store_data
  store_data --> is_leader2{Is this unit\nthe leader}
  is_leader2 -- no --> rtn([Return])
  is_leader2 -- yes --> create_pg_data[Create user and database\n on backend postgres charm]
  create_pg_data --> add_to_cfg[Add database\nand user to\npgbouncer config]
  add_to_cfg --> rtn2([Return])
```

#### db And db-admin Relation Changed Hook

file: [src/relations/db.py](https://github.com/canonical/pgbouncer-k8s-operator/blob/main/src/relations/db.py)

`db` and `db-admin` relations share the same logic. `db` has been used in this documentation, but they're interchangeable.

TODO

```mermaid
flowchart TD
  hook_fired([db-relation-changed Hook])
```

#### db And db-admin Relation Departed Hook

file: [src/relations/db.py](https://github.com/canonical/pgbouncer-k8s-operator/blob/main/src/relations/db.py)

`db` and `db-admin` relations share the same logic. `db` has been used in this documentation, but they're interchangeable.

TODO

```mermaid
flowchart TD
  hook_fired([db-relation-departed Hook])
```

#### db And db-admin Relation Broken Hook

file: [src/relations/db.py](https://github.com/canonical/pgbouncer-k8s-operator/blob/main/src/relations/db.py)

`db` and `db-admin` relations share the same logic. `db` has been used in this documentation, but they're interchangeable.

TODO

```mermaid
flowchart TD
  hook_fired([db-relation-Broken Hook])
```
