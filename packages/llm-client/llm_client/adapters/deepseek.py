"""DeepSeek v4 adapter — primary provider for both Pro and Flash tiers.

Uses the OpenAI-compatible endpoint (POST /v1/chat/completions). Streaming
is OFF by default (workflow 03 §12.2). Token counts come from the response
`usage` block, not local estimation.
"""

from __future__ import annotations

import time
import uuid

import httpx

from llm_client.adapters.base import Adapter
from llm_client.exceptions import DeepSeekDown, ProviderError, ProviderTimeout
from llm_client.pricing import cost_usd
from llm_client.types import ChatMessage, ChatResponse, EmbedResponse, LlmTier

CHAT_PATH = "/v1/chat/completions"
EMBED_PATH = "/v1/embeddings"


class DeepSeekAdapter(Adapter):
    name = "deepseek"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model_pro: str = "deepseek-v4-pro",
        model_flash: str = "deepseek-v4-flash",
        embed_model: str = "deepseek-bge-m3",
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._base = base_url.rstrip("/")
        self._model_pro = model_pro
        self._model_flash = model_flash
        self._embed_model = embed_model
        self._http = http or httpx.AsyncClient(timeout=30.0)

    def _model_for(self, tier: LlmTier) -> str:
        if tier == "pro":
            return self._model_pro
        if tier == "flash":
            return self._model_flash
        return self._embed_model

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
            raise ProviderError("embed tier does not support chat()")
        model = self._model_for(tier)
        payload = {
            "model": model,
            "messages": [m.model_dump() for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        t0 = time.perf_counter()
        try:
            resp = await self._http.post(
                f"{self._base}{CHAT_PATH}",
                json=payload,
                headers=self._headers(),
                timeout=timeout_s,
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(f"deepseek timeout after {timeout_s}s") from exc
        except httpx.HTTPError as exc:
            raise DeepSeekDown(f"deepseek connection error: {exc}") from exc

        latency_ms = int((time.perf_counter() - t0) * 1000)
        if resp.status_code >= 500:
            raise DeepSeekDown(f"deepseek 5xx: {resp.status_code} {resp.text[:200]}")
        if resp.status_code >= 400:
            raise ProviderError(f"deepseek {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        choice = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        prompt_tokens = int(usage.get("prompt_tokens", 0))
        completion_tokens = int(usage.get("completion_tokens", 0))
        return ChatResponse(
            text=choice,
            model=model,
            tier=tier,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd(model, prompt_tokens, completion_tokens),
            cached=False,
            fallback_used=False,
            request_id=data.get("id", str(uuid.uuid4())),
            latency_ms=latency_ms,
        )

    async def embed(self, texts: list[str], *, timeout_s: float) -> EmbedResponse:
        payload = {"model": self._embed_model, "input": texts}
        try:
            resp = await self._http.post(
                f"{self._base}{EMBED_PATH}",
                json=payload,
                headers=self._headers(),
                timeout=timeout_s,
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(f"deepseek embed timeout after {timeout_s}s") from exc
        except httpx.HTTPError as exc:
            raise DeepSeekDown(f"deepseek embed error: {exc}") from exc
        if resp.status_code >= 400:
            raise ProviderError(f"deepseek embed {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        usage = data.get("usage", {})
        prompt_tokens = int(usage.get("prompt_tokens", 0))
        return EmbedResponse(
            vectors=[item["embedding"] for item in data["data"]],
            model=self._embed_model,
            cost_usd=cost_usd(self._embed_model, prompt_tokens, 0),
            request_id=data.get("id", str(uuid.uuid4())),
        )

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
        except (ProviderError, ProviderTimeout, DeepSeekDown):
            return False
