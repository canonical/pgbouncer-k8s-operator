#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Application charm that connects to database charms.

This charm is meant to be used only for testing
of the libraries in this repository.
"""

import json
import logging

import psycopg2
from charms.data_platform_libs.v0.database_requires import (
    DatabaseCreatedEvent,
    DatabaseEndpointsChangedEvent,
    DatabaseRequires,
)
from ops.charm import ActionEvent, CharmBase
from ops.main import main
from ops.model import ActiveStatus

logger = logging.getLogger(__name__)

# Extra roles that this application needs when interacting with the database.
EXTRA_USER_ROLES = "CREATEDB,CREATEROLE"


class ApplicationCharm(CharmBase):
    """Application charm that connects to database charms."""

    def __init__(self, *args):
        super().__init__(*args)

        # Default charm events.
        self.framework.observe(self.on.start, self._on_start)

        # Events related to the first database that is requested
        # (these events are defined in the database requires charm library).
        database_name = f'{self.app.name.replace("-", "_")}_first_database'
        self.first_database = DatabaseRequires(
            self, "first-database", database_name, EXTRA_USER_ROLES
        )
        self.framework.observe(
            self.first_database.on.database_created, self._on_first_database_created
        )
        self.framework.observe(
            self.first_database.on.endpoints_changed, self._on_first_database_endpoints_changed
        )

        # Events related to the second database that is requested
        # (these events are defined in the database requires charm library).
        database_name = f'{self.app.name.replace("-", "_")}_second_database'
        self.second_database = DatabaseRequires(
            self, "second-database", database_name, EXTRA_USER_ROLES
        )
        self.framework.observe(
            self.second_database.on.database_created, self._on_second_database_created
        )
        self.framework.observe(
            self.second_database.on.endpoints_changed, self._on_second_database_endpoints_changed
        )

        # Multiple database clusters charm events (clusters/relations without alias).
        database_name = f'{self.app.name.replace("-", "_")}_multiple_database_clusters'
        self.database_clusters = DatabaseRequires(
            self, "multiple-database-clusters", database_name, EXTRA_USER_ROLES
        )
        self.framework.observe(
            self.database_clusters.on.database_created, self._on_cluster_database_created
        )
        self.framework.observe(
            self.database_clusters.on.endpoints_changed,
            self._on_cluster_endpoints_changed,
        )

        self.framework.observe(self.on.run_sql_action, self._on_run_sql_action)

    def _on_start(self, _) -> None:
        """Only sets an Active status."""
        self.unit.status = ActiveStatus()

    # First database events observers.
    def _on_first_database_created(self, event: DatabaseCreatedEvent) -> None:
        """Event triggered when a database was created for this application."""
        # Retrieve the credentials using the charm library.
        logger.info(f"first database credentials: {event.username} {event.password}")
        self.unit.status = ActiveStatus("received database credentials of the first database")

    def _on_first_database_endpoints_changed(self, event: DatabaseEndpointsChangedEvent) -> None:
        """Event triggered when the read/write endpoints of the database change."""
        logger.info(f"first database endpoints have been changed to: {event.endpoints}")

    # Second database events observers.
    def _on_second_database_created(self, event: DatabaseCreatedEvent) -> None:
        """Event triggered when a database was created for this application."""
        # Retrieve the credentials using the charm library.
        logger.info(f"second database credentials: {event.username} {event.password}")
        self.unit.status = ActiveStatus("received database credentials of the second database")

    def _on_second_database_endpoints_changed(self, event: DatabaseEndpointsChangedEvent) -> None:
        """Event triggered when the read/write endpoints of the database change."""
        logger.info(f"second database endpoints have been changed to: {event.endpoints}")

    # Multiple database clusters events observers.
    def _on_cluster_database_created(self, event: DatabaseCreatedEvent) -> None:
        """Event triggered when a database was created for this application."""
        # Retrieve the credentials using the charm library.
        logger.info(
            f"cluster {event.relation.app.name} credentials: {event.username} {event.password}"
        )
        self.unit.status = ActiveStatus(
            f"received database credentials for cluster {event.relation.app.name}"
        )

    def _on_cluster_endpoints_changed(self, event: DatabaseEndpointsChangedEvent) -> None:
        """Event triggered when the read/write endpoints of the database change."""
        logger.info(
            f"cluster {event.relation.app.name} endpoints have been changed to: {event.endpoints}"
        )

    def _on_run_sql_action(self, event: ActionEvent):
        relation_id = event.params["relation-id"]
        databag = self.first_database.fetch_relation_data()[relation_id]

        dbname = event.params["dbname"]
        query = event.params["query"]
        user = databag.get("username")
        password = databag.get("password")
        if event.params["readonly"]:
            host = databag.get("read-only-endpoints").split(",")[0]
            dbname = f"{dbname}_readonly"
        else:
            host = databag.get("endpoints").split(",")[0]
        endpoint = host.split(":")[0]
        port = host.split(":")[1]

        logger.error(f"running query: \n{query}")

        connection = self.connect_to_database(
            database=dbname, user=user, password=password, host=endpoint, port=port
        )
        cursor = connection.cursor()
        cursor.execute(query)

        try:
            results = cursor.fetchall()
        except psycopg2.Error as error:
            results = [str(error)]
        logger.error(results)

        event.set_results({"results": json.dumps(results)})

    def connect_to_database(
        self, host: str, port: str, database: str, user: str, password: str
    ) -> psycopg2.extensions.connection:
        """Creates a psycopg2 connection object to the database, with autocommit enabled.

        Args:
            host: network host for the database
            port: port on which to access the database
            database: database to connect to
            user: user to use to connect to the database
            password: password for the given user

        Returns:
            psycopg2 connection object using the provided data
        """
        connstr = f"dbname='{database}' user='{user}' host='{host}' port='{port}' password='{password}' connect_timeout=1"
        logger.debug(f"connecting to database: \n{connstr}")
        connection = psycopg2.connect(connstr)
        connection.autocommit = True
        return connection


if __name__ == "__main__":
    main(ApplicationCharm)
