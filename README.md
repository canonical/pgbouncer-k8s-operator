# Charmed PgBouncer Kubernetes Operator
[![Charmhub](https://charmhub.io/pgbouncer-k8s/badge.svg)](https://charmhub.io/pgbouncer-k8s)
[![Release](https://github.com/canonical/pgbouncer-k8s-operator/actions/workflows/release.yaml/badge.svg)](https://github.com/canonical/pgbouncer-k8s-operator/actions/workflows/release.yaml)
[![Tests](https://github.com/canonical/pgbouncer-k8s-operator/actions/workflows/ci.yaml/badge.svg?branch=main)](https://github.com/canonical/pgbouncer-k8s-operator/actions/workflows/ci.yaml)

## Description

The PgBouncer Kubernetes Operator deploys and operates the [PgBouncer](https://www.pgbouncer.org) lightweight connection pooler for PostgreSQL.

## Usage

As this charm is not yet published, you need to follow the build and deploy instructions from [CONTRIBUTING.md](https://github.com/canonical/pgbouncer-k8s-operator/CONTRIBUTING.md).

## Relations

- `backend-database:postgresql-client`
  - Provides a relation to the corresponding [postgresql-k8s charm](https://github.com/canonical/postgresql-k8s-operator).
  - Makes use of the [data-platform-libs DatabaseRequires library](https://github.com/canonical/data-platform-libs/blob/main/lib/charms/data_platform_libs/v0/database_provides.py).
- `database:postgresql-client`
  - Provides a relation to client applications.
  - Importantly, this relation doesn't handle scaling the same way others do. All PgBouncer nodes are read/writes, and they expose the read-only nodes of the backend database through the database name `f"{dbname}_readonly"`.

The expected data presented in a relation interface is provided in the docstring at the top of the source files for each relation.

### Legacy

These relations will be deprecated in future. When deploying these relations, please ensure the `backend` relation is completed first. Using legacy relations with normal relations is not extensively tested.

- `db:`[`pgsql`](https://github.com/canonical/ops-lib-pgsql/)
- `db-admin:`[`pgsql`](https://github.com/canonical/ops-lib-pgsql/)

## OCI Images

This charm uses the canonical pgbouncer-container docker image, available [here](https://code.launchpad.net/~data-platform/+git/pgbouncer), stored in [dockerhub](https://hub.docker.com/r/dataplatformoci/pgbouncer).

## License

The Charmed PgBouncer Operator is free software, distributed under the Apache Software License, version 2.0. See [LICENSE](https://github.com/canonical/pgbouncer-k8s-operator/blob/main/LICENSE) for more information.

## Security

Security issues in the Charmed PgBouncer Operator can be reported through [LaunchPad](https://wiki.ubuntu.com/DebuggingSecurity#How%20to%20File). Please do not file GitHub issues about security issues.

## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines
on enhancements to this charm following best practice guidelines, and
[CONTRIBUTING.md](https://github.com/canonical/pgbouncer-k8s-operator/CONTRIBUTING.md) for developer guidance.
