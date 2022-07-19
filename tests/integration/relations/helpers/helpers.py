# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

from pytest_operator.plugin import OpsTest

def get_backend_relation(ops_test: OpsTest):
    """gets the backend-database relation used to connect pgbouncer to the backend."""
    for rel in ops_test.model.relations:
        if "pgbouncer-k8s-operator" in rel.endpoints and "postgresql-k8s" in rel.endpoints:
            return rel

    return None
