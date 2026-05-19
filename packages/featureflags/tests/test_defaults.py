"""Default-state assertions for canonical IIC flags.

These tests verify that flags ship with the expected defaults out-of-the-box,
so a fresh install does not accidentally enable behaviour that requires
explicit opt-in (P0 in `plan/D7`).
"""

from __future__ import annotations

import importlib

import featureflags


def _reload_registry() -> None:
    import featureflags.registry as registry

    importlib.reload(registry)


def test_cost_breaker_disabled_by_default(_isolated_flags):
    """`cost_breaker.enabled` must default to False (P0.1).

    With the breaker disabled, `LlmRouter.chat_or_skip` delegates to
    `chat_or_raise` and any provider failure surfaces as a real exception
    instead of a `synthetic-skip` placeholder.
    """
    _reload_registry()
    assert featureflags.flag("cost_breaker.enabled") is False


def test_persona_live_mark_default_on(_isolated_flags):
    _reload_registry()
    assert featureflags.flag("persona.live_mark.enabled") is True


def test_agent_breaker_default_on(_isolated_flags):
    _reload_registry()
    assert featureflags.flag("orchestrator.agent_breaker.enabled") is True


def test_event_triage_default_off(_isolated_flags):
    _reload_registry()
    assert featureflags.flag("trading_room.event_triage.enabled") is False
