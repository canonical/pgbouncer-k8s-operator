# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import string
import unittest

import pytest

from lib.charms.pgbouncer_k8s.v0 import pgb

DATA_DIR = "tests/unit/data"
TEST_VALID_INI = f"{DATA_DIR}/test.ini"


class TestPgb(unittest.TestCase):
    def test_pgb_config_read_string(self):
        with open(TEST_VALID_INI, "r") as test_ini:
            input_string = test_ini.read()
        ini = pgb.PgbConfig(input_string)
        expected_dict = {
            "databases": {
                "test": {
                    "host": "test",
                    "port": "4039",
                    "dbname": "testdatabase",
                },
                "test2": {"host": "test2"},
            },
            "pgbouncer": {
                "logfile": "test/logfile",
                "pidfile": "test/pidfile",
                "admin_users": {"Test"},
                "stats_users": {"Test", "test_stats"},
                "listen_port": "4545",
            },
            "users": {
                "Test": {
                    "pool_mode": "session",
                    "max_user_connections": "10",
                }
            },
        }
        self.assertDictEqual(dict(ini), expected_dict)

    def test_pgb_config_read_dict(self):
        input_dict = {
            "databases": {
                "db1": {"dbname": "test"},
                "db2": {"host": "test_host"},
            },
            "pgbouncer": {
                "logfile": "/etc/pgbouncer/pgbouncer.log",
                "pidfile": "/etc/pgbouncer/pgbouncer.pid",
                "admin_users": {"test"},
                "stats_users": {"test", "stats_test"},
            },
            "users": {
                "test": {"pool_mode": "session", "max_user_connections": "22"},
            },
        }
        ini = pgb.PgbConfig(input_dict)
        self.assertDictEqual(input_dict, dict(ini))

    def test_pgb_config_render(self):
        with open(TEST_VALID_INI, "r") as test_ini:
            input_string = test_ini.read()
        output = pgb.PgbConfig(input_string).render()
        self.assertEqual(input_string, output)

    def test_pgb_config_validate(self):
        # PgbConfig.validate() is called in read_string() and read_dict() methods, which are called
        # in the constructor.

        with open(TEST_VALID_INI, "r") as test_ini:
            normal_cfg = pgb.PgbConfig(test_ini.read())

            # Test parsing fails without necessary config file values
            del normal_cfg["databases"]
            with pytest.raises(pgb.PgbConfig.ConfigParsingError):
                normal_cfg.validate()

        with open(f"{DATA_DIR}/test_no_logfile.ini", "r") as no_logfile:
            with pytest.raises(pgb.PgbConfig.ConfigParsingError):
                pgb.PgbConfig(no_logfile.read())

        with open(f"{DATA_DIR}/test_no_pidfile.ini", "r") as no_pidfile:
            with pytest.raises(pgb.PgbConfig.ConfigParsingError):
                pgb.PgbConfig(no_pidfile.read())

        # Test parsing fails when database names are malformed
        with open(f"{DATA_DIR}/test_bad_db.ini", "r") as bad_db:
            with pytest.raises(pgb.PgbConfig.ConfigParsingError):
                pgb.PgbConfig(bad_db.read())

        with open(f"{DATA_DIR}/test_bad_dbname.ini", "r") as bad_dbname:
            with pytest.raises(pgb.PgbConfig.ConfigParsingError):
                pgb.PgbConfig(bad_dbname.read())

        with open(f"{DATA_DIR}/test_reserved_db.ini", "r") as reserved_db:
            with pytest.raises(pgb.PgbConfig.ConfigParsingError):
                pgb.PgbConfig(reserved_db.read())

    def test_pgb_config_validate_dbname(self):
        config = pgb.PgbConfig()
        # Valid dbnames include alphanumeric characters and -_ characters. Everything else must
        # be wrapped in double quotes.
        good_dbnames = ["test-_1", 'test"%$"1', 'multiple"$"bad"^"values', '" "', '"\n"', '""']
        for dbname in good_dbnames:
            config._validate_dbname(dbname)

        bad_dbnames = ['"', "%", " ", '"$"test"', "\n"]
        for dbname in bad_dbnames:
            with pytest.raises(pgb.PgbConfig.ConfigParsingError):
                config._validate_dbname(dbname)

    def test_set_max_db_connection_derivatives(self):
        cfg = pgb.PgbConfig(pgb.DEFAULT_CONFIG)

        # Test setting 0 instances fails to update config
        with pytest.raises(pgb.PgbConfig.ConfigParsingError):
            cfg.set_max_db_connection_derivatives(44, 0)

        cfg.set_max_db_connection_derivatives(44, 2)

        self.assertEqual(cfg["pgbouncer"]["max_db_connections"], "44")
        self.assertEqual(cfg["pgbouncer"]["default_pool_size"], "11")
        self.assertEqual(cfg["pgbouncer"]["min_pool_size"], "6")
        self.assertEqual(cfg["pgbouncer"]["reserve_pool_size"], "6")

        # Test defaults when max_db_connection is unlimited
        cfg.set_max_db_connection_derivatives(0, 123252)

        self.assertEqual(cfg["pgbouncer"]["max_db_connections"], "0")
        self.assertEqual(cfg["pgbouncer"]["default_pool_size"], "20")
        self.assertEqual(cfg["pgbouncer"]["min_pool_size"], "10")
        self.assertEqual(cfg["pgbouncer"]["reserve_pool_size"], "10")

    def test_generate_password(self):
        pw = pgb.generate_password()
        self.assertEqual(len(pw), 24)
        valid_chars = string.ascii_letters + string.digits
        for char in pw:
            assert char in valid_chars

    def test_generate_pgbouncer_ini(self):
        config = {
            "databases": {
                "test": {
                    "host": "test",
                    "port": "4039",
                    "dbname": "testdatabase",
                },
                "test2": {"host": "test2"},
            },
            "pgbouncer": {
                "logfile": "test/logfile",
                "pidfile": "test/pidfile",
                "admin_users": {"Test"},
                "stats_users": {"Test", "test_stats"},
                "listen_port": "4545",
            },
            "users": {
                "Test": {
                    "pool_mode": "session",
                    "max_user_connections": "10",
                }
            },
        }

        generated_ini = pgb.generate_pgbouncer_ini(config)
        with open(TEST_VALID_INI, "r") as test_ini:
            expected_generated_ini = test_ini.read()
        self.assertEqual(generated_ini, expected_generated_ini)

    def test_initialise_userlist_from_ini(self):
        with open(TEST_VALID_INI, "r") as test_ini:
            config = pgb.PgbConfig(test_ini.read())

        # Test with blank userlist
        blank_userlist = {}
        new_userlist = pgb.initialise_userlist_from_ini(config, blank_userlist)
        for key in config["pgbouncer"]["admin_users"] + config["pgbouncer"]["stats_users"]:
            self.assertIn(key, new_userlist)
            self.assertIsNotNone(new_userlist[key])

        # Test with existing userlist
        existing_userlist = {
            "test_user": "test_pass",
            "programmerfuel": "coffee",
        }
        updated_userlist = pgb.initialise_userlist_from_ini(config, existing_userlist)
        for key in config["pgbouncer"]["admin_users"] + config["pgbouncer"]["stats_users"]:
            self.assertIn(key, updated_userlist)
            self.assertIsNotNone(updated_userlist[key])
        for key, value in existing_userlist.items():
            self.assertEqual(updated_userlist[key], value)

    def test_generate_userlist(self):
        users = {"test1": "pw1", "test2": "pw2"}
        userlist = pgb.generate_userlist(users)
        expected_userlist = '''"test1" "pw1"\n"test2" "pw2"'''
        self.assertEqual(userlist, expected_userlist)
        self.assertDictEqual(pgb.parse_userlist(expected_userlist), users)

    def test_parse_userlist(self):
        with open("tests/unit/data/test_userlist.txt") as f:
            userlist = f.read()
        users = pgb.parse_userlist(userlist)
        expected_users = {
            "testuser": "testpass",
            "another_testuser": "anotherpass",
            "1234": "",
            "": "",
        }
        self.assertDictEqual(users, expected_users)

        # Check that we can run input through a few times without anything getting corrupted.
        regen_userlist = pgb.generate_userlist(users)
        regen_users = pgb.parse_userlist(regen_userlist)
        # Assert invalid users aren't represented anywhere in userlist data
        self.assertNotEqual(regen_userlist, userlist)
        self.assertDictEqual(users, regen_users)
