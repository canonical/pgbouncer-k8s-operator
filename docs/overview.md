# PgBouncer K8s Documentation

The PgBouncer K8s Operator delivers automated operations management from day 0 to day 2 on the [PgBouncer](http://www.pgbouncer.org/) - the lightweight connection pooler for [PostgreSQL](https://www.postgresql.org/). It is an open source, end-to-end, production-ready data platform on top of [Juju](https://juju.is/).

![image|690x423](upload://fqMd5JlHeegw0PlUjhWKRu858Nc.png)

PostgreSQL is a powerful, open source object-relational database system that uses and extends the SQL language combined with many features that safely store and scale the most complicated data workloads. Consider to use [Charmed PostgreSQL K8s](https://charmhub.io/postgresql-k8s).

The PgBouncer K8s operator can deploy and operate on both [physical/virtual machines](https://github.com/canonical/pgbouncer-operator) and on [Kubernetes](https://github.com/canonical/pgbouncer-k8s-operator). Both flavours offer identical features and simplify deployment, scaling, configuration and management of PgBouncer reliably in production.

## Project and community

This PgBouncer K8s charm is an official distribution of PgBouncer. It’s an open-source project that welcomes community contributions, suggestions, fixes and constructive feedback.
- [Read our Code of Conduct](https://ubuntu.com/community/code-of-conduct)
- [Join the Discourse forum](https://discourse.charmhub.io/tag/pgbouncer)
- [Contribute](https://github.com/canonical/pgbouncer-k8s-operator/blob/main/CONTRIBUTING.md) and report [issues](https://github.com/canonical/pgbouncer-k8s-operator/issues/new/choose)
- Explore [Canonical Data Fabric solutions](https://canonical.com/data)
-  [Contact us](/t/12264) for any further questions

## In this documentation

| | |
|--|--|
|  [Tutorials](/t/12251)</br>  Get started - a hands-on introduction to using PgBouncer operator for new users </br> |  [How-to guides](/t/12257) </br> Step-by-step guides covering key operations and common tasks |
| [Reference](/t/12261) </br> Technical information - specifications, APIs, architecture | [Explanation](/t/12265) </br> Concepts - discussion and clarification of key topics  |

# Navigation

[details=Navigation]

| Level | Path | Navlink |
|---------|---------|-------------|
| 1 | tutorial | [Tutorial](/t/12251) |
| 2 | t-setup-environment | [1. Set up the environment](/t/12252) |
| 2 | t-deploy-charm | [2. Deploy PgBouncer](/t/12253) |
| 2 | t-managing-units | [3. Manage units](/t/12254) |
| 2 | t-enable-security | [4. Enable TLS](/t/12255) |
| 2 | t-cleanup-environment | [5. Clean up environment](/t/12256) |
| 1 | how-to | [How-to guides](/t/16793) |
| 2 | h-deploy-microk8s | [Deploy](/t/12257) |
| 2 | h-manage-units | [Manage units](/t/12258) |
| 2 | h-manage-app | [Manage integrations](/t/12260) |
| 2 | h-enable-encryption | [Enable TLS](/t/12259) |
| 2 | h-external-access | [External network access](/t/15694) |
| 2 | h-monitoring | [Monitoring (COS)]() |
| 3 | h-enable-monitoring | [Enable monitoring](/t/12279) |
| 3 | h-enable-tracing | [Enable tracing](/t/14789) |
| 2 | h-upgrade | [Upgrade](/t/12267) |
| 3 | h-upgrade-minor | [Perform a minor upgrade](/t/12270) |
| 3 | h-rollback-minor | [Perform a minor rollback](/t/12271) |
| 1 | reference | [Reference](/t/16795) |
| 2 | r-releases | [Releases](/t/12261) |
| 2 | r-requirements | [System requirements](/t/12263) |
| 2 | r-testing | [Software testing](/t/12272) |
| 2 | r-contacts | [Contacts](/t/12264) |
| 1 | explanation | [Explanation](/t/16797) |
| 2 | e-juju-details | [Juju](/t/12274) |
| 2 | e-interfaces | [Interfaces/endpoints](/t/12265) |
| 2 | e-statuses | [Statuses](/t/12266) |
| 2 | e-events-hooks | [Events and hooks](/t/15662) |
[/details]

<!-- Archived
| 3 | h-upgrade-major | [Major upgrade](/t/12268) |
| 3 | h-rollback-major | [Major rollback](/t/12269) |

| 3 | r-revision-359-360 | [Revision 359/360](/t/16124) |
| 3 | r-revision-268-269 | [Revision 268/269](/t/15443) |
| 3 | r-revision-228-229 | [Revision 228/229](/t/15090) |
| 3 | r-revision-144 | [Revision 144/145](/t/14070) |
| 3 | r-revision-103 | [Revision 103](/t/13297) |
| 3 | r-revision-81 | [Revision 81](/t/12751) |
| 3 | r-revision-76 | [Revision 76](/t/12262) |
-->

# Redirects

[details=Mapping table]
| Path | Location |
| ---- | -------- |
[/details]