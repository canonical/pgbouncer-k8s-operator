# Upgrade

Currently, the charm supports PgBouncer major version 1 only. Therefore, in-place upgrades/rollbacks are not possible for major versions. 

> **Note**: Canonical is not planning to support in-place upgrades for major version change. The new PgBouncer K8s charm will have to be installed nearby, and the data will be copied from the old to the new installation. After announcing the next PostgreSQL + PgBouncer major version support, the appropriate documentation for data migration will be published.

For instructions on carrying out **minor version upgrades**, see the following guides:

* [Minor upgrade](/t/12270), e.g. PgBouncer 1.18 -> PgBouncer 1.19<br/>
(including charm revision bump 99 -> 102).
* [Minor rollback](/t/12271), e.g. PgBouncer 1.19 -> PgBouncer 1.18<br/>
(including charm revision return 102 -> 99).