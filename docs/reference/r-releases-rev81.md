# PgBouncer K8s revision 81
<sub>Wednesday, December 6, 2023</sub>

Dear community, this is to inform you that new PgBouncer K8s is published in `1/stable` [charmhub](https://charmhub.io/pgbouncer-k8s?channel=1/stable) channel for Kubernetes.

## The features you can start using today:

* PgBouncer is updated from 1.18 to 1.21 [[DPE-3040](https://warthogs.atlassian.net/browse/DPE-3040)]
* Open TCP port `6432` on K8s [[GH PR#159](https://github.com/canonical/pgbouncer-k8s-operator/pull/159)]
* Updated Python library dependencies [[GH PR#158](https://github.com/canonical/pgbouncer-k8s-operator/pull/158)]

## Bugfixes included:

Canonical Data issues are now public on both [Jira](https://warthogs.atlassian.net/jira/software/c/projects/DPE/issues/) and [GitHub](https://github.com/canonical/pgbouncer-k8s-operator/issues) platforms.<br/>[GitHub Releases](https://github.com/canonical/pgbouncer-k8s-operator/releases) provide a detailed list of bugfixes/PRs/Git commits for each revision.

* Juju Secrets fixes provided by updated data Interfaces library (LIBPATCH 24).
* Fixed [GitHub Issue #166](https://github.com/canonical/pgbouncer-k8s-operator/issues/166) [[DPE-3113](https://warthogs.atlassian.net/browse/DPE-3113)]

## What is inside the charms:

* Charmed PgBouncer K8s ships the latest PgBouncer “1.21.0-0ubuntu0.22.04.1~ppa1”
* The Prometheus pgbouncer-exporter is "0.7.0-0ubuntu0.22.04.1~ppa1"
* K8s charms [based on our](https://github.com/orgs/canonical/packages?tab=packages&q=charmed) ROCK OCI (Ubuntu LTS “22.04” - ubuntu:22.04-based)
* Principal charms supports the latest LTS series “22.04” only.
* Subordinate charms support LTS “22.04” and “20.04” only.

## Technical notes:

* Upgrade (`juju refresh`) is possible from this revision 76+.
* Please check [the external components requirements](/t/12263)
* Use this operator together with a modern operator "[Charmed PostgreSQL K8s](https://charmhub.io/postgresql-k8s)".

## How to reach us:

If you would like to chat with us about your use-cases or ideas, you can reach us at [Canonical Mattermost public channel](https://chat.charmhub.io/charmhub/channels/data-platform) or [Discourse](https://discourse.charmhub.io/). Check all other contact details [here](/t/12264).

Consider [opening a GitHub issue](https://github.com/canonical/pgbouncer-k8s-operator/issues) if you want to open a bug report.<br/>[Contribute](https://github.com/canonical/pgbouncer-k8s-operator/blob/main/CONTRIBUTING.md) to the project!