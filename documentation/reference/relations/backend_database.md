# backend_database Relation Reference Documentation

This reference documentation details the implementation of the `backend-database` relation. The file implementing these relations can be found here: [src/relations/backend_database.py](../../../src/relations/backend_database.py).

## Expected Interface

These are the expected contents of the databags in this relation (all values are examples, generated in a running test instance):
| category         |             keys | pgbouncer-k8s-o… | postgresql-k8s/0 |
|---|---|---|--|
| metadata         |         endpoint | 'backend-databa… | 'database'       |
|                  |           leader | True             | True             |
| application data |             data | {"endpoints":"postgresql-k8s", "password":"18cqKCp19xOPBh",   "read-only-endpoints":"postgresql-k8s","username":"relation_18", "version":"12.9"}    | {"database":"postgresql", "extra-user-roles","SUPERUSER"    |
|                  |         database | pgbouncer        |                  |
|                  |        endpoints |                  | postgresql-k8s-… |
|                  | extra-user-roles | SUPERUSER        |                  |
|                  |         password |                  | 18cqKCp19xOPBh |
|                  | read-only-endpoints |                  | postgresql-k8s-… |
|                  |         username |                  | relation_18      |
|                  |          version |                  | 12.9             |

## Hook Handler Flowcharts

These flowcharts detail the control flow of the hooks in this program. Unless otherwise stated, **a hook deferral is always followed by a return**.

### Backend Database Created Hook

```mermaid
flowchart TD
  hook_fired([backend-database-requested Hook]) --> is_leader{Is current\nunit leader?}
  is_leader -- no --> rtn([return])
  is_leader -- yes --> is_running{Is pgbouncer\nrunning?}
  is_running -- no --> rtn3([return])
  is_running -- yes --> is_backend_ready{is backend database charm ready,\nand has pgbouncer been\nprovided with the\nnecessary relation data?}
  is_backend_ready -- no --> defer>defer]
  is_backend_ready -- yes --> generate_user[Generate username & password]
  generate_user --> create_auth_func[create auth function on postgres]
  create_auth_func --> save_auth_data[update pgbouncer config, and save\nauth data to container and peer databag]
  save_auth_data --> update_relations[update postgres endpoints in client relations]
  update_relations --> update_status[update charm status]
  update_status --> rtn2([return])
```

### Backend Database Departed Hook

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

### Backend Database Broken Hook

```mermaid
flowchart TD
  hook_fired([backend-database-relation-broken Hook]) --> check_depart{Is this unit not\nthe leader, or is the\nrelation_departing flag\n in the unit databag?}
  check_depart -- yes --> rtn([return])
  check_depart -- no --> is_cfg{Is pgbouncer\nconfig available?}
  is_cfg -- no --> defer>defer]
  is_cfg -- yes --> remove_auth[Remove authentication\ninformation from\npgbouncer config]
  remove_auth --> rtn2([return])
```
