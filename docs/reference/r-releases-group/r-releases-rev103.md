# PgBouncer K8s revision 103
<sub>March 8, 2024</sub>

Dear community, we are excited to announce that the new Charmed PgBouncer K8s operator is published in the `1/stable` [charmhub](https://charmhub.io/pgbouncer-k8s?channel=1/stable) channel for Kubernetes.

## New features

* Juju 3.1.7 support (changes to Juju secrets) ([#196](https://github.com/canonical/pgbouncer-k8s-operator/pull/196))
* Improved stability ([DPE-3049](https://warthogs.atlassian.net/browse/DPE-3049)| [#186](https://github.com/canonical/pgbouncer-k8s-operator/pull/186))
* Fewer restarts on deployments and integrations
* Updated Charmed PostgreSQL ROCK ([revision 96](https://github.com/canonical/pgbouncer-k8s-operator/pull/210))
* Updated Python library dependencies ([#226](https://github.com/canonical/pgbouncer-k8s-operator/pull/226))

## Bugfixes

Canonical Data issues are now public on both [Jira](https://warthogs.atlassian.net/jira/software/c/projects/DPE/issues/) and [GitHub](https://github.com/canonical/pgbouncer-k8s-operator/issues) platforms. [GitHub Releases](https://github.com/canonical/pgbouncer-k8s-operator/releases) provide a detailed list of bugfixes/PRs/Git commits for each revision.

### Highlights for the current revision

* Fix secret keys: do not set peer secrets as peer data ([#212](https://github.com/canonical/pgbouncer-k8s-operator/pull/212))
* Removed binary dependencies ([DPE-3062](https://warthogs.atlassian.net/browse/DPE-3062) | [#179](https://github.com/canonical/pgbouncer-k8s-operator/pull/179))
* Fixed Juju secrets usage ([DPE-3184](https://warthogs.atlassian.net/browse/DPE-3184) | [#178](https://github.com/canonical/pgbouncer-k8s-operator/pull/178))
* Updated TLS libraries ([#191](https://github.com/canonical/pgbouncer-k8s-operator/pull/191))

## Inside the charms

* Charmed PgBouncer K8s ships the latest PgBouncer `1.21.0-0ubuntu0.22.04.1~ppa1`
* The Prometheus pgbouncer-exporter is `0.7.0-0ubuntu0.22.04.1~ppa1`
* K8s charms based on our [ROCK OCI](https://github.com/orgs/canonical/packages?tab=packages&q=charmed) (Ubuntu LTS 22.04 - `ubuntu:22.04`-based)

## Technical notes

* Upgrade via `juju refresh` is possible from this revision onwards (103+)
* Please check [the external components requirements](/t/12263)
* Use this operator together with the [Charmed PostgreSQL K8s](https://charmhub.io/postgresql-k8s) operator

## Contact

[Open a GitHub issue](https://github.com/canonical/pgbouncer-k8s-operator/issues) if you want to submit a bug report, or [contribute](https://github.com/canonical/pgbouncer-k8s-operator/blob/main/CONTRIBUTING.md) to the project!

Check our [Contacts](/t/12264) page for more ways to reach us.