"""Unit tests for D7.1 §H0.1 — env-driven LlmRouter construction."""

from __future__ import annotations

import pytest

from llm_client import router as router_mod
from llm_client.adapters.anthropic import AnthropicAdapter
from llm_client.adapters.deepseek import DeepSeekAdapter
from llm_client.adapters.groq import GroqAdapter
from llm_client.bootstrap import (
    bootstrap_router_optional,
    bootstrap_router_or_die,
    router_from_env,
)


PROVIDER_ENV_VARS = (
    "DEEPSEEK_API_KEY",
    "ANTHROPIC_API_KEY",
    "GROQ_API_KEY",
    "LAKE_DSN",
)


@pytest.fixture(autouse=True)
def _isolate_provider_env(monkeypatch):
    """Each test starts with no provider keys + no telemetry DSN."""
    for var in PROVIDER_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    yield
    # Reset the module singleton so a leaked router from one test does
    # not influence the next.
    router_mod.set_router(None)


def test_router_from_env_returns_none_without_keys():
    assert router_from_env() is None


def test_bootstrap_or_die_raises_without_keys():
    with pytest.raises(RuntimeError, match="no LLM provider configured"):
        bootstrap_router_or_die("test_agent")


def test_bootstrap_optional_returns_none_without_keys():
    assert bootstrap_router_optional("test_agent") is None


def test_bootstrap_constructs_deepseek_adapter(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-fake-deepseek")
    router = router_from_env()
    assert router is not None
    assert isinstance(router.primary, DeepSeekAdapter)
    # No anthropic / groq keys → fallback chain is empty.
    assert router.fallback.pro_fallback is None
    assert router.fallback.flash_fallback is None


def test_bootstrap_promotes_anthropic_when_no_deepseek(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake-anthropic")
    router = router_from_env()
    assert router is not None
    assert isinstance(router.primary, AnthropicAdapter)
    # Anthropic was promoted to primary; pro_fallback also points at
    # Anthropic for symmetry — fallback chain doesn't fire when primary
    # succeeds, so the duplicate is harmless.
    assert isinstance(router.fallback.pro_fallback, AnthropicAdapter)


def test_bootstrap_promotes_groq_when_no_deepseek_no_anthropic(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "sk-fake-groq")
    router = router_from_env()
    assert router is not None
    assert isinstance(router.primary, GroqAdapter)
    assert isinstance(router.fallback.flash_fallback, GroqAdapter)


def test_bootstrap_wires_full_fallback_chain(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-fake-deepseek")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake-anthropic")
    monkeypatch.setenv("GROQ_API_KEY", "sk-fake-groq")
    router = router_from_env()
    assert router is not None
    assert isinstance(router.primary, DeepSeekAdapter)
    assert isinstance(router.fallback.pro_fallback, AnthropicAdapter)
    assert isinstance(router.fallback.flash_fallback, GroqAdapter)


def test_bootstrap_or_die_installs_module_singleton(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-fake-deepseek")
    router = bootstrap_router_or_die("test_agent")
    # Legacy module-level chat() must reach the same instance.
    assert router_mod.get_router() is router


def test_bootstrap_optional_installs_module_singleton(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-fake-deepseek")
    router = bootstrap_router_optional("test_agent")
    assert router is not None
    assert router_mod.get_router() is router
