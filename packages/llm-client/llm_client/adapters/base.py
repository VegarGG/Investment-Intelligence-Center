"""Adapter ABC — every provider implements this surface (workflow 03 §12.2)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from llm_client.types import ChatMessage, ChatResponse, EmbedResponse, LlmTier


class Adapter(ABC):
    """Provider-agnostic chat / embed surface."""

    name: str

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tier: LlmTier,
        max_tokens: int,
        temperature: float,
        timeout_s: float,
    ) -> ChatResponse:
        """One non-streaming chat completion. Token counts come from the
        provider's `usage` block — never estimated locally (workflow 03 §15)."""

    @abstractmethod
    async def embed(self, texts: list[str], *, timeout_s: float) -> EmbedResponse:
        """Embed `texts` with the provider's embedding model. DeepSeek only —
        Anthropic and Groq adapters raise NotImplementedError."""

    @abstractmethod
    async def health(self) -> bool:
        """Cheap 1-token round-trip; True if the model_string still resolves."""
