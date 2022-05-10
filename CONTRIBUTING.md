# Contributing

## Overview

This documents explains the processes and practices recommended for contributing enhancements to
this operator.

- Generally, before developing enhancements to this charm, you should consider [opening an issue
  ](https://github.com/canonical/pgbouncer-k8s-operator/issues) explaining your use case.
- If you would like to chat with us about your use-cases or proposed implementation, you can reach
  us at [Canonical Mattermost public channel](https://chat.charmhub.io/charmhub/channels/charm-dev)
  or [Discourse](https://discourse.charmhub.io/).
- Familiarising yourself with the [Charmed Operator Framework](https://juju.is/docs/sdk) library
  will help you a lot when working on new features or bug fixes.
- All enhancements require at least 2 approving reviews before being merged. Code review typically examines
  - code quality
  - test coverage
  - user experience for Juju administrators this charm.
- Please help us out in ensuring easy to review branches by rebasing your pull request branch onto
  the `main` branch. This also avoids merge commits and creates a linear Git commit history.

## Environment Setup

This setup is required for testing and deploying this charm. These instructions are written assuming you're using microk8s as your juju substrate. Instructions for setting this up can be found [here](https://juju.is/docs/olm/microk8s). If you're using a different substrate, update these instructions accordingly.

```shell
# Import container
git clone https://github.com/canonical/pgbouncer-container.git
# Build container locally, since it's not been exported anywhere yet.
docker build . -t pgbouncer:latest
docker save pgbouncer:latest -o pgb.tar
# Import container file into microk8s container registry
microk8s ctr image import pgb.tar

# Create a model
juju add-model dev
# Enable DEBUG logging
juju model-config logging-config="<root>=INFO;unit=DEBUG"

# initialise an environment using tox
tox --notest -e unit
source .tox/unit/bin/activate
```

### Testing

```shell
tox -e fmt           # update your code according to linting rules
tox -e lint          # code style
tox -e unit          # unit tests
tox -e integration   # integration tests
tox                  # runs 'lint' and 'unit' environments
```

## Build charm

Build the charm in this git repository using:

```shell
charmcraft pack
```

### Deploy

```bash
juju deploy ./pgbouncer-k8s-operator_ubuntu-20.04-amd64.charm \
    --resource pgbouncer-image=pgbouncer:0.8
```

## Canonical Contributor Agreement

Canonical welcomes contributions to the Charmed PGBouncer Operator. Please check out our [contributor agreement](https://ubuntu.com/legal/contributors) if you're interested in contributing to the solution.
