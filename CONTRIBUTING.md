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

#### Start Hook

```mermaid
flowchart TD
  hook_fired([start Hook]) --> is_container{ Is container\navailable? }
  is_container -- no --> defer> defer ]
  is_container -- yes --> is_cfg{ Is pgbouncer config\navailable in container or\npeer databag? }
  is_cfg -- no --> is_leader{ Is the current unit Leader? }
  is_cfg -- yes --> render_cfg[ render config, update\nrelations if available ]
  is_leader -- no --> defer_wait> defer:\nwait for leader unit to generate\nconfig and upload to peer databag ]
  is_leader -- yes --> gen_cfg[ generate new config ]
  gen_cfg --> render_cfg
  render_cfg --> rtn(( return ))
```

#### PgBouncer Pebble Ready Hook

```mermaid
flowchart TD
  hook_fired([pgbouncer-pebble-ready Hook]) --> is_cfg{Is pgbouncer\nconfig available?}
  is_cfg -- no --> defer>defer]
  is_cfg -- yes --> gen_cfg[Generate pebble config\nand start service]
  gen_cfg --> verify[Verify pgbouncer is\nrunning, and set charm\n status accordingly]
  verify --> rtn([return])
```

#### Config Changed Hook

```mermaid
flowchart TD
  hook_fired([config-changed Hook]) --> is_leader{Is current\nunit leader?}
  is_leader -- no --> rtn([return])
  is_leader -- yes --> is_cfg{Is pgbouncer\nconfig available?}
  is_cfg -- no --> defer>defer]
  is_cfg -- yes --> match_cfg[Modify pgbouncer\nconfig to match\ncharm config]
  match_cfg --> render_cfg[Render config &\nreload pgbouncer]
  render_cfg --> rtn2([return])
```

#### Peer Relation Created Hook

```mermaid
flowchart TD
  hook_fired([peer-relation-created Hook]) --> save_hostname[Save unit hostname\n in unit databag]
  save_hostname --> is_leader{Is current\nunit leader?}
  is_leader -- no --> rtn([return])
  is_leader -- yes --> is_cfg{Is pgbouncer\nconfig available?}
  is_cfg -- no --> defer>defer]
  is_cfg -- yes --> is_backend_ready{Is backend\ndatabase ready?}
  is_backend_ready -- no --> defer2>defer]
  is_backend_ready -- yes --> update_auth[Add auth file to\npeer databag]
  update_auth --> rtn2([return])
```

#### Peer Relation Changed Hook

TODO

```mermaid
flowchart TD
  hook_fired([peer-relation-changed Hook]) --> save_hostname[Save unit hostname\n in unit databag]
  save_hostname --> update_relations[Update peer data\n in relation databags]
  update_relations --> is_leader{Is current\nunit leader?}
  is_leader -- yes --> is_cfg{Is local pgbouncer\nconfig available?}
  is_cfg -- no --> defer>defer]
  is_cfg -- yes --> update_cfg[Update pgbouncer config\nand leader hostname\n in app databag]
  update_cfg --> rtn([return])
  is_leader -- no --> is_cfg_in_databag{Is a valid config\nfile in the\napp databag?}
  is_cfg_in_databag -- yes --> save_cfg[Save config from\napplication databag]
  is_cfg_in_databag -- no --> is_auth_in_databag{Is a valid auth\nfile in the\napp databag?}
  save_cfg --> is_auth_in_databag
  is_auth_in_databag -- yes --> save_auth[Save auth file from\napplication databag]
  is_auth_in_databag -- no --> reload[if auth file or\n config have changed,\nreload pgbouncer]
  save_auth --> reload
  reload --> rtn2([return])
```

#### Backend Database Created Hook

```mermaid
flowchart TD
  hook_fired([backend-database-requested Hook]) --> is_leader{Is current\nunit leader?}
  is_leader -- no --> rtn([return])
  is_leader -- yes --> is_running{Is pgbouncer\nrunning?}
  is_running -- no --> rtn3([return])
  is_running -- yes --> is_backend_ready{is backend database ready,\nand has pgbouncer been\nprovided with the\nnecessary relation data?}
  is_backend_ready -- no --> defer>defer]
  is_backend_ready -- yes --> generate_user[Generate username & password]
  generate_user --> create_auth_func[create auth function on postgres]
  create_auth_func --> save_auth_data[update pgbouncer config, and save\nauth data to container and peer databag]
  save_auth_data --> update_relations[update postgres endpoints in client relations]
  update_relations --> update_status[update charm status]
  update_status --> rtn2([return])
```

#### Backend Database Departed Hook

```mermaid
flowchart TD
  hook_fired([backend-database-relation-departed Hook]) --> update_info[update relation connection information]
  update_info --> is_this_unit_departing{Is this unit the\ndeparting unit?}
  is_this_unit_departing -- yes --> tell_peers[update unit databag to tell\npeers this unit is departing]
  tell_peers --> rtn([return])
  is_this_unit_departing -- no --> is_leader{is this unit the\nleader, and is\nit departing}
  is_leader -- no --> rtn2([return])
  is_leader -- yes --> scale_down{Is this application\nscaling down,\nbut not to 0?}
  scale_down -- no --> rtn3([return])
  scale_down -- yes --> remove_auth[Remove auth function, and \n delete auth user]
  remove_auth --> rtn4([return])
```

#### Backend Database Broken Hook

```mermaid
flowchart TD
  hook_fired([backend-database-relation-broken Hook]) --> check_depart{Is this unit not\nthe leader, or is the\nrelation_departing flag\n in the unit databag?}
  check_depart -- yes --> rtn([return])
  check_depart -- no --> is_cfg{Is pgbouncer\nconfig available?}
  is_cfg -- no --> defer>defer]
  is_cfg -- yes --> remove_auth[Remove authentication\ninformation from\npgbouncer config]
  remove_auth --> rtn2([return])
```

#### Database Requested Hook

TODO

```mermaid
flowchart TD
  hook_fired([database-requested Hook])
```

#### Database Relation Departed Hook

TODO

```mermaid
flowchart TD
  hook_fired([database-relation-departed Hook])
```


#### Database Relation Broken Hook

TODO

```mermaid
flowchart TD
  hook_fired([database-relation-broken Hook])
```

#### db And db-admin Relation Joined Hook

`db` and `db-admin` relations share the same logic. `db` has been used in this documentation, but they're interchangeable.

TODO

```mermaid
flowchart TD
  hook_fired([db-relation-joined Hook])
```

#### db And db-admin Relation Changed Hook

`db` and `db-admin` relations share the same logic. `db` has been used in this documentation, but they're interchangeable.

TODO

```mermaid
flowchart TD
  hook_fired([db-relation-changed Hook])
```

#### db And db-admin Relation Departed Hook

`db` and `db-admin` relations share the same logic. `db` has been used in this documentation, but they're interchangeable.

TODO

```mermaid
flowchart TD
  hook_fired([db-relation-departed Hook])
```

#### db And db-admin Relation Broken Hook

`db` and `db-admin` relations share the same logic. `db` has been used in this documentation, but they're interchangeable.

TODO

```mermaid
flowchart TD
  hook_fired([db-relation-Broken Hook])
```
