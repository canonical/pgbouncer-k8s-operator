# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import string
from unittest import TestCase

from charms.pgbouncer_k8s.v0 import pgb


class TestPgb(TestCase):
    def test_parse_kv_string_to_dict(self):
        assert pgb.parse_kv_string_to_dict("test=val another=other") == {
            "test": "val",
            "another": "other",
        }

    def test_parse_dict_to_kv_string(self):
        assert (
            pgb.parse_dict_to_kv_string({
                "test": "val",
                "another": "other",
            })
            == "test=val another=other"
        )

    def test_generate_password(self):
        pw = pgb.generate_password()
        self.assertEqual(len(pw), 24)
        valid_chars = string.ascii_letters + string.digits
        for char in pw:
            assert char in valid_chars

    # @patch("charms.pgbouncer_k8s.v0.pgb.md5")
    # def test_get_hashed_password(self, _md5):
    #     hexdigest = _md5.return_value.hexdigest
    #     hexdigest.return_value = "hashval"
    #     assert pgb.get_hashed_password("user", "pass") == "md5hashval"
    #     _md5.assert_called_once_with(b"passuser")
    #     hexdigest.assert_called_once_with()
