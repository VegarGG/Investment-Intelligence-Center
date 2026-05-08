# Workflow 40 — Trading Room overview (placeholder for T2)

> **Source plan:** [`plan/IIC_Development_Plan_v2.5_Combined.md`](../plan/IIC_Development_Plan_v2.5_Combined.md) §3 (T2)
> **Status:** PLACEHOLDER — fills out as T2 lands. Currently shipped: **T2.0 NATS request-reply substrate** (B3.1) + **T2.2 plan.v1 schema** (B3.2). Investment Board (T2.4), Event-Triage Gate (T2.1), and the trading-room DAG (T2.8) are next-iteration work.

---

## 1. Purpose

T2 is the user-visible product shift. v2.1 has a single morning-brief DAG that fans out to four analyst agents and a Secretary composes a brief at the end. T2 introduces an **event-driven trading-room** modeled on the TradingAgents 5-phase pipeline:

```
Intel ingest (OSINT + APIs + RSS + sudden-move detector)
        │
        ├──> Event-Triage Gate (T2.1) — is this important enough?
        │
        ▼
Analysis teams (Quant, Fundamental, Persona — N parallel plans)
        │
        ▼
Plan Aggregator — canonical plan.v1 envelope, one per team per ticker
        │
        ├────────> Investment Board (T2.4) — Bull/Bear → 3-way Risk → Chair
        │                    │
        │                    ▼
        │          Best plan + dissent record
        │
        └────────> Backtest team — paper-trading machinery, scorecards
                            │
                            ▼
                  Live benchmarking surface (T2.5)
                            │
                            ▼
            Per-team / per-plan leaderboard
```

## 2. What's shipped (B3.1, B3.2)

### T2.0 NATS request-reply substrate (B3.1)

```
packages/data-bus/data_bus/request_reply.py    # nats_call + register_handler + agent_subject
apps/orchestrator/orchestrator/plan/agent_client.py  # transport shim, flag-gated
apps/orchestrator/tests/test_nats_request_reply_shim.py
```

Feature flag: `orchestrator.use_nats_for_agent_calls` (default off). When on, every `HttpxAgentClient.call` goes through NATS request-reply instead of HTTP. Trace IDs auto-propagate. Agents register handlers on `iic.agent.<slug>`.

### T2.2 plan.v1 schema (B3.2)

```
packages/schema/schema/plan.py                 # PlanV1 + PortfolioContextV1
packages/schema/tests/test_plan_v1.py          # 34 cases
tests/fixtures/plan_v1_examples.json           # goldens-set (4 examples, every team × action)
apps/dashboard/src/types/plan.ts               # TS mirror + isValidPlanV1 runtime guard
```

Invariants enforced:
- `entry_window_close > entry_window_open`.
- `buy`: `target_price > entry_price > stop_loss`.
- `sell`: `stop_loss > entry_price > target_price`.
- `hold`: price ordering relaxed; evidence may be empty.
- `team='persona'` requires `persona_slug` AND `disclaimer`.
- `team!='persona'` must NOT set `persona_slug`.
- `expires_at - issued_at <= 365d`.

## 3. What's NOT shipped (next-iteration scope)

- **T2.1 Event-Triage Gate.** Promotes Intel candidate events → `intel.event.high_impact.v1`. Wakes the analysis teams.
- **T2.3 Analysis teams emit plan.v1.** Each existing agent grows a `team_plan` endpoint that consumes a high-impact event and emits exactly one `plan.v1` per affected ticker.
- **T2.4 Investment Board.** Bull/Bear → 3-way Risk → Chair. New `apps/agent_board/` service.
- **T2.5 Live benchmarking.** Per-plan + per-team scorecards in `lake.plan_scorecard`.
- **T2.6 Plan delivery to user.** Secretary's `compose_brief` extended with the trading-room shape.
- **T2.8 Trading-room DAG.** End-to-end orchestration tying T2.1–T2.7 together.
- **T2.9 + T2.10** Bull/Bear at the Fundamental layer + the indicator-taxonomy block for Quant.

## 4. Acceptance

T2 unblocks once the burn-in regime is green AND **at least one** real-event run end-to-end produces a valid `plan.v1` from each of {quant, fundamental, persona, intel}.

## Changelog

- **v0.1** — Placeholder created with B3.1 + B3.2 detail; T2.1/T2.4/T2.5/T2.6/T2.8 deferred.
