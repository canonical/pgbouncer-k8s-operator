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

METRICS_PORT = 9127
PGB_LOG_DIR = "/var/log/pgbouncer"
MONITORING_PASSWORD_KEY = "monitoring_password"
AUTH_FILE_DATABAG_KEY = "auth_file"
CFG_FILE_DATABAG_KEY = "cfg_file"

EXTENSIONS_BLOCKING_MESSAGE = "bad relation request - remote app requested extensions, which are unsupported. Please remove this relation."
CONTAINER_UNAVAILABLE_MESSAGE = "PgBouncer container currently unavailable"

SECRET_LABEL = "secret"
SECRET_INTERNAL_LABEL = "internal-secret"
SECRET_DELETED_LABEL = "None"

APP_SCOPE = "app"
UNIT_SCOPE = "unit"

# TEST
SECRET_KEY_OVERRIDES = {
    "ca": "cauth",
    "monitoring_password": "monitoring-password",
    "auth_file": "auth-file",
}

TRACING_RELATION_NAME = "tracing"
TRACING_PROTOCOL = "otlp_http"
