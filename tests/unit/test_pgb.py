# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import string
import unittest

import pytest

from lib.charms.pgbouncer_k8s.v0 import pgb
from lib.charms.pgbouncer_k8s.v0.pgb import DEFAULT_CONFIG, PgbConfig

DATA_DIR = "tests/unit/data"
TEST_VALID_INI = f"{DATA_DIR}/test.ini"
PGB = "pgbouncer"


class TestPgb(unittest.TestCase):
    def test_pgb_config_read_string(self):
        with open(TEST_VALID_INI, "r") as test_ini:
            input_string = test_ini.read()
        ini = PgbConfig(input_string)
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
                "stats_users": {"test_stats"},
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
        ini = PgbConfig(input_dict)
        self.assertDictEqual(input_dict, dict(ini))

    def test_pgb_config_render(self):
        with open(TEST_VALID_INI, "r") as test_ini:
            input_string = test_ini.read()
        output = PgbConfig(input_string).render()
        self.assertEqual(input_string, output)

    def test_pgb_config_validate(self):
        # PgbConfig.validate() is called in read_string() and read_dict() methods, which are called
        # in the constructor.

        with open(TEST_VALID_INI, "r") as test_ini:
            normal_cfg = PgbConfig(test_ini.read())

            # Test parsing fails without necessary config file values
            del normal_cfg["databases"]
            with pytest.raises(PgbConfig.ConfigParsingError):
                normal_cfg.validate()

        with open(f"{DATA_DIR}/test_no_logfile.ini", "r") as no_logfile:
            with pytest.raises(PgbConfig.ConfigParsingError):
                PgbConfig(no_logfile.read())

        with open(f"{DATA_DIR}/test_no_pidfile.ini", "r") as no_pidfile:
            with pytest.raises(PgbConfig.ConfigParsingError):
                PgbConfig(no_pidfile.read())

        # Test parsing fails when database names are malformed
        with open(f"{DATA_DIR}/test_bad_db.ini", "r") as bad_db:
            with pytest.raises(PgbConfig.ConfigParsingError):
                PgbConfig(bad_db.read())

        with open(f"{DATA_DIR}/test_bad_dbname.ini", "r") as bad_dbname:
            with pytest.raises(PgbConfig.ConfigParsingError):
                PgbConfig(bad_dbname.read())

        with open(f"{DATA_DIR}/test_reserved_db.ini", "r") as reserved_db:
            with pytest.raises(PgbConfig.ConfigParsingError):
                PgbConfig(reserved_db.read())

    def test_pgb_config_validate_dbname(self):
        config = PgbConfig()
        # Valid dbnames include alphanumeric characters and -_ characters. Everything else must
        # be wrapped in double quotes.
        good_dbnames = ["test-_1", 'test"%$"1', 'multiple"$"bad"^"values', '" "', '"\n"', '""']
        for dbname in good_dbnames:
            config._validate_dbname(dbname)

        bad_dbnames = ['"', "%", " ", '"$"test"', "\n"]
        for dbname in bad_dbnames:
            with pytest.raises(PgbConfig.ConfigParsingError):
                config._validate_dbname(dbname)

    def test_set_max_db_connection_derivatives(self):
        cfg = PgbConfig(DEFAULT_CONFIG)

        # Test setting 0 instances fails to update config
        with pytest.raises(PgbConfig.ConfigParsingError):
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

    def test_add_user(self):
        cfg = PgbConfig(DEFAULT_CONFIG)
        cfg.add_user(
            user="max-test",
            admin=True,
            stats=True,
        )
        assert cfg[PGB].get("admin_users") == {"max-test"}
        assert cfg[PGB].get("stats_users") == {"max-test"}

        # Test we can't duplicate users
        cfg.add_user(user="max-test", admin=True, stats=True)
        assert cfg[PGB].get("admin_users") == {"max-test"}
        assert cfg[PGB].get("stats_users") == {"max-test"}

    def test_remove_user(self):
        user = "test_user"
        cfg = PgbConfig(DEFAULT_CONFIG)
        cfg.add_user(user, admin=True, stats=True)
        # convert to set, so we aren't just comparing two pointers to the same thing.
        admin_users = set(cfg[PGB]["admin_users"])
        stats_users = set(cfg[PGB]["stats_users"])

        # try to remove user that doesn't exist
        cfg.remove_user("nonexistent-user")
        assert cfg[PGB]["admin_users"] == admin_users
        assert cfg[PGB]["stats_users"] == stats_users

        # remove user that does exist
        cfg.remove_user(user)
        assert user not in cfg[PGB]["admin_users"]
        assert user not in cfg[PGB]["stats_users"]
