# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Dict

from charms.pgbouncer_operator.v0 import pgb
from pytest_operator.plugin import OpsTest


def get_backend_relation(ops_test: OpsTest):
    """gets the backend-database relation used to connect pgbouncer to the backend."""
    for rel in ops_test.model.relations:
        if "pgbouncer-k8s-operator" in rel.endpoints and "postgresql-k8s" in rel.endpoints:
            return rel

    return None


async def get_userlist(ops_test: OpsTest) -> Dict[str, str]:
    cat_userlist = await ops_test.juju(
        "ssh",
        "--container",
        "pgbouncer",
        "pgbouncer-k8s-operator/0",
        "cat",
        f"{pgb.PGB_DIR}/userlist.txt",
    )
    return pgb.parse_userlist(cat_userlist[1])


async def get_cfg(ops_test: OpsTest) -> pgb.PgbConfig:
    cat_cfg = await ops_test.juju(
        "ssh",
        "--container",
        "pgbouncer",
        "pgbouncer-k8s-operator/0",
        "cat",
        f"{pgb.PGB_DIR}/pgbouncer.ini",
    )
    return pgb.PgbConfig(cat_cfg[1])


def new_relation_joined(ops_test: OpsTest, endpoint_one: str, endpoint_two: str) -> bool:
    for rel in ops_test.model.relations:
        endpoints = [endpoint.name for endpoint in rel.endpoints]
        if endpoint_one in endpoints and endpoint_two in endpoints:
            return True
    return False


def relation_exited(ops_test: OpsTest, relation_name) -> bool:
    return relation_name not in ops_test.model.relations.keys()
