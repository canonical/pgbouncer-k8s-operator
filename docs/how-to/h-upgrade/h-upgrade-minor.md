# Minor Upgrade

TODO...
<!---
> :information_source: **Example**: MySQL Router 8.0.33 -> MySQL Router 8.0.34<br/>
(including simple charm revision bump: from revision 99 to revision 102)

We strongly recommend to **NOT** perform any other extraordinary operations on Charmed MySQL K8s cluster and/or MySQL Router K8s, while upgrading. As an examples, these may be (but not limited to) the following:

1. Adding or removing units
2. Creating or destroying new relations
3. Changes in workload configuration
4. Upgrading other connected/related/integrated applications simultaneously

The concurrency with other operations is not supported, and it can lead the cluster into inconsistent states.

> **:warning: NOTE:** Make sure to have a [Charmed MySQL K8s backups](/t/9653) of your data when running any type of upgrades.

> **:warning: TIP:** The "MySQL Router K8s" upgrade should follow first, before "Charmed MySQL K8s" upgrade!!!

## Minor upgrade steps

1. **Collect** all necessary pre-upgrade information. It will be necessary for the rollback (if requested). Do NOT skip this step, it is better safe the sorry!
2. (optional) **Scale-up**. The new `sacrificial` unit will be the first one to be updated, and it will simplify the rollback procedure a lot in case of the upgrade failure.
3. **Prepare** "Charmed MySQL K8s" Juju application for the in-place upgrade. See the step description below for all technical details executed by charm here.
4. **Upgrade** (phase 1). Once started, only one unit in a cluster will be upgraded. In case of failure, the rollback is simple: remove newly added pod (in step 2).
5. **Resume** upgrade (phase 2). If the new pod is OK after the refresh, the upgrade can be resumed for all other units in the cluster. All units in a cluster will be executed sequentially: from biggest ordinal to the lowest one. Resume is available for Server charm only, the Router charm upgrades all units at once if no issues found for previous steps.
6. (optional) Consider to [**Rollback**](/t/11749) in case of disaster. Please inform and include us in your case scenario troubleshooting to trace the source of the issue and prevent it in the future. [Contact us](https://chat.charmhub.io/charmhub/channels/data-platform)!
7. (optional) **Scale-back**. Remove no longer necessary K8s pod created in step 2 (if any).
8. Post-upgrade **Check**. Make sure all units are in the proper state and the cluster is healthy.

## Step 1: Collect

> **:information_source: NOTE:** The step is only valid when deploying from charmhub. If the [local charm](https://juju.is/docs/sdk/deploy-a-charm) deployed (revision is small, e.g. 0-10), make sure the proper/current local revision of the `.charm` file is available BEFORE going further. You might need it for rollback.

The first step is to record the revision of the running application, as a safety measure for a rollback action. To accomplish this, simply run the `juju status` command and look for the deployed Charmed MySQL and MySQL Router revisions in the command output, e.g.:

```shell
Model    Controller  Cloud/Region        Version  SLA          Timestamp
upgrade  microk8s    microk8s/localhost  3.1.6    unsupported  15:32:04+02:00

App               Version                  Status  Scale  Charm             Channel     Rev  Address         Exposed  Message
mysql-k8s         8.0.34-0ubuntu0.22.04.1  active      3  mysql-k8s         8.0/stable   99  10.152.183.238  no       
mysql-router-k8s  8.0.34-0ubuntu0.22.04.1  active      3  mysql-router-k8s  8.0/stable   69  10.152.183.184  no       
mysql-test-app    0.0.2                    active      1  mysql-test-app    stable       26  10.152.183.36   no       

Unit                 Workload  Agent  Address     Ports  Message
mysql-k8s/0*         active    idle   10.1.12.24         Primary
mysql-k8s/1          active    idle   10.1.12.36         
mysql-k8s/2          active    idle   10.1.12.22         
mysql-router-k8s/0   active    idle   10.1.12.28         
mysql-router-k8s/1   active    idle   10.1.12.10         
mysql-router-k8s/2*  active    idle   10.1.12.5          
mysql-test-app/0*    active    idle   10.1.12.57   
```

For this example, the current revision is `XX` for MySQL and `TT` for Router. Store it safely to use in case of rollback!

## Step 2: Scale-up (optional)

Optionally, it is recommended to scale the application up by one unit before starting the upgrade process.

The new unit will be the first one to be updated, and it will assert that the upgrade is possible. In case of failure, having the extra unit will ease the rollback procedure, without disrupting service. More on the [Minor rollback](/t/12239) tutorial.

```shell
juju scale-application mysql-k8s <current_units_count+1>
juju scale-application mysql-router-k8s <current_units_count+1>
```

Wait for the new unit up and ready.

## Step 3: Prepare

After the application has settled, it’s necessary to run the `pre-upgrade-check` action against the leader unit (for the MySQL Server only):

```shell
juju run mysql-k8s/leader pre-upgrade-check
```

The action will configure the charm to minimize the amount of primary switchover, among other preparations for the upgrade process. After successful execution, charms are ready to be upgraded.

## Step 4: Upgrade

Use the [`juju refresh`](https://juju.is/docs/juju/juju-refresh) command to trigger the charm upgrade process. If using juju version 3 or higher, it is necessary to add the `--trust` option.

```shell
# example with channel selection and juju 2.9.x
juju refresh mysql-router-k8s --channel 8.0/edge

# example with channel selection and juju 3.x
juju refresh mysql-router-k8s --channel 8.0/edge --trust

# example with specific revision selection
juju refresh mysql-router-k8s --revision=89
```

After the Router upgrade is completed, upgrade the Server:
```shell
# example with channel selection and juju 2.9.x
juju refresh mysql-k8s --channel 8.0/edge

# example with channel selection and juju 3.x
juju refresh mysql-k8s --channel 8.0/edge --trust

# example with specific revision selection
juju refresh mysql-k8s --revision=89
```

> **:information_source: IMPORTANT:** The Server upgrade will execute only on the highest ordinal unit, for the running example `mysql-k8s/2`, the `juju status` will look like*:

```shell
TODO
```

> **:information_source: Note:** It is expected to have some status changes during the process: waiting, maintenance, active. Do NOT trigger `rollback` procedure during the running `upgrade` procedure. Make sure `upgrade` has failed/stopped and cannot be fixed/continued before triggering `rollback`!

> **:information_source: Note:** The unit should recover shortly after, but the time can vary depending on the amount of data written to the cluster while the unit was not part of the cluster. Please be patient on the huge installations.

## Step 5: Resume

After the unit is upgraded, the charm will set the unit upgrade state as completed. If deemed necessary the user can further assert the success of the upgrade. Being the unit healthy within the cluster, the next step is to resume the upgrade process, by running:

```shell
juju run-action mysql-k8s/leader resume-upgrade --wait
```

The `resume-upgrade` will rollout the Server upgrade for the following unit, always from highest from lowest, and for each successful upgraded unit, the process will rollout the next automatically.

```shell
Model    Controller  Cloud/Region        Version  SLA          Timestamp
upgrade  microk8s    microk8s/localhost  3.1.6    unsupported  15:56:25+02:00

App               Version                  Status   Scale  Charm             Channel   Rev  Address         Exposed  Message
mysql-k8s         8.0.34-0ubuntu0.22.04.1  waiting    3/4  mysql-k8s         8.0/edge  109  10.152.183.238  no       installing agent
mysql-router-k8s  8.0.34-0ubuntu0.22.04.1  active       4  mysql-router-k8s  8.0/edge   69  10.152.183.184  no       
mysql-test-app    0.0.2                    active       1  mysql-test-app    stable     26  10.152.183.36   no       

Unit                 Workload     Agent  Address     Ports  Message
mysql-k8s/0*         waiting      idle   10.1.12.24         other units upgrading first...
mysql-k8s/1          unknown      lost   10.1.12.36         agent lost, see 'juju show-status-log mysql-k8s/1'
mysql-k8s/2          maintenance  idle   10.1.12.14         upgrade completed
mysql-k8s/3          maintenance  idle   10.1.12.32         upgrade completed
mysql-router-k8s/0   active       idle   10.1.12.28         
mysql-router-k8s/1   active       idle   10.1.12.10         
mysql-router-k8s/2*  active       idle   10.1.12.5          
mysql-router-k8s/3   active       idle   10.1.12.9          
mysql-test-app/0*    active       idle   10.1.12.57    
```

## Step 6: Rollback (optional)

The step must be skipped if the upgrade went well! 

Although the underlying MySQL Cluster and Router continue to work, it’s important to rollback the charm to previous revision so an update can be later attempted after a further inspection of the failure. Please switch to the dedicated [minor rollback](/t/12239) tutorial if necessary.

## Step 7: Scale-back

Case the application scale was changed for the upgrade procedure, it is now safe to scale it back to the desired unit count:

```shell
juju scale-application mysql-k8s <unit_count>
juju scale-application mysql-router-k8s <unit_count>
```

## Step 8: Check

The future [improvement is planned](https://warthogs.atlassian.net/browse/DPE-2620) to check the state on pod/cluster on a low level. At the moment check `juju status` to make sure the cluster [state](/t/12231) is OK.
--->