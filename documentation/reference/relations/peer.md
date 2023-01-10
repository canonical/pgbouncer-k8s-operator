
## Hook Handler Lifecycle Flowcharts

These flowcharts detail the control flow of the hooks in this program. Unless otherwise stated, **a hook deferral is always followed by a return**.

### Peer Relation Created Hook

file: [src/relations/peers.py](https://github.com/canonical/pgbouncer-k8s-operator/blob/main/src/relations/peers.py)

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

### Peer Relation Changed Hook

file: [src/relations/peers.py](https://github.com/canonical/pgbouncer-k8s-operator/blob/main/src/relations/peers.py)

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
