# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

from ops.model import Relation
from pytest_operator.plugin import OpsTest

def get_backend_relation(ops_test: OpsTest) -> Relation:
    """Gets the backend-database relation from the current model if it exists.

    Args:
        ops_test

    Returns:
        backend-database Relation object if exists, otherwise None
    """
    for rel in ops_test.model.relations:
        if rel.name == "backend-database":
            return rel

    return None
