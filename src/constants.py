#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Constants for the PgBouncer charm."""

PGB = "pgbouncer"
PG_USER = "postgres"

PGB_DIR = "/var/lib/postgresql/pgbouncer"
INI_PATH = f"{PGB_DIR}/pgbouncer.ini"
AUTH_FILE_PATH = f"{PGB_DIR}/userlist.txt"
LOG_PATH = f"{PGB_DIR}/pgbouncer.log"

PEER_RELATION_NAME = "pgb-peers"
BACKEND_RELATION_NAME = "backend-database"
DB_RELATION_NAME = "db"
DB_ADMIN_RELATION_NAME = "db-admin"
