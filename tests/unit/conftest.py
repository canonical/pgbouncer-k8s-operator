# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import pytest
from charms.tempo_k8s.v1.charm_tracing import charm_tracing_disabled


@pytest.fixture(autouse=True)
def disable_charm_tracing():
    with charm_tracing_disabled():
        yield
