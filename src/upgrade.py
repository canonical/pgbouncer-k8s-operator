# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Manager for handling Pgbouncer in-place upgrades."""

import json
import logging

from charms.data_platform_libs.v0.upgrade import (
    ClusterNotReadyError,
    DataUpgrade,
    DependencyModel,
    KubernetesClientError,
)
from lightkube.core.client import Client
from lightkube.core.exceptions import ApiError
from lightkube.resources.apps_v1 import StatefulSet
from ops.charm import WorkloadEvent
from ops.pebble import ConnectionError as PebbleConnectionError
from pydantic import BaseModel
from typing_extensions import override

from constants import (
    APP_SCOPE,
    AUTH_FILE_DATABAG_KEY,
    CLIENT_RELATION_NAME,
    MONITORING_PASSWORD_KEY,
)

DEFAULT_MESSAGE = "Pre-upgrade check failed and cannot safely upgrade"

logger = logging.getLogger(__name__)


class PgbouncerDependencyModel(BaseModel):
    """Model for Pgbouncer Operator dependencies."""

    charm: DependencyModel
    rock: DependencyModel


def get_pgbouncer_k8s_dependencies_model() -> PgbouncerDependencyModel:
    """Return the Pgbouncer dependencies model."""
    with open("src/dependency.json") as dependency_file:
        _deps = json.load(dependency_file)
    return PgbouncerDependencyModel(**_deps)


class PgbouncerUpgrade(DataUpgrade):
    """Implementation of :class:`DataUpgrade` overrides for in-place upgrades."""

    def __init__(self, charm, model: BaseModel, **kwargs):
        super().__init__(charm, model, **kwargs)
        self.charm = charm

        self.framework.observe(self.charm.on.upgrade_relation_changed, self._on_upgrade_changed)
        self.framework.observe(
            self.charm.on.pgbouncer_pebble_ready, self._on_pgbouncer_pebble_ready
        )

    def _cluster_checks(self) -> None:
        """Check that the cluster is in healthy state."""
        try:
            if not self.charm.check_pgb_running():
                raise ClusterNotReadyError(
                    DEFAULT_MESSAGE, "Not all pgbouncer services are up yet."
                )
        except PebbleConnectionError as e:
            raise ClusterNotReadyError(
                DEFAULT_MESSAGE, "Not all pgbouncer services are missing."
            ) from e

        if self.charm.backend.postgres and not self.charm.backend.ready:
            raise ClusterNotReadyError(DEFAULT_MESSAGE, "Backend relation is still initialising.")

    @override
    def pre_upgrade_check(self) -> None:
        """Runs necessary checks validating the cluster is in a healthy state to upgrade.

        Called by all units during :meth:`_on_pre_upgrade_check_action`.

        Raises:
            :class:`ClusterNotReadyError`: if cluster is not ready to upgrade.
        """
        self._cluster_checks()

        try:
            self._set_rolling_update_partition(self.charm.app.planned_units() - 1)
        except KubernetesClientError as e:
            raise ClusterNotReadyError(e.message, e.cause) from e

    def _handle_md5_monitoring_auth(self) -> None:
        if not self.charm.unit.is_leader() or not (
            auth_file := self.charm.get_secret(APP_SCOPE, AUTH_FILE_DATABAG_KEY)
        ):
            return

        monitoring_prefix = f'"{self.charm.backend.stats_user}" "md5'
        # Regenerate monitoring user if it is still md5
        new_auth = []
        for line in auth_file.split("\n"):
            if line.startswith(monitoring_prefix):
                stats_password = self.charm.get_secret(APP_SCOPE, MONITORING_PASSWORD_KEY)
                new_auth.append(f'"{self.charm.backend.stats_user}" "{stats_password}"')
            else:
                new_auth.append(line)
        new_auth_file = "\n".join(new_auth)
        if new_auth_file != auth_file:
            self.charm.set_secret(APP_SCOPE, AUTH_FILE_DATABAG_KEY, new_auth_file)

    def _on_pgbouncer_pebble_ready(self, event: WorkloadEvent) -> None:
        if (
            not self.peer_relation
            or not self.charm.peers.relation
            or self.charm.peers.unit_databag.get("container_initialised") != "True"
        ):
            logger.debug("Deferring on_pebble_ready: no upgrade peer relation yet")
            event.defer()
            return

        if self.state not in ["upgrading", "recovery"]:
            return

        if self.charm.unit.is_leader():
            self.charm.reconcile_k8s_service()
            for relation in self.model.relations.get(CLIENT_RELATION_NAME, []):
                self.charm.client_relation.update_connection_info(relation)
        self._handle_md5_monitoring_auth()

        try:
            self._cluster_checks()
        except ClusterNotReadyError:
            logger.exception("Deferring on_pebble_ready: checks did not pass")
            event.defer()
            return

        self.set_unit_completed()
        self.charm.update_status()

    def _on_upgrade_changed(self, _) -> None:
        """Rerenders the configuration."""
        try:
            if not self.peer_relation or not self.charm.check_pgb_running():
                return
        except PebbleConnectionError:
            logger.debug("on_upgrade_changed early exit: Cannot get pebble services")
            return

        self.charm.update_config()

    @override
    def log_rollback_instructions(self) -> None:
        logger.info(
            "Run `juju refresh --revision <previous-revision> pgbouncer-k8s` to initiate the rollback"
        )
        logger.info(
            "and `juju run-action pgbouncerl-k8s/leader resume-upgrade` to resume the rollback"
        )

    @override
    def _set_rolling_update_partition(self, partition: int) -> None:
        """Set the rolling update partition to a specific value."""
        try:
            patch = {"spec": {"updateStrategy": {"rollingUpdate": {"partition": partition}}}}
            Client().patch(
                StatefulSet,
                name=self.charm.model.app.name,
                namespace=self.charm.model.name,
                obj=patch,
            )
            logger.debug(f"Kubernetes StatefulSet partition set to {partition}")
        except ApiError as e:
            cause = "`juju trust` needed" if e.status.code == 403 else str(e)
            raise KubernetesClientError("Kubernetes StatefulSet patch failed", cause) from e
