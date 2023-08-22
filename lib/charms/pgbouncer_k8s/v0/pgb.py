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

import io
import logging
import math
import re
import secrets
import string
from collections.abc import MutableMapping
from configparser import ConfigParser, ParsingError
from copy import deepcopy
from hashlib import md5
from typing import Dict, Union

# The unique Charmhub library identifier, never change it
LIBID = "113f4a7480c04631bfdf5fe776f760cd"
# Increment this major API version when introducing breaking changes
LIBAPI = 0
# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 8

logger = logging.getLogger(__name__)

PGB = "pgbouncer"
PGB_DIR = "/var/lib/postgresql/pgbouncer"
INI_PATH = f"{PGB_DIR}/pgbouncer.ini"

DEFAULT_CONFIG = {
    "databases": {},
    "pgbouncer": {
        "listen_addr": "*",
        "listen_port": 6432,
        "logfile": f"{PGB_DIR}/pgbouncer.log",
        "pidfile": f"{PGB_DIR}/pgbouncer.pid",
        "admin_users": set(),
        "stats_users": set(),
        "auth_type": "md5",
        "user": "postgres",
        "max_client_conn": "10000",
        "ignore_startup_parameters": "extra_float_digits,options",
        "server_tls_sslmode": "prefer",
        "so_reuseport": "1",
        "unix_socket_dir": PGB_DIR,
    },
}


class PgbConfig(MutableMapping):
    """A mapping that represents the pgbouncer config.

    The PgbConfig class provides an abstraction for the pgbouncer.ini config file. This file
    essentially governs how each instance of pgbouncer operates, including the connection
    information for each database, user authentication, local file management, and how connections
    are pooled in detail. This config also contains a `validate` function that allows a user to
    verify their changes will result in a valid pgbouncer config, and a `render` function to render
    this object out to a string.

    This config is implemented as a MutableMapping with a few `dict`-style methods for ease of use.
    Config can be passed to the constructor as a string, a dict (such as the default variable
    DEFAULT_CONFIG), or another PgbConfig object.

    For more pgbouncer config documentation, visit: https://www.pgbouncer.org/config.html

    The following is an example of a pgbouncer.ini config file output by PgbConfig.render(), taken
    from a test deployment:
    [databases]
    discourse-k8s = host=postgresql-k8s-primary.test-db-admin-ipve.svc.cluster.local dbname=discourse-k8s port=5432
    discourse-k8s_standby = host=postgresql-k8s-replicas.test-db-admin-ipve.svc.cluster.local dbname=discourse-k8s port=5432
    discourse-charmers-discourse-k8s = host=postgresql-k8s-primary.test-db-admin-ipve.svc.cluster.local dbname=discourse-charmers-discourse-k8s port=5432
    discourse-charmers-discourse-k8s_standby = host=postgresql-k8s-replicas.test-db-admin-ipve.svc.cluster.local dbname=discourse-charmers-discourse-k8s port=5432

    [pgbouncer]
    listen_addr = *
    listen_port = 6432
    logfile = /var/lib/postgresql/pgbouncer/pgbouncer.log
    pidfile = /var/lib/postgresql/pgbouncer/pgbouncer.pid
    admin_users = relation_1,pgbouncer_k8s_user_2_test_db_admin_ipve,pgbouncer_k8s_user_4_test_db_admin_ipve
    stats_users =
    auth_type = md5
    user = postgres
    max_client_conn = 10000
    ignore_startup_parameters = extra_float_digits,options
    server_tls_sslmode = prefer
    so_reuseport = 1
    unix_socket_dir = /var/lib/postgresql/pgbouncer
    pool_mode = session
    max_db_connections = 100
    default_pool_size = 13
    min_pool_size = 7
    reserve_pool_size = 7
    auth_user = pgbouncer_auth_relation_1
    auth_query = SELECT username, password FROM pgbouncer_auth_relation_1.get_auth($1)

    """  # noqa: W505

    # Define names of ini sections:
    # [databases] defines the config options for each database. This section is mandatory.
    # [pgbouncer] defines pgbouncer-specific config
    # [users] defines config for specific users.
    db_section = "databases"
    pgb_section = "pgbouncer"
    users_section = "users"
    user_types = ["admin_users", "stats_users"]

    def __init__(
        self,
        config: Union[str, dict, "PgbConfig"] = None,
        *args,
        **kwargs,
    ):
        """Constructor.

        Args:
            config: an existing config. Can be passed in as a string, dict, or PgbConfig object.
                pgb.DEFAULT_CONFIG can be used here as a default dict.
            args: arguments.
            kwargs: keyword arguments.
        """
        self.__dict__.update(*args, **kwargs)

        if isinstance(config, str):
            self.read_string(config)
        elif isinstance(config, dict):
            self.read_dict(config)
        elif isinstance(config, PgbConfig):
            self.read_dict(dict(config))

    def __delitem__(self, key: str):
        """Deletes item from internal mapping."""
        del self.__dict__[key]

    def __getitem__(self, key: str):
        """Gets item from internal mapping."""
        return self.__dict__[key]

    def __setitem__(self, key: str, value):
        """Set an item in internal mapping."""
        self.__dict__[key] = value

    def __iter__(self):
        """Returns an iterable of internal mapping."""
        return iter(self.__dict__)

    def __len__(self):
        """Gets number of key-value pairs in internal mapping."""
        return len(self.__dict__)

    def __str__(self):
        """String representation of PgbConfig object."""
        return str(self.__dict__)

    def __eq__(self, other_config):
        """Checks if self and other_config are equal."""
        return self.__dict__ == other_config.__dict__

    def keys(self):
        """Returns keys of PgbConfig object."""
        return self.__dict__.keys()

    def items(self):
        """Returns items of PgbConfig object."""
        return self.__dict__.items()

    def read_dict(self, data: Dict) -> None:
        """Populates this object from a dictionary.

        Args:
            data: Dict to be read into this object. This dict must follow the pgbouncer config
                  spec (https://pgbouncer.org/config.html) to pass validation, implementing each
                  section as its own subdict. Lists should be represented as python lists, not
                  comma-separated strings.
        """
        self.update(deepcopy(data))
        self.validate()

    def read_string(self, data: str) -> None:
        """Populates this class from a pgbouncer.ini file, passed in as a string.

        Args:
            data: pgbouncer.ini file to be parsed, represented as a string. This string must
                  follow the pgbouncer config spec (https://pgbouncer.org/config.html)
        """
        # Since the parser persists data across reads, we have to create a new one for every read.
        parser = ConfigParser()
        parser.optionxform = str
        parser.read_string(data)

        self.update(deepcopy(dict(parser)))
        # Convert Section objects to dictionaries, so they can hold dictionaries themselves.
        for section, data in self.items():
            self[section] = dict(data)

        # ConfigParser object creates a DEFAULT section of an .ini file, which we don't need.
        del self["DEFAULT"]

        self._parse_complex_variables()
        self.validate()

    def _parse_complex_variables(self) -> None:
        """Parse complex config variables from string representation into dicts.

        In a pgbouncer.ini file, certain values are represented by more complex data structures,
        which are themselves represented as delimited strings. This method parses these strings
        into more usable python objects.

        Raises:
            PgbConfig.ConfigParsingError: raised when [databases] section is not available
        """
        db = PgbConfig.db_section
        users = PgbConfig.users_section
        pgb = PgbConfig.pgb_section

        try:
            for name, cfg_string in self[db].items():
                self[db][name] = parse_kv_string_to_dict(cfg_string)
        except KeyError as err:
            raise PgbConfig.ConfigParsingError(source=str(err))

        for name, cfg_string in self.get(users, {}).items():
            self[users][name] = parse_kv_string_to_dict(cfg_string)

        for user_type in PgbConfig.user_types:
            users = set(self[pgb].get(user_type, "").split(","))
            if "" in users:
                users.remove("")
            self[pgb][user_type] = users

    def render(self) -> str:
        """Returns a valid pgbouncer.ini file as a string.

        Returns:
            str: a string containing a valid pgbouncer.ini file.
        """
        self.validate()

        # Create a copy of the config with dicts and lists parsed into valid ini strings
        output_dict = deepcopy(dict(self))
        for section, subdict in output_dict.items():
            for option, config_value in subdict.items():
                if isinstance(config_value, dict):
                    output_dict[section][option] = parse_dict_to_kv_string(config_value)
                elif isinstance(config_value, set):
                    output_dict[section][option] = ",".join(config_value)
                else:
                    output_dict[section][option] = str(config_value)

        # Populate parser object with local data.
        parser = ConfigParser()
        parser.optionxform = str
        parser.read_dict(output_dict)

        # ConfigParser can only write to a file, so write to a StringIO object and then read back
        # from it.
        with io.StringIO() as string_io:
            parser.write(string_io)
            string_io.seek(0)
            output = string_io.read()
        return output

    def validate(self):
        """Validates that this object will provide a valid pgbouncer.ini config when rendered.

        Raises:
            PgbConfig.ConfigParsingError:
                - when necessary config sections [databases] and [pgbouncer] are not present.
                - when necessary "logfile" and "pidfile" config values are not present.
        """
        db = self.db_section

        # Ensure the config contains the bare minimum it needs to be valid
        essentials = {
            "databases": [],
            "pgbouncer": ["logfile", "pidfile"],
        }
        if not set(essentials.keys()).issubset(set(self.keys())):
            missing_keys = set(essentials.keys()) - (set(self.keys()))
            raise PgbConfig.ConfigParsingError(
                f"necessary sections not found in config: {missing_keys}"
            )

        if not set(essentials["pgbouncer"]).issubset(set(self["pgbouncer"].keys())):
            missing_config_values = set(essentials["pgbouncer"]) - set(self["pgbouncer"].keys())
            raise PgbConfig.ConfigParsingError(
                f"necessary pgbouncer config values not found in config: {', '.join(missing_config_values)}"
            )

        # Guarantee db names are valid
        for db_id in self[db].keys():
            db_name = self[db][db_id].get("dbname", "")
            self._validate_dbname(db_id)
            self._validate_dbname(db_name)

    def _validate_dbname(self, string: str):
        """Checks string is a valid database name.

        For a database name to be valid, it must contain only alphanumeric characters, hyphens,
        and underscores. Any other invalid character must be in double quotes.

        Args:
            string: the string to be validated
        Raises:
            PgbConfig.ConfigParsingError when database names are invalid. This can occur when
                database names use the reserved "pgbouncer" database name, and when database names
                do not quote invalid characters (anything that isn't alphanumeric, hyphens, or
                underscores).
        """
        # Check dbnames don't use the reserved "pgbouncer" database name
        if string == "pgbouncer":
            raise PgbConfig.ConfigParsingError(source=string)

        # Check dbnames are valid characters (alphanumeric and _- )
        search = re.compile(r"[^A-Za-z0-9-_]+").search
        filtered_string = "".join(filter(search, string))
        if len(filtered_string) == 0:
            # The string only contains the permitted characters
            return

        # Check the contents of the string left after removing valid characters are all enclosed
        # in double quotes.
        quoted_substrings = re.findall(r'"(?:\\.|[^"])*"', filtered_string)
        if "".join(quoted_substrings) == filtered_string:
            # All substrings of invalid characters are properly quoted
            return

        # dbname is invalid, raise parsing error
        raise PgbConfig.ConfigParsingError(source=filtered_string)

    def set_max_db_connection_derivatives(
        self, max_db_connections: int, pgb_instances: int
    ) -> None:
        """Calculates and sets config values from the charm config & deployment state.

        The config values that are set include:
            - default_pool_size
            - min_pool_size
            - reserve_pool_size

        Args:
            max_db_connections: the maximum number of database connections, given by the user in
                the juju config
            pgb_instances: the number of pgbouncer instances, which is equal to the number of CPU
                cores available on the juju unit. Setting this to zero throws an error.
        """
        if pgb_instances < 1:
            raise PgbConfig.ConfigParsingError(source="pgb_instances cannot be less than 1 ")

        pgb = PgbConfig.pgb_section

        self[pgb]["max_db_connections"] = str(max_db_connections)

        if max_db_connections == 0:
            # Values have to be derived differently if max_db_connections is unlimited. These
            # values are set based on the pgbouncer default value for default_pool_size, which is
            # used to create values for min_pool_size and reserve_pool_size according to the same
            # ratio as below.
            self[pgb]["default_pool_size"] = "20"
            self[pgb]["min_pool_size"] = "10"
            self[pgb]["reserve_pool_size"] = "10"
            return

        effective_db_connections = max_db_connections / pgb_instances
        self[pgb]["default_pool_size"] = str(math.ceil(effective_db_connections / 2))
        self[pgb]["min_pool_size"] = str(math.ceil(effective_db_connections / 4))
        self[pgb]["reserve_pool_size"] = str(math.ceil(effective_db_connections / 4))

    def add_user(self, user: str, admin: bool = False, stats: bool = False):
        """Adds a user to the config.

        Args:
            user: the username for the intended user
            admin: whether or not the user has admin permissions
            stats: whether or not the user has stats permissions
        """
        admin_users = self[PGB].get("admin_users", set())
        if admin:
            self[PGB]["admin_users"] = admin_users.union({user})

        stats_users = self[PGB].get("stats_users", set())
        if stats:
            self[PGB]["stats_users"] = stats_users.union({user})

    def remove_user(self, user: str):
        """Removes a user from config.

        Args:
            user: the username for the intended user.
        """
        if user in self[PGB].get("admin_users", {}):
            self[PGB]["admin_users"].remove(user)
        if user in self[PGB].get("stats_users", {}):
            self[PGB]["stats_users"].remove(user)

    class ConfigParsingError(ParsingError):
        """Error raised when parsing config fails."""

        pass

    class PgbConfigError(Exception):
        """Generic Pgbouncer config error."""

        pass


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


def get_hashed_password(username: str, password: str) -> str:
    """Creates an md5 hashed password for the given user, in the format postgresql expects."""
    hash_password = md5((password + username).encode()).hexdigest()
    return f"md5{hash_password}"
