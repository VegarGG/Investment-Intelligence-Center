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
    LlmRouter,
    chat,
    embed,
    get_router,
    set_router,
    with_signals,
)
from llm_client.types import ChatMessage, ChatResponse, EmbedResponse, LlmTier

__version__ = "0.1.0"
__all__ = [
    "LlmRouter",
    "chat",
    "embed",
    "get_router",
    "set_router",
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
