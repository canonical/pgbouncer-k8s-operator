# External K8s connection

To make the Charmed PostgreSQL K8s database reachable from outside the Kubernetes cluster, this charm PgBouncer K8s should be deployed. It creates and manages several K8s services including the NodePort one:

```shell
kubectl get services -n <model>
```

```
NAME                      TYPE        CLUSTER-IP       EXTERNAL-IP   PORT(S)             AGE
...
pgbouncer-k8s             ClusterIP   10.152.183.48    <none>        65535/TCP           20m
pgbouncer-k8s-endpoints   ClusterIP   None             <none>        <none>              20m
pgbouncer-k8s-nodeport    NodePort    10.152.183.116   <none>        6432:30288/TCP      20m
...
```

The `pgbouncer-k8s-nodeport` NodePort service exposes a port to access both R/W and R/O PostgreSQL servers from outside of K8s. The charm opens NodePort if requested in relation as `external-node-connectivity: true`. Example (relate pgbouncer-k8s with data-integrator):
```shell
> juju run data-integrator/0 get-credentials
...
postgresql:
  data: '{"database": "test123", "external-node-connectivity": "true", "requested-secrets":
    "[\"username\", \"password\", \"tls\", \"tls-ca\", \"uris\"]"}'
  database: test123
  endpoints: 10.76.203.225:30288
  password: lJPIjF04GCPYptiR2k1f4NUt
  read-only-endpoints: 10.76.203.225:30288
  uris: postgresql://relation_id_22:lJPIjF04GCPYptiR2k1f4NUt@10.76.203.225:30288/test123
  username: relation_id_22
  version: "14.13"
```
> **Note**: the relation flag `external-node-connectivity` is experimental and will be replaced in the future. Follow https://warthogs.atlassian.net/browse/DPE-5636 for more details. 

> **Note**: The `pgbouncer-k8s` and `pgbouncer-k8s-endpoints` ClusterIP services seen above are created for every Juju application by default as part of the StatefulSet they are associated with. These services are not relevant to users and can be safely ignored.

## Client connections using the bootstrap service

A client can be configured to connect to the `pgbouncer-k8s-nodeport` service using a Kubernetes NodeIP, and desired NodePort.

To get NodeIPs:

```shell
kubectl get nodes -o wide -n model | awk -v OFS='\t\t' '{print $1, $6}'
```

```
NAME        INTERNAL-IP
node-0      10.155.67.110
node-1      10.155.67.120
node-2      10.155.67.130
```

NodeIPs are different for each deployment as they are randomly allocated.
For the example from the previous section, the created NodePorts was:

```shell
6432:30288/TCP
```

Users can use this NodePort to access read-write / Primary server from outside of K8s:
```shell
> psql postgresql://relation_id_22:lJPIjF04GCPYptiR2k1f4NUt@10.155.67.120:30288/test123
...

test123=> create table A (id int);
CREATE TABLE

test123=> \d
           List of relations
 Schema | Name | Type  |     Owner
--------+------+-------+----------------
 public | a    | table | relation_id_22
(1 row)
...
```
Read-only servers can be accessed using the `_readonly` suffix to the desired DB name:
```shell
> psql postgresql://relation_id_22:lJPIjF04GCPYptiR2k1f4NUt@10.155.67.120:30288/test123_readonly
...

test123_readonly=> create table B (id int);
ERROR:  cannot execute CREATE TABLE in a read-only transaction

test123_readonly=> \d
           List of relations
 Schema | Name | Type  |     Owner
--------+------+-------+----------------
 public | a    | table | relation_id_22
(1 row)
```