#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Constants for the PgBouncer charm."""

PGB = "pgbouncer"
PG = PG_USER = PG_GROUP = "postgres"

PGB_DIR = "/var/lib/pgbouncer"
INI_PATH = f"{PGB_DIR}/pgbouncer.ini"
AUTH_FILE_PATH = f"{PGB_DIR}/userlist.txt"

PEER_RELATION_NAME = "pgb-peers"
BACKEND_RELATION_NAME = "backend-database"
DB_RELATION_NAME = "db"
DB_ADMIN_RELATION_NAME = "db-admin"
CLIENT_RELATION_NAME = "database"

TLS_KEY_FILE = "key.pem"
TLS_CA_FILE = "ca.pem"
TLS_CERT_FILE = "cert.pem"
