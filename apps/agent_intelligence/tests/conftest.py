"""Shared fixtures: stub LLM router so unit tests don't reach DeepSeek."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from llm_client import (
    ChatMessage,
    ChatResponse,
    EmbedResponse,
    LlmTier,
    set_router,
)


class StubAdapter:
    name = "stub"

    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self._responses = responses or {}

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tier: LlmTier,
        max_tokens: int,
        temperature: float,
        timeout_s: float,
    ) -> ChatResponse:
        last = messages[-1].content if messages else ""
        text = self._responses.get(last, _default_for(messages))
        return ChatResponse(
            text=text,
            model="stub",
            tier=tier,
            prompt_tokens=10,
            completion_tokens=20,
            cost_usd=0.0,
            request_id="stub-req",
            latency_ms=1,
        )

    async def embed(self, texts: list[str], *, timeout_s: float) -> EmbedResponse:
        return EmbedResponse(
            vectors=[[0.0] * 8 for _ in texts],
            model="stub-embed",
            cost_usd=0.0,
            request_id="stub-embed",
        )


def _default_for(messages: list[ChatMessage]) -> str:
    """Heuristic default — returns a synth-shaped JSON when the prompt mentions
    'synthesizer' or 'digest'; otherwise returns a one-line translation."""
    text = " ".join(m.content for m in messages)
    if "macro thesis" in text.lower() or "candidate event" in text.lower():
        return (
            '{"id":"01HX0000000000000000000000",'
            '"issued_at":"2026-01-01T00:00:00Z",'
            '"macro_regime":"unknown",'
            '"macro_thesis":"Stub thesis.",'
            '"events":[],'
            '"bias_balance":{"by_region":{},"by_lean":{}}}'
        )
    if "translate" in text.lower():
        return "Translated headline\nTranslated body."
    return "Stub response."


class _StubRouter:
    """Minimal LlmRouter shape — bypasses cache/cost/rate gates so tests
    don't need Redis."""

    def __init__(self, adapter: StubAdapter) -> None:
        self._adapter = adapter

    async def chat(
        self,
        caller_id: str,
        messages: list[ChatMessage],
        *,
        force_tier: LlmTier | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.4,
        timeout_s: float = 30.0,
    ) -> ChatResponse:
        return await self._adapter.chat(
            messages,
            tier=force_tier or "flash",
            max_tokens=max_tokens,
            temperature=temperature,
            timeout_s=timeout_s,
        )

    async def embed(self, caller_id: str, texts: list[str]) -> EmbedResponse:
        return await self._adapter.embed(texts, timeout_s=30.0)


@pytest.fixture(autouse=True)
def stub_llm() -> Iterator[None]:
    set_router(_StubRouter(StubAdapter()))  # type: ignore[arg-type]
    try:
        yield
    finally:
        set_router(None)
