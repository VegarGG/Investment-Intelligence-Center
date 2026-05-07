"""Typed exceptions for the LLM client (workflow 03 §6, §7, §10)."""

from __future__ import annotations


class LlmClientError(Exception):
    """Base for every typed error raised by llm_client."""


class CostBudgetExceeded(LlmClientError):
    """The monthly spend cap (or fallback cap) is exhausted; the breaker is OPEN."""


class ProviderTimeout(LlmClientError):
    """An adapter call exceeded its timeout."""


class ProviderError(LlmClientError):
    """The provider returned a non-success HTTP status (5xx, 4xx)."""


class DeepSeekDown(ProviderError):
    """DeepSeek-specific failure that triggers the fallback path."""


class NoLLMAvailable(LlmClientError):
    """Both the primary (DeepSeek) and the fallback (Anthropic/Groq) are unhealthy."""


class UnknownCallerId(LlmClientError):
    """Caller ID isn't in the routing matrix — refuse rather than guess."""
