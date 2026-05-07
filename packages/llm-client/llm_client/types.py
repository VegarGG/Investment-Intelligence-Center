"""Public types for the LLM client (workflow 03 §5)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

LlmTier = Literal["flash", "pro", "embed"]
Outcome = Literal["ok", "error", "timeout", "rate_limit"]


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatResponse(BaseModel):
    text: str
    model: str
    tier: LlmTier
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    cost_usd: float = Field(ge=0.0)
    cached: bool = False
    fallback_used: bool = False
    request_id: str
    latency_ms: int = Field(ge=0)


class EmbedResponse(BaseModel):
    vectors: list[list[float]]
    model: str
    cost_usd: float = Field(ge=0.0)
    request_id: str
