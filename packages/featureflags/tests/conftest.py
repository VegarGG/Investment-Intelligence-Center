from __future__ import annotations

import os

import pytest

from featureflags import core, reset_for_test


@pytest.fixture(autouse=True)
def _isolated_flags(tmp_path, monkeypatch):
    """Each test gets a private flags.yaml + cleared registry/overrides."""
    flags_path = tmp_path / "flags.yaml"
    monkeypatch.setenv("IIC_FEATUREFLAGS_PATH", str(flags_path))

    # Reset module-level state between tests.
    saved_registry = dict(core._REGISTRY)
    core._REGISTRY.clear()
    core._CACHE.mtime = -1.0
    core._CACHE.values = {}
    reset_for_test()
    try:
        yield flags_path
    finally:
        core._REGISTRY.clear()
        core._REGISTRY.update(saved_registry)
        core._CACHE.mtime = -1.0
        core._CACHE.values = {}
        reset_for_test()
        os.environ.pop("IIC_FEATUREFLAGS_PATH", None)
