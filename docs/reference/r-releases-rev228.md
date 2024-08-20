>Reference > Release Notes > [All revisions](/t/12261) > Revisions 228/229

# Revision 228/229
<sub>Aug 13, 2024</sub>

Dear community,

Canonical’s newest Charmed PgBouncer K8s operator has been published in the 1/stable [channel](https://charmhub.io/pgbouncer-k8s?channel=1/stable) :tada: 

Due to its mult-architecture support, PgBouncer charm releases two revisions simultaneously: 
* Revision 229 is built for `amd64`
* Revision 228 is built for for `arm64`

To make sure you deploy for the right architecture, we recommend setting an [architecture constraint](https://juju.is/docs/juju/constraint#heading--arch) for your entire juju model.

Otherwise, it can be done at deploy time with the `--constraints` flag:
```shell
juju deploy pgbouncer-k8s --trust --constraints arch=<arch> 
```
where `<arch>` can be `amd64` or `arm64`.

[note]
If you are jumping over several stable revisions, make sure to check [previous release notes](/t/12261?channel=1/stable) before upgrading to this revision.
[/note]  

## Highlights

Below are the major highlights of this release. To see all changes since the previous stable release, check the [release notes on GitHub](https://github.com/canonical/pgbouncer-k8s-operator/releases/tag/rev229)

* Added support for multiple databases ([PR #324](https://github.com/canonical/pgbouncer-k8s-operator/pull/324)) ([DPE-4642](https://warthogs.atlassian.net/browse/DPE-4642))
* Added support for tracing with Tempo K8s ([PR #296](https://github.com/canonical/pgbouncer-k8s-operator/pull/296)) ([DPE-4619](https://warthogs.atlassian.net/browse/DPE-4619))
  * Check the new guide: [How to enable tracing](https://charmhub.io/pgbouncer-k8s/docs/h-enable-tracing)
* Updated database ownership to allow dropping tables after re-relation ([PR #287](https://github.com/canonical/pgbouncer-k8s-operator/pull/287)) ([DPE-1454](https://warthogs.atlassian.net/browse/DPE-1454))
* Added UX message for charm deployed without `--trust` flag in ([PR #319](https://github.com/canonical/pgbouncer-k8s-operator/pull/319)) ([DPE-4062](https://warthogs.atlassian.net/browse/DPE-4062))

### Enhancements
* Upgraded Nodeport ([PR #342](https://github.com/canonical/pgbouncer-k8s-operator/pull/342)) ([DPE-4236](https://warthogs.atlassian.net/browse/DPE-4236))
* Added jinja2 as a dependency ([PR #332](https://github.com/canonical/pgbouncer-k8s-operator/pull/332)) ([DPE-4816](https://warthogs.atlassian.net/browse/DPE-4816))
* Updated Juju agent to v.3.4.4 for CI ([PR #337](https://github.com/canonical/pgbouncer-k8s-operator/pull/337)) ([DPE-4811](https://warthogs.atlassian.net/browse/DPE-4811))      
* Updated charm libs ([PR #357](https://github.com/canonical/pgbouncer-k8s-operator/pull/357))                         
* Updated Juju dependency to v3.4.5 ([PR #359](https://github.com/canonical/pgbouncer-k8s-operator/pull/359))         
* Added integration tests to arm64 runners ([PR #291](https://github.com/canonical/pgbouncer-k8s-operator/pull/291))                
* Updated Python dependencies

### Bugfixes

* Updated old information on CONTRIBUTING ([PR #290](https://github.com/canonical/pgbouncer-k8s-operator/pull/290)) ([DPE-3991](https://warthogs.atlassian.net/browse/DPE-3991))                   
* Increased PostgreSQL deploy timeouts ([PR #340](https://github.com/canonical/pgbouncer-k8s-operator/pull/340))        
* Stabilized tests and CI

<!-- Removed some points that don't seem too relevant/major at a glance, but feel free to re-add if you think they should be here.
* Secrets tweaks ([PR #298](https://github.com/canonical/pgbouncer-k8s-operator/pull/298))
* Use preset renovate configuration ([PR #316](https://github.com/canonical/pgbouncer-k8s-operator/pull/316))     
-->

Canonical Data issues are now public on both [Jira](https://warthogs.atlassian.net/jira/software/c/projects/DPE/issues/) and [GitHub](https://github.com/canonical/pgbouncer-k8s-operator/issues). To see all commits since the previous stable release, check the [release notes on GitHub](https://github.com/canonical/pgbouncer-k8s-operator/releases/tag/rev229).


## Technical details
This section contains some technical details about the charm's contents and dependencies. Make sure to also check the [system requirements](https://charmhub.io/pgbouncer-k8s/docs/r-requirements).

### Packaging
This charm is based on the [ROCK OCI](https://github.com/orgs/canonical/packages?tab=packages&q=charmed) for Ubuntu LTS 22.04.4  <!--revision `TODO`-->. It packages:

* pgbouncer `v.1.21`
  *  [`1.21.0-0ubuntu0.22.04.1~ppa1`](https://launchpad.net/~data-platform/+archive/ubuntu/pgbouncer)
* prometheus pgbouncer-exporter `v.0.7.01`
  *  [`0.7.0-0ubuntu0.22.04.1~ppa1`](https://launchpad.net/~data-platform/+archive/ubuntu/pgbouncer-exporter)

### Libraries and interfaces
These are some of the libraries supported by the charm:
* **grafana_k8s `v0`** for integration with Grafana 
    * Implements  `grafana_dashboard` interface
* **tempo_k8s `v1`, `v2`** for integration with Tempo charm
    * Implements `tracing` interface
* **loki_k8s `v0`** for integration with Loki
  * Implements the `loki_push_api` interface
* **tls_certificates_interface `v2`** for integration with TLS charms
    * Implements `tls-certificates` interface

See the [`/lib/charms` directory on GitHub](https://github.com/canonical/pgbouncer-k8s-operator/tree/main/lib/charms) for more details about all supported libraries.

See the [`metadata.yaml` file on GitHub](https://github.com/canonical/pgbouncer-k8s-operator/blob/main/metadata.yaml) for a full list of supported interfaces.

## Contact us

Charmed PgBouncer K8s is an open source project that warmly welcomes community contributions, suggestions, fixes, and constructive feedback.  
* Raise software issues or feature requests on [**GitHub**](https://github.com/canonical/pgbouncer-k8s-operator/issues)  
*  Report security issues through [**Launchpad**](https://wiki.ubuntu.com/DebuggingSecurity#How%20to%20File)  
* Contact the Canonical Data Platform team through our [Matrix](https://matrix.to/#/#charmhub-data-platform:ubuntu.com) channel.