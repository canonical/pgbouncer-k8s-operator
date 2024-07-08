# Interfaces/endpoints

PgBouncer K8s supports modern ['postgresql_client'](https://github.com/canonical/charm-relation-interfaces) interface. Applications can easily connect PgBouncer using ['data_interfaces'](https://charmhub.io/data-platform-libs/libraries/data_interfaces) library from ['data-platform-libs'](https://github.com/canonical/data-platform-libs/).

### Modern `postgresql_client` interface (`database` endpoint):

Adding a relation is accomplished with `juju relate` (or `juju integrate` for Juju 3.x) via endpoint `database`. Read more about [Juju relations (integrations)](https://juju.is/docs/olm/relations). Example:

```shell
# Deploy Charmed PostgreSQL K8s and PgBouncer K8s clusters with 3 nodes each
juju deploy postgresql-k8s -n 3 --trust --channel 14/stable
juju deploy pgbouncer-k8s -n 3 --trust --channel 1/stable

# Deploy the relevant charms, e.g. postgresql-test-app
juju deploy postgresql-test-app

# Relate all applications
juju integrate postgresql-k8s pgbouncer-k8s
juju integrate pgbouncer-k8s postgresql-test-app:first-database

# Check established relation (using postgresql_client interface):
juju status --relations

# Example of the properly established relation:
# > Integration provider         Requirer                              Interface              Type     Message
# > pgbouncer-k8s:database       postgresql-test-app:first-database    postgresql_client      regular  
# > postgresql-k8s:database      pgbouncer-k8s:backend-database        postgresql_client      regular  
# > ...
```

See all the charm interfaces [here](https://charmhub.io/pgbouncer-k8s/integrations).