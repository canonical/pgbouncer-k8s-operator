# How to manage related applications

## Modern `postgresql_client` interface:

Relations to new applications are supported via the "[postgresql_client](https://github.com/canonical/charm-relation-interfaces/blob/main/interfaces/postgresql_client/v0/README.md)" interface. To create a relation:

```shell
juju integrate pgbouncer-k8s application
```

To remove a relation:

```shell
juju remove-relation pgbouncer-k8s application
```

All listed on CharmHub applications are available [here](https://charmhub.io/pgbouncer-k8s/integrations), e.g.:
 * [postgresql-test-app](https://charmhub.io/postgresql-test-app)
 * [mattermost-k8s](https://charmhub.io/mattermost-k8s)

## Legacy `pgsql` interface:

This charm also supports the legacy relation via the `pgsql` interface. Please note that these interface is deprecated.

 ```shell
juju relate pgbouncer-k8s:db myapplication-k8s
```

Also extended permissions can be requested using `db-admin` endpoint:
```shell
juju relate pgbouncer-k8s:db-admin myapplication-k8s
```

## Internal operator user

To rotate the internal router passwords, the relation with backend-database should be removed and related again. That process will generate a new user and password for the application, while retaining the requested database and data.

```shell
juju remove-relation postgresql-k8s pgbouncer-k8s

juju integrate postgresql-k8s pgbouncer-k8s
```