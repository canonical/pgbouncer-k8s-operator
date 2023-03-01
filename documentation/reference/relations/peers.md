# pgb-peers Relation Reference Documentation

This reference documentation details the implementation of the `pgb-peers` peer relation. This is the peer relation for pgbouncer, used to share user and config information from the leader unit to the follower units. The file implementing these relations can be found here: [src/relations/peers.py](../../../src/relations/peers.py).

## Expected Interface

These are the expected contents of the databags in this relation (all values are examples, generated in a running test instance):

| relation (id: 2) | pgbouncer-k8s |
|---|---|
| **metadata** |  |
| relation name       | pgb_peers|
| interface           | pgb_peers|
| leader unit         | 0|
| type                | peer|
| **application databag** |  |
|  auth_file       | "pgbouncer_auth_relation_id_3" "md5aad46d9afbcc8c8248d254d567b577c1"       |
|  cfg_file        | [example pgbouncer config file](../../../lib/charms/pgbouncer_k8s/v0/pgb.py) |
|  leader_hostname | pgbouncer-k8s-0.pgbouncer-k8s-endpoints.test-pgbouncer-provider-gnrj.svc…  |
|  relation_id_4   | Z4OtFCe6r5HG6mk1XuR6LkwZ                                                   |

## Hook Handler Flowcharts

These flowcharts detail the control flow of the hooks in this program. Unless otherwise stated, **a hook deferral is always followed by a return**.

### Peer Relation Created Hook

```mermaid
flowchart TD
  hook_fired([peer-relation-created Hook]) --> save_hostname[Save unit hostname\n in unit databag]
  save_hostname --> is_leader{Is current\nunit leader?}
  is_leader -- no --> rtn([return])
  is_leader -- yes --> is_cfg{Is pgbouncer\nconfig available?}
  is_cfg -- no --> defer>defer]
  is_cfg -- yes --> update_cfg[Update config in\npeer databag]
  update_cfg --> is_backend_ready{Is backend\ndatabase ready?}
  is_backend_ready -- no --> defer2>defer]
  is_backend_ready -- yes --> update_auth[Add auth file to\nsecret store]
  update_auth --> rtn2([return])
```

### Peer Relation Changed Hook

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
