"""Anthropic Claude Sonnet 4.6 — fallback for the Pro tier (workflow 03 §10).

⚠️ Anthropic uses `system` as a top-level field, not in messages (workflow 03
   §12.2). Roles are mapped accordingly.
"""

from __future__ import annotations

import time
import uuid

import httpx

from llm_client.adapters.base import Adapter
from llm_client.exceptions import ProviderError, ProviderTimeout
from llm_client.pricing import cost_usd
from llm_client.types import ChatMessage, ChatResponse, EmbedResponse, LlmTier

CHAT_URL = "https://api.anthropic.com/v1/messages"


class AnthropicAdapter(Adapter):
    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "claude-sonnet-4-6",
        anthropic_version: str = "2023-06-01",
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._version = anthropic_version
        self._http = http or httpx.AsyncClient(timeout=30.0)

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": self._version,
            "Content-Type": "application/json",
        }

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tier: LlmTier,
        max_tokens: int,
        temperature: float,
        timeout_s: float,
    ) -> ChatResponse:
        if tier == "embed":
            raise ProviderError("anthropic does not support embeddings")

        # Anthropic: system is top-level, not in messages.
        system_text = "\n\n".join(m.content for m in messages if m.role == "system")
        non_system = [m for m in messages if m.role != "system"]
        payload: dict[str, object] = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in non_system],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_text:
            payload["system"] = system_text

        t0 = time.perf_counter()
        try:
            resp = await self._http.post(
                CHAT_URL, json=payload, headers=self._headers(), timeout=timeout_s
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(f"anthropic timeout after {timeout_s}s") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"anthropic connection error: {exc}") from exc

        latency_ms = int((time.perf_counter() - t0) * 1000)
        if resp.status_code >= 400:
            raise ProviderError(f"anthropic {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        text = "".join(block.get("text", "") for block in data.get("content", []))
        usage = data.get("usage", {})
        prompt_tokens = int(usage.get("input_tokens", 0))
        completion_tokens = int(usage.get("output_tokens", 0))
        return ChatResponse(
            text=text,
            model=self._model,
            tier=tier,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd(self._model, prompt_tokens, completion_tokens),
            cached=False,
            fallback_used=True,
            request_id=data.get("id", str(uuid.uuid4())),
            latency_ms=latency_ms,
        )

    async def embed(self, texts: list[str], *, timeout_s: float) -> EmbedResponse:
        raise NotImplementedError("anthropic adapter does not provide embeddings")

    async def health(self) -> bool:
        try:
            r = await self.chat(
                [ChatMessage(role="user", content="ok")],
                tier="pro",
                max_tokens=1,
                temperature=0.0,
                timeout_s=5.0,
            )
            return r.completion_tokens >= 0
        except (ProviderError, ProviderTimeout):
            return False
