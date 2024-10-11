# Events and hooks

Detailed information about the charm's internal behaviour can be found in the charm's [GitHub wiki](https://github.com/canonical/pgbouncer-k8s-operator/wiki). 

It includes flowcharts of events in the charm's lifecycle, examples of the expected interface resulting from relations (databag contents), and hook flowcharts:

* **Main file:** [**`charm.py`**][charm.py]
  * [Event flowcharts]
    * [Charm startup]
    * [Config updates]
    * [Leader updates]
  * [Hook handler flowcharts]
    * [`start`]
    * [`pgbouncer-pebble-ready`]
    * [`config-changed`]
    * [`update-status`]
* **Relations**
  * [**`backend_database`**][backend_database relation]
    * [Example databag contents][backend_database example]
    * [Hook handler flowcharts][backend_database hooks]
  * [**`database`**][database relation]
    * [Example databag contents][database example]
    * [Hook handler flowcharts][database hooks]
  * [**`db` and `db-admin`**][db and db-admin relations]
    * [Example databag contents][db example]
    * [Hook handler flowcharts][db hooks]
  * [**`pgb-peers`**][pgb-peers relation]
    * [Example databag contents][pgb-peers example]
    * [Hook handler flowcharts][pgb-peers hooks]

<!-- LINKS -->
[charm.py]: https://github.com/canonical/pgbouncer-k8s-operator/wiki/charm.py

[backend_database relation]: https://github.com/canonical/pgbouncer-k8s-operator/wiki/backend_database-relation
[backend_database example]: https://github.com/canonical/pgbouncer-k8s-operator/wiki/backend_database-relation#expected-interface
[backend_database hooks]: https://github.com/canonical/pgbouncer-k8s-operator/wiki/backend_database-relation#hook-handler-flowcharts

[database relation]: https://github.com/canonical/pgbouncer-k8s-operator/wiki/database-relation
[database example]: https://github.com/canonical/pgbouncer-k8s-operator/wiki/database-relation#expected-interface
[database hooks]: https://github.com/canonical/pgbouncer-k8s-operator/wiki/database-relation#hook-handler-flowcharts

[db and db-admin relations]: https://github.com/canonical/pgbouncer-k8s-operator/wiki/db-and-db%E2%80%90admin-relations
[db example]: https://github.com/canonical/pgbouncer-k8s-operator/wiki/db-and-db%E2%80%90admin-relations#expected-interface
[db hooks]: https://github.com/canonical/pgbouncer-k8s-operator/wiki/db-and-db%E2%80%90admin-relations#hook-handler-flowcharts

[pgb-peers relation]: https://github.com/canonical/pgbouncer-k8s-operator/wiki/pgb%E2%80%90peers-relation
[pgb-peers example]: https://github.com/canonical/pgbouncer-k8s-operator/wiki/pgb%E2%80%90peers-relation#expected-interface
[pgb-peers hooks]: https://github.com/canonical/pgbouncer-k8s-operator/wiki/pgb%E2%80%90peers-relation#hook-handler-flowcharts

[Event flowcharts]: https://github.com/canonical/pgbouncer-k8s-operator/wiki/charm.py#event-flow
[Charm startup]: https://github.com/canonical/pgbouncer-k8s-operator/wiki/charm.py#charm-startup
[Config updates]: https://github.com/canonical/pgbouncer-k8s-operator/wiki/charm.py#config-updates
[Leader updates]: https://github.com/canonical/pgbouncer-k8s-operator/wiki/charm.py#leader-updates

[Hook handler flowcharts]: https://github.com/canonical/pgbouncer-k8s-operator/wiki/charm.py#hook-handler-flowcharts
[`start`]: https://github.com/canonical/pgbouncer-k8s-operator/wiki/charm.py#start-hook
[`pgbouncer-pebble-ready`]: https://github.com/canonical/pgbouncer-k8s-operator/wiki/charm.py#pgbouncer-pebble-ready-hook
[`config-changed`]: https://github.com/canonical/pgbouncer-k8s-operator/wiki/charm.py#config-changed-hook
[`update-status`]: https://github.com/canonical/pgbouncer-k8s-operator/wiki/charm.py#update-status-hook