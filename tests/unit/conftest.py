# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import pytest
from charms.tempo_coordinator_k8s.v0.charm_tracing import charm_tracing_disabled


@pytest.fixture(autouse=True)
def disable_charm_tracing():
    with charm_tracing_disabled():
        yield
