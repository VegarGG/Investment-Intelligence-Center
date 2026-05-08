from __future__ import annotations

import os
import time

import pytest

import featureflags
from featureflags import flag, flag_value, list_flags, register, set_for_test, with_flag


def test_unregistered_flag_is_false(_isolated_flags):
    assert flag("nonexistent.flag") is False


def test_registered_flag_default(_isolated_flags):
    register(
        name="t.alpha",
        description="example",
        added_in="v2.5-T0.1",
        default=False,
        owner="platform",
    )
    assert flag("t.alpha") is False


def test_yaml_overrides_default(_isolated_flags):
    register(name="t.alpha", description="x", added_in="v2.5", default=False, owner="x")
    _isolated_flags.write_text("t.alpha: true\n")
    assert flag("t.alpha") is True


def test_yaml_hot_reload_within_2s(_isolated_flags):
    register(name="t.alpha", description="x", added_in="v2.5", default=False, owner="x")
    _isolated_flags.write_text("t.alpha: false\n")
    assert flag("t.alpha") is False
    # Simulate the YAML being edited.
    time.sleep(0.05)
    _isolated_flags.write_text("t.alpha: true\n")
    # Bump mtime explicitly (filesystem may have 1 s resolution on some hosts).
    new_mtime = _isolated_flags.stat().st_mtime + 1
    os.utime(_isolated_flags, (new_mtime, new_mtime))
    assert flag("t.alpha") is True


def test_flag_value_typed_default(_isolated_flags):
    register(
        name="t.throttle_per_min",
        description="rate cap",
        added_in="v2.5",
        default=12,
        owner="x",
    )
    assert flag_value("t.throttle_per_min", 0) == 12
    _isolated_flags.write_text("t.throttle_per_min: 30\n")
    assert flag_value("t.throttle_per_min", 0) == 30


def test_set_for_test_overrides_yaml(_isolated_flags):
    register(name="t.alpha", description="x", added_in="v2.5", default=False, owner="x")
    _isolated_flags.write_text("t.alpha: false\n")
    set_for_test("t.alpha", True)
    assert flag("t.alpha") is True


def test_list_flags_snapshot(_isolated_flags):
    register(name="t.alpha", description="A", added_in="v2.5", default=False, owner="x")
    register(name="t.bravo", description="B", added_in="v2.5", default=True, owner="x")
    _isolated_flags.write_text("t.alpha: true\n")
    snap = list_flags()
    by_name = {row["name"]: row for row in snap}
    assert by_name["t.alpha"]["current"] is True
    assert by_name["t.bravo"]["current"] is True
    assert by_name["t.alpha"]["default"] is False


@pytest.mark.asyncio
async def test_with_flag_yields_current_value(_isolated_flags):
    register(name="t.alpha", description="x", added_in="v2.5", default=False, owner="x")
    set_for_test("t.alpha", True)
    async with with_flag("t.alpha") as on:
        assert on is True


def test_v25_canonical_flags_loaded():
    """Re-importing the registry must populate the well-known v2.5 flag names.

    The conftest fixture clears `_REGISTRY` between tests, so we re-execute
    `registry.py`'s body via `importlib.reload` to confirm the side-effecting
    imports actually register flags (rather than relying on Python's import
    cache to silently do the work).
    """
    import importlib

    import featureflags.registry as registry

    importlib.reload(registry)

    by_name = {row["name"] for row in featureflags.list_flags()}
    for name in (
        "iic.featureflags.bootstrap",
        "persona.live_mark.enabled",
        "orchestrator.agent_breaker.enabled",
        "trading_room.event_triage.enabled",
        "trading_room.investment_board.enabled",
        "agent_futu.enabled",
    ):
        assert name in by_name, f"v2.5 canonical flag {name!r} missing"
