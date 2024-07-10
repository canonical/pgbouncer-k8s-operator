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

# Contents

1. [Tutorial](tutorial)
  1. [1. Introduction](tutorial/t-overview.md)
  1. [2. Set up the environment](tutorial/t-setup-environment.md)
  1. [3. Deploy PgBouncer](tutorial/t-deploy-charm.md)
  1. [4. Manage units](tutorial/t-managing-units.md)
  1. [5. Enable security](tutorial/t-enable-security.md)
  1. [6. Clean up environment](tutorial/t-cleanup-environment.md)
1. [How To](how-to)
  1. [Setup](how-to/h-setup)
    1. [Deploy on MicroK8s](how-to/h-setup/h-deploy-microk8s.md)
    1. [Manage units](how-to/h-setup/h-manage-units.md)
    1. [Enable encryption](how-to/h-setup/h-enable-encryption.md)
    1. [Manage applications](how-to/h-setup/h-manage-app.md)
  1. [Upgrade](how-to/h-upgrade)
    1. [Intro](how-to/h-upgrade/h-upgrade-intro.md)
    1. [Major upgrade](how-to/h-upgrade/h-upgrade-major.md)
    1. [Major rollback](how-to/h-upgrade/h-rollback-major.md)
    1. [Minor upgrade](how-to/h-upgrade/h-upgrade-minor.md)
    1. [Minor rollback](how-to/h-upgrade/h-rollback-minor.md)
  1. [Monitor (COS)](how-to/h-enable-monitoring.md)
1. [Reference](reference)
  1. [Release Notes](reference/r-releases-group)
    1. [All releases](reference/r-releases-group/r-releases.md)
    1. [Revision 144/145](reference/r-releases-group/r-releases-rev144.md)
    1. [Revision 103](reference/r-releases-group/r-releases-rev103.md)
    1. [Revision 81](reference/r-releases-group/r-releases-rev81.md)
    1. [Revision 76](reference/r-releases-group/r-releases-rev76.md)
  1. [Requirements](reference/r-requirements.md)
  1. [Contributing](https://github.com/canonical/pgbouncer-k8s-operator/blob/main/CONTRIBUTING.md)
  1. [Testing](reference/r-testing.md)
  1. [Contacts](reference/r-contacts.md)
1. [Explanation](explanation)
  1. [Interfaces/endpoints](explanation/e-interfaces.md)
  1. [Statuses](explanation/e-statuses.md)
  1. [Juju](explanation/e-juju-details.md)