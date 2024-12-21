## Juju version

The charm supports both [Juju 2.9 LTS](https://github.com/juju/juju/releases) and [Juju 3.x](https://github.com/juju/juju/releases). The supported Juju versions are:

* 3.6.1+ LTS (recommended)
* 3.1.7+ (minimal for 3.x: Juju secrets refactored/stabilized in Juju 3.1.7)
* 2.9.32+ (minimal for 2.x)

## Kubernetes requirements

* Kubernetes 1.27+
* Canonical MicroK8s 1.27+ (snap channel 1.27-strict/stable and newer)
## Minimum requirements

Make sure your machine meets the following requirements:
- Ubuntu 22.04 (Jammy) or later.
- 8GB of RAM.
- 2 CPU threads.
- At least 20GB of available storage.
- Access to the internet for downloading the required OCI/ROCKs and charms.

## Supported architectures

The charm is based on [ROCK OCI](https://github.com/canonical/charmed-postgresql-rock) named "[charmed-postgresql](https://github.com/canonical/charmed-postgresql-rock/pkgs/container/charmed-postgresql)", which is recursively based on SNAP "[charmed-postgresql](https://snapcraft.io/charmed-postgresql)", which is currently available for `amd64` and `arm64` (revision 146+). Please [contact us](/t/12264) if you are interested in new architecture!

## Charmed PostgreSQL K8s requirements
Please also keep in mind "[Charmed PostgreSQL K8s](https://charmhub.io/postgresql-k8s/docs/r-requirements)" requirements.