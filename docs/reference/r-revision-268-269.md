>Reference > Release Notes > [All revisions] > Revision 268/269

# Revision 268/269
<sub>September 11, 2024</sub>

Dear community,

Canonical's newest Charmed PgBouncer K8s operator has been published in the [1/stable channel].

Due to the newly added support for `arm64` architecture, the PgBouncer K8s charm now releases multiple revisions simultaneously:
* Revision 269 is built for `amd64` on Ubuntu 22.04 LTS ( pgbouncer-image r85 )
* Revision 268 is built for `arm64` on Ubuntu 22.04 LTS ( pgbouncer-image r85 )


To make sure you deploy for the right architecture, we recommend setting an [architecture constraint](https://juju.is/docs/juju/constraint#heading--arch) for your entire juju model.

Otherwise, it can be done at deploy time with the `--constraints` flag:
```shell
juju deploy pgbouncer-k8s --trust --constraints arch=<arch> 
```
where `<arch>` can be `amd64` or `arm64`.

---

## Highlights 
* Lightweight deployments due to the new and tiny [charmed-pgbouncer](https://github.com/canonical/charmed-pgbouncer-rock/) rock ([PR #376](https://github.com/canonical/pgbouncer-k8s-operator/pull/376))
* Added URI to relation data ([PR #380](https://github.com/canonical/pgbouncer-k8s-operator/pull/380))

## Bugfixes
* Ported PVC error test workaround and nodeport fixes ([PR #395](https://github.com/canonical/pgbouncer-k8s-operator/pull/395)) ([DPE-5205](https://warthogs.atlassian.net/browse/DPE-5205))
* Switched Jira issue sync from workflow to bot ([PR #377](https://github.com/canonical/pgbouncer-k8s-operator/pull/377))
* Automatically update rock by renovate ([PR #387](https://github.com/canonical/pgbouncer-k8s-operator/pull/387))


## Dependencies and automations
* Lock file maintenance ([PR #399](https://github.com/canonical/pgbouncer-k8s-operator/pull/399))
* Lock file maintenance Python dependencies ([PR #409](https://github.com/canonical/pgbouncer-k8s-operator/pull/409))
* Update canonical/charming-actions action to v2.6.3 ([PR #403](https://github.com/canonical/pgbouncer-k8s-operator/pull/403))
* Update data-platform-workflows to v21.0.1 ([PR #398](https://github.com/canonical/pgbouncer-k8s-operator/pull/398))
* Update dependency canonical/microk8s to v1.31 ([PR #373](https://github.com/canonical/pgbouncer-k8s-operator/pull/373))
* Update dependency cryptography to v43.0.1 [SECURITY] ([PR #406](https://github.com/canonical/pgbouncer-k8s-operator/pull/406))
* Update ghcr.io/canonical/charmed-pgbouncer:1.21-22.04_edge Docker digest to 005a551 ([PR #390](https://github.com/canonical/pgbouncer-k8s-operator/pull/390))

## Technical details
This section contains some technical details about the charm's contents and dependencies. 

If you are jumping over several stable revisions, check [previous release notes][All revisions] before upgrading.

### Requirements
See the [system requirements] for more details about Juju versions and other software and hardware prerequisites.

### Packaging

This charm is based on the CharmedPgBouncer K8s [rock image] (CharmHub `pgbouncer-image` resource-revision `85`). It packages:
* [pgbouncer `v.1.21`]
* [prometheus-pgbouncer-exporter `v.0.7.0`]

See the [`/lib/charms` directory on GitHub] for more details about all supported libraries.

See the [`metadata.yaml` file on GitHub] for a full list of supported interfaces.

<!-- Topics -->
[All revisions]: /t/12261
[system requirements]: /t/12263

<!-- GitHub -->
[`/lib/charms` directory on GitHub]: https://github.com/canonical/pgbouncer-k8s-operator/tree/main/lib/charms
[`metadata.yaml` file on GitHub]: https://github.com/canonical/pgbouncer-k8s-operator/blob/main/metadata.yaml

<!-- Charmhub -->
[1/stable channel]: https://charmhub.io/pgbouncer?channel=1/stable

<!-- Snap/Rock -->
[`charmed-pgbouncer` packaging]: https://github.com/canonical/charmed-pgbouncer-rock

[snap Revision 3/4]: https://github.com/canonical/charmed-pgbouncer-snap/releases/tag/rev4
[rock image]: https://github.com/orgs/canonical/packages?repo_name=charmed-pgbouncer-rock

[pgbouncer `v.1.21`]: https://launchpad.net/~data-platform/+archive/ubuntu/pgbouncer
[prometheus-pgbouncer-exporter `v.0.7.0`]: https://launchpad.net/~data-platform/+archive/ubuntu/pgbouncer-exporter


<!-- Badges -->
[amd64]: https://img.shields.io/badge/amd64-darkgreen
[arm64]: https://img.shields.io/badge/arm64-blue