# Deploy PgBouncer K8s

Please follow the [PgBouncer K8s Tutorial](/t/12251) for technical details and explanations.

Short story for your Ubuntu 22.04 LTS:
```shell
sudo snap install multipass
multipass launch --cpus 4 --memory 8G --disk 30G --name my-vm charm-dev # tune CPU/RAM/HDD accordingly to your needs
multipass shell my-vm

juju add-model demo
juju deploy postgresql-k8s --channel 14/stable --trust # --config profile=testing
juju deploy pgbouncer-k8s --channel 1/stable --trust

juju integrate postgresql-k8s pgbouncer-k8s

juju status --watch 1s
```

The expected result:
```shell 
Model  Controller  Cloud/Region        Version  SLA          Timestamp
demo   microk8s    microk8s/localhost  3.1.6    unsupported  22:42:26+02:00

App             Version  Status  Scale  Charm           Channel    Rev  Address         Exposed  Message
pgbouncer-k8s   1.18.0   active      1  pgbouncer-k8s   1/stable    76  10.152.183.128  no       backend-database relation initialised.
postgresql-k8s  14.9     active      1  postgresql-k8s  14/stable  158  10.152.183.110  no       

Unit               Workload  Agent      Address     Ports  Message
pgbouncer-k8s/0*   active    executing  10.1.12.36         backend-database relation initialised.
postgresql-k8s/0*  active    idle       10.1.12.22
```
The charm PgBouncer K8s is now waiting for relations with a client application, e.g. [postgresql-test-app](https://charmhub.io/postgresql-test-app), [mattermost](https://charmhub.io/mattermost-k8s), ...

Check the [Testing](/t/12272) reference to test your deployment.