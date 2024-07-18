# How to enable monitoring

Enable monitoring requires that you:
* [Have a PgBouncer K8s deployed](/t/12253)
* [Deploy `cos-lite` bundle in a Kubernetes environment](https://charmhub.io/topics/canonical-observability-stack/tutorials/install-microk8s)
* [COS configured for Charmed PostgreSQL K8s](https://charmhub.io/postgresql-k8s/docs/h-enable-monitoring)

Switch to COS K8s environment and offer COS interfaces to be cross-model related with PgBouncer K8s model:
```shell
# Switch to Kubernetes controller, for the cos model.
juju switch <k8s_cos_controller>:<cos_model_name>

juju offer grafana:grafana-dashboard
juju offer loki:logging
juju offer prometheus:receive-remote-write
```

Switch to PgBouncer K8s model, find offers and consume them:
```shell
# We are on the Kubernetes controller, for the cos model. Switch to postgresql model
juju switch <k8s_db_controller>:<postgresql_model_name>

juju find-offers <k8s_cos_controller>: # Do not miss ':' here!
```

A similar output should appear, if `k8s` is the k8s controller name and `cos` the model where `cos-lite` has been deployed:
```shell
Store  URL                    Access  Interfaces
k8s    admin/cos:grafana      admin   grafana:grafana-dashboard
k8s    admin/cos.loki         admin   loki:logging
k8s    admin/cos.prometheus   admin   prometheus:receive-remote-write
...
```

Consume offers to be reachable in the current model:
```shell
juju consume <k8s_cos_controller>:admin/cos.grafana
juju consume <k8s_cos_controller>:admin/cos.loki
juju consume <k8s_cos_controller>:admin/cos.prometheus
```

Now, deploy '[grafana-agent-k8s](https://charmhub.io/grafana-agent-k8s)' (as `pgbouncer-cos-agent`) and integrate (relate) it with PgBouncer K8s, later integrate (relate) `pgbouncer-cos-agent` with consumed COS offers:
```shell
juju deploy grafana-agent-k8s pgbouncer-cos-agent --trust

juju relate pgbouncer-cos-agent grafana
juju relate pgbouncer-cos-agent loki
juju relate pgbouncer-cos-agent prometheus

juju relate pgbouncer-cos-agent pgbouncer-k8s:grafana-dashboard
juju relate pgbouncer-cos-agent pgbouncer-k8s:logging
juju relate pgbouncer-cos-agent pgbouncer-k8s:metrics-endpoint
```

After this is complete, Grafana will show the new dashboards: `PgBouncer Exporter` and allows access for PgBouncer logs on Loki.

The example of `juju status` for Charmed PostgreSQL K8s + PgBouncer K8s model:
```shell
TODO
```

The example of `juju status` on COS K8s model:
```shell
Model  Controller  Cloud/Region        Version  SLA          Timestamp
cos    microk8s    microk8s/localhost  3.1.6    unsupported  00:21:19+02:00

App           Version  Status  Scale  Charm             Channel  Rev  Address         Exposed  Message
alertmanager  0.25.0   active      1  alertmanager-k8s  edge      91  10.152.183.215  no       
catalogue              active      1  catalogue-k8s     edge      27  10.152.183.187  no       
grafana       9.2.1    active      1  grafana-k8s       edge      92  10.152.183.95   no       
loki          2.7.4    active      1  loki-k8s          edge      99  10.152.183.28   no       
prometheus    2.46.0   active      1  prometheus-k8s    edge     149  10.152.183.232  no       
traefik       2.10.4   active      1  traefik-k8s       edge     155  10.76.203.228   no       

Unit             Workload  Agent  Address       Ports  Message
alertmanager/0*  active    idle   10.1.142.186         
catalogue/0*     active    idle   10.1.142.176         
grafana/0*       active    idle   10.1.142.189         
loki/0*          active    idle   10.1.142.187         
prometheus/0*    active    idle   10.1.142.188         
traefik/0*       active    idle   10.1.142.185         

Offer       Application  Charm           Rev  Connected  Endpoint              Interface                Role
grafana     grafana      grafana-k8s     92   1/1        grafana-dashboard     grafana_dashboard        requirer
loki        loki         loki-k8s        99   1/1        logging               loki_push_api            provider
prometheus  prometheus   prometheus-k8s  149  1/1        receive-remote-write  prometheus_remote_write  provider

```

To connect Grafana WEB interface, follow the COS section "[Browse dashboards](https://charmhub.io/topics/canonical-observability-stack/tutorials/install-microk8s)":
```shell
juju run grafana/leader get-admin-password --model <k8s_cos_controller>:<cos_model_name>
```