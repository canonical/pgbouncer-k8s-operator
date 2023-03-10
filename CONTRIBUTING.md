# Contributing

More extensive documentation can be found in the ./documentation directory.

## Overview

This documents explains the processes and practices recommended for contributing enhancements to this operator.

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

This setup is required for testing and deploying this charm. These instructions are written assuming you have a bootstrapped kubernetes juju controller, and you're using microk8s as your juju substrate. Instructions for setting this up can be found [here](https://juju.is/docs/olm/microk8s). If you're using a different substrate, update these instructions accordingly.

```bash
# Create a model
juju add-model dev
# Enable DEBUG logging
juju model-config logging-config="<root>=INFO;unit=DEBUG"

# initialise an environment using tox
tox devenv -e integration
source venv/bin/activate

# export kubernetes config to lightkube, for integration testing.
microk8s config > ~/.kube/config
```

### Testing

Use the following tox commands to run tests:

```bash
tox run -e format              # update your code according to linting rules
tox run -e lint                # code style
tox run -e unit                # unit tests
tox                            # runs 'fmt', 'lint', and 'unit' environments
```

Integration tests for individual functionality can be found in tox.ini

## Build charm

Build the charm in this git repository using:

```bash
charmcraft pack
```

This will generate a file called something like `pgbouncer-k8s_ubuntu-22.04-amd64.charm`. The `22.04` component of this filename relates to the **ubuntu version used in the build container used to build the charm**, designated by the `build-on` parameter in `./metadata.yaml`. It does not relate to the ubuntu version of the charm.

### Deploy

```bash
# This .charm file was built using the default `charmcraft pack` command.
juju deploy ./pgbouncer-k8s_ubuntu-22.04-amd64.charm \
    --resource pgbouncer-image=dataplatformoci/pgbouncer:1.16-22.04
```

## Canonical Contributor Agreement

Canonical welcomes contributions to the Charmed PGBouncer Operator. Please check out our [contributor agreement](https://ubuntu.com/legal/contributors) if you're interested in contributing.
