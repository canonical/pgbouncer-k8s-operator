# Scale your PgBouncer K8s

This is part of the [PgBouncer K8s Tutorial](/t/12251). Please refer to this page for more information and the overview of the content.

## Adding and Removing units

Please check the explanation of scaling Charmed PostgreSQL K8s operator [here](https://charmhub.io/postgresql-k8s/docs/t-scale).

### Add more PgBouncer instances

You can add two more units to your deployed PgBouncer application by scaling it using:
```shell
juju scale-application pgbouncer-k8s 3
```

You can now watch the scaling process in live using: `juju status --watch 1s`. It usually takes several minutes for new cluster members to be added. You’ll know that all three nodes are in sync when `juju status` reports `Workload=active` and `Agent=idle`:
```shell
Model   Controller  Cloud/Region        Version  SLA          Timestamp
test16  microk8s    microk8s/localhost  3.1.6    unsupported  22:16:20+02:00

App              Version  Status  Scale  Charm            Channel    Rev  Address         Exposed  Message
data-integrator           active      1  data-integrator  stable      13  10.152.183.136  no       
pgbouncer-k8s    1.18.0   active      3  pgbouncer-k8s    1/stable    76  10.152.183.84   no       
postgresql-k8s   14.9     active      1  postgresql-k8s   14/stable  158  10.152.183.92   no       Primary

Unit                Workload  Agent  Address     Ports  Message
data-integrator/0*  active    idle   10.1.12.16         
pgbouncer-k8s/0*    active    idle   10.1.12.15         
pgbouncer-k8s/1     active    idle   10.1.12.61         
pgbouncer-k8s/2     active    idle   10.1.12.50         
postgresql-k8s/0*   active    idle   10.1.12.6          Primary
```

You can scale Charmed PostgreSQL in the same way:
```shell
juju scale-application postgresql-k8s 3
```
Make sure all units are active using `juju status`:
```shell
Model   Controller  Cloud/Region        Version  SLA          Timestamp
test16  microk8s    microk8s/localhost  3.1.6    unsupported  22:18:00+02:00

App              Version  Status  Scale  Charm            Channel    Rev  Address         Exposed  Message
data-integrator           active      1  data-integrator  stable      13  10.152.183.136  no       
pgbouncer-k8s    1.18.0   active      3  pgbouncer-k8s    1/stable    76  10.152.183.84   no       
postgresql-k8s   14.9     active      3  postgresql-k8s   14/stable  158  10.152.183.92   no       

Unit                Workload  Agent  Address     Ports  Message
data-integrator/0*  active    idle   10.1.12.16         
pgbouncer-k8s/0*    active    idle   10.1.12.15         
pgbouncer-k8s/1     active    idle   10.1.12.61         
pgbouncer-k8s/2     active    idle   10.1.12.50         
postgresql-k8s/0*   active    idle   10.1.12.6          Primary
postgresql-k8s/1    active    idle   10.1.12.35         
postgresql-k8s/2    active    idle   10.1.12.39
```

### Remove extra members
Removing a unit from the application scales the replicas down.
```shell
juju scale-application pgbouncer-k8s 2
```
```shell
juju scale-application postgresql-k8s 2
```

You’ll know that the replica was successfully removed when `juju status --watch 1s` reports:
```shell
Model   Controller  Cloud/Region        Version  SLA          Timestamp
test16  microk8s    microk8s/localhost  3.1.6    unsupported  22:19:10+02:00

App              Version  Status  Scale  Charm            Channel    Rev  Address         Exposed  Message
data-integrator           active      1  data-integrator  stable      13  10.152.183.136  no       
pgbouncer-k8s    1.18.0   active      2  pgbouncer-k8s    1/stable    76  10.152.183.84   no       
postgresql-k8s   14.9     active      2  postgresql-k8s   14/stable  158  10.152.183.92   no       

Unit                Workload  Agent  Address     Ports  Message
data-integrator/0*  active    idle   10.1.12.16         
pgbouncer-k8s/0*    active    idle   10.1.12.15         
pgbouncer-k8s/1     active    idle   10.1.12.61         
postgresql-k8s/0*   active    idle   10.1.12.6          Primary
postgresql-k8s/1    active    idle   10.1.12.35 
```