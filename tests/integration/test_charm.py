#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import hashlib
import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]

PGB_DIR = "/etc/pgbouncer"
INI_PATH = f"{PGB_DIR}/pgbouncer.ini"
USERLIST_PATH = f"{PGB_DIR}/userlist.txt"


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    """Build and deploy pgbouncer charm."""
    charm = await ops_test.build_charm(".")
    resources = {
        "pgbouncer-image": METADATA["resources"]["pgbouncer-image"]["upstream-source"],
    }
    await ops_test.model.deploy(
        charm,
        resources=resources,
        application_name=APP_NAME,
        config={"pgb_admin_users": "juju-admin"},
    )
    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000)


async def test_user_management(ops_test: OpsTest):
    """Test user management through config and actions.

    We complete the following steps, verifying each action has the expected output:
    - Create a user through `pgb_admin_users` config variable
    - Change this user's password
    - Add a new user through the `add-user` action
    - Check we have all three expected users, using the `get-users` action
    - Remove the created users in preparation for the next test, and check that they have been
      removed using the `get-users` action
    """
    await ops_test.model.applications[APP_NAME].set_config({"pgb_admin_users": "test1"})
    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000)

    # check test1 and juju-admin users have generated and hashed passwords
    userlist = await get_userlist_from_container(ops_test)
    assert "juju-admin" in userlist
    assert "test1" in userlist

    unit = ops_test.model.applications[APP_NAME].units[0]
    action = await unit.run_action("change-password", username="test1", password="pw1")
    action = await action.wait()
    assert action.results["result"] == "password updated for user test1"

    action = await unit.run_action("add-user", username="test2", password="pw2")
    action = await action.wait()
    assert action.results["result"] == "new user test2 added"

    action = await unit.run_action("get-users")
    action = await action.wait()
    # juju-admin is the default user defined in config.yaml
    assert action.results["result"] == "juju-admin test1 test2"

    # Assert passwords are correct, with expected md5 hashing. This also verifies userlist.txt is
    # correctly formatted, with double quotes surrounding usernames and hashed passwords.
    userlist = await get_userlist_from_container(ops_test)
    assert "juju-admin" in userlist
    assert f'"test1" "{hashlib.md5("pw1".encode()).hexdigest()}"' in userlist
    assert f'"test2" "{hashlib.md5("pw2".encode()).hexdigest()}"' in userlist

    # teardown users before next test
    action = await unit.run_action("remove-user", username="test1")
    action = await action.wait()
    assert action.results["result"] == "user test1 removed"

    action = await unit.run_action("remove-user", username="test2")
    action = await action.wait()
    assert action.results["result"] == "user test2 removed"

    action = await unit.run_action("get-users")
    action = await action.wait()
    assert action.results["result"] == "juju-admin"

    # Assert juju-admin in userlist, and test1 and test2 have been removed.
    userlist = await get_userlist_from_container(ops_test)
    assert "juju-admin" in userlist
    assert "test1" not in userlist
    assert "test2" not in userlist


async def get_userlist_from_container(ops_test):
    """Helper function to get userlist.txt from pgbouncer container.

    ops_test.scp_from() doesn't seem to work on k8s charms, and we don't particularly want to save
    the file locally anyway, so instead we run `cat` over ssh and return the output.
    """
    userlist = await ops_test.run(
        "juju",
        "ssh",
        "--container",
        "pgbouncer",
        f"{APP_NAME}/0",
        "cat",
        f"{USERLIST_PATH}",
    )
    return userlist[1]
