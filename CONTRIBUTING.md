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

These flowcharts detail the control flow of the hooks in this program. Unless otherwise stated, **a hook deferral is always followed by a return**.

TODO:

- Copy the relevant hook flowcharts into relation documentation, along with the expected relation interface.
- update id syntax because it's clunky

#### Start Hook

```mermaid
flowchart TD
  start([start Hook]) --> is_container{Is container\navailable?}
  is_container -- no --> defer>defer]
  is_container -- yes --> is_cfg{Is pgbouncer config\navailable in container or\npeer databag?}
  is_cfg -- no --> is_leader{Is the current unit Leader?}
  is_cfg -- yes --> render_cfg[render config, update\nrelations if available]
  is_leader -- no --> defer_wait>defer:\nwait for leader unit to generate\nconfig and upload to peer databag]
  is_leader -- yes --> gen_cfg[generate new config]
  gen_cfg --> render_cfg
  render_cfg --> rtn((return))
```

#### PgBouncer Pebble Ready Hook

```mermaid
flowchart TD
  id201([pgbouncer-pebble-ready Hook]) --> id202{Is pgbouncer\nconfig available?}
  id202 -- no --> id203>defer]
  id202 -- yes --> id204[Generate pebble config\nand start service]
  id204 --> id205[Verify pgbouncer is\nrunning, and set charm\n status accordingly]
  id205 --> rtn((return))
```

#### Config Changed Hook

```mermaid
flowchart TD
  id301([config-changed Hook]) --> id302{Is current\nunit leader?}
  id302 -- no --> rtn((return))
  id302 -- yes --> id303{Is pgbouncer\nconfig available?}
  id303 -- no --> id304>defer]
  id303 -- yes --> id305[Modify pgbouncer\nconfig to match\ncharm config]
  id305 --> id306[Render config &\nreload pgbouncer]
  id306 --> id1((return))
```

#### Peer Relation Created Hook

TODO

```mermaid
flowchart TD
  id601([peer-relation-created Hook])
```

#### Peer Relation Changed Hook

TODO

```mermaid
flowchart TD
  id701([peer-relation-changed Hook])
```

#### Backend Database Created Hook

```mermaid
flowchart TD
  id401([backend-database-requested Hook]) --> id402{Is current\nunit leader?}
  id402 -- no --> id2((return))
  id402 -- yes --> id403{Is pgbouncer\nrunning?}
  id403 -- no --> id3((return))
  id403 -- yes --> id405{is backend database ready,\nand has pgbouncer been\nprovided with the\nnecessary relation data?}
  id405 -- no --> id406>defer]
  id405 -- yes --> id407[Generate username & password]
  id407 --> id408[create auth function on postgres]
  id408 --> id409[update pgbouncer config, and save\nauth data to container and peer databag]
  id409 --> id410[update postgres endpoints in client relations]
  id410 --> id411[update charm status]
  id411 --> id1((return))
```

#### Backend Database Departed Hook

TODO

```mermaid
flowchart TD
  id501([backend-database-relation-departed Hook]) --> id502[update relation connection information]
  id502 --> id503{Is this unit the\ndeparting unit?}
  id503 -- yes --> id504[update unit databag to tell\npeers this unit is departing]
  id504 --> id505((return))
  id503 -- no --> id506
```

#### Backend Database Broken Hook

TODO

```mermaid
flowchart TD
  id801([backend-database-relation-broken Hook])
```

#### Database Requested Hook

TODO

```mermaid
flowchart TD
  id901([database-requested Hook])
```

#### Database Relation Departed Hook

TODO

```mermaid
flowchart TD
  id1001([database-relation-departed Hook])
```


#### Database Relation Broken Hook

TODO

```mermaid
flowchart TD
  id1101([database-relation-broken Hook])
```

#### db And db-admin Relation Joined Hook

`db` and `db-admin` relations share the same logic. `db` has been used in this documentation.

TODO

```mermaid
flowchart TD
  id1001([db-relation-joined Hook])
```

#### db And db-admin Relation Changed Hook

`db` and `db-admin` relations share the same logic. `db` has been used in this documentation.

TODO

```mermaid
flowchart TD
  id1001([db-relation-changed Hook])
```

#### db And db-admin Relation Departed Hook

`db` and `db-admin` relations share the same logic. `db` has been used in this documentation.

TODO

```mermaid
flowchart TD
  id1001([db-relation-departed Hook])
```

#### db And db-admin Relation Broken Hook

`db` and `db-admin` relations share the same logic. `db` has been used in this documentation.

TODO

```mermaid
flowchart TD
  id1001([db-relation-Broken Hook])
```
