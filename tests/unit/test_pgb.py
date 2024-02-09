# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import string
import unittest

from charms.pgbouncer_k8s.v0 import pgb

DATA_DIR = "tests/unit/data"
TEST_VALID_INI = f"{DATA_DIR}/test.ini"
PGB = "pgbouncer"


class TestPgb(unittest.TestCase):
    def test_generate_password(self):
        pw = pgb.generate_password()
        self.assertEqual(len(pw), 24)
        valid_chars = string.ascii_letters + string.digits
        for char in pw:
            assert char in valid_chars
