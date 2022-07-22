# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from tests.integration.relations.helpers.helpers import (
    get_userlist,
    wait_for_relation_joined_between,
)
from tests.integration.relations.helpers.postgresql_helpers import (
    check_database_creation,
    check_database_users_existence,
    get_unit_address,
)

FIRST_DISCOURSE_APP_NAME = "discourse-k8s"
SECOND_DISCOURSE_APP_NAME = "discourse-charmers-discourse-k8s"
REDIS_APP_NAME = "redis-k8s"
APPLICATION_UNITS = 1
DATABASE_UNITS = 3

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
PGB = METADATA["name"]
PG = "postgresql-k8s"
PSQL = "psql"
APPS = [PG, PGB, PSQL]


@pytest.mark.abort_on_fail
@pytest.mark.legacy_relations
async def test_create_db_admin_legacy_relation(ops_test: OpsTest):
    # Build, deploy, and relate charms.
    charm = await ops_test.build_charm(".")
    resources = {
        "pgbouncer-image": METADATA["resources"]["pgbouncer-image"]["upstream-source"],
    }

    async with ops_test.fast_forward():
        await asyncio.gather(
            ops_test.model.deploy(
                charm,
                resources=resources,
                application_name=PGB,
            ),
            ops_test.model.deploy(PG, trust=True, num_units=3, channel="edge"),
            ops_test.model.deploy(
                FIRST_DISCOURSE_APP_NAME, application_name=FIRST_DISCOURSE_APP_NAME
            ),
            ops_test.model.deploy(REDIS_APP_NAME, application_name=REDIS_APP_NAME),
        )
        await ops_test.model.wait_for_idle(apps=[PG, PGB], status="active", timeout=1000)

        backend_relation = await ops_test.model.relate(f"{PGB}:backend-database", f"{PG}:database")
        pgb_user = f"relation_id_{backend_relation.id}"
        wait_for_relation_joined_between(ops_test, PGB, PG)
        await ops_test.model.wait_for_idle(
            apps=[PG, PGB, REDIS_APP_NAME], status="active", timeout=1000
        )

        # Discourse becomes blocked waiting for relations.
        await ops_test.model.wait_for_idle(
            apps=[FIRST_DISCOURSE_APP_NAME], status="blocked", timeout=1000
        )

        # Add both relations to Discourse (PostgreSQL and Redis) and wait for it to be ready.
        first_discourse_relation = await ops_test.model.add_relation(
            f"{PGB}:db-admin",
            FIRST_DISCOURSE_APP_NAME,
        )
        await ops_test.model.add_relation(
            REDIS_APP_NAME,
            FIRST_DISCOURSE_APP_NAME,
        )
        wait_for_relation_joined_between(ops_test, REDIS_APP_NAME, FIRST_DISCOURSE_APP_NAME)
        wait_for_relation_joined_between(ops_test, PGB, FIRST_DISCOURSE_APP_NAME)
        await ops_test.model.wait_for_idle(
            apps=[PG, PGB, FIRST_DISCOURSE_APP_NAME, REDIS_APP_NAME],
            status="active",
            timeout=2000,  # Discourse takes a longer time to become active (a lot of setup).
        )
        userlist = await get_userlist(ops_test)
        pgb_password = userlist[pgb_user]

        # Check for the correct databases and users creation.
        await check_database_creation(
            ops_test, "discourse-k8s", user=pgb_user, password=pgb_password
        )
        discourse_users = [f"relation_id_{first_discourse_relation.id}"]
        await check_database_users_existence(
            ops_test,
            discourse_users,
            [],
            admin=True,
            pg_user=pgb_user,
            pg_user_password=pgb_password,
        )

        # Test the second Discourse charm.

        # Get the Redis instance IP address.
        redis_host = await get_unit_address(ops_test, f"{REDIS_APP_NAME}/0")

        # Deploy Discourse and wait for it to be blocked waiting for database relation.
        await ops_test.model.deploy(
            SECOND_DISCOURSE_APP_NAME,
            application_name=SECOND_DISCOURSE_APP_NAME,
            config={
                "redis_host": redis_host,
                "developer_emails": "user@foo.internal",
                "external_hostname": "foo.internal",
                "smtp_address": "127.0.0.1",
                "smtp_domain": "foo.internal",
            },
        )
        # Discourse becomes blocked waiting for PostgreSQL relation.
        await ops_test.model.wait_for_idle(
            apps=[SECOND_DISCOURSE_APP_NAME], status="blocked", timeout=1000
        )

        # Relate PostgreSQL and Discourse, waiting for Discourse to be ready.
        second_discourse_relation = await ops_test.model.add_relation(
            f"{PGB}:db-admin",
            SECOND_DISCOURSE_APP_NAME,
        )
        wait_for_relation_joined_between(ops_test, PGB, SECOND_DISCOURSE_APP_NAME)
        await ops_test.model.wait_for_idle(
            apps=[PG, PGB, SECOND_DISCOURSE_APP_NAME, REDIS_APP_NAME],
            status="active",
            timeout=2000,  # Discourse takes a longer time to become active (a lot of setup).
        )

        # Check for the correct databases and users creation.
        await check_database_creation(
            ops_test, "discourse-charmers-discourse-k8s", user=pgb_user, password=pgb_password
        )
        discourse_users = [f"relation_id_{second_discourse_relation.id}"]
        await check_database_users_existence(
            ops_test,
            discourse_users,
            [],
            admin=True,
            pg_user=pgb_user,
            pg_user_password=pgb_password,
        )
