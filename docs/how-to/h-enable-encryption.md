# How to enable encryption

PgBouncer will enable encrypted connections by default with self generated certificates. Though also by default, connecting clients can disable encryption by setting the connection ssl-mode as disabled.
When related with the `tls-certificates-operator` the charmed operator for PgBouncer will require that every client connection (new and running connections) use encryption, rendering an error when attempting to establish an unencrypted connection.

> **Note**: The TLS settings here are for self-signed-certificates which are not recommended for production clusters, the `tls-certificates-operator` charm offers a variety of configurations, read more on the TLS charm [here](https://charmhub.io/tls-certificates-operator)

## Enable TLS

```shell
# deploy the TLS charm
juju deploy tls-certificates-operator --channel legacy/stable

# add the necessary configurations for TLS
juju config tls-certificates-operator generate-self-signed-certificates="true" ca-common-name="Test CA"

# to enable TLS relate the two applications
juju relate tls-certificates-operator pgbouncer-k8s
```

## Manage keys

Updates to private keys for certificate signing requests (CSR) can be made via the `set-tls-private-key` action. Note passing keys to external/internal keys should *only be done with* `base64 -w0` *not* `cat`. With three routers this schema should be followed:

* Generate a shared internal (private) key:

```shell
openssl genrsa -out internal-key.pem 3072
```

* apply newly generated internal key on each unit:

```
juju run pgbouncer-k8s/0 set-tls-private-key "internal-key=$(base64 -w0 internal-key.pem)"
juju run pgbouncer-k8s/1 set-tls-private-key "internal-key=$(base64 -w0 internal-key.pem)"
juju run pgbouncer-k8s/2 set-tls-private-key "internal-key=$(base64 -w0 internal-key.pem)"
```

* updates can also be done with auto-generated keys with:

```
juju run pgbouncer-k8s/0 set-tls-private-key
juju run pgbouncer-k8s/1 set-tls-private-key
juju run pgbouncer-k8s/2 set-tls-private-key
```

## Disable TLS

To disable TLS, remove the relation:
```shell
juju remove-relation tls-certificates-operator pgbouncer-k8s
```