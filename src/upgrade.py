# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Manager for handling Pgbouncer in-place upgrades."""

import json
import logging

from charms.data_platform_libs.v0.upgrade import (
    DataUpgrade,
    DependencyModel,
)
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

    def __init__(self, charm, **kwargs):
        super().__init__(charm, **kwargs)
        self.charm = charm

    @override
    def pre_upgrade_check(self) -> None:
        """Runs necessary checks validating the cluster is in a healthy state to upgrade.
        Called by all units during :meth:`_on_pre_upgrade_check_action`.
        Raises:
            :class:`ClusterNotReadyError`: if cluster is not ready to upgrade
        """
