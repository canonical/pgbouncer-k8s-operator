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
from pydantic import BaseModel
from typing_extensions import override

logger = logging.getLogger(__name__)


class PgbouncerDependencyModel(BaseModel):
    """Model for Pgbouncer Operator dependencies."""

    charm: DependencyModel
    rock: DependencyModel


def get_pgbouncer_k8s_dependencies_model() -> PgbouncerDependencyModel:
    """Return the PostgreSQL dependencies model."""
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
            getattr(self.charm.on, "pgbouncer_pebble_ready"), self._on_pgbouncer_pebble_ready
        )

    @override
    def pre_upgrade_check(self) -> None:
        """Runs necessary checks validating the cluster is in a healthy state to upgrade.

        Called by all units during :meth:`_on_pre_upgrade_check_action`.

        Raises:
            :class:`ClusterNotReadyError`: if cluster is not ready to upgrade.
        """
        try:
            self._set_rolling_update_partition(self.charm.app.planned_units() - 1)
        except KubernetesClientError as e:
            raise ClusterNotReadyError(e.message, e.cause)

    def _on_pgbouncer_pebble_ready(self, event: WorkloadEvent) -> None:
        if not self.peer_relation:
            logger.debug("Deferring on_pebble_ready: no upgrade peer relation yet")
            event.defer()
            return

        if self.peer_relation.data[self.charm.unit].get("state") != "upgrading":
            return

        if not self.charm.check_pgb_running():
            logger.debug("Deferring on_pebble_ready: services not up yet")
            event.defer()
            return

        self.set_unit_completed()

    def _on_upgrade_changed(self, _) -> None:
        """Update the Patroni nosync tag in the unit if needed."""
        if not self.peer_relation:
            return

        self.charm.update_config()

    @override
    def log_rollback_instructions(self) -> None:
        logger.info(
            "Run `juju refresh --revision <previous-revision> postgresql-k8s` to initiate the rollback"
        )
        logger.info(
            "and `juju run-action postgresql-k8s/leader resume-upgrade` to resume the rollback"
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
            if e.status.code == 403:
                cause = "`juju trust` needed"
            else:
                cause = str(e)
            raise KubernetesClientError("Kubernetes StatefulSet patch failed", cause)
