# PgBouncer K8s revision 76
<sub>Monday, October 23, 2023</sub>

Dear community, we would like to inform you that new PgBouncer K8s is published in the `1/stable` [charmhub](https://charmhub.io/pgbouncer-k8s?channel=1/stable) channel for Kubernetes.

## Features you can start using today:

* Added [Juju 3 support](/t/12263) (Juju 2 is still supported) [[DPE-1762](https://warthogs.atlassian.net/browse/DPE-1762)]
* Juju peer and relation secrets support [[DPE-1766](https://warthogs.atlassian.net/browse/DPE-1766)][[DPE-2296](https://warthogs.atlassian.net/browse/DPE-2296)] 
* Charm [minor upgrades](/t/12270) and [minor rollbacks](/t/12271) [[DPE-1771](https://warthogs.atlassian.net/browse/DPE-1771)]
* ["Charmed PostgreSQL K8s" extensions support ](https://charmhub.io/postgresql-k8s/docs/h-enable-plugins) [[DPE-2056](https://warthogs.atlassian.net/browse/DPE-2056)]
* [COS support](/t/12279) [[DPE-1779](https://warthogs.atlassian.net/browse/DPE-1779)]
* Logs rotation [[DPE-1756](https://warthogs.atlassian.net/browse/DPE-1756)]
* [TLS support](/t/12255) [[DPE-335](https://warthogs.atlassian.net/browse/DPE-335)]
* The "[data-integrator](https://charmhub.io/data-integrator)" support
* [Support](https://charmhub.io/pgbouncer-k8s/integrations?channel=1/stable) for modern `postgresql_client`, legacy `pgsql` and `tls-certificates` interfaces
* Workload updated to [PgBouncer 1.18](https://www.pgbouncer.org/changelog.html) (fixes for PostgreSQL 14)
* [Complete documentation on CharmHub](https://charmhub.io/pgbouncer-k8s?channel=1/stable)

## Bugfixes included:

Canonical Data issues are now public on both [Jira](https://warthogs.atlassian.net/jira/software/c/projects/DPE/issues/) and [GitHub](https://github.com/canonical/pgbouncer-k8s-operator/issues) platforms.<br/>[GitHub Releases](https://github.com/canonical/pgbouncer-k8s-operator/releases) provides a detailed list of bugfixes/PRs/commits for each revision.

## What is inside the charms:

* Charmed PgBouncer K8s ships the latest PgBouncer “1.18.0-0ubuntu0.22.04.1”
* The Prometheus pgbouncer-exporter is "0.7.0-0ubuntu0.22.04.1~ppa1"
* K8s charms [based on our](https://github.com/orgs/canonical/packages?tab=packages&q=charmed) ROCK OCI (Ubuntu LTS “22.04” - ubuntu:22.04-based)
* Principal charms supports the latest LTS series “22.04” only.
* Subordinate charms support LTS “22.04” and “20.04” only.

## Technical notes:

* Upgrade (`juju refresh`) is possible from this revision 76+.
* Please check [the external components requirements](/t/12263)
* Use this operator together with modern [Charmed PostgreSQL K8s](https://charmhub.io/postgresql-k8s) operator.

## How to reach us:

If you would like to chat with us about your use-cases or ideas, you can reach us at [Canonical Mattermost public channel](https://chat.charmhub.io/charmhub/channels/data-platform) or [Discourse](https://discourse.charmhub.io/). Check all other contact details [here](/t/12264).

Consider [opening a GitHub issue](https://github.com/canonical/pgbouncer-k8s-operator/issues) if you want to open a bug report.<br/>[Contribute](https://github.com/canonical/pgbouncer-k8s-operator/blob/main/CONTRIBUTING.md) to the project!

## Footer:

It is the first stable release of the operator "PgBouncer K8s" by Canonical Data.<br/>Well done, Team!