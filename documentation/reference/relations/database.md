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

TODO format

```mermaid
flowchart TD
  hook_fired([database-requested Hook]) --> is_backend_ready{Is backend\ndatabase ready?}
  is_backend_ready -- no --> defer>defer]
  is_backend_ready -- yes --> is_leader{is this unit\nthe leader}
  is_leader -- no --> rtn([Return])
  is_leader -- yes --> get_user[Get user data and generate password]
  get_user --> create_user_and_db[Create user and database]
  create_user_and_db --> add_user[Add user to pgbouncer config and peer databag]
  add_user --> update_pg[Update pgbouncer config with updated connection information]
  update_pg --> update_databag[Update relation databag with credentials and connection information]
  update_databag --> rtn2([Return])
```

### Database Relation Departed Hook

TODO format

```mermaid
flowchart TD
  hook_fired([database-relation-departed Hook]) --> update_connection_info[Update connection information in relation databag]
  update_connection_info --> is_departing{Is this unit departing from the relation during this hook?}
  is_departing -- yes --> add_flag[Add departing flag so this unit knows that it's being removed if the relation-broken hook fires after this.]
  is_departing -- no --> rtn([Return])
  add_flag --> rtn
```

### Database Relation Broken Hook

TODO format

```mermaid
flowchart TD
  hook_fired([database-relation-broken Hook]) --> update_connection_info[Update connection information in relation databag]
  update_connection_info --> is_backend_and_leader{Is the backend ready, and is this unit the leader?}
  is_backend_and_leader -- no --> rtn([Return])
  is_backend_and_leader -- yes --> is_departing{Is this unit departing, according to the flag set in the departed hook?}
  is_departing -- yes --> rtn2([Return])
  is_departing -- no --> remove_data[Remove user and database from pgb config]
  remove_data --> delete_user[Delete user from backend charm]
  delete_user --> rtn3([Return])
```
