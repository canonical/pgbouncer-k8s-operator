# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest
from unittest.mock import Mock, patch

from ops.model import ActiveStatus
from ops.testing import Harness

from charm import PgBouncerK8sCharm

INI_PATH = "/etc/pgbouncer/pgbouncer.ini"
USERLIST_PATH = "/etc/pgbouncer/userlist.txt"


class TestCharm(unittest.TestCase):
    def setUp(self):
        self._pgbouncer_container = "pgbouncer"
        self._peer_relation = "pgbouncer-replicas"

        self.harness = Harness(PgBouncerK8sCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_on_install(self):
        self.harness.charm._on_install("mock_event")

        # Local config is tested more extensively in its own test below, but it's necessary that
        # some config is available after on_install hook.
        pgb_container = self.harness.model.unit.get_container(self._pgbouncer_container)

        ini = pgb_container.pull(INI_PATH).read()
        self.assertEqual(ini, self.harness.charm._generate_pgbouncer_ini())

        userlist = pgb_container.pull(USERLIST_PATH).read()
        self.assertEqual(userlist, self.harness.charm._generate_userlist())

    @patch("charm.PgBouncerK8sCharm._reload_pgbouncer")
    def test_on_config_changed(self, _reload_pgbouncer):
        self.harness.update_config()
        initial_plan = self.harness.get_container_pebble_plan(self._pgbouncer_container).to_dict()

        self.harness.update_config({"pgb_databases": "db"})
        updated_plan = self.harness.get_container_pebble_plan(self._pgbouncer_container).to_dict()
        self.assertNotEqual(initial_plan, updated_plan)

        placeholder = updated_plan["services"]["pgbouncer"]["environment"]["PGB_DATABASES"]
        self.assertEqual(placeholder, "db")
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

        _reload_pgbouncer.assert_called()

    def test_on_pgbouncer_pebble_ready(self):
        initial_plan = self.harness.get_container_pebble_plan(self._pgbouncer_container)
        self.assertEqual(initial_plan.to_yaml(), "{}\n")

        expected_plan = {
            "services": {
                "pgbouncer": {
                    "summary": "pgbouncer service",
                    "user": "pgbouncer",
                    "command": "pgbouncer /etc/pgbouncer/pgbouncer.ini",
                    "startup": "enabled",
                    "override": "replace",
                    "environment": {
                        "PGB_DATABASES": "exampledb = host=pg-host port=5432 dbname=exampledb",
                        "PGB_LISTEN_PORT": 6432,
                        "PGB_LISTEN_ADDRESS": "localhost",
                        "PGB_ADMIN_USERS": "juju-admin",
                    },
                }
            },
        }
        container = self.harness.model.unit.get_container(self._pgbouncer_container)
        self.harness.charm.on.pgbouncer_pebble_ready.emit(container)
        updated_plan = self.harness.get_container_pebble_plan(self._pgbouncer_container).to_dict()
        self.assertEqual(expected_plan, updated_plan)

        service = self.harness.model.unit.get_container(self._pgbouncer_container).get_service(
            "pgbouncer"
        )
        self.assertTrue(service.is_running())
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    @patch("charm.PgBouncerK8sCharm._reload_pgbouncer")
    def test_update_local_config(self, _reload_pgbouncer):
        self.harness.charm._on_install("mock_event")

        pgb_container = self.harness.model.unit.get_container(self._pgbouncer_container)

        initial_ini = pgb_container.pull(INI_PATH).read()
        self.assertEqual(initial_ini, self.harness.charm._generate_pgbouncer_ini())

        initial_userlist = pgb_container.pull(USERLIST_PATH).read()
        self.assertEqual(initial_userlist, self.harness.charm._generate_userlist())

        self.harness.update_config(
            {
                "pgb_databases": "updated_db",
                "pgb_listen_port": "4444",
                "pgb_listen_address": "8.8.8.8",
                "pgb_admin_users": "test-admin,another_test_admin",
            }
        )

        updated_ini = pgb_container.pull(INI_PATH).read()
        self.assertEqual(updated_ini, self.harness.charm._generate_pgbouncer_ini())

        updated_userlist = pgb_container.pull(USERLIST_PATH).read()
        self.assertEqual(updated_userlist, self.harness.charm._generate_userlist())

        self.assertNotEqual(initial_ini, updated_ini)
        self.assertNotEqual(initial_userlist, updated_userlist)

        _reload_pgbouncer.assert_called()

    def test_reload_pgbouncer(self):
        pass

    @patch("charm.PgBouncerK8sCharm._reload_pgbouncer")
    def test_on_reload_pgbouncer_action(self, _reload_pgbouncer):
        self.harness.charm._on_reload_pgbouncer_action(Mock())
        _reload_pgbouncer.assert_called()
        # TODO assert pgbouncer is running in the container

    def test_on_update_password_action(self):
        self.harness.update_config({"pgb_admin_users": "test-admin"})

        pgb_container = self.harness.model.unit.get_container(self._pgbouncer_container)
        initial_userlist = pgb_container.pull(USERLIST_PATH).read()
        self.assertEqual(initial_userlist, self.harness.charm._generate_userlist())

        update_password_event = Mock(
            params={
                "username": "test-admin",
                "password": "password",
            }
        )
        self.harness.charm._on_update_password_action(update_password_event)

        result = self.get_result(update_password_event)
        self.assertDictEqual(result, {"result": "password updated for user test-admin"})

        updated_userlist = pgb_container.pull(USERLIST_PATH).read()
        self.assertEqual(updated_userlist, self.harness.charm._generate_userlist())
        self.assertEqual(updated_userlist, '"test-admin" "password"')
        self.assertNotEqual(updated_userlist, initial_userlist)

    def test_on_update_password_action_nonexistent_user(self):
        self.harness.update_config({"pgb_admin_users": "test-admin"})

        pgb_container = self.harness.model.unit.get_container(self._pgbouncer_container)
        initial_userlist = pgb_container.pull(USERLIST_PATH).read()
        self.assertEqual(initial_userlist, self.harness.charm._generate_userlist())

        nonexistent_user_event = Mock(
            params={
                "username": "nonexistent-user",
                "password": "password",
            }
        )
        self.harness.charm._on_update_password_action(nonexistent_user_event)

        result = self.get_result(nonexistent_user_event)
        self.assertDictEqual(
            result,
            {
                "result": "user nonexistent-user does not exist - use the get-users action to list existing users."
            },
        )
        self.assertEqual(initial_userlist, self.harness.charm._generate_userlist())
        self.assertNotEqual(initial_userlist, '"nonexistent-user" "password"')

    def test_on_add_user_action(self):
        self.harness.update_config({"pgb_admin_users": "existing-user"})

        pgb_container = self.harness.model.unit.get_container(self._pgbouncer_container)
        initial_userlist = pgb_container.pull(USERLIST_PATH).read()

        new_user_event = Mock(params={"username": "new-user"})

        self.harness.charm._on_add_user_action(new_user_event)
        result = self.get_result(new_user_event)
        self.assertEqual(result, {"result": "new user new-user added"})

        generated_password = self.harness.charm._users["new-user"]
        updated_userlist = pgb_container.pull(USERLIST_PATH).read()
        self.assertNotEqual(initial_userlist, updated_userlist)
        self.assertIn(f'"new-user" "{generated_password}"', updated_userlist)

    def test_on_add_user_action_with_password(self):
        self.harness.update_config({"pgb_admin_users": "existing-user"})

        pgb_container = self.harness.model.unit.get_container(self._pgbouncer_container)
        initial_userlist = pgb_container.pull(USERLIST_PATH).read()

        new_user_event = Mock(
            params={
                "username": "new-user",
                "password": "password",
            }
        )
        self.harness.charm._on_add_user_action(new_user_event)
        result = self.get_result(new_user_event)
        self.assertEqual(result, {"result": "new user new-user added"})

        updated_userlist = pgb_container.pull(USERLIST_PATH).read()
        self.assertNotEqual(initial_userlist, updated_userlist)
        self.assertIn('"new-user" "password"', updated_userlist)

    def test_on_add_existing_user_action(self):
        self.harness.update_config({"pgb_admin_users": "existing-user"})

        pgb_container = self.harness.model.unit.get_container(self._pgbouncer_container)
        initial_userlist = pgb_container.pull(USERLIST_PATH).read()

        existing_user_event = Mock(params={"username": "existing-user"})

        self.harness.charm._on_add_user_action(existing_user_event)
        result = self.get_result(existing_user_event)
        self.assertEqual(result, {"result": "user existing-user already exists"})

        updated_userlist = pgb_container.pull(USERLIST_PATH).read()
        self.assertEqual(initial_userlist, updated_userlist)

    def test_on_remove_user_action(self):
        self.harness.update_config({"pgb_admin_users": "existing-user"})

        pgb_container = self.harness.model.unit.get_container(self._pgbouncer_container)
        initial_userlist = pgb_container.pull(USERLIST_PATH).read()

        remove_user_event = Mock(params={"username": "existing-user"})

        self.harness.charm._on_remove_user_action(remove_user_event)
        result = self.get_result(remove_user_event)
        self.assertEqual(result, {"result": "user existing-user removed"})

        updated_userlist = pgb_container.pull(USERLIST_PATH).read()
        self.assertNotEqual(initial_userlist, updated_userlist)
        self.assertNotIn('"existing-user"', updated_userlist)

    def test_on_remove_nonexistent_user_action(self):
        self.harness.update_config({"pgb_admin_users": "existing-user"})

        pgb_container = self.harness.model.unit.get_container(self._pgbouncer_container)
        initial_userlist = pgb_container.pull(USERLIST_PATH).read()

        remove_user_event = Mock(params={"username": "nonexistent-user"})

        self.harness.charm._on_remove_user_action(remove_user_event)
        result = self.get_result(remove_user_event)
        self.assertEqual(result, {"result": "user nonexistent-user does not exist"})

        updated_userlist = pgb_container.pull(USERLIST_PATH).read()
        self.assertEqual(initial_userlist, updated_userlist)

    def test_on_get_users_action(self):
        self.harness.update_config({"pgb_admin_users": "test1,test2,test3"})
        get_users_event = Mock()

        self.harness.charm._on_get_users_action(get_users_event)
        results = self.get_result(get_users_event)
        self.assertEqual(results, {"result": "test1 test2 test3"})
        # for each password, assert it is not passed out in the results of this action.
        for _, password in self.harness.charm._users.items():
            self.assertNotIn(password, results["result"])

    # UTILITIES

    def get_result(self, event):
        """Get the intended result from a mocked event.

        Effectively this gets whatever is passed into `event.set_results()`, given that event is
        actually a `Mock` object.
        """
        return dict(event.method_calls[0][1][0])
