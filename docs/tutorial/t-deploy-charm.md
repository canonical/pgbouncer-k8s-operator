# Get a PgBouncer K8s up and running

This is part of the [PgBouncer K8s Tutorial](/t/12251). Please refer to this page for more information and the overview of the content. 

In this section, you will deploy PgBouncer together with a PostgreSQL server from [Charmed PostgreSQL K8s](https://charmhub.io/postgresql-k8s). 

## Deploy Charmed PostgreSQL K8s + PgBouncer K8s

To deploy Charmed PostgreSQL K8s + PgBouncer K8s, all you need to do is run the following commands:

```shell
juju deploy pgbouncer-k8s --channel 1/stable --trust
juju deploy postgresql-k8s --trust
```
[note]
**Note**: `--trust` is required to create some K8s resources.
[/note]

Juju will now fetch charms from [Charmhub](https://charmhub.io/) and begin deploying them to MicroK8s. This process can take several minutes depending on how provisioned (RAM, CPU, etc) your machine is. 

You can track the progress by running
```shell
juju status --watch 1s
```

This command is useful for checking the status of Juju applications and gathering information about the machines hosting them. It displays helpful information like IP addresses, ports, state, etc. The `--watch 1s` flag updates the status of charms every second, so as the application starts, you can watch the status and messages as they change. 

When the application is ready, `juju status` will show
```shell
Model   Controller  Cloud/Region        Version  SLA          Timestamp
test16  microk8s    microk8s/localhost  3.1.6    unsupported  21:55:49+02:00

App             Version  Status   Scale  Charm           Channel    Rev  Address        Exposed  Message
pgbouncer-k8s   1.18.0   waiting      1  pgbouncer-k8s   1/stable    76  10.152.183.84  no       installing agent
postgresql-k8s  14.9     active       1  postgresql-k8s  14/stable  158  10.152.183.92  no       Primary

Unit               Workload  Agent  Address     Ports  Message
pgbouncer-k8s/0*   blocked   idle   10.1.12.15         waiting for backend database relation to initialise
postgresql-k8s/0*  active    idle   10.1.12.6          Primary
```
[note]
**Note**: To exit the screen with `juju status --watch 1s`, enter `Ctrl+C`.

If you want to further inspect juju logs, can watch for logs with `juju debug-log`.
More info on logging at [juju logs](https://juju.is/docs/olm/juju-logs).
[/note]

At this stage, PgBouncer will be in a blocked state due to missing [relation/integration](https://charmhub.io/postgresql-k8s/docs/t-integrations#integrations-juju-30-or-relations-juju-29-2) with PostgreSQL DB.

Integrate them by using the command
```shell
juju integrate postgresql-k8s pgbouncer-k8s
```
Shortly,  `juju status` will report a new blocking reason `Missing relation: database` as it waits for a client to consume the DB service.

Let's deploy [data-integrator](https://charmhub.io/data-integrator) and request access to database `test123`:
```shell
juju deploy data-integrator --config database-name=test123
juju integrate data-integrator pgbouncer-k8s
```
In a couple of seconds, the status will be happy for the entire model:
```shell
Model   Controller  Cloud/Region        Version  SLA          Timestamp
test16  microk8s    microk8s/localhost  3.1.6    unsupported  21:57:34+02:00

App              Version  Status  Scale  Charm            Channel    Rev  Address         Exposed  Message
data-integrator           active      1  data-integrator  stable      13  10.152.183.136  no       
pgbouncer-k8s    1.18.0   active      1  pgbouncer-k8s    1/stable    76  10.152.183.84   no       
postgresql-k8s   14.9     active      1  postgresql-k8s   14/stable  158  10.152.183.92   no       Primary

Unit                Workload  Agent  Address     Ports  Message
data-integrator/0*  active    idle   10.1.12.16         
pgbouncer-k8s/0*    active    idle   10.1.12.15         
postgresql-k8s/0*   active    idle   10.1.12.6          Primary
```

## Access database
The easiest way to access PostgreSQL is via the [PostgreSQL Command Line Client](https://www.postgresql.org/docs/14/app-psql.html) `psql`. Connecting to the database requires that you know the values for `host`, `username` and `password`. 

To retrieve these values, please run data-integrator action `get-credentials`:
```shell
juju run data-integrator/leader get-credentials
```

Running the command above should output:
```yaml
postgresql:
  database: test123
  endpoints: pgbouncer-k8s-0.pgbouncer-k8s-endpoints.test16.svc.cluster.local:6432
  password: VYm6tg2KkFOBj8mP3IW9O821
  username: relation_id_7
  version: "14.9"
```

The IP address of the PgBouncer K8s's host can be found with `juju status`:
```shell
...
App              Version  Status  Scale  Charm            Channel    Rev  Address         Exposed  Message
pgbouncer-k8s    1.18.0   active      1  pgbouncer-k8s    1/stable    76  10.152.183.84   no      
```

Make sure `psql` is installed with the command `psql --version`.  

To access the PostgreSQL database via PgBouncer, use the port 6432 and your host's IP address:
```shell
psql -h 10.152.183.84 -p 6432 -U relation_id_7 -W -d test123
```
Inside PostgreSQL, list DBs available on the host with  `show databases`:
```shell
Password for user relation_id_7:  VYm6tg2KkFOBj8mP3IW9O821
psql (14.9 (Ubuntu 14.9-0ubuntu0.22.04.1))
Type "help" for help.

test123=> \l
                                     List of databases
   Name    |     Owner     | Encoding | Collate |  Ctype  |        Access privileges        
-----------+---------------+----------+---------+---------+---------------------------------
...
 test123   | relation_id_5 | UTF8     | C       | C.UTF-8 | relation_id_5=CTc/relation_id_5+
           |               |          |         |         | relation_id_7=CTc/relation_id_5+
           |               |          |         |         | admin=CTc/relation_id_5
...
```
[note]
**Note**: If at any point you'd like to leave the PostgreSQL client, enter `Ctrl+D` or type `exit`.
[/note]

You can now interact with PostgreSQL directly using any [SQL Queries](https://www.postgresql.org/docs/14/sql-syntax.html). 

For example, entering `SELECT VERSION(), CURRENT_DATE;` should output something like:
```shell
test123=> SELECT VERSION(), CURRENT_DATE;
                                                               version                                                                | current_date 
--------------------------------------------------------------------------------------------------------------------------------------+--------------
 PostgreSQL 14.9 (Ubuntu 14.9-0ubuntu0.22.04.1) on x86_64-pc-linux-gnu, compiled by gcc (Ubuntu 11.4.0-1ubuntu1~22.04) 11.4.0, 64-bit | 2023-10-23
(1 row)
```

Feel free to test out any other PostgreSQL queries. When you’re ready to leave the `psql` shell, you can just type `exit`. 

Now you will be in your original shell where you first started the tutorial. Here you can interact with Juju and MicroK8s.

### Remove the user

To remove the user, remove the relation. Removing the relation automatically removes the user that was created when the relation was created. Enter the following to remove the relation:
```shell
juju remove-relation pgbouncer-k8s data-integrator
```

Now try again to connect to the same PgBouncer K8s you used earlier:
```shell
psql -h 10.152.183.84 -p 6432 -U relation_id_7 -W -d test123
```

This will output an error message because this user no longer exists.
```shell
psql: error: connection to server at "10.152.183.92", port 5432 failed: FATAL:  password authentication failed for user "relation_id_7"
```
This is expected, as `juju remove-relation pgbouncer-k8s data-integrator` also removes the user.

[note]
**Note**: Data remains on the server at this stage.
[/note]

Relate the two applications again if you wanted to recreate the user:
```shell
juju integrate data-integrator pgbouncer-k8s
```
Re-relating generates a new user and password:
```shell
juju run data-integrator/leader get-credentials
```
You can connect to the database with these new credentials.
From here you will see all of your data is still present in the database.