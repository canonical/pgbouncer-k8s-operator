# database Relation Reference Documentation

This reference documentation details the implementation of the `database` relation. This relation is used to connect to applications that use the updated client interface for postgres. The file implementing these relations can be found here: [src/relations/pgbouncer_provider.py](../../../src/relations/pgbouncer_provider.py).

Importantly, this relation doesn't handle scaling the same way others do. All PgBouncer nodes are read/writes, and they expose the read/write nodes of the backend database through the database name f"{dbname}_readonly".

## Expected Interface

These are the expected contents of the databags in this relation (all values are examples, generated in a running test instance):

| relation (id: 4) | application | pgbouncer-k8s|
|---|---|---|
|**metadata**|
| relation name    | first-database | database|
| interface        | postgresql_client | postgresql_client  |
| leader unit      | 0| 1 |
| **application data**|
| data                |   {"endpoints": "pgbouncer-k8s-1.pgbouncer-k8s-endpoints.test-pgbouncer-provider-5l5…","password": "2LDDKswhH5DdMvjEAZ9igVET", "read-only-endpoints":"pgbouncer-k8s-2.pgbouncer-k8s-endpoints.test-pgbouncer-provider-5l5…", "username": "relation_id_4", "version": "14.5"}  | {"database": "application_first_database", "extra-user-roles":"CREATEDB,CREATEROLE"} |
| endpoints           | | pgbouncer-k8s-1.pgbouncer-k8s-endpoints.test-pgbouncer-provider-5l…  |
| password            | |2LDDKswhH5DdMvjEAZ9igVET |
| read-only-endpoints | | pgbouncer-k8s-2.pgbouncer-k8s-endpoints.test-pgbouncer-provider-5l…  |
| username            | |  relation_id_4|
| version             | | 14.5 |
| database            | application_first_database | |
| extra-user-roles    | CREATEDB,CREATEROLE| |

## Hook Handler Flowcharts

These flowcharts detail the control flow of the hooks in this program. Unless otherwise stated, **a hook deferral is always followed by a return**.

### Database Requested Hook

```mermaid
flowchart TD
  hook_fired([database-requested Hook]) --> is_leader{is this unit\nthe leader}
  is_leader -- no --> rtn([Return])
  is_leader -- yes --> is_backend_ready{Is backend\ndatabase ready?}
  is_backend_ready -- no --> defer>defer]
  is_backend_ready -- yes --> get_user[Get user data and\ngenerate password]
  get_user --> create_user_and_db[Create user\nand database]
  create_user_and_db --> add_user[Add user to\npgbouncer config\nand peer databag]
  add_user --> update_pg[Update pgbouncer\nconfig with updated\nconnection information]
  update_pg --> update_databag[Update relation databag\nwith credentials and\nconnection information]
  update_databag --> rtn2([Return])
```

### Database Relation Departed Hook

```mermaid
flowchart TD
  hook_fired([database-relation-departed Hook]) --> update_connection_info[Update connection\ninformation in\nrelation databag]
  update_connection_info --> is_departing{Is this unit departing\nfrom the relation\nduring this hook?}
  is_departing -- yes --> add_flag[Add departing flag\nso this unit knows\nthat it's being removed\nif the relation-broken\nhook fires after this.]
  is_departing -- no --> rtn([Return])
  add_flag --> rtn
```

### Database Relation Broken Hook

```mermaid
flowchart TD
  hook_fired([database-relation-broken Hook]) --> update_connection_info[Update connection\ninformation in\nrelation databag]
  update_connection_info --> is_backend_and_leader{Is the backend\nready, and is this\nunit the leader?}
  is_backend_and_leader -- no --> rtn([Return])
  is_backend_and_leader -- yes --> is_departing{Is this unit departing,\naccording to the flag\nset in the departed hook?}
  is_departing -- yes --> rtn2([Return])
  is_departing -- no --> remove_data[Remove user and\ndatabase from\npgb config]
  remove_data --> delete_user[Delete user from\nbackend charm]
  delete_user --> rtn3([Return])
```
