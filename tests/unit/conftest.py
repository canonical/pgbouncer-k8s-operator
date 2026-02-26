# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import pytest


@pytest.fixture(autouse=True)
def lightkube_patch(monkeypatch):
    monkeypatch.setattr("lightkube.Client", lambda *_, **__: None)
