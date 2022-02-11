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

        self.harness = Harness(PgBouncerK8sCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_on_install(self):
        self.harness.charm.on.install.emit()
        pgb_container = self.harness.model.unit.get_container(self._pgbouncer_container)

        # Local config is tested more extensively in its own test below, but it's necessary that
        # some config is available after on_install hook.
        ini = pgb_container.pull(INI_PATH).read()
        self.assertEqual(ini, self.harness.charm._generate_pgbouncer_ini())

        userlist = pgb_container.pull(USERLIST_PATH).read()
        # Since we can't access the password without reading from the userlist in the container,
        # which is effectively what we're testing, we assert the default username and a password of
        # length 32 are both in the userlist file.
        self.assertIn('"juju-admin" "', userlist)
        self.assertEqual(len('"juju-admin" ""') + 32, len(userlist))

    @patch("charm.PgBouncerK8sCharm._reload_pgbouncer")
    def test_on_config_changed(self, _reload_pgbouncer):
        self.harness.update_config()
        _reload_pgbouncer.assert_called()

        initial_plan = self.harness.get_container_pebble_plan(self._pgbouncer_container).to_dict()
        self.harness.update_config({"pgb_admin_users": "test-user"})
        updated_plan = self.harness.get_container_pebble_plan(self._pgbouncer_container).to_dict()
        self.assertNotEqual(initial_plan, updated_plan)

        placeholder = updated_plan["services"]["pgbouncer"]["environment"]["PGB_ADMIN_USERS"]
        self.assertEqual(placeholder, "test-user")
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

        # Test changing charm config propagates to container config files.
        pgb_container = self.harness.model.unit.get_container(self._pgbouncer_container)
        userlist = pgb_container.pull(USERLIST_PATH).read()
        self.assertIn("test-user", userlist)
        ini = pgb_container.pull(INI_PATH).read()
        self.assertIn("test-user", ini)

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
    def test_on_reload_pgbouncer_action(self, _reload_pgbouncer):
        self.harness.charm._on_reload_pgbouncer_action(Mock())
        # TODO assert pgbouncer is running in the container once service handling is implemented
        _reload_pgbouncer.assert_called()

    def test_on_change_password_action(self):
        self.harness.update_config({"pgb_admin_users": "test-admin"})

        pgb_container = self.harness.model.unit.get_container(self._pgbouncer_container)
        initial_userlist = pgb_container.pull(USERLIST_PATH).read()
        # Since we can't access the password without reading from the userlist in the container,
        # we assert the expected username and a password of length 32 are both in the userlist.
        self.assertIn('"test-admin" "', initial_userlist)
        self.assertEqual(len('"test-admin" ""') + 32, len(initial_userlist))

        change_password_event = Mock(
            params={
                "username": "test-admin",
                "password": "password",
            }
        )
        self.harness.charm._on_change_password_action(change_password_event)

        result = self.get_result(change_password_event)
        self.assertDictEqual(result, {"result": "password updated for user test-admin"})

        updated_userlist = pgb_container.pull(USERLIST_PATH).read()
        # Assert password is correctly hashed.
        self.assertEqual(updated_userlist, '"test-admin" "5f4dcc3b5aa765d61d8327deb882cf99"')
        self.assertNotEqual(updated_userlist, initial_userlist)
        self.assertNotEqual(initial_userlist, '"test-admin" "password"')

    def test_on_change_password_action_nonexistent_user(self):
        self.harness.update_config({"pgb_admin_users": "test-admin"})

        pgb_container = self.harness.model.unit.get_container(self._pgbouncer_container)
        initial_userlist = pgb_container.pull(USERLIST_PATH).read()
        # Since we can't access the password without reading from the userlist in the container,
        # we assert the expected username and a password of length 32 are both in the userlist.
        self.assertIn('"test-admin" "', initial_userlist)
        self.assertEqual(len('"test-admin" ""') + 32, len(initial_userlist))

        nonexistent_user_event = Mock(
            params={
                "username": "nonexistent-user",
                "password": "password",
            }
        )
        self.harness.charm._on_change_password_action(nonexistent_user_event)

        result = self.get_result(nonexistent_user_event)
        self.assertDictEqual(
            result,
            {
                "result": "user nonexistent-user does not exist - use the get-users action to list existing users."
            },
        )
        current_userlist = pgb_container.pull(USERLIST_PATH).read()
        self.assertEqual(initial_userlist, current_userlist)
        self.assertNotEqual(
            initial_userlist, '"nonexistent-user" "5f4dcc3b5aa765d61d8327deb882cf99"'
        )

    def test_on_add_user_action(self):
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
        # check password is hashed
        self.assertIn('"new-user" "5f4dcc3b5aa765d61d8327deb882cf99"', updated_userlist)
        self.assertNotIn('"new-user" "password"', updated_userlist)

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
        for _, password in self.harness.charm._get_userlist_from_container().items():
            self.assertNotIn(password, results["result"])

    @patch("charm.PgBouncerK8sCharm._reload_pgbouncer")
    def test_push_container_config(self, _reload_pgbouncer):
        self.harness.charm._on_install("mock_event")

        pgb_container = self.harness.model.unit.get_container(self._pgbouncer_container)

        # Ensure pushing container config with no users copies users from userlist to pgbouncer.ini
        self.harness.charm._push_userlist({"test1": "pw"})
        initial_ini = pgb_container.pull(INI_PATH).read()
        initial_userlist = pgb_container.pull(USERLIST_PATH).read()

        self.harness.charm._push_container_config()
        updated_userlist = pgb_container.pull(USERLIST_PATH).read()
        self.assertEqual(initial_userlist, updated_userlist)

        updated_ini = pgb_container.pull(INI_PATH).read()
        self.assertNotEqual(initial_ini, updated_ini)
        self.assertIn("test1", updated_ini)

        # Pushing container config with user dict should update both config files.
        self.harness.charm._push_container_config({"test2": "pw"})
        updated_userlist2 = pgb_container.pull(USERLIST_PATH).read()
        self.assertNotEqual(updated_userlist, updated_userlist2)
        self.assertEqual(updated_userlist2, '"test2" "pw"')

        updated_ini2 = pgb_container.pull(INI_PATH).read()
        self.assertIn("test2", updated_ini2)

        _reload_pgbouncer.assert_called()

    @patch("charm.PgBouncerK8sCharm._reload_pgbouncer")
    def test_push_pgbouncer_ini(self, _reload_pgbouncer):
        self.harness.charm._push_userlist({"test-user": "pw"})
        self.harness.charm._push_pgbouncer_ini(users=None, reload_pgbouncer=True)
        _reload_pgbouncer.assert_called()

        pgb_container = self.harness.model.unit.get_container(self._pgbouncer_container)
        ini = pgb_container.pull(INI_PATH).read()
        self.assertIn("test-user", ini)

    @patch("charm.PgBouncerK8sCharm._reload_pgbouncer")
    def test_push_userlist(self, _reload_pgbouncer):
        self.harness.charm._push_userlist({"initial-user": "pw"})
        pgb_container = self.harness.model.unit.get_container(self._pgbouncer_container)

        self.harness.charm._push_userlist(users={"test-user": "pw"}, reload_pgbouncer=True)
        _reload_pgbouncer.assert_called()

        userlist = pgb_container.pull(USERLIST_PATH).read()
        self.assertEqual('"test-user" "pw"', userlist)

        self.harness.charm._push_userlist(users=None, reload_pgbouncer=True)

    def test_get_userlist_from_container(self):
        self.harness.update_config({"pgb_admin_users": "test-admin"})
        self.harness.charm._push_container_config(users={"test-admin": "pass"})
        users = self.harness.charm._get_userlist_from_container()
        self.assertDictEqual(users, {"test-admin": "pass"})

        self.harness.charm._push_container_config(users={})
        empty_users = self.harness.charm._get_userlist_from_container()
        self.assertDictEqual(empty_users, {})

    # ===========
    #  UTILITIES
    # ===========

    def get_result(self, event):
        """Get the intended result from a mocked event.

        Effectively this gets whatever is passed into `event.set_results()`, given that event is
        actually a `Mock` object.
        """
        return dict(event.method_calls[0][1][0])
