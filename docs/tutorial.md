 # Tutorial

This section of our documentation contains a hands-on tutorial to help you learn how to deploy Charmed PgBouncer together with PostgreSQL on Kubernetes, and become familiar with some of its operations.

## Prerequisites

While this tutorial intends to guide you as you deploy Charmed PgBouncer K8s for the first time, it will be most beneficial if:
- You have some experience using a Linux-based CLI
- You are familiar with PgBouncer concepts such as load balancing and connection pooling.
- Your computer fulfils the [minimum system requirements](/t/12263)

## Tutorial contents
This Charmed PgBouncer K8s tutorial has the following parts:

| Step | Details |
| ------- | ---------- |
| 1. [**Set up the environment**](/t/12252) | Set up a cloud environment for your deployment using [Multipass](https://multipass.run/) with [MicroK8s](https://microk8s.io/docs) and [Juju](https://juju.is/).
| 2. [**Deploy PgBouncer**](/t/12253) | Learn to deploy Charmed PgBouncer with Juju
| 3. [**Manage your units**](/t/12254) | Learn how to scale PgBouncer units
| 4. [**Enable security with TLS**](/t/12255) |  Learn how to enable TLS encryption in PgBouncer traffic
| 5. [**Clean up the environment**](/t/12256) | Free up your machine's resources