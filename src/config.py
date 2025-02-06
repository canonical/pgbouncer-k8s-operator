#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Structured configuration for the PostgreSQL charm."""

import enum
import logging
from typing import Literal

from charms.data_platform_libs.v0.data_models import BaseConfigModel
from pydantic import PositiveInt, conint

logger = logging.getLogger(__name__)


class ServiceType(enum.Enum):
    """Supported K8s service types."""

    ClusterIP = "false"
    NodePort = "nodeport"
    LoadBalancer = "loadbalancer"


class CharmConfig(BaseConfigModel):
    """Manager for the structured configuration."""

    listen_port: PositiveInt
    pool_mode: Literal["session", "transaction", "statement"]
    max_db_connections: conint(ge=0)
    expose_external: ServiceType
    loadbalancer_extra_annotations: str
