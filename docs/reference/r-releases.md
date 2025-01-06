# Release Notes

This page provides high-level overviews of the dependencies and features that are supported by each revision in every stable release. To learn more about the different release tracks, see the [Juju documentation about risk levels](https://juju.is/docs/juju/channel?#heading--risk).

To see all releases and commits, check the [Charmed PgBouncer K8s Releases page on GitHub](https://github.com/canonical/pgbouncer-k8s-operator/releases).

## Dependencies and supported features

For each release, this table shows:

* The PgBouncer version packaged inside
* The minimum Juju version required to reliably operate **all** features of the release
  > This charm still supports older versions of Juju 2.9. See the [system requirements](/t/12263) for more details
* Support for specific features

| Revision | PgBouncer version | Juju version | [TLS encryption](/t/12259) | [COS monitoring](/t/12279) |  [Minor version upgrades](/t/12270) |
|:---:|:---:|:---:|:---:|:---:|:---:|
|[359], [360]| `1.21.0` | `3.4.5+` | ![check] | ![check] | ![check]
|[268], [269]| `1.21.0` | `3.4.5+` | ![check] | ![check] | ![check]
|[228], [229]| `1.21.0` | `3.4.5+` | ![check] | ![check] |
|[144], [145]| `1.21.0` | `3.1.8+` | ![check] | ![check] |
|[103] | `1.21.0` | `3.1.7+` | ![check] | ![check] |
|[81] | `1.21.0` | `3.1.6+` |  |  ![check] |
|[76] | `1.18.0` | `3.1.6+` |  | ![check]  |

## Architecture and base

Several [revisions](https://juju.is/docs/sdk/revision) are released simultaneously for different [bases/series](https://juju.is/docs/juju/base) using the same charm code. In other words, one release contains multiple revisions.

> If you do not specify a revision on deploy time, Juju will automatically choose the revision that matches your base and architecture.

> If you deploy a specific revision, **you must make sure it matches your base and architecture** via the tables below or with [`juju info`](https://juju.is/docs/juju/juju-info).

### Release 359/360 (latest)
| Revision | `amd64` | `arm64` |  Ubuntu 22.04 (jammy)
|:-----:|:--------:|:--------:|:-----:|
| [360] |          | ![check] | ![check] |
| [359] | ![check] |          | ![check] |

[details=Release 268/269]

### Release 268/269 (latest)
| Revision | `amd64` | `arm64` |  Ubuntu 22.04 (jammy)
|:-----:|:--------:|:--------:|:-----:|
| [268] |          | ![check] | ![check] |
| [269] | ![check] |          | ![check] |
[/details]

[details=Release 228/229]

| Revision | `amd64` | `arm64` |  Ubuntu 22.04 (jammy)
|:-----:|:--------:|:--------:|:-----:|
| [228] |          | ![check] | ![check] |
| [229] | ![check] |  | ![check] |

[/details]

[details=Release 144/145]

| Revision | `amd64` | `arm64` |  Ubuntu 22.04 (jammy)
|:-----:|:--------:|:--------:|:-----:|
| [144] | ![check] |  | ![check] |
| [145] |  | ![check] | ![check] |

[/details]

[details=Release 103]

| Revision | `amd64` | `arm64` |  Ubuntu 22.04 (jammy)
|:-----:|:--------:|:--------:|:-----:|
| [103] | ![check] |  | ![check] |

[/details]

[details=Release 81]

| Revision | `amd64` | `arm64` |  Ubuntu 22.04 (jammy)
|:-----:|:--------:|:--------:|:-----:|
| [81] | ![check] |  | ![check] |

[/details]

[details=Release 76]

| Revision | `amd64` | `arm64` |  Ubuntu 22.04 (jammy)
|:-----:|:--------:|:--------:|:-----:|
| [81] | ![check] |  | ![check] |

[/details]

<br>

[note]
 Our release notes are an ongoing work in progress. If there is any additional information about releases that you would like to see or suggestions for other improvements, don't hesitate to contact us on [Matrix ](https://matrix.to/#/#charmhub-data-platform:ubuntu.com) or [leave a comment](https://discourse.charmhub.io/t/pgbouncer-k8s-reference-release-notes/12261).
[/note]

<!--LINKS-->
[360]: /t/16124
[359]: /t/16124
[268]: /t/15443
[269]: /t/15443
[228]: /t/15090
[229]: /t/15090
[144]: /t/14070
[145]: /t/14070
[103]: /t/13297
[81]: /t/12751
[76]: /t/12262

<!-- BADGES -->
[check]: https://img.icons8.com/color/20/checkmark--v1.png