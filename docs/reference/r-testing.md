# Charm Testing reference

There are [a lot of test types](https://en.wikipedia.org/wiki/Software_testing) available and most of them are well applicable for PgBouncer K8s. Here is a list prepared by Canonical:

* Smoke test
* Unit tests
* Integration tests
* System test
* Performance test

**:information_source: Note:** below examples are written for Juju 3.x, but Juju 2.9 is [supported](/t/12263) as well.<br/>Please adopt the `juju run ...` commands as `juju run-action ... --wait` for Juju 2.9.

## Smoke test

[u]Complexity[/u]: trivial<br/>
[u]Speed[/u]: fast<br/>
[u]Goal[/u]: ensure basic functionality works over short amount of time.

[Setup an Juju 3.x environment](/t/12252), deploy DB with test application and start "continuous write" test:
```shell
juju add-model smoke-test

juju deploy postgresql-k8s --trust --channel 14/stable --config profile=testing
juju deploy pgbouncer-k8s --trust --channel 1/stable
juju relate postgresql-k8s pgbouncer-k8s

juju scale-application postgresql-k8s 3 # (optional)
juju scale-application pgbouncer-k8s 3 # (optional)

juju deploy postgresql-test-app --channel latest/stable
juju relate pgbouncer-k8s postgresql-test-app:first-database

# Make sure random data inserted into DB by test application:
juju run postgresql-test-app/leader get-inserted-data

# Start "continuous write" test:
juju run postgresql-test-app/leader start-continuous-writes
export password=$(juju run postgresql-k8s/leader get-password username=operator | yq '.. | select(. | has("password")).password')
watch -n1 -x juju ssh --container postgresql postgresql-k8s/leader "psql -h 127.0.0.1 -p 6432 -U operator -W  -e \"select count(*) from TODO.TODO\""

# Watch the counter is growing!
```
[u]Expected results[/u]:

* postgresql-test-app continuously inserts records in database `TODO` table `TODO`.
* the counters (amount of records in table) are growing on all cluster members

[u]Hints[/u]:
```shell
# Stop "continuous write" test
juju run postgresql-test-app/leader stop-continuous-writes

# Truncate "continuous write" table (delete all records from DB)
juju run postgresql-test-app/leader clear-continuous-writes
```

## Unit tests

Please check the "[Contributing](https://github.com/canonical/pgbouncer-k8s-operator/blob/main/CONTRIBUTING.md#testing)" guide and follow `tox run -e unit` examples there.

## Integration tests

Please check the "[Contributing](https://github.com/canonical/pgbouncer-k8s-operator/blob/main/CONTRIBUTING.md#testing)" guide and follow `tox run -e integration` examples there.

## System test

Please check/deploy the charm [postgresql-k8s-bundle](https://charmhub.io/pgbouncer-k8s-bundle) ([Git](https://github.com/canonical/pgbouncer-k8s-bundle)). It deploy and test all the necessary parts at once.

## Performance test

Please use the separate [Charmed PostgreSQL K8s performance testing document](https://charmhub.io/postgresql-k8s/docs/r-testing) but deploy Charmed PostgreSQL K8s behind PgBouncer K8s.