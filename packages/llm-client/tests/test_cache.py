"""Workflow 03 §9 — prompt cache: deterministic key + cached=True on hit."""

from __future__ import annotations

import pytest
from llm_client.cache import InMemoryCacheStore, PromptCache, cache_key
from llm_client.types import ChatMessage, ChatResponse


def _msgs() -> list[ChatMessage]:
    return [
        ChatMessage(role="system", content="be brief"),
        ChatMessage(role="user", content="translate hello"),
    ]


def _response() -> ChatResponse:
    return ChatResponse(
        text="hola",
        model="deepseek-v4-flash",
        tier="flash",
        prompt_tokens=10,
        completion_tokens=2,
        cost_usd=0.001,
        cached=False,
        fallback_used=False,
        request_id="t",
        latency_ms=50,
    )


class TestCacheKey:
    def test_same_inputs_same_key(self) -> None:
        a = cache_key("intel.crawler.translate", "flash", _msgs())
        b = cache_key("intel.crawler.translate", "flash", _msgs())
        assert a == b

    def test_message_change_changes_key(self) -> None:
        a = cache_key("intel.crawler.translate", "flash", _msgs())
        msgs2 = [
            ChatMessage(role="system", content="be brief"),
            ChatMessage(role="user", content="translate goodbye"),
        ]
        b = cache_key("intel.crawler.translate", "flash", msgs2)
        assert a != b

    def test_caller_change_changes_key(self) -> None:
        a = cache_key("intel.crawler.translate", "flash", _msgs())
        b = cache_key("intel.sentiment.classify", "flash", _msgs())
        assert a != b


class TestPromptCacheRoundTrip:
    @pytest.mark.asyncio
    async def test_miss_then_hit_marks_cached_true(self) -> None:
        cache = PromptCache(InMemoryCacheStore())
        msgs = _msgs()
        miss = await cache.get("intel.crawler.translate", "flash", msgs)
        assert miss is None

        await cache.set("intel.crawler.translate", "flash", msgs, _response(), 60)
        hit = await cache.get("intel.crawler.translate", "flash", msgs)
        assert hit is not None
        assert hit.cached is True
        assert hit.cost_usd == 0.0  # cached responses cost zero
        assert hit.text == "hola"

    @pytest.mark.asyncio
    async def test_different_message_misses(self) -> None:
        cache = PromptCache(InMemoryCacheStore())
        await cache.set("intel.crawler.translate", "flash", _msgs(), _response(), 60)
        other = [ChatMessage(role="user", content="something else")]
        assert await cache.get("intel.crawler.translate", "flash", other) is None
