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
tox -e integration   # integration tests # TODO does this actually still work?
tox                  # runs 'fmt', 'lint', and 'unit' environments
```

## Build charm

Build the charm in this git repository using:

```shell
charmcraft pack
```

### Deploy

```bash
juju deploy ./pgbouncer-k8s_ubuntu-20.04-amd64.charm \
    --resource pgbouncer-image=dataplatformoci/pgbouncer:1.12-20.04
```

## Canonical Contributor Agreement

Canonical welcomes contributions to the Charmed PGBouncer Operator. Please check out our [contributor agreement](https://ubuntu.com/legal/contributors) if you're interested in contributing.

## Appendices

### Appendix A: Charm Lifecycle Flowcharts

These flowcharts detail the control flow of the hooks in this program.

#### Start Hook

```mermaid
flowchart TD
  id101([start Hook]) --> id102{Is container\navailable?}
  id102 -- no --> id103>defer]
  id102 -- yes --> id104{Is pgbouncer config\navailable in container or\npeer databag?}
  id105 --> id0((return))
  id104 -- no --> id106{Is the current unit Leader?}
  id106 -- no --> id109>defer:\nwait for leader unit to generate\nconfig and upload to peer databag]
  id106 -- yes --> id108[generate new config]
  id108 --> id105
  id104 -- yes --> id105[render config, update\nrelations if available]
```

#### PgBouncer Pebble Ready Hook

```mermaid
flowchart TD
  id201([pgbouncer-pebble-ready Hook]) --> id202{Is pgbouncer\nconfig available?}
  id202 -- no --> id203>defer]
  id202 -- yes --> id204[Generate pebble config\nand start service]
  id204 --> id205[Verify pgbouncer is\nrunning, and set charm\n status accordingly]
  id205 --> id0((return))
```

#### Config Changed Hook

```mermaid
flowchart TD
  id301([config-changed Hook]) --> id302{Is current\nunit leader?}
  id302 -- yes --> id303{Is pgbouncer\nconfig available?}
  id302 -- no --> id0((return))
  id303 -- no --> id304>defer]
  id303 -- yes --> id305[Modify pgbouncer\nconfig to match\ncharm config]
  id305 --> id306[Render config &\nreload pgbouncer]
  id306 --> id1((return))
```

#### Backend Database Created Hook

```mermaid
flowchart TD
  id401([backend-database-requested Hook]) --> id402{Is current\nunit leader?}
  id402 -- yes --> id403{Is pgbouncer\nrunning?}
  id402 -- no --> id2((return))
  id403 -- yes --> id405{is backend database ready,\nand has pgbouncer been\nprovided with the\nnecessary relation data?}
  id403 -- no --> id3((return))
  id405 -- no --> id406>defer]
  id405 -- yes --> id407[Generate username & password]
  id407 --> id408[create auth function on postgres]
  id408 --> id409[update pgbouncer config, and save auth data to container and peer databag]
  id409 --> id410[update postgres endpoints in client relations]
  id410 --> id411[update charm status]
  id411 --> id1((return))
```
