# ADR-0001 — LLM strategy: DeepSeek v4 (Pro + Flash) with API-first routing

- **Status:** Accepted
- **Date:** 2026-05-06
- **Supersedes:** v1.1's local-LLM-first plan

## Context

v1.1 of the Intelligence Center assumed a local GPU running an open-weights model. v2.x decouples intelligence from advice and adds a fleet of advisory agents — that workload mix (lots of cheap classification + bursts of deep synthesis) is a poor fit for a single local model. We considered three options:

1. **Local-only (status quo).** Requires a GPU on the home box. Cost surfaces as power and depreciation, not invoice. Caps the fleet at one tier of model.
2. **API-only.** Cheap per call, two tiers available, no GPU needed.
3. **Hybrid.** Run a small local model for ingest, call an API for synthesis. Operationally the worst of both worlds at our scale.

## Decision

API-first with **DeepSeek v4 Pro + Flash**. Pro for synthesis, Flash for everything bulk.

- **Pro:** orchestrator plan, `intel.synth`, `fund.valuation`, `persona.*` reasoning, deep secretary answers.
- **Flash:** ingest classification, translation, sentiment, factor narration, default chat, post-trade narrative.
- Routing is a single matrix in `packages/llm-client/router.py` (PLAN §5).
- Cost gate: hard cap at $90/month enforced by circuit breaker in `llm-client`.
- Fallback chain: Pro → Anthropic Claude Sonnet 4.6; Flash → Groq Llama-3.3-70B. Both adapters live in `packages/llm-client/adapters/`.

## Consequences

- ✅ No GPU required. Hardware tier collapses from "workstation" to "mini-PC."
- ✅ Both tiers are independently rate-limited and individually swappable.
- ✅ Multi-region failover comes for free.
- ⚠️ Ongoing API spend. Monitored via cost burndown panel in Grafana.
- ⚠️ External dependency. Mitigated by the two-vendor fallback chain.
- ⚠️ Prompt drift between vendors is real. Eval harness with a frozen 60-prompt golden set runs weekly and alerts on > 10% regression (workflow 30).

## Re-evaluation trigger

When DeepSeek-V4-distill ships open weights, evaluate replacing Flash for non-time-critical paths to cut spend.
