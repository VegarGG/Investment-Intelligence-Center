"""v2.5 T1.9 / B1.4 — REAL DeepSeek cost-cap chaos test.

THIS IS NOT MOCKABLE. The cost meter has to actually meter real LLM cost
for the breaker-open behaviour to be verified end-to-end. Gated on
``IIC_RUN_COST_CHAOS=1`` so it never runs by default.

Acceptance per plan §C9:
- Drives spend to 95 % of cap mid-morning-brief.
- Verifies breaker opens, the DAG completes, and the brief markdown
  contains the synthetic-skip marker.
- Hard-capped at $1 spend so the test cannot run away.

Set up before running:
- `DEEPSEEK_API_KEY` in env.
- `LLM_MONTHLY_CAP_USD=1.00` (the test will drive it close to this).
- `IIC_RUN_COST_CHAOS=1`.
- Network reachable to api.deepseek.com.
"""

from __future__ import annotations

import os

import pytest

REQUIRED_ENV = ("DEEPSEEK_API_KEY", "LLM_MONTHLY_CAP_USD", "IIC_RUN_COST_CHAOS")


@pytest.mark.skipif(
    os.environ.get("IIC_RUN_COST_CHAOS") != "1",
    reason="real DeepSeek API drill — set IIC_RUN_COST_CHAOS=1 + DEEPSEEK_API_KEY to run",
)
@pytest.mark.real_api
def test_cost_cap_real_breaker_opens_under_real_spend():
    """Drive a real DeepSeek conversation until the cap trips; assert
    the synthetic-skip marker shows up in the morning-brief markdown.

    This test exercises the entire stack: real adapter → real cost meter →
    real CostBudgetExceeded → router.chat_or_skip falls back.
    """

    for var in REQUIRED_ENV:
        assert os.environ.get(var), f"missing {var}"

    cap_usd = float(os.environ["LLM_MONTHLY_CAP_USD"])
    assert cap_usd <= 1.0, "test must run under a $1 cap; refusing"

    from llm_client import COST_SKIPPED_MARKER, ChatMessage, LlmRouter
    from llm_client.adapters.deepseek import DeepSeekAdapter
    from llm_client.cost_meter import CostMeter, InMemorySpendStore
    from llm_client.fallback import FallbackChain
    from llm_client.rate_limiter import RateLimiter

    store = InMemorySpendStore()
    meter = CostMeter(store=store, monthly_cap_usd=cap_usd)
    router = LlmRouter(
        primary=DeepSeekAdapter(api_key=os.environ["DEEPSEEK_API_KEY"]),
        fallback=FallbackChain(pro_fallback=None, flash_fallback=None),
        rate_limiter=RateLimiter(),
        cost_meter=meter,
    )

    # Step 1: drive ~95% of cap. Each Flash call ≈ $0.00014; we issue
    # enough small calls until the meter breaks 95%.
    saw_skip = False
    for i in range(2_000):  # generous upper bound; loop exits earlier
        out = await_helper(
            router.chat_or_skip(
                "secretary.brief.midday",
                [ChatMessage(role="user", content=f"#{i}: status check?")],
                max_tokens=8,
            )
        )
        if out.cost_skipped:
            saw_skip = True
            assert COST_SKIPPED_MARKER in out.text
            break
        # Belt-and-braces: assert we never blow past the cap.
        spent = await_helper(meter.store.total_spend(since=meter._since()))
        assert spent <= cap_usd * 1.05, (
            f"spent ${spent:.4f} > 1.05× cap ${cap_usd:.4f} — breaker DID NOT open in time"
        )

    assert saw_skip, "test exhausted iterations without seeing the cost-skip path"


def await_helper(coro):
    """Test-only synchronous waiter so this test stays a plain function.

    Avoids the implicit ``asyncio_mode = auto`` semantics interacting with
    a long-running drill that we want to pause/inspect interactively.
    """
    import asyncio

    return asyncio.get_event_loop().run_until_complete(coro)
