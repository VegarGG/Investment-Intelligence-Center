"""Stub LLM router for fundamental agent tests."""

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

_FIXED_RESPONSES: dict[str, str] = {}


def set_response(prompt_substring: str, text: str) -> None:
    _FIXED_RESPONSES[prompt_substring] = text


class _Adapter:
    name = "stub"

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tier: LlmTier,
        max_tokens: int,
        temperature: float,
        timeout_s: float,
    ) -> ChatResponse:
        joined = " ".join(m.content for m in messages)
        for needle, text in _FIXED_RESPONSES.items():
            if needle in joined:
                return _resp(text, tier)
        return _resp(
            "Default fundamental thesis. Trades at 18x earnings vs sector 14x [ref:filing].",
            tier,
        )

    async def embed(self, texts: list[str], *, timeout_s: float) -> EmbedResponse:
        return EmbedResponse(
            vectors=[[0.0] * 8 for _ in texts],
            model="stub-embed",
            cost_usd=0.0,
            request_id="stub",
        )


def _resp(text: str, tier: LlmTier) -> ChatResponse:
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


class _Router:
    def __init__(self) -> None:
        self._adapter = _Adapter()

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
            tier=force_tier or "pro",
            max_tokens=max_tokens,
            temperature=temperature,
            timeout_s=timeout_s,
        )

    async def embed(self, caller_id: str, texts: list[str]) -> EmbedResponse:
        return await self._adapter.embed(texts, timeout_s=30.0)


@pytest.fixture(autouse=True)
def stub_llm() -> Iterator[None]:
    _FIXED_RESPONSES.clear()
    set_router(_Router())  # type: ignore[arg-type]
    try:
        yield
    finally:
        set_router(None)
