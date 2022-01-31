# PgBouncer Kubernetes Operator

## Description

The PgBouncer Kubernetes Operator deploys and operates the [PgBouncer](https://www.pgbouncer.org) lightweight connection pooler for PostgreSQL.

## Usage

As this charm is not yet published, you need to follow the build and deploy instructions from [CONTRIBUTING.md](CONTRIBUTING.md).

## Relations

#### Planned
- `db:[pgsql](https://github.com/canonical/ops-lib-pgsql/)`
- `db-admin:[pgsql](https://github.com/canonical/ops-lib-pgsql/)`
- `backend-db-admin:[pgsql](https://github.com/canonical/ops-lib-pgsql/)`
  - Provides a relaton to the corresponding [postgresql-k8s-operator charm](https://github.com/canonical/postgresql-k8s-operator).

The following relations provide support for the [LMA charm bundle](https://juju.is/docs/lma2), our expected observability stack.

- `prometheus:prometheus_scrape`
- `loki:loki_push_api`
- `grafana:grafana_dashboards`

## OCI Images

This charm uses the canonical pgbouncer-container docker image, available here (currently in a PR): [https://github.com/canonical/pgbouncer-container](https://github.com/canonical/pgbouncer-container).

## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines
on enhancements to this charm following best practice guidelines, and
[CONTRIBUTING.md](./CONTRIBUTING.md) for developer guidance.
