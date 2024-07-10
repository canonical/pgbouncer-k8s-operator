# Environment Setup

This is part of the [PgBouncer K8s Tutorial](/t/12251). Please refer to this page for more information and the overview of the content.

## Minimum requirements
Before we start, make sure your machine meets [the following requirements](https://charmhub.io/pgbouncer-k8s/docs/r-requirements).

## Multipass environment
[Multipass](https://multipass.run/) is a quick and easy way to launch virtual machines running Ubuntu. It uses the [cloud-init](https://cloud-init.io/) standard to install and configure all the necessary parts automatically.

Install Multipass from [Snap](https://snapcraft.io/multipass):
```shell
sudo snap install multipass
```

Launch a new VM using the [charm-dev](https://github.com/canonical/multipass-blueprints/blob/main/v1/charm-dev.yaml) cloud-init config:
```shell
multipass launch --cpus 4 --memory 8G --disk 30G --name my-vm charm-dev
```
[note type=""]
**Note**: All 'multipass launch' params are [described here](https://multipass.run/docs/launch-command).
[/note]

The Multipass [list of commands](https://multipass.run/docs/multipass-cli-commands) is short and self-explanatory. For example, to show all running VMs, just run the command `multipass list`.

As soon as a new VM has started, access it using
```shell
multipass shell my-vm
```

[note]
**Note**:  If at any point you'd like to leave a Multipass VM, enter `Ctrl+D` or type `exit`.
[/note]

All the parts have been pre-installed inside the VM already, like MicroK8s and Juju. The files `/var/log/cloud-init.log` and `/var/log/cloud-init-output.log` contain all low-level installation details. 

The Juju controller can work with different models. Models host applications such as Charmed PostgreSQL K8s + PgBouncer K8s. 

Set up a specific model named ‘tutorial’:
```shell
juju add-model tutorial
```

You can now view the model you created above by entering the command `juju status` into the command line. 

You should see the following:
```
Model     Controller  Cloud/Region        Version  SLA          Timestamp
tutorial  microk8s    microk8s/localhost  3.1.6    unsupported  11:56:38+01:00

Model "admin/tutorial" is empty.
```