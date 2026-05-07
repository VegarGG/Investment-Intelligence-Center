"""Secretary stub LLM router."""

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
        return ChatResponse(
            text="## Morning brief\n\nMacro: rate cut. Calls: AAPL long.",
            model="stub",
            tier=tier,
            prompt_tokens=10,
            completion_tokens=20,
            cost_usd=0.0,
            request_id="stub",
            latency_ms=1,
        )

    async def embed(self, texts: list[str], *, timeout_s: float) -> EmbedResponse:
        return EmbedResponse(
            vectors=[[0.0] * 4 for _ in texts], model="stub", cost_usd=0.0, request_id="stub"
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
    set_router(_Router())  # type: ignore[arg-type]
    try:
        yield
    finally:
        set_router(None)
