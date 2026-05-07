"""Provider pricing — single source of truth (workflow 03 §7).

⚠️ Updates here MUST be accompanied by an INSERT into lake.llm_pricing_history
   (audit trail). The audit-log helper is `record_pricing_change()` below.

Prices are USD per 1,000,000 tokens.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelPricing:
    in_per_1m_usd: float
    out_per_1m_usd: float


PRICING: dict[str, ModelPricing] = {
    "deepseek-v4-pro": ModelPricing(in_per_1m_usd=0.55, out_per_1m_usd=2.20),
    "deepseek-v4-flash": ModelPricing(in_per_1m_usd=0.07, out_per_1m_usd=0.28),
    "deepseek-bge-m3": ModelPricing(in_per_1m_usd=0.02, out_per_1m_usd=0.0),
    # Fallback Pro
    "claude-sonnet-4-6": ModelPricing(in_per_1m_usd=3.00, out_per_1m_usd=15.00),
    # Fallback Flash (free tier)
    "llama-3.3-70b-versatile": ModelPricing(in_per_1m_usd=0.0, out_per_1m_usd=0.0),
}


def cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Compute USD cost for a single call. Returns 0.0 for unknown models —
    caller's telemetry will note the unknown model, but a typo in PRICING
    must not crash the request path."""
    p = PRICING.get(model)
    if p is None:
        return 0.0
    return (prompt_tokens / 1_000_000) * p.in_per_1m_usd + (
        completion_tokens / 1_000_000
    ) * p.out_per_1m_usd
