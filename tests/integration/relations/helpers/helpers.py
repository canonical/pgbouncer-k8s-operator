#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

from pytest_operator.plugin import OpsTest


async def new_relation_joined(ops_test: OpsTest, endpoint_one: str, endpoint_two: str) -> bool:
    for rel in ops_test.model.relations:
        endpoints = [endpoint.name for endpoint in rel.endpoints]
        if endpoint_one in endpoints and endpoint_two in endpoints:
            return True
    return False

async def relation_exited(ops_test: OpsTest, relation_name) -> bool:
    return relation_name not in ops_test.model.relations.keys()