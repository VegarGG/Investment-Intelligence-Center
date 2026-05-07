"""Fallback decision (workflow 03 §10).

Decision tree:
  DeepSeek Pro down  → Anthropic Claude Sonnet 4.6
  DeepSeek Flash down → Groq Llama-3.3-70B
  embed tier         → no fallback (only DeepSeek does embeddings)
  Both down          → NoLLMAvailable
"""

from __future__ import annotations

from dataclasses import dataclass

from llm_client.adapters.base import Adapter
from llm_client.exceptions import (
    DeepSeekDown,
    NoLLMAvailable,
    ProviderError,
    ProviderTimeout,
)
from llm_client.types import ChatMessage, ChatResponse, LlmTier


@dataclass(slots=True)
class FallbackChain:
    pro_fallback: Adapter | None  # Anthropic
    flash_fallback: Adapter | None  # Groq

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tier: LlmTier,
        max_tokens: int,
        temperature: float,
        timeout_s: float,
        primary_error: Exception,
    ) -> ChatResponse:
        adapter = self._adapter_for(tier)
        if adapter is None:
            raise NoLLMAvailable(
                f"no fallback configured for tier={tier}; primary error: {primary_error}"
            )
        try:
            return await adapter.chat(
                messages,
                tier=tier,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout_s=timeout_s,
            )
        except (ProviderError, ProviderTimeout, DeepSeekDown) as exc:
            raise NoLLMAvailable(
                f"primary + fallback both down: primary={primary_error}; fallback={exc}"
            ) from exc

    def _adapter_for(self, tier: LlmTier) -> Adapter | None:
        if tier == "pro":
            return self.pro_fallback
        if tier == "flash":
            return self.flash_fallback
        return None  # embed: no fallback path
