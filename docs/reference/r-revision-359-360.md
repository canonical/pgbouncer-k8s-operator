>Reference > Release Notes > [All revisions] > Revision 359/360

# Revision 359/360
<sub>December 20, 2024</sub>
 
Dear community,

Canonical's newest Charmed PgBouncer K8s operator has been published in the [1/stable channel].

Due to the newly added support for `arm64` architecture, the PgBouncer K8s charm now releases multiple revisions simultaneously:
* Revision 359 is built for `amd64` on Ubuntu 22.04 LTS
* Revision 360 is built for `arm64` on Ubuntu 22.04 LTS

If you are jumping over several stable revisions, check [previous release notes][All revisions] before upgrading.

---

## Highlights / Features

* Tested [Juju 3.6 LTS](https://juju.is/docs/juju/roadmap#juju-juju-361-11-dec-2024) compatibility. Juju 3.6.1+ is a new [recommended Juju version](/t/12263)!
* Introduced [COS Tracing support](/t/14789) using [Tempo COS coordinator](https://charmhub.io/tempo-coordinator-k8s) ([PR #434](https://github.com/canonical/pgbouncer-k8s-operator/pull/434))

## Bugfixes and maintenance

* Switched to typed charm and fixes for legacy interface `pgsql` ([PR #435](https://github.com/canonical/pgbouncer-k8s-operator/pull/435))
* Quote tox.ini repository paths ([PR #461](https://github.com/canonical/pgbouncer-k8s-operator/pull/461)) ([DPE-6042](https://warthogs.atlassian.net/browse/DPE-6042))
* Fix `test_tls.py` test by installing 1 mattermost unit only ([PR #460](https://github.com/canonical/pgbouncer-k8s-operator/pull/460)) ([DPE-5622](https://warthogs.atlassian.net/browse/DPE-5622))
* Re-enabled cached builds on CI/CD ([PR #456](https://github.com/canonical/pgbouncer-k8s-operator/pull/456))

[details=Libraries, testing, and CI]
* Increased ruff rules ([PR #405](https://github.com/canonical/pgbouncer-k8s-operator/pull/405)) ([DPE-5324](https://warthogs.atlassian.net/browse/DPE-5324))
* Run juju 3.6 nightly tests against 3.6/stable ([PR #465](https://github.com/canonical/pgbouncer-k8s-operator/pull/465))
* Run tests against juju 3.6/candidate on nightly schedule ([PR #452](https://github.com/canonical/pgbouncer-k8s-operator/pull/452)) ([DPE-5622](https://warthogs.atlassian.net/browse/DPE-5622))
* Disabled tox requirements generation for lib release ([PR #426](https://github.com/canonical/pgbouncer-k8s-operator/pull/426))
* Deleted internal_docs directory ([PR #427](https://github.com/canonical/pgbouncer-k8s-operator/pull/427))
* Updated charm libs ([PR #433](https://github.com/canonical/pgbouncer-k8s-operator/pull/433))
* Disabled linting for docs ([PR #437](https://github.com/canonical/pgbouncer-k8s-operator/pull/437))
* Disabled cached builds ([PR #442](https://github.com/canonical/pgbouncer-k8s-operator/pull/442))
* Lock file maintenance Python dependencies ([PR #464](https://github.com/canonical/pgbouncer-k8s-operator/pull/464))
* Migrate `config .github/renovate.json5` ([PR #454](https://github.com/canonical/pgbouncer-k8s-operator/pull/454))
* Switched from tox build wrapper to `charmcraft.yaml` overrides ([PR #423](https://github.com/canonical/pgbouncer-k8s-operator/pull/423))
* Updated codecov/codecov-action action to v5 ([PR #455](https://github.com/canonical/pgbouncer-k8s-operator/pull/455))
* Updated data-platform-workflows to v23.1.1 ([PR #470](https://github.com/canonical/pgbouncer-k8s-operator/pull/470))
* Updated dependency cryptography to v44 ([PR #467](https://github.com/canonical/pgbouncer-k8s-operator/pull/467))
* Updated Juju agents ([PR #429](https://github.com/canonical/pgbouncer-k8s-operator/pull/429))
[/details]

## Requirements and compatibility

See the [system requirements] for more details about Juju versions and other software and hardware prerequisites.


See the [`/lib/charms` directory on GitHub] for more details about all supported libraries.

See the [`metadata.yaml` file on GitHub] for a full list of supported interfaces.

### Packaging

This charm is based on the CharmedPgBouncer K8s [rock image]. It packages:
* [pgbouncer `v.1.21`]
* [prometheus-pgbouncer-exporter `v.0.7.0`]

<!-- Topics -->
[All revisions]: /t/12261
[system requirements]: /t/12263

<!-- GitHub -->
[`/lib/charms` directory on GitHub]: https://github.com/canonical/pgbouncer-k8s-operator/tree/main/lib/charms
[`metadata.yaml` file on GitHub]: https://github.com/canonical/pgbouncer-k8s-operator/blob/main/metadata.yaml

<!-- Charmhub -->
[1/stable channel]: https://charmhub.io/pgbouncer-k8s?channel=1/stable

<!-- Snap/Rock -->
[`charmed-pgbouncer` packaging]: https://github.com/canonical/charmed-pgbouncer-rock

[snap Revision 3/4]: https://github.com/canonical/charmed-pgbouncer-snap/releases/tag/rev4
[rock image]: https://github.com/orgs/canonical/packages?repo_name=charmed-pgbouncer-rock

[pgbouncer `v.1.21`]: https://launchpad.net/~data-platform/+archive/ubuntu/pgbouncer
[prometheus-pgbouncer-exporter `v.0.7.0`]: https://launchpad.net/~data-platform/+archive/ubuntu/pgbouncer-exporter


<!-- Badges -->
[juju-2_amd64]: https://img.shields.io/badge/Juju_2.9.51-amd64-darkgreen?labelColor=ea7d56 
[juju-3_amd64]: https://img.shields.io/badge/Juju_3.4.6-amd64-darkgreen?labelColor=E95420 
[juju-3_arm64]: https://img.shields.io/badge/Juju_3.4.6-arm64-blue?labelColor=E95420