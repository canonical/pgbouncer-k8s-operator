# Copyright 2023 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""PgBouncer Charm Library.

This charm library provides common pgbouncer-specific features for the pgbouncer machine and
Kubernetes charms, including automatic config management using the PgbConfig object, and the
default config for pgbouncer.

"""

import logging
import secrets
import string
from hashlib import md5
from typing import Dict

from psycopg2 import extensions

# The unique Charmhub library identifier, never change it
LIBID = "113f4a7480c04631bfdf5fe776f760cd"
# Increment this major API version when introducing breaking changes
LIBAPI = 0
# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 11

logger = logging.getLogger(__name__)

PGB = "pgbouncer"
PGB_DIR = "/var/lib/postgresql/pgbouncer"
INI_PATH = f"{PGB_DIR}/pgbouncer.ini"


def parse_kv_string_to_dict(string: str) -> Dict[str, str]:
    """Parses space-separated key=value pairs into a python dict.

    TODO this could make use of pgconnstr, but that requires that this charm lib has a dependency.

    Args:
        string: a string containing a set of key=value pairs, joined with = characters and
            separated with spaces
    Returns:
        A dict containing the key-value pairs represented as strings.
    """
    parsed_dict = {}
    for kv_pair in string.split(" "):
        key, value = kv_pair.split("=")
        parsed_dict[key] = value
    return parsed_dict


def parse_dict_to_kv_string(dictionary: Dict[str, str]) -> str:
    """Helper function to encode a python dict into a pgbouncer-readable string.

    TODO this could make use of pgconnstr, but that requires that this charm lib has a dependency.

    Args:
        dictionary: A dict containing the key-value pairs represented as strings.
    Returns: a string containing a set of key=value pairs, joined with = characters and
            separated with spaces
    """
    return " ".join([f"{key}={value}" for key, value in dictionary.items()])


def generate_password() -> str:
    """Generates a secure password of alphanumeric characters.

    Passwords are alphanumeric only, to ensure compatibility with the userlist.txt format -
    specifically, spaces and double quotes may interfere with parsing this file.

    Returns:
        A random 24-character string of letters and numbers.
    """
    choices = string.ascii_letters + string.digits
    return "".join([secrets.choice(choices) for _ in range(24)])


def get_md5_password(username: str, password: str) -> str:
    """Creates an md5 hashed password for the given user, in the format postgresql expects."""
    # Should be handled in DPE-1430
    return f"md5{md5((password + username).encode()).hexdigest()}"  # noqa: S324


def get_scram_password(username: str, password: str, connection) -> str:
    """Creates an SCRAM SHA 256 hashed password for the given user, in the format postgresql expects."""
    return extensions.encrypt_password(password, username, connection, "scram-sha-256")
