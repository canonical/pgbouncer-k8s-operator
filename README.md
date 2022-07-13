# PgBouncer Kubernetes Operator

## Description

The PgBouncer Kubernetes Operator deploys and operates the [PgBouncer](https://www.pgbouncer.org) lightweight connection pooler for PostgreSQL.

## Usage

As this charm is not yet published, you need to follow the build and deploy instructions from [CONTRIBUTING.md](https://github.com/canonical/pgbouncer-k8s-operator/CONTRIBUTING.md).

## Relations

- `backend:postgresql-client`
  - Provides a relation to the corresponding [postgresql-k8s-operator charm](https://github.com/canonical/postgresql-k8s-operator).
  - Makes use of the [data-platform-libs DatabaseRequires object](), and expects something im

### Planned

- `db:`[`pgsql`](https://github.com/canonical/ops-lib-pgsql/)
- `db-admin:`[`pgsql`](https://github.com/canonical/ops-lib-pgsql/)

The following relations provide support for the [LMA charm bundle](https://juju.is/docs/lma2), our expected observability stack.

- `prometheus:prometheus_scrape`
- `loki:loki_push_api`
- `grafana:grafana_dashboards`

## OCI Images

This charm uses the canonical pgbouncer-container docker image, available [here](https://github.com/canonical/pgbouncer-container). As this container has not been uploaded anywhere, **you will need to build this image locally and import it into your container registry before use**, following the instructions in [CONTRIBUTING.md]([CONTRIBUTING.md](https://github.com/canonical/pgbouncer-k8s-operator/CONTRIBUTING.md)).

## License

The Charmed PgBouncer Operator is free software, distributed under the Apache Software License, version 2.0. See [LICENSE](https://github.com/canonical/pgbouncer-k8s-operator/blob/main/LICENSE) for more information.

## Security

Security issues in the Charmed PgBouncer Operator can be reported through [LaunchPad](https://wiki.ubuntu.com/DebuggingSecurity#How%20to%20File). Please do not file GitHub issues about security issues.

## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines
on enhancements to this charm following best practice guidelines, and
[CONTRIBUTING.md](https://github.com/canonical/pgbouncer-k8s-operator/CONTRIBUTING.md) for developer guidance.
