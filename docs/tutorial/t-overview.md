# PgBouncer K8s tutorial

The PgBouncer K8s Operator delivers automated operations management from day 0 to day 2 on the [PgBouncer](http://www.pgbouncer.org/) - the lightweight connection pooler for PostgreSQL. It is an open source, end-to-end, production-ready data platform on top of [Juju](https://juju.is/). 

As a first step, this tutorial will show you how to get PgBouncer K8s up and running. Then, you will learn a variety of operations such as adding replicas and enabling Transport Layer Security (TLS). 

In this tutorial, we will walk through how to:
- Set up an environment using [Multipass](https://multipass.run/) with [MicroK8s](https://microk8s.io/) and [Juju](https://juju.is/).
- Deploy PgBouncer K8s using a single command.
- Configure TLS certificate in one command.

## Requirements

While this tutorial intends to guide and teach you as you deploy PgBouncer K8s, it will be most beneficial if:
- You are familiar with basic terminal commands.
- You are familiar with basic PostgreSQL and PgBouncer concepts.
- You are familiar with [Charmed PostgreSQL K8s](https://charmhub.io/postgresql-k8s)
- Your machine fulfils the [minimum requirements](https://charmhub.io/postgresql-k8s/docs/r-requirements).

## Step-by-step guide

Here’s an overview of the steps you will take in this tutorial:
* [Set up the environment](/t/12252)
* [Deploy PgBouncer](/t/12253)
* [Managing your units](/t/12254)
* [Enable security](/t/12255)
* [Clean up your environment](/t/12256)