# How to deploy and manage units

## Basic Usage

To deploy a single unit of PgBouncer using its default configuration
```shell
juju deploy pgbouncer-k8s --trust --channel 1/stable
```

It is customary to use PgBouncer in HA setup. Hence usually more than one unit (preferably an odd number to prohibit a "split-brain" scenario) is deployed. To deploy PgBOuncer in HA mode, specify the number of desired units with the `-n` option.
```shell
juju deploy pgbouncer-k8s --trust --channel 1/stable -n <number_of_replicas>
```

## Scaling

Both scaling-up and scaling-down operations are performed using `juju scale-application`:
```shell
juju scale-application pgbouncer-k8s <desired_num_of_units>
```

> :tipping_hand_man: **Tip**: scaling-down to zero units is supported to safe K8s resources!