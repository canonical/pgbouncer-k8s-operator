# How to connect DB from outside of Kubernetes

To expose a Charmed PostgreSQL K8s database externally, this charm (PgBouncer K8s) should be deployed and related with the Charmed PostgreSQL K8s application. Charmed PgBouncer K8s then provides a configuration option `expose-external` (with options `false`, `nodeport` and `loadbalancer`) to control precisely how the database will be externally exposed.

By default (when `expose-external=false`), Charmed PgBouncer K8s creates a K8s service of type `ClusterIP` which it provides as endpoints to the related client applications. These endpoints are only accessible from within the K8s namespace (or juju model) where the PgBouncer K8s application is deployed.

Below is a juju model where PgBouncer K8s is related to PostgreSQL K8s and Data Integrator, which we will later use to demonstrate the configuration of `expose-external`:

```shell
$ juju status --relations
Model     Controller  Cloud/Region        Version  SLA          Timestamp
database  uk8s-3-6-2  microk8s/localhost  3.6.2    unsupported  14:06:38Z

App              Version  Status  Scale  Charm            Channel        Rev  Address         Exposed  Message
data-integrator           active      1  data-integrator  latest/stable   78  10.152.183.106  no       
pgbouncer-k8s    1.21.0   active      1  pgbouncer-k8s    1/edge         406  10.152.183.170  no       
postgresql-k8s   14.15    active      2  postgresql-k8s   14/edge        495  10.152.183.164  no       

Unit                Workload  Agent  Address       Ports  Message
data-integrator/0*  active    idle   10.1.241.222         
pgbouncer-k8s/0*    active    idle   10.1.241.211         
postgresql-k8s/0    active    idle   10.1.241.223         
postgresql-k8s/1*   active    idle   10.1.241.251         Primary

Integration provider                   Requirer                               Interface              Type     Message
data-integrator:data-integrator-peers  data-integrator:data-integrator-peers  data-integrator-peers  peer     
pgbouncer-k8s:database                 data-integrator:postgresql             postgresql_client      regular  
pgbouncer-k8s:pgb-peers                pgbouncer-k8s:pgb-peers                pgb_peers              peer     
pgbouncer-k8s:upgrade                  pgbouncer-k8s:upgrade                  upgrade                peer     
postgresql-k8s:database                pgbouncer-k8s:backend-database         postgresql_client      regular  
postgresql-k8s:database-peers          postgresql-k8s:database-peers          postgresql_peers       peer     
postgresql-k8s:restart                 postgresql-k8s:restart                 rolling_op             peer     
postgresql-k8s:upgrade                 postgresql-k8s:upgrade                 upgrade                peer
```

When `expose-external=false` (default value), the following shows the endpoints returned to the client:

```shell
$ juju config pgbouncer-k8s expose-external=false

$ juju run data-integrator/0 get-credentials
Running operation 1 with 1 task
  - task 2 on unit-data-integrator-0

Waiting for task 2...
ok: "True"
postgresql:
  data: '{"database": "test_database", "external-node-connectivity": "true", "requested-secrets":
    "[\"username\", \"password\", \"tls\", \"tls-ca\", \"uris\"]"}'
  database: test_database
  endpoints: pgbouncer-k8s-service.database.svc.cluster.local:6432
  password: fXw7lzSrHtRT8EUILPo4xfXA
  read-only-endpoints: pgbouncer-k8s-service.database.svc.cluster.local:6432
  uris: postgresql://relation_id_6:fXw7lzSrHtRT8EUILPo4xfXA@pgbouncer-k8s-service.database.svc.cluster.local:6432/test_database
  username: relation_id_6
  version: "14.15"
```

The following shows a postgresql client connecting to the the provided endpoints from the data integrator unit (which is deployed in the same K8s namespace, i.e. the same juju model, as PgBouncer K8s):

```shell
root@data-integrator-0:/var/lib/juju# psql postgresql://relation_id_6:fXw7lzSrHtRT8EUILPo4xfXA@pgbouncer-k8s-service.database.svc.cluster.local:6432/test_database
psql (14.15 (Ubuntu 14.15-0ubuntu0.22.04.1))
Type "help" for help.

test_database=> \l
                                       List of databases
     Name      |     Owner     | Encoding | Collate |  Ctype  |        Access privileges        
---------------+---------------+----------+---------+---------+---------------------------------
 pgbouncer     | operator      | UTF8     | C       | C.UTF-8 | operator=CTc/operator          +
               |               |          |         |         | relation_id_7=CTc/operator     +
               |               |          |         |         | admin=CTc/operator             +
               |               |          |         |         | backup=CTc/operator            +
               |               |          |         |         | replication=CTc/operator       +
               |               |          |         |         | rewind=CTc/operator            +
               |               |          |         |         | monitoring=CTc/operator
 postgres      | operator      | UTF8     | C       | C.UTF-8 | operator=CTc/operator          +
               |               |          |         |         | backup=CTc/operator            +
               |               |          |         |         | replication=CTc/operator       +
               |               |          |         |         | rewind=CTc/operator            +
               |               |          |         |         | monitoring=CTc/operator        +
               |               |          |         |         | admin=c/operator
 template0     | operator      | UTF8     | C       | C.UTF-8 | =c/operator                    +
               |               |          |         |         | operator=CTc/operator
 template1     | operator      | UTF8     | C       | C.UTF-8 | =c/operator                    +
               |               |          |         |         | operator=CTc/operator
 test_database | relation_id_7 | UTF8     | C       | C.UTF-8 | relation_id_7=CTc/relation_id_7+
               |               |          |         |         | relation_id_6=CTc/relation_id_7+
               |               |          |         |         | admin=CTc/relation_id_7
(5 rows)

test_database=> exit
root@data-integrator-0:/var/lib/juju# psql postgresql://relation_id_6:fXw7lzSrHtRT8EUILPo4xfXA@pgbouncer-k8s-service.database.svc.cluster.local:6432/test_database_readonly
psql (14.15 (Ubuntu 14.15-0ubuntu0.22.04.1))
Type "help" for help.

test_database_readonly=> \l
                                       List of databases
     Name      |     Owner     | Encoding | Collate |  Ctype  |        Access privileges        
---------------+---------------+----------+---------+---------+---------------------------------
 pgbouncer     | operator      | UTF8     | C       | C.UTF-8 | operator=CTc/operator          +
               |               |          |         |         | relation_id_7=CTc/operator     +
               |               |          |         |         | admin=CTc/operator             +
               |               |          |         |         | backup=CTc/operator            +
               |               |          |         |         | replication=CTc/operator       +
               |               |          |         |         | rewind=CTc/operator            +
               |               |          |         |         | monitoring=CTc/operator
 postgres      | operator      | UTF8     | C       | C.UTF-8 | operator=CTc/operator          +
               |               |          |         |         | backup=CTc/operator            +
               |               |          |         |         | replication=CTc/operator       +
               |               |          |         |         | rewind=CTc/operator            +
               |               |          |         |         | monitoring=CTc/operator        +
               |               |          |         |         | admin=c/operator
 template0     | operator      | UTF8     | C       | C.UTF-8 | =c/operator                    +
               |               |          |         |         | operator=CTc/operator
 template1     | operator      | UTF8     | C       | C.UTF-8 | =c/operator                    +
               |               |          |         |         | operator=CTc/operator
 test_database | relation_id_7 | UTF8     | C       | C.UTF-8 | relation_id_7=CTc/relation_id_7+
               |               |          |         |         | relation_id_6=CTc/relation_id_7+
               |               |          |         |         | admin=CTc/relation_id_7
(5 rows)
```

## External Access

PgBouncer K8s can be made externally accessible by setting `expose-external=nodeport` (corresponding to K8s NodePort service) or `expose-external=loadbalancer` (corresponding to K8s LoadBalancer service).

When `expose-external=nodeport`, PgBouncer K8s will provide as endpoints comma-separated node:port values of the nodes where the PgBouncer K8s units are scheduled.

```
$ juju config pgbouncer-k8s expose-external=nodeport

$ juju run data-integrator/0 get-credentials
Running operation 3 with 1 task
  - task 4 on unit-data-integrator-0

Waiting for task 4...
ok: "True"
postgresql:
  data: '{"database": "test_database", "external-node-connectivity": "true", "requested-secrets":
    "[\"username\", \"password\", \"tls\", \"tls-ca\", \"uris\"]"}'
  database: test_database
  endpoints: 10.0.0.44:31872
  password: fXw7lzSrHtRT8EUILPo4xfXA
  read-only-endpoints: 10.0.0.44:31872
  uris: postgresql://relation_id_6:fXw7lzSrHtRT8EUILPo4xfXA@10.0.0.44:31872/test_database
  username: relation_id_6
  version: "14.15"

$ psql postgresql://relation_id_6:fXw7lzSrHtRT8EUILPo4xfXA@10.0.0.44:31872/test_database
psql (14.15 (Ubuntu 14.15-0ubuntu0.22.04.1))
Type "help" for help.

test_database=> \l
                                       List of databases
     Name      |     Owner     | Encoding | Collate |  Ctype  |        Access privileges        
---------------+---------------+----------+---------+---------+---------------------------------
 pgbouncer     | operator      | UTF8     | C       | C.UTF-8 | operator=CTc/operator          +
               |               |          |         |         | relation_id_7=CTc/operator     +
               |               |          |         |         | admin=CTc/operator             +
               |               |          |         |         | backup=CTc/operator            +
               |               |          |         |         | replication=CTc/operator       +
               |               |          |         |         | rewind=CTc/operator            +
               |               |          |         |         | monitoring=CTc/operator
 postgres      | operator      | UTF8     | C       | C.UTF-8 | operator=CTc/operator          +
               |               |          |         |         | backup=CTc/operator            +
               |               |          |         |         | replication=CTc/operator       +
               |               |          |         |         | rewind=CTc/operator            +
               |               |          |         |         | monitoring=CTc/operator        +
               |               |          |         |         | admin=c/operator
 template0     | operator      | UTF8     | C       | C.UTF-8 | =c/operator                    +
               |               |          |         |         | operator=CTc/operator
 template1     | operator      | UTF8     | C       | C.UTF-8 | =c/operator                    +
               |               |          |         |         | operator=CTc/operator
 test_database | relation_id_7 | UTF8     | C       | C.UTF-8 | relation_id_7=CTc/relation_id_7+
               |               |          |         |         | relation_id_6=CTc/relation_id_7+
               |               |          |         |         | admin=CTc/relation_id_7
(5 rows)

test_database=> exit
$ psql postgresql://relation_id_6:fXw7lzSrHtRT8EUILPo4xfXA@10.0.0.44:31872/test_database_readonly
psql (14.15 (Ubuntu 14.15-0ubuntu0.22.04.1))
Type "help" for help.

test_database_readonly=> \l
                                       List of databases
     Name      |     Owner     | Encoding | Collate |  Ctype  |        Access privileges        
---------------+---------------+----------+---------+---------+---------------------------------
 pgbouncer     | operator      | UTF8     | C       | C.UTF-8 | operator=CTc/operator          +
               |               |          |         |         | relation_id_7=CTc/operator     +
               |               |          |         |         | admin=CTc/operator             +
               |               |          |         |         | backup=CTc/operator            +
               |               |          |         |         | replication=CTc/operator       +
               |               |          |         |         | rewind=CTc/operator            +
               |               |          |         |         | monitoring=CTc/operator
 postgres      | operator      | UTF8     | C       | C.UTF-8 | operator=CTc/operator          +
               |               |          |         |         | backup=CTc/operator            +
               |               |          |         |         | replication=CTc/operator       +
               |               |          |         |         | rewind=CTc/operator            +
               |               |          |         |         | monitoring=CTc/operator        +
               |               |          |         |         | admin=c/operator
 template0     | operator      | UTF8     | C       | C.UTF-8 | =c/operator                    +
               |               |          |         |         | operator=CTc/operator
 template1     | operator      | UTF8     | C       | C.UTF-8 | =c/operator                    +
               |               |          |         |         | operator=CTc/operator
 test_database | relation_id_7 | UTF8     | C       | C.UTF-8 | relation_id_7=CTc/relation_id_7+
               |               |          |         |         | relation_id_6=CTc/relation_id_7+
               |               |          |         |         | admin=CTc/relation_id_7
(5 rows)
```

Similarly, when `expose-external=loadbalancer`, PgBouncer K8s will provide as endpoints comma-separated node:port values of the load balancer nodes associated with the PgBouncer K8s service:

```shell
$ juju config pgbouncer-k8s expose-external=loadbalancer

$ juju run data-integrator/0 get-credentials
Running operation 5 with 1 task
  - task 6 on unit-data-integrator-0

Waiting for task 6...
ok: "True"
postgresql:
  data: '{"database": "test_database", "external-node-connectivity": "true", "requested-secrets":
    "[\"username\", \"password\", \"tls\", \"tls-ca\", \"uris\"]"}'
  database: test_database
  endpoints: 10.0.0.44:6432
  password: fXw7lzSrHtRT8EUILPo4xfXA
  read-only-endpoints: 10.0.0.44:6432
  uris: postgresql://relation_id_6:fXw7lzSrHtRT8EUILPo4xfXA@10.0.0.44:6432/test_database
  username: relation_id_6
  version: "14.15"

$ psql postgresql://relation_id_6:fXw7lzSrHtRT8EUILPo4xfXA@10.0.0.44:6432/test_database
psql (14.15 (Ubuntu 14.15-0ubuntu0.22.04.1))
Type "help" for help.

test_database=> \l
                                       List of databases
     Name      |     Owner     | Encoding | Collate |  Ctype  |        Access privileges        
---------------+---------------+----------+---------+---------+---------------------------------
 pgbouncer     | operator      | UTF8     | C       | C.UTF-8 | operator=CTc/operator          +
               |               |          |         |         | relation_id_7=CTc/operator     +
               |               |          |         |         | admin=CTc/operator             +
               |               |          |         |         | backup=CTc/operator            +
               |               |          |         |         | replication=CTc/operator       +
               |               |          |         |         | rewind=CTc/operator            +
               |               |          |         |         | monitoring=CTc/operator
 postgres      | operator      | UTF8     | C       | C.UTF-8 | operator=CTc/operator          +
               |               |          |         |         | backup=CTc/operator            +
               |               |          |         |         | replication=CTc/operator       +
               |               |          |         |         | rewind=CTc/operator            +
               |               |          |         |         | monitoring=CTc/operator        +
               |               |          |         |         | admin=c/operator
 template0     | operator      | UTF8     | C       | C.UTF-8 | =c/operator                    +
               |               |          |         |         | operator=CTc/operator
 template1     | operator      | UTF8     | C       | C.UTF-8 | =c/operator                    +
               |               |          |         |         | operator=CTc/operator
 test_database | relation_id_7 | UTF8     | C       | C.UTF-8 | relation_id_7=CTc/relation_id_7+
               |               |          |         |         | relation_id_6=CTc/relation_id_7+
               |               |          |         |         | admin=CTc/relation_id_7
(5 rows)

test_database=> exit
```

Add the suffix `_readonly` to the database name to access read-only endpoints:

```shell
$ psql postgresql://relation_id_6:fXw7lzSrHtRT8EUILPo4xfXA@10.0.0.44:6432/test_database_readonly
psql (14.15 (Ubuntu 14.15-0ubuntu0.22.04.1))
Type "help" for help.

test_database_readonly=> \l
                                       List of databases
     Name      |     Owner     | Encoding | Collate |  Ctype  |        Access privileges        
---------------+---------------+----------+---------+---------+---------------------------------
 pgbouncer     | operator      | UTF8     | C       | C.UTF-8 | operator=CTc/operator          +
               |               |          |         |         | relation_id_7=CTc/operator     +
               |               |          |         |         | admin=CTc/operator             +
               |               |          |         |         | backup=CTc/operator            +
               |               |          |         |         | replication=CTc/operator       +
               |               |          |         |         | rewind=CTc/operator            +
               |               |          |         |         | monitoring=CTc/operator
 postgres      | operator      | UTF8     | C       | C.UTF-8 | operator=CTc/operator          +
               |               |          |         |         | backup=CTc/operator            +
               |               |          |         |         | replication=CTc/operator       +
               |               |          |         |         | rewind=CTc/operator            +
               |               |          |         |         | monitoring=CTc/operator        +
               |               |          |         |         | admin=c/operator
 template0     | operator      | UTF8     | C       | C.UTF-8 | =c/operator                    +
               |               |          |         |         | operator=CTc/operator
 template1     | operator      | UTF8     | C       | C.UTF-8 | =c/operator                    +
               |               |          |         |         | operator=CTc/operator
 test_database | relation_id_7 | UTF8     | C       | C.UTF-8 | relation_id_7=CTc/relation_id_7+
               |               |          |         |         | relation_id_6=CTc/relation_id_7+
               |               |          |         |         | admin=CTc/relation_id_7
(5 rows)

test_database_readonly=> create table test (id int);
ERROR:  cannot execute CREATE TABLE in a read-only transaction

test_database_readonly=> exit
```

**Note**:  The K8s service created by PgBouncer K8s is owned by the K8s StatefulSet that represents the PgBouncer K8s juju application. Thus, the K8s service is cleaned up when the PgBouncer K8s application is removed.