"""Cost meter default-state assertions (P0.3).

After P0, ``DEFAULT_MONTHLY_CAP_USD`` is unbounded so a fresh install
never gates calls on cost. The env vars ``LLM_MONTHLY_CAP_USD`` and
``LLM_FALLBACK_CAP_USD`` remain as the one-knob path to tighten back up.
"""

from __future__ import annotations

import importlib
import math

import pytest

from llm_client import cost_meter


def _reload(monkeypatch, env: dict[str, str]) -> None:
    for key in ("LLM_MONTHLY_CAP_USD", "LLM_FALLBACK_CAP_USD"):
        monkeypatch.delenv(key, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(cost_meter)


def test_default_cap_unbounded(monkeypatch):
    _reload(monkeypatch, {})
    assert math.isinf(cost_meter.DEFAULT_MONTHLY_CAP_USD)
    assert math.isinf(cost_meter.DEFAULT_FALLBACK_CAP_USD)


def test_env_overrides_monthly_cap(monkeypatch):
    _reload(monkeypatch, {"LLM_MONTHLY_CAP_USD": "12.5"})
    assert cost_meter.DEFAULT_MONTHLY_CAP_USD == pytest.approx(12.5)


def test_env_overrides_fallback_cap(monkeypatch):
    _reload(monkeypatch, {"LLM_FALLBACK_CAP_USD": "3.5"})
    assert cost_meter.DEFAULT_FALLBACK_CAP_USD == pytest.approx(3.5)


def test_invalid_env_falls_back_to_inf(monkeypatch):
    _reload(monkeypatch, {"LLM_MONTHLY_CAP_USD": "not-a-number"})
    assert math.isinf(cost_meter.DEFAULT_MONTHLY_CAP_USD)
