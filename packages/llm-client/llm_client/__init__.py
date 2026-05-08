"""IIC llm_client — DeepSeek v4 Pro+Flash router with Anthropic/Groq fallbacks (workflow 03)."""

from llm_client.exceptions import (
    CostBudgetExceeded,
    DeepSeekDown,
    LlmClientError,
    NoLLMAvailable,
    ProviderError,
    ProviderTimeout,
    UnknownCallerId,
)
from llm_client.router import (
    COST_SKIPPED_MARKER,
    LlmRouter,
    chat,
    embed,
    get_router,
    runtime_signals,
    set_router,
    synthetic_skip_response,
    with_signals,
)
from llm_client.types import ChatMessage, ChatResponse, EmbedResponse, LlmTier

__version__ = "0.1.0"
__all__ = [
    "COST_SKIPPED_MARKER",
    "LlmRouter",
    "chat",
    "embed",
    "get_router",
    "runtime_signals",
    "set_router",
    "synthetic_skip_response",
    "with_signals",
    "ChatMessage",
    "ChatResponse",
    "EmbedResponse",
    "LlmTier",
    "LlmClientError",
    "CostBudgetExceeded",
    "DeepSeekDown",
    "NoLLMAvailable",
    "ProviderError",
    "ProviderTimeout",
    "UnknownCallerId",
]
