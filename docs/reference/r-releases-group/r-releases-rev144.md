>Reference > Release Notes > [All revisions](/t/12261) > Revision 144/145  
# Revision 144/145

<sub>18 May, 2024</sub>

Dear community,

We'd like to announce that Canonical's newest Charmed PgBouncer K8s operator has been published in the 1/stable [channel](https://charmhub.io/pgbouncer-k8s?channel=1/stable) :tada: :

|   |AMD64|ARM64|
|---:|:---:|:---:|
| Revision: | 144 | 145 |

[note]
If you are jumping over several stable revisions, make sure to check [previous release notes](/t/12261) before upgrading to this revision.
[/note]  

## Features you can start using today

* [New ARM support!](https://charmhub.io/pgbouncer-k8s/docs/r-requirements) [[#250](https://github.com/canonical/pgbouncer-k8s-operator/pull/250)]
* Add K8s NodePort support [[#264](https://github.com/canonical/pgbouncer-k8s-operator/pull/264)][[DPE-3777](https://warthogs.atlassian.net/browse/DPE-3777)]
 * Add charm upgrade tests [[#217](https://github.com/canonical/pgbouncer-k8s-operator/pull/217)][[DPE-3255](https://warthogs.atlassian.net/browse/DPE-3255)]
* All the functionality from [previous revisions](https://charmhub.io/pgbouncer-k8s/docs/r-releases)

## Bugfixes

*  Recreate auth_query on backend rerelation in [#284](https://github.com/canonical/pgbouncer-k8s-operator/pull/284), [[DPE-4221](https://warthogs.atlassian.net/browse/DPE-4221)]
* Update data-platform-libs: data_interfaces to 34 in [#277](https://github.com/canonical/pgbouncer-k8s-operator/pull/277)
* Update Rock in [#281](https://github.com/canonical/pgbouncer-k8s-operator/pull/281)
* Fixed autostart metrics service if password is not yet set in [#279](https://github.com/canonical/pgbouncer-k8s-operator/pull/279)
* Various bugfixes in [#252](https://github.com/canonical/pgbouncer-k8s-operator/pull/252)
* Update ROCK in [#263](https://github.com/canonical/pgbouncer-k8s-operator/pull/263)

Canonical Data issues are now public on both [Jira](https://warthogs.atlassian.net/jira/software/c/projects/DPE/issues/) and [GitHub](https://github.com/canonical/pgbouncer-k8s-operator/issues) platforms.  
[GitHub Releases](https://github.com/canonical/pgbouncer-k8s-operator/releases) provide a detailed list of bugfixes, PRs, and commits for each revision.  

## Inside the charms

* Charmed PgBouncer K8s ships the latest PgBouncer `1.21.0-0ubuntu0.22.04.1~ppa1`
* The Prometheus pgbouncer-exporter is `0.7.0-0ubuntu0.22.04.1~ppa1`
* K8s charms based on our [ROCK OCI](https://github.com/orgs/canonical/packages?tab=packages&q=charmed) (Ubuntu LTS 22.04.4)  revision `113`

## Technical notes

* Upgrade via `juju refresh` is possible from this revision onwards (103+)
* Please check [the external components requirements](https://charmhub.io/pgbouncer-k8s/docs/r-requirements)
* Use this operator together with the [Charmed PostgreSQL K8s](https://charmhub.io/postgresql-k8s) operator  

## Contact us

Charmed PgBouncer K8s is an open source project that warmly welcomes community contributions, suggestions, fixes, and constructive feedback.  
* Raise software issues or feature requests on [**GitHub**](https://github.com/canonical/pgbouncer-k8s-operator/issues)  
*  Report security issues through [**Launchpad**](https://wiki.ubuntu.com/DebuggingSecurity#How%20to%20File)  
* Contact the Canonical Data Platform team through our [Matrix](https://matrix.to/#/#charmhub-data-platform:ubuntu.com) channel.