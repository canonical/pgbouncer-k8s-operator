# Major Rollback

> :information_source: **Example**: PgBouncer 2 -> PgBouncer 1

Currently, the charm supports PgBouncer major version 1 only; therefore, minor rollbacks are only possible. Canonical is NOT planning to support in-place rollbacks for the major PgBouncer version change as the old PostgreSQL cluster with the old PgBouncer installation will stay nearby and can be reused for the rollback.