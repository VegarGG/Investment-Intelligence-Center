"""Groq Llama-3.3-70B — fallback for the Flash tier (workflow 03 §10).

OpenAI-compatible endpoint.
"""

from __future__ import annotations

import time
import uuid

import httpx

from llm_client.adapters.base import Adapter
from llm_client.exceptions import ProviderError, ProviderTimeout
from llm_client.pricing import cost_usd
from llm_client.types import ChatMessage, ChatResponse, EmbedResponse, LlmTier

CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqAdapter(Adapter):
    name = "groq"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._http = http or httpx.AsyncClient(timeout=30.0)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
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
            raise ProviderError("groq adapter does not support embeddings")
        payload = {
            "model": self._model,
            "messages": [m.model_dump() for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        t0 = time.perf_counter()
        try:
            resp = await self._http.post(
                CHAT_URL, json=payload, headers=self._headers(), timeout=timeout_s
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(f"groq timeout after {timeout_s}s") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"groq connection error: {exc}") from exc

        latency_ms = int((time.perf_counter() - t0) * 1000)
        if resp.status_code >= 400:
            raise ProviderError(f"groq {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        prompt_tokens = int(usage.get("prompt_tokens", 0))
        completion_tokens = int(usage.get("completion_tokens", 0))
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
        raise NotImplementedError("groq adapter does not provide embeddings")

    async def health(self) -> bool:
        try:
            r = await self.chat(
                [ChatMessage(role="user", content="ok")],
                tier="flash",
                max_tokens=1,
                temperature=0.0,
                timeout_s=5.0,
            )
            return r.completion_tokens >= 0
        except (ProviderError, ProviderTimeout):
            return False
