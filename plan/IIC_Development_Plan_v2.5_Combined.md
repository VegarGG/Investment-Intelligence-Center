# Investment Intelligence Center — Development Plan v2.5 (Combined)

**Deliverable 4 of 4** · Investment Intelligence Center research dossier · Prepared for Ziwei · 2026-05-08

> **What this is.** A consolidated successor to `D3_IIC_Development_Plan_v2.2_and_v3.0.md`, written after the architecture review surfaced gaps in the v2.1 prototype and the v2.2/v3.0 sequencing. This plan supersedes the prior v2.2 + v2.3 split and is named **v2.5** because the user-facing shape changes meaningfully: a new **Investment Board** team, an **Intel-driven event-flow workflow**, and **FUTU OpenAPI integration (read-only, multi-account)**.
>
> **Premise.** Same v2.0 hard constraints carry over: suggestion-only, every advice carries citations, persona disclaimer mandatory, every persona-style brief includes a disclaimer that the agent is not the real person.
>
> **Sequencing rule.** Tier 0 (T0) before Tier 1 (T1) before Tier 2 (T2) before Tier 3 (T3). Items inside a tier may parallelize. T0 is the rollback-safety substrate; T1 is correctness fixes; T2 is the Investment Board + new workflow + FUTU; T3 is research depth and product expansion.
>
> **Cost budget.** $200/month all-in hard ceiling (was $160 in v2.0). Cost cap raises proportionally with surface, not exponentially. T2 expansion driven by an explicit cost-cap chaos test (see C9).

---

## Table of contents

- [Section 0 — Scope and architectural shift](#section-0--scope-and-architectural-shift)
- [Section 1 — Tier 0: rollback substrate (no A1 work begins until T0 is green)](#section-1--tier-0-rollback-substrate-no-a1-work-begins-until-t0-is-green)
- [Section 2 — Tier 1: correctness, reliability, DAG coverage](#section-2--tier-1-correctness-reliability-dag-coverage)
- [Section 3 — Tier 2: Investment Board, event-flow workflow, FUTU integration](#section-3--tier-2-investment-board-event-flow-workflow-futu-integration)
- [Section 4 — Tier 3: research depth and product expansion (former v3.0)](#section-4--tier-3-research-depth-and-product-expansion-former-v30)
- [Section 5 — Cross-cutting concerns](#section-5--cross-cutting-concerns)
- [Section 6 — Acceptance gates](#section-6--acceptance-gates)
- [Section 7 — Architecture rework summary](#section-7--architecture-rework-summary)
- [Appendix A — Investment Board prompt skeletons](#appendix-a--investment-board-prompt-skeletons)
- [Appendix B — FUTU OpenD deployment topology](#appendix-b--futu-opend-deployment-topology)
- [Appendix C — Live benchmarking schema](#appendix-c--live-benchmarking-schema)

---

# Section 0 — Scope and architectural shift

## 0.1 What changes from v2.1

Three changes are real architectural shifts; everything else is incremental.

**Shift 1 — From cron-driven brief to event-driven trading-room.** v2.1 has a single `morning_brief` DAG that fans out to four analyst agents in parallel and the Secretary composes a brief at the end. v2.5 introduces a **trading-room workflow** modeled on TradingAgents' five-phase pipeline, but native to IIC's bus + StateGraph runtime:

```
Intel ingest (OSINT + APIs + RSS + X/Reddit/Telegram + sudden-move detector)
        │
        ├──> Event-Triage Gate (is this important enough to wake the room?)
        │
        ▼
Analysis teams (Quant team, Fundamental team, Persona team — N parallel plans)
        │
        ▼
Plan Aggregator (canonical plan.v1 envelope; one plan per team per ticker)
        │
        ├────────> Investment Board (Bull/Bear → 3-way Risk → Board Chair)
        │                    │
        │                    ▼
        │          Best plan + dissent record
        │
        └────────> Backtest team (live-market replay, paper-trading machinery)
                            │
                            ▼
                  Per-plan / per-team scorecards
                            │
                            ▼
            Live benchmarking surface (dashboard + WeChat brief)
```

**Shift 2 — Investment Board.** Borrowed in spirit (not code-for-code) from TradingAgents' Research Manager + 3-way Risk Debate + Portfolio Manager. The Board is a sub-system whose only job is to look at every team's plan, surface dissent, and pick the best one — with a structured rationale and a public disagreement record. See §3.2.

**Shift 3 — FUTU OpenAPI integration (read-only, multi-account).** The Board and the analysis teams gain a **portfolio-context oracle**: they know what Ziwei actually holds, in which accounts, in which currencies, with what cost basis. Strictly read-only — no order placement, no `unlock_trade()`, no broker-side state mutation. See §3.3.

## 0.2 What does NOT change

- **v2.0 hard constraints** — suggestion-only, citations mandatory, persona disclaimer mandatory.
- **v2.1 substrate** — bind-mount-everything storage, single-host topology with NAS-ready layout, hash-chained advice ledger, sqlglot-based PIT enforcement, LangGraph-shaped StateGraph runtime, multi-provider LLM router, Postgres + Timescale + Chroma + MinIO + Redis + observability stack.
- **The six original agents** — Intelligence, Fundamental, Quant, Persona, Backtest, Secretary. They don't go away; they become **teams** under the Investment Board, with the Board acting as their tribunal. The `agent_*` containers stay; new containers (`agent_board`, `agent_event_triage`, `agent_futu`) are added.

## 0.3 Architecture review findings — how this plan addresses each

| Review finding | Severity | Plan response |
|---|---|---|
| `px = 100.0` placeholder in `persona/reasoner.py` | Critical | T1.1 |
| Soros / Burry persona inconsistency | Critical | T1.2 + T0.2 (single source of truth) |
| Intelligence pipeline not bound at startup | Critical | T1.3 |
| `_relevant_events` is a no-op stub | High | T1.1 (folded in) |
| Notifier `NotifyExhausted` — no retry queue | High | T1.4 |
| 5 cron jobs, 1 DAG registered → silent drops | High | T1.5 (close all gaps OR trim cron) |
| 3 NATS subjects, 0 DAGs registered → silent drops | High | T2 trading-room workflow uses these subjects natively |
| `packages/featureflags` does not exist | Critical | T0.1 |
| `packages/data-lake/data_lake/quotes.py` does not exist | High | T1.1a (write the module) |
| No per-agent circuit breaker on `HttpxAgentClient` | High | T1.6 |
| Orchestrator + Postgres + NATS SPOFs unstated | Medium | T0.3 (acceptance ADR) |
| Single-node JetStream | Medium | T1.7 (backup cron) |
| No per-service memory caps | Medium | T1.8 |
| Cost-breaker behavior under load undefined | Medium | T1.9 (chaos test) |
| HTTP fan-out conflicts with v3.0 streaming | Medium | T2.0 (NATS request-reply substrate before T2 fan-out) |
| `NotifyExhausted` failure mode | Medium | T1.4 (split compose vs deliver) |

---

# Section 1 — Tier 0: rollback substrate (no A1 work begins until T0 is green)

These three items together are the prerequisite for safely shipping anything in T1+. Without them, the first item that lands hardens into a redeploy-or-revert path and the rollback story is gone.

## T0.1 Build `packages/featureflags`

**Problem.** Plan v2.2 § C5 promised feature-flag-based rollback, but the package doesn't exist. Every v2.5 item assumes feature-flag existence.

**Action.**
- New package `packages/featureflags/featureflags/`. API: `flag(name: str) -> bool`, `flag_value(name: str, default: T) -> T`, `with_flag(name)` async context manager.
- YAML-backed config at `/srv/iic/featureflags/flags.yaml`, hot-reload via `inotifywait` on Linux.
- Flag registry documented in `docs/featureflags.md` — every flag has `name | description | added_in | default_state | owner`.
- Mandatory header for every new agent / DAG / endpoint: feature-flag-gated, default off.

**Acceptance.** A new flag can be flipped via YAML edit; affected service responds within 2s; flag-flip is observable in Grafana as `featureflag.changed{name=...}`. **Depends on:** none. **Blocks:** every other tier-0/1/2 item.

## T0.2 Single source of truth for personas

**Problem.** `DEFAULT_PERSONA_SLUGS` is hard-coded in `morning_brief.py`; the URL map is hard-coded in `app.py:_bootstrap`; the YAML directory has a different list. Three places drift.

**Action.**
- New helper `apps/orchestrator/orchestrator/plan/personas.py:list_personas() -> list[PersonaSpec]` reads `docs/prompts/persona/*.yaml` at startup.
- `morning_brief.py` and any future trading-room DAG calls `list_personas()` — never hard-codes the slug list.
- `_bootstrap` builds the URL map from `list_personas()`.
- Add `test_persona_source_of_truth.py` — fails if any code references a persona slug not present in the YAML directory.

**Acceptance.** Add `soros.yaml` and the morning brief picks it up automatically without code changes. **Depends on:** none.

## T0.3 SPOF acceptance ADR

**Problem.** The system is single-host single-Postgres single-NATS by deliberate design. The architecture review flagged this as risk worth documenting — not changing.

**Action.** Write `docs/adr/ADR-0004-single-host-acceptance.md` naming:
- The orchestrator, Postgres, NATS, and dashboard SPOFs.
- The recovery mechanism (restic-from-NAS, NATS stream-backup cron from T1.7).
- Explicit RPO (last hourly restic snapshot — typically ≤ 1 h) and RTO (NAS bind-mount + `docker compose up` — typically ≤ 15 min on a fresh box).
- Trigger conditions for promoting beyond single-host (e.g., if Ziwei opens IIC up to family read-only mode at scale).

**Acceptance.** ADR merged, referenced from README and runbooks. **Depends on:** none.

---

# Section 2 — Tier 1: correctness, reliability, DAG coverage

T1 is the v2.2 must-have list with the architecture review's amendments folded in. T1 must be in production for ≥ 14 days before T2 (Investment Board) wiring begins.

## T1.1 Wire live mark price + remove the persona-events stub

**Problem.** `apps/agent_persona/persona/reasoner.py` hard-codes `px = 100.0` and `_relevant_events` ignores the persona spec.

**Action.**
- **T1.1a** Create `packages/data-lake/data_lake/quotes.py:get_mark(asset, asof)` that hits the same vendor router used by the Quant Agent. After-hours / weekend → return last close + a `stale_seconds` field. Cache marks in Redis with a 30 s TTL; invalidate on `quotes.v1` NATS events.
- **T1.1b** Replace the placeholder in `_to_advice` with a call to `get_mark`.
- **T1.1c** Implement `_relevant_events` to filter the digest by `spec.universe` weights (sector, region, asset class).
- **T1.1d** Persona advice JSON fields `entry_band / target_band / stop_loss` derive from the live mark via the spec's `priors` (e.g., Buffett: target = mark × (1 + 25 % over horizon); Soros: target = mark × (1 + macro-momentum-implied %)).

**Acceptance.** Persona advice JSON shows realistic bands across the 50-ticker watchlist. `test_persona_mark_resolution.py` covers fallback to last close on weekends and surfaces `stale_seconds`. Grafana panel `persona advice with stale marks` added. **Depends on:** T0.1, T0.2. **Blocks:** T1.2, T2.1.

## T1.2 Resolve the Soros / Burry inconsistency

**Action.** Author `docs/prompts/persona/soros.yaml` (priors, universe weights, guardrails, disclaimer) **and** add `docs/prompts/persona/wood.yaml` and `docs/prompts/persona/dalio.yaml` while we're at it — Ziwei's project-level brief lists 8 personas (Rogers, Buffett, Soros, Druckenmiller, Wood, Dalio, Burry, retail-degen). Wire `list_personas()` (T0.2) so the morning brief and the new trading-room DAG both fan out to the full set.

**Acceptance.** Morning brief runs end-to-end with no missing-persona errors. `test_persona_loader.py` enforces 1:1 between code defaults and YAML files. **Depends on:** T0.2.

## T1.3 Bind the Intelligence Agent's pipeline at startup

**Action.** Move pipeline construction into `agent_intelligence/intel/main.py:@app.on_event("startup")` using a deterministic config-driven factory `build_pipeline(config)`. Add `/health/deep` that runs a 1-doc dry-run through the pipeline. Reserve env-driven binding for tests / CI overrides.

**Acceptance.** `docker compose up agent_intelligence` followed by `curl :8081/run/synthesize -X POST -d '{...}'` returns 200 in < 30 s. `test_intelligence_startup.py` verifies the pipeline is bound before the first request. **Depends on:** none. **Blocks:** T1.4 notifier, T1.10 eval.

## T1.4 Notifier durable redelivery + compose/deliver split

**Problem.** `NotifyExhausted` is raised but the orchestrator's `n_notify` propagates it; the morning_brief DAG fails and the brief is lost. Plus there's no retry queue.

**Action.**
- **T1.4a** Redis-backed retry queue keyed by `(notification_id, severity)`. On `NotifyExhausted`, push to queue with TTL = severity-dependent (CRITICAL: 1 h, ALERT: 6 h, INFO: 24 h). 60-second background drain job. CRITICAL falls back to a Tailscale-only ntfy push to Ziwei's phone.
- **T1.4b** Split DAG node `n_notify` into `n_compose_brief` (produces markdown, writes to MinIO + dashboard, always succeeds) and `n_deliver_brief` (calls notifier; failures here do not fail the DAG, only emit `notify.deferred.v1`).
- **T1.4c** Reconciliation page in dashboard: deferred notifications + age + replay button.

**Acceptance.** Chaos test: kill all four notifier adapters mid-fanout, verify message redelivered within TTL once any adapter recovers; brief still appears in dashboard regardless. **Depends on:** T0.1.

## T1.5 Close the silent-drop surface — DAGs for every cron + every NATS subject

**Problem.** Today: 5 cron jobs declared, only `morning_brief` registered. 3 NATS subscriptions wired, none route to a DAG.

**Action.** Three of the new DAGs are part of T2 (intraday trading-room, fill notification, leaderboard publication). For T1, ship the two that don't depend on T2:

- **T1.5a `cron:midday_check`** → DAG `midday_pulse.py` — light Intel re-fetch + Quant regime check + Secretary one-line WeCom message if regime changed since morning. No persona fan-out, no LLM-heavy work.
- **T1.5b `cron:evening_recap`** → DAG `evening_recap.py` — Backtest's daily MTM + leaderboard delta + one-page recap brief, MinIO + WeCom push.
- **T1.5c `cron:hourly_intel`** → DAG `hourly_intel_pulse.py` — Intel agent hourly synthesize, push `intel.digest.v1`. This is the heartbeat for downstream subscribers.
- **T1.5d `cron:weekly_eval`** → DAG `weekly_eval.py` — runs the prompt-eval golden set + emits leaderboard.
- **T1.5e** Add CI test `test_registered_dags_match_cron.py` that fails if a cron entry has no registered DAG. Fail closed.

**NATS subscriptions.** Wire DAGs for all three subscribed subjects:
- `intel.digest.v1` → re-fan-out to analysis teams (becomes T2's primary trigger).
- `backtest.fill.v1` → fill-notification DAG (T2.5).
- `ops.alert.v1` → ops-incident DAG that writes a `runbook hint` to the dashboard.

**Acceptance.** No `"no DAG registered for trigger=X — dropping"` log lines in normal operation. CI test green. **Depends on:** T0.1, T1.3.

## T1.6 Per-agent circuit breaker on `HttpxAgentClient`

**Problem.** One unhealthy agent slows every DAG run.

**Action.** Wrap `HttpxAgentClient.call` with a per-target circuit breaker (using `pybreaker` or a hand-rolled state machine). Open after 5 consecutive failures; half-open probe every 60 s. When open, the call returns `{"advices": [], "_breaker_open": True}` so fan-out legs degrade gracefully. Emit `agent_breaker.opened` / `agent_breaker.closed` events. **Acceptance.** Chaos test: stop one agent container, verify the morning brief still completes (with that agent's advice missing) within SLA. **Depends on:** T0.1.

## T1.7 NATS JetStream backup cron

**Action.** Daily 03:00 local cron runs `nats stream backup --all /srv/iic/nats-backups/$(date +%F)` and rotates older than 14 days into MinIO with restic. **Acceptance.** Restore drill on a clean machine recovers all durable consumers. **Depends on:** none.

## T1.8 Per-service memory caps

**Action.** Add `deploy.resources.limits.memory` to every service in `docker-compose.yml`. Recommended caps for Mac mini M4 Pro 24 GB host: Postgres 4 GB, Chroma 4 GB, MinIO 1 GB, Redis 512 MB, NATS 512 MB, Loki 1 GB, Prometheus 1 GB, Grafana 512 MB, each agent 1 GB, orchestrator 1 GB, dashboard 256 MB. Total ~16 GB; leaves 8 GB OS + headroom. **Acceptance.** Chaos test: balloon Chroma's index to 6 GB and verify Postgres survives. **Depends on:** none.

## T1.9 Cost-breaker behavior pin-down

**Action.** Define behavior at breaker-open: in-flight calls drain gracefully (deadline 30 s); new calls within the same DAG node fall back to "skipped advice" with `evidence=[]` and a synthetic note. `llm_client/cost_meter.py` emits `llm.cost.skipped` events. `with_signals(cost_breaker_open=True)` makes the state visible to downstream nodes. **Acceptance.** Chaos test: drive spend to 95 % of cap mid-morning-brief, verify breaker opens and brief still completes (with synthetic skips noted). **Depends on:** T0.1.

## T1.10 PIT enforcement at the ingest boundary

**Action.** Every record entering Postgres / Timescale carries `as_of_ts` (when the data became knowable) and `ingested_at_ts` (when IIC first saw it). Backtests filter `as_of_ts <= trade_date`. Extend `test_pit_correctness.py` to cover all four agent ingest paths plus the new trading-room. **Acceptance.** Replaying any trade date 6 months in the past gives the same agent advice ± LLM nondeterminism. **Depends on:** none. **Blocks:** T2.7 walk-forward.

## T1.11 Markdown decision log + Backtest reflection

(merged former A4.3 + A4.4 because they're inseparable and unblock the live benchmarking surface)

**Action.**
- `packages/data-lake/data_lake/decision_log.py` — append-only markdown file per agent, atomic temp-file + `os.replace`, HTML-comment delimiter. Per-advice entry: rating, thesis, evidence URLs, post-hoc reflection (filled by Backtest).
- Backtest `Reflector` writes 2-4 sentence reflection to source agent's decision-log entry on every realised outcome. Cite alpha vs SPY, declare thesis-held vs thesis-failed, name one concrete lesson.
- Hosted under `/srv/iic/decision_logs/`, backed up with restic.

**Acceptance.** Every advice in `advice_ledger` has a corresponding markdown entry; reflections appear within 7 trading days of the advice. **Depends on:** none. **Blocks:** T2.6 live benchmarking, T3 walk-forward.

## T1.12 Walk-forward backtest harness (was v3.0 B5.1 — promoted)

**Why promoted.** The architecture review identified this as a v2.2 prerequisite, not a v3.0 nice-to-have: prompt-version bumps need a real gate, not just a static eval. T1.12 is the gate.

**Action.** Backtest agent gains an offline mode that, given a prompt-version bump, re-runs the past 24 months walk-forward with the new prompts and produces a delta vs the prior version. CI gate: a prompt change does not promote without a green walk-forward delta or an explicit override (cap one override per quarter). Required before any prompt promotes to production. **Acceptance.** Run a synthetic prompt-bump and verify the walk-forward CI gate fails or passes correctly. **Depends on:** T1.10.

---

# Section 3 — Tier 2: Investment Board, event-flow workflow, FUTU integration

T2 is the user-visible product shift. None of T2 begins until T1 has been in production ≥ 14 days.

## T2.0 NATS request-reply substrate (prerequisite)

**Problem.** Today every orchestrator → agent call is HTTP. The new event-flow workflow wakes analysis teams from a NATS event (`intel.event.high_impact.v1`); HTTP fan-out couples orchestrator and agent lifecycles tightly. T2.0 builds the abstraction so future trading-room DAGs can fan out via NATS request-reply, not HTTP.

**Action.**
- New module `packages/data-bus/data_bus/request_reply.py:nats_call(subject, payload, timeout_s) -> dict`. NATS request-reply with auto-trace propagation.
- `HttpxAgentClient` becomes a thin shim that picks HTTP or NATS based on a feature flag (`flag('use_nats_for_agent_calls')`). Default off in T2.0; flipped on per-DAG in T2.x.
- Each agent grows a NATS handler that mirrors its HTTP `/run` endpoint.

**Acceptance.** Morning brief DAG runs identically with the flag on or off. **Depends on:** T0.1, T1.6 (per-agent breaker still works over NATS).

## T2.1 Event-Triage Gate

**Problem.** Today the morning_brief is the only trigger; intra-day events are not actionable. The user's workflow requirement: news / sudden movements wake the analysis teams.

**Action.** New small agent `apps/agent_event_triage/`:
- Subscribes to `intel.event.candidate.v1` (emitted by Intel for every new news item, sudden-move detector, OSINT signal).
- A lightweight LLM (DeepSeek Flash) classifies each candidate as one of: `noise | watch | high_impact | tail`.
- Emits `intel.event.high_impact.v1` (and `intel.event.tail.v1` for chaos events) — these are the wake-up subjects for analysis teams.
- Throttle: max 6 high_impact events per market session per ticker; idempotency key includes the news event hash + a 30-min cool-down.
- Sudden-move detector: rolling z-score on 1-minute bars from the live quote stream — z > 4 within 15 min triggers a synthetic candidate even if no news arrived.

**Acceptance.** Synthetic 10 % drop on a watchlist ticker fires the trading-room DAG within 60 s. **Depends on:** T1.5c (hourly_intel), T2.0.

## T2.2 New schema — `plan.v1`

**Problem.** The user's workflow specifies a richer team-level output than `advice.v1`: action, price, period, max drawdown — each plan is a complete trade thesis at the team level.

**Action.** New canonical schema `packages/schema/schema/plan.py:PlanV1`:

```python
class PlanV1(BaseModel):
    schema_version: Literal["plan.v1"] = "plan.v1"
    id: str  # ULID
    team: Literal["quant", "fundamental", "persona", "intel"]   # which team produced this plan
    persona_slug: str | None = None   # only set when team == "persona"
    issued_at: datetime
    asset: Asset
    action: Literal["buy", "sell", "hold"]    # team-level recommendation
    entry_price: float                          # exact entry price the plan recommends
    entry_window_open: datetime                # plan is valid from
    entry_window_close: datetime               # plan expires after
    target_price: float
    stop_loss: float
    max_drawdown_pct: float                    # acceptable peak-to-trough loss
    horizon_days: int
    sizing_pct_nav: float                       # % of NAV the team would allocate
    confidence: float                           # 0..1
    thesis: str                                 # 4-6 sentence team-level thesis
    evidence: list[Evidence]
    portfolio_context: PortfolioContextV1 | None = None   # FUTU-derived; see T2.4
    expires_at: datetime
    disclaimer: str | None = None              # mandatory for persona team
```

This schema is **additive**, not replacing `advice.v1`. The Backtest agent grades `plan.v1` directly; it grades `advice.v1` for backward-compat. Internally, a `plan.v1` aggregates 1+ `advice.v1` entries from the same team. **Acceptance.** Pydantic validators enforce:
- `entry_window_close > entry_window_open`
- For `action=buy`: `target_price > entry_price > stop_loss`
- For `action=sell`: `stop_loss > entry_price > target_price`
- `max_drawdown_pct ∈ [0, 100]`
- `horizon_days ∈ [1, 365]`
- `evidence` non-empty unless `action=hold`

**Depends on:** none (additive schema).

## T2.3 Analysis teams produce `plan.v1`

**Action.** Each existing agent gains a `team_plan` endpoint that consumes a high-impact event and emits exactly one `plan.v1` per affected ticker.

- **Quant team** (`agent_quant`) — runs the 8-factor library + regime classifier; emits a `plan.v1` whose entry/target/stop are factor-implied.
- **Fundamental team** (`agent_fundamental`) — DCF + multiples + filings excerpt; bull/bear pass (former A4.2) before final plan. Emits a `plan.v1` whose horizon is typically 90-180 days.
- **Persona team** (`agent_persona`) — fan-out across all 8 personas; each persona emits a `plan.v1` with the persona's slug. The persona team aggregates the 8 plans into a "persona consensus" `plan.v1` (median entry, conservative stop, weighted confidence) and ALSO publishes the individual 8 for transparency. The Investment Board sees the consensus by default; can drill into individuals on disagreement.

All three teams run in parallel after the Event-Triage Gate fires. **Acceptance.** Synthetic high-impact event produces 3 team plans (or more, counting persona individuals) within the SLA. **Depends on:** T1.1, T1.2, T1.3, T2.0, T2.1, T2.2.

## T2.4 Investment Board

**Workflow shape (TradingAgents-inspired, IIC-native).**

```
                  Plan Aggregator (collects all plan.v1 for the same trigger event)
                                    │
                                    ▼
       ┌───────── Bull/Bear research debate (max 2 rounds) ───────────┐
       │ Bull reads ALL plans + portfolio_context; argues why the most  │
       │ aggressive buy is right. Bear argues why the most conservative │
       │ hold/sell is right. They debate plan-by-plan, not all at once. │
       └────────────────────────────┬───────────────────────────────────┘
                                    │
                                    ▼
        ┌── 3-way Risk debate (max 3 turns) ──┐
        │ Aggressive / Conservative / Neutral │
        │ each respond to the bull/bear summary│
        │ with one 2-3 sentence position.      │
        └─────────────────┬────────────────────┘
                          │
                          ▼
                  Board Chair (deep-thinking LLM)
                  - reads everything: all plans, bull/bear, risk debate, portfolio_context
                  - emits BoardDecision: best plan id + rationale + dissent record + risk view
                  - persists to advice ledger as agent='board' with hash chain
```

**Action.** New service `apps/agent_board/` + four sub-agents inside (Bull, Bear, three Risk debators, Board Chair). Reused conceptually from TradingAgents Apache-2.0 prompts (per C4 attribution policy); rewritten to consume IIC's `plan.v1` envelope. Output: a single `board.decision.v1` event per trigger event, persisted to the advice ledger.

**Schema** `BoardDecisionV1`:

```python
class BoardDecisionV1(BaseModel):
    schema_version: Literal["board.decision.v1"] = "board.decision.v1"
    id: str
    trigger_event_id: str
    issued_at: datetime
    chosen_plan_id: str | None       # the winning plan.v1 id; None if Board recommends "no action"
    chosen_team: str
    rating: Literal["Buy", "Overweight", "Hold", "Underweight", "Sell"]
    executive_summary: str
    investment_thesis: str
    risk_view: str                    # one-line synthesis of 3-way risk debate
    dissent_record: list[Dissent]    # for every plan NOT chosen: which team, why rejected
    plan_universe: list[str]          # ids of every plan considered
    bull_bear_transcript_ref: str    # MinIO URL
    risk_debate_transcript_ref: str  # MinIO URL
    confidence: float
    expires_at: datetime

class Dissent(BaseModel):
    plan_id: str
    team: str
    rejected_because: str            # 1-2 sentence rejection rationale
    minority_view: str | None         # if any board member sided with this plan
```

**Cost guardrail.** Board runs once per high-impact event. The 5 LLM-heavy roles (Bull, Bear, 3 Risk) are quick-thinking-LLM (DeepSeek Flash); only the Board Chair is deep-thinking-LLM (DeepSeek Pro). Per-event budget: ≤ $0.30. Hard cap via the cost circuit breaker (T1.9). If breaker is open, the Board falls back to "highest-confidence plan wins, no debate, dissent_record empty" — explicitly logged.

**Acceptance.** Board decision JSON validates; transcript files in MinIO; dissent record is non-empty when teams disagreed; advice ledger entry exists with hash chain. Synthetic disagreement test (force teams to disagree) shows the dissent record clearly. **Depends on:** T2.2, T2.3, T0.1.

**Reuse note.** TradingAgents' `bull_researcher.py`, `bear_researcher.py`, three risk-debator prompts, and the `ResearchPlan` Pydantic shape are Apache-2.0 and trivially portable to IIC's prompt registry. Per C4 (this plan): NOTICE entry + top-of-file copyright header. ~3 engineer-days for the port + IIC's disclaimer pipeline wrapper.

## T2.5 Live benchmarking — every plan and every team

**Problem.** Today the leaderboard is per-agent. The new workflow needs per-plan and per-team scorecards, with live market data feeding the comparison.

**Action.**

- Backtest agent extends to consume `plan.v1` events: opens a paper-trading position at `entry_price` when the live mark crosses into `[entry_window_open, entry_window_close]` and the price is in the entry band; mark-to-market hourly using live quotes; closes at `target_price`, `stop_loss`, or `expires_at` whichever first. Records realized P&L, alpha vs SPY (or HSI for HK tickers), max drawdown realized vs predicted, time-to-target.
- Per-team and per-plan scorecards live in `lake.plan_scorecard` (new Postgres table). Schema in Appendix C.
- Dashboard route `/leaderboard` extended: tabs for `agent (legacy)`, `team`, `plan`, `persona`. Each tab shows hit-rate, alpha, Sharpe, max drawdown, sample size.
- Weekly Sunday 18:00 leaderboard publication DAG (was A3.4) WeCom push with rank-change diff vs prior week.
- The Backtest team runs **parallel** to the Investment Board — they receive the same `plan.v1` events and grade independently. The Board does not see Backtest scorecards on the same event (those grades come days/weeks later). The Board sees Backtest scorecards from **prior** events in the team's `past_context`.

**Acceptance.** A trigger event 30 days ago produced N plans; today the dashboard shows scorecards for all N. WeCom weekly recap shows team rankings. **Depends on:** T1.11, T2.2, T2.3.

## T2.6 Plan delivery to user — best plan + all plans

**Workflow requirement.** The user wants both: the best plan (Board's pick) AND all plans (transparency).

**Action.**
- Secretary's `compose_brief` extended: produces a "Trading Room Brief" markdown with sections (a) Triggering event, (b) Board recommendation, (c) All team plans (one paragraph each, including the rejected ones with the dissent record), (d) Live benchmark snapshot.
- Push to all configured channels (WeCom, ServerChan, ntfy, SMTP) per the existing notifier router.
- Dashboard route `/trading-room` shows the live trading-room state: triggering event, plans-in-flight, board status (debating | decided | failed), board decision card, deferred-notify queue.
- Per-channel mute / quiet hours (was A7.1) — defaults configured so WeCom does not push trading-room briefs after 22:00 local; CRITICAL severity always pushes regardless.
- "Explain to my mom" tone (was A7.2) — accessible via dashboard toggle and `/why-plain` slash command in WeChat.

**Acceptance.** Synthetic trading-room run produces a brief that includes both the chosen plan and the rejected plans with dissent. **Depends on:** T1.4, T2.4, T2.5.

## T2.7 FUTU OpenAPI integration (read-only, multi-account)

**Problem.** Analysis teams and the Investment Board don't know what Ziwei actually holds. Knowing the current portfolio is worth a measurable bump in plan quality (avoid recommending what's already overweight; avoid stops that conflict with cost basis; surface tax-lot considerations).

**Architecture.** Two-process design forced by FUTU's OpenD gateway model:

- **OpenD instances** — FUTU's Python SDK requires running `OpenD` (a desktop gateway) per logged-in Futu ID. Multi-account support requires multiple OpenD instances on different ports. We run one OpenD per Futu ID, each on its own port (11111, 11112, ...), each with its own credentials volume mount.
- **`agent_futu` service** — a new IIC service that opens a `OpenTradeContext` to each OpenD, queries holdings, funds, and historical orders, normalizes across accounts, and publishes a `portfolio.snapshot.v1` event every 5 minutes during market hours and on demand.

**Read-only enforcement (defense in depth):**

1. **Never call `unlock_trade()`.** Without it, FUTU physically rejects any order placement at the gateway level even if a bug attempts one. This is the load-bearing safeguard.
2. **Wrapper class** `FutuReadOnlyClient` exposes only: `get_acc_list`, `accinfo_query`, `position_list_query`, `order_list_query` (open orders for context, but no `place_order`), `history_order_list_query`, `history_deal_list_query`, `get_market_state`. Never re-exports `place_order`, `modify_order`, `cancel_order`. Type-checked: `mypy --strict` will refuse a build that imports the forbidden methods.
3. **Network-level** — the agent's container has firewall rules blocking outbound to FUTU's order-routing endpoints; only OpenD's local socket is reachable.
4. **Audit log** — every FUTU API call writes to `lake.futu_audit` (Postgres) with method, args, account, and result. Hash-chained like the advice ledger.

**Schema** `PortfolioSnapshotV1`:

```python
class PortfolioSnapshotV1(BaseModel):
    schema_version: Literal["portfolio.snapshot.v1"] = "portfolio.snapshot.v1"
    snapshot_at: datetime
    accounts: list[AccountState]
    aggregate: AggregateState

class AccountState(BaseModel):
    futu_id: str          # hashed; never raw
    account_id: str       # FUTU account_id
    market: Literal["HK", "US", "CN", "FX", "FUND"]
    base_currency: str
    nav_base_ccy: float
    cash_base_ccy: float
    purchasing_power_base_ccy: float
    positions: list[PositionState]

class PositionState(BaseModel):
    asset: Asset                    # reuses advice.v1 Asset
    qty: float
    cost_basis_per_share: float
    avg_cost_currency: str
    market_value_base_ccy: float
    unrealized_pnl_base_ccy: float
    open_orders_count: int           # for context only
```

**`portfolio_context` field on plan.v1** (T2.2). Each team plan can carry the relevant slice of the portfolio snapshot — current position in this ticker, current open orders on this ticker, percentage of NAV — so the Board's debate is grounded in what Ziwei actually owns.

**Multi-account topology.**

- Run N OpenD containers (`futu-opend-1`, `futu-opend-2`, ...) per Futu ID. Each has its own bind mount under `/srv/iic/futu/<futu_id_hash>/` for credentials and config.
- The `agent_futu` service iterates all configured OpenDs at boot, opens a `FutuReadOnlyClient` per OpenD, and aggregates.
- Adding a new Futu ID = (1) provision a new OpenD container with credentials, (2) add an entry to `agents/agent_futu/config/futu_ids.yaml`, (3) bounce `agent_futu`. No code change.

**Bind-mount layout** under `/srv/iic/futu/`:
- `<futu_id_hash>/openD-config/` — OpenD's encrypted credential store
- `<futu_id_hash>/openD-logs/` — OpenD logs (rotated)
- `<futu_id_hash>/snapshots/` — local cache of last-known snapshot for offline resilience

**Cost.** FUTU's API is free for personal use. Zero LLM cost. The marginal infra cost is N OpenD containers (~150 MB each) + Postgres rows for the audit log.

**Acceptance.**
- `agent_futu` can read positions across 2+ Futu IDs; aggregate snapshot validates schema.
- A unit test imports the `FutuReadOnlyClient` wrapper and tries to call `place_order` — fails with `AttributeError`.
- A static check (`bandit` rule + custom mypy plugin) flags any direct import of `futu.OpenSecTradeContext.place_order` outside `tests/`.
- Synthetic test: verify that without `unlock_trade()`, FUTU rejects an order placement attempt (even if a malicious bypass made it through the wrapper).
- Audit log shows every call; hash chain verifies.

**Depends on:** T0.1 (feature flag `agent_futu.enabled`), T2.2.

## T2.8 Trading-room DAG end-to-end

**Action.** New orchestrator DAG `trading_room.py` that ties T2.1–T2.7 together. Triggered by `intel.event.high_impact.v1`. Topology:

```
n_event_triage_gate (already done by agent_event_triage; this node validates the event)
    └─> n_fetch_portfolio_context  (calls agent_futu for current portfolio, attaches to state)
        ├─> n_team_quant
        ├─> n_team_fundamental
        ├─> n_team_persona  (8 personas internally; aggregated)
            (all three run in parallel)
            └─> n_plan_aggregator (collects plan.v1 events into state)
                ├─> n_board_debate (Bull/Bear → Risk → Chair)
                └─> n_backtest_grade  (parallel to board; grades the plans against the live market feed start)
                    └─> n_secretary_brief
                        └─> n_compose_brief + n_deliver_brief (T1.4 split)
```

Per-node SLA via `SLA_TABLE`. Idempotency key: `(trigger_event_id, ticker)`. Throttle: max 1 firing per ticker per 30 min.

**Acceptance.** Synthetic high-impact event runs the DAG end-to-end in < 4 min wall-clock; brief lands in WeCom; all events appear in advice ledger with hash chain. **Depends on:** T2.0–T2.7.

## T2.9 Bull/Bear research debate at the Fundamental layer (was A4.2)

**Action.** Inside `agent_fundamental/fund/writer.py`, add a two-turn bull/bear pass before the final plan write. Each side reads the DCF + multiples + filings excerpts and produces a 3-sentence argument. Final plan explicitly addresses both. Fundamental's `plan.v1` therefore arrives at the Board pre-debated. **Depends on:** T2.2. *Reuse: TradingAgents `bull_researcher.py` + `bear_researcher.py` prompts.*

## T2.10 Indicator-taxonomy block for the Quant team (was A4.5)

**Action.** Add a system-prompt fragment in `agent_quant/quant/writer.py` that lists 12 canonical indicators (50 SMA / 200 SMA / 10 EMA / MACD / MACDS / MACDH / RSI / Bollinger upper/middle/lower / ATR / VWMA), one-line usage and one-line caveat per indicator, and instructs the LLM to pick at most 8 non-redundant ones for the plan. **Depends on:** T2.2. *Reuse: TradingAgents `analysts/market_analyst.py` indicator block.*

---

# Section 4 — Tier 3: research depth and product expansion (former v3.0)

T3 begins after T2 has been in production ≥ 30 days with the cost cap holding. Each item is optional; ship in dependency order. Items rewritten / re-scoped relative to v3.0 as the architectural shift to the trading-room workflow makes some items easier and some redundant.

## T3.1 New analysis teams (was B1)

- **T3.1a Options-flow team** — UOA detection on watchlist, daily UOA brief, intraday alerts on threshold-cross. Feeds the Board as a fourth analysis team.
- **T3.1b On-chain team** — BTC/ETH/stablecoin universe; Glassnode (free tier) + on-chain RPC.
- **T3.1c Geopolitics team** — GDELT, ACLED, central-bank RSS. Tags events to affected sectors and regions. **High priority** — directly aligned with the project's geographic-balance goal.
- **T3.1d Macro-credit team** — credit spreads, repo, Fed balance sheet; emits a "credit weather" signal that gates risk-on / risk-off plans at the Board level.
- **T3.1e Alt-data team** — satellite + payment + web traffic; quarterly only.

Each new team is plug-in via the same `team_plan` endpoint contract from T2.3. The Investment Board does not need code changes — just a config update to include the new team in the fan-out.

## T3.2 Real-time streaming and tick-driven plans (was B2)

- **T3.2a Per-symbol NATS partitions** — `quotes.AAPL.v2` etc. Required before T3.2b.
- **T3.2b Tick-driven Quant team** — intraday signals (MACD cross, support break) wake the Quant team for the affected symbol only. Throttle: max 1 fire per symbol per 15 minutes. Plugs into the Event-Triage Gate as another candidate-event source.
- **T3.2c Live trade-tape view** — dashboard switches from polling to NATS-WS push for sub-second latency.

## T3.3 Multi-modal ingest (was B3)

- **T3.3a Chart-pattern recognition** — Claude Sonnet vision on rendered candlestick + indicator overlays. Output: `chart_pattern.v1` event consumed by Quant.
- **T3.3b Earnings-call audio** — Whisper-class STT + sentiment + topic over the transcript. "Tone vs prepared remarks" delta as a Quant signal.
- **T3.3c Satellite imagery** — Phase 1 free-tier (Sentinel-2 via Copernicus); Phase 2 commercial pixel imagery if budget allows.

## T3.4 Black-Litterman portfolio construction (was B4)

- **T3.4a Convert ratings to views** — per-ticker `plan.v1` ratings → Black-Litterman views (μ_view, Ω_view). Confidence maps to view strength. Cross-ticker correlation from rolling 252-day Pearson covariance.
- **T3.4b Optimizer** — mean-variance with BL posterior, sector caps, per-position max weight. Rebalances weekly. Outputs target weights.
- **T3.4c Paper-trade vs current portfolio** — Backtest moves toward target weights using existing paper-trading machinery. Tracks turnover and BL alpha.
- **T3.4d FUTU-grounded.** Because T2.7 made portfolio snapshots first-class, T3.4 can use the **actual** current portfolio as the BL prior, not a synthetic one. This is a meaningful improvement over the v3.0 plan.

## T3.5 StockBench external benchmark (was B5.2)

Run IIC against StockBench-defined episodes monthly; publish to dashboard. External reality check on the leaderboard. **Depends on:** T1.12.

## T3.6 Synthetic regime stress-test (was B5.3)

Crisis playback — 2008, 2020 March, 2022 H1 — replayed against the current agent fleet. Used as a kill-switch acceptance gate before any team is allowed to size positions above 2 % of paper portfolio.

## T3.7 Mobile app + per-user surfaces (was B6)

- **T3.7a Expo / React Native app** — push via APNs / FCM. Three core screens: trading-room, agent feed, leaderboard.
- **T3.7b Per-user dashboards** — different watchlists, persona fan-outs, cost caps.
- **T3.7c Read-only family share** — curated subset of briefs, scoped read-only token.

## T3.8 Federated personas + prompt marketplace (was B7)

- **T3.8a Custom-persona authoring** — YAML editor + LLM-assisted authoring + golden-set eval before promote.
- **T3.8b Persona benchmark** — independent of agent leaderboard.
- **T3.8c Prompt versioning UI** — A/B-compare two versions on the same input; promote button gated by walk-forward green.

## T3.9 Local-LLM tier (was B8 — restructured as a fork in the road)

**Two paths:**

- **Path A (portable, recommended)** — keep DeepSeek for everything. Raise cap to $130/month if needed. Stays cloud-portable; can move from Mac mini to any Linux box.
- **Path B (Mac-bound, cheaper)** — migrate `quick_thinking_llm` for analysts to local Ollama (Qwen 2.5 32B or Llama 3.3 70B). Drops baseline cost to ~$30/month. Ties IIC to Apple Silicon.

This is a Ziwei decision, not an engineering decision. Plan v3.0 implicitly picked Path B; v2.5 makes the trade-off explicit. Default to Path A unless Ziwei has explicit hardware commitment.

## T3.10 Cross-asset and macro overlay (was B9)

- **T3.10a Bonds and rates** — IG/HY ETFs, 2y/10y/30y curve. New asset_class field on `plan.v1`.
- **T3.10b FX** — DXY + 6 majors. Macro-credit team already touches; promote to its own surface.
- **T3.10c Commodities** — crude, gold, copper. Same pattern.

---

# Section 5 — Cross-cutting concerns

## C1. Suggestion-only constraint preserved

All v2.0 invariants carry through: suggestion-only, no broker integration in any tier (FUTU is read-only — see T2.7), every advice carries citations, persona disclaimer mandatory.

## C2. Cost discipline

- T1 introduces stricter cost telemetry (T1.9).
- T2 introduces the Investment Board, which is a cost-amplifier (5+ LLM roles per event). Mitigations: Flash for all roles except Chair; per-event budget cap; circuit breaker forces fallback to "highest-confidence wins."
- T3 expands the LLM surface significantly. Hard ceiling: $200 / month. Path A LLM strategy: this means ~$130–160 for production traffic, $30 reserved for chaos tests + walk-forward replays.

**Cost-cap chaos test (T1.9 + new C9).** Drives synthetic trading-room replays at 95% of cap and verifies breaker opens before overrun. Becomes acceptance for any item that expands LLM surface (T2.4 Board, T3.x).

## C3. Privacy and PII

- FUTU credentials stored encrypted under `/srv/iic/futu/<futu_id_hash>/` with sops + age. Never plaintext on disk, never in logs.
- The mobile app (T3.7a) — local-only logs, no third-party analytics SDKs.
- Family share (T3.7c) — scoped read-only tokens, never the primary auth.
- Portfolio snapshots are never broadcast outside the local network. Notifier briefs reference positions abstractly ("you're already long AAPL") not numerically.
- `futu_id` is hashed before any logging or telemetry; raw IDs are only in the OpenD's encrypted store.

## C4. Open-source attribution

Any TradingAgents-borrowed prompt or code (Apache-2.0) requires top-of-file copyright header + NOTICE entry at IIC repo root. New `NOTICE` file tracks every borrow with file path, source repo, license, date borrowed, and IIC's adaptation summary. CI gate: `tools/notice/check_notice.sh` fails the build if a borrowed file lacks a header.

## C5. Regression safety — feature flags everywhere

(promoted from C5 in v2.2 to T0.1) — every T1 / T2 / T3 item ships behind a feature flag. Rollbacks are flag-flips, not redeploys. No exceptions.

## C6. Documentation

Every new agent / DAG / endpoint adds a workflow document under `workflows/` (numbered consistently with v2.1's 00-31 scheme). v2.5 reserves:
- 32-39 for T0 + T1
- 40-49 for T2 (trading-room workflow + Investment Board + FUTU)
- 50-69 for T3

## C7. Eval-gate-as-a-bottleneck

Every prompt change runs through `prompt-eval.yml` CI before merge. v2.5 replaces this with a stronger gate: walk-forward CI (T1.12). Static eval is kept as a faster pre-screen.

## C8. NAS migration validation continues

`infra/nas/migrate.sh --dry-run` continues to run on every push. v2.5 adds new bind-mount paths (decision logs, FUTU credentials, futu audit logs, plan scorecards, NATS backups); the migration script handles them.

## C9. Cost-cap chaos test (new)

A nightly chaos test drives the LLM cost meter to 95% of cap during a synthetic trading-room run. Verifies the breaker opens, the Board falls back to "highest-confidence wins," and the brief still ships. CI gate.

## C10. FUTU audit transparency (new)

Every FUTU API call is hash-chained in `lake.futu_audit` (mirroring the advice ledger pattern). Daily 00:00 the chain head is committed to OpenTimestamps. The dashboard's `/audit` route shows a verification status badge + last-anchored timestamp.

---

# Section 6 — Acceptance gates

## v2.5 (T0 + T1) acceptance

ALL of:

1. T0.1 feature-flags package shipped, used by ≥ 1 T1 item, hot-reload verified.
2. T0.2 single source of truth for personas in production; YAML directory drift prevented by CI.
3. T0.3 SPOF acceptance ADR merged.
4. T1.1, T1.2, T1.3 critical fixes shipped, in production ≥ 14 days.
5. T1.4 notifier durable redelivery + compose/deliver split shipped, chaos test green.
6. T1.5 silent-drop surface closed: every cron has a DAG, every NATS subscription has a DAG, CI test in place.
7. T1.6 per-agent breaker shipped, chaos test green.
8. T1.7 NATS backup cron running, restore drill done once.
9. T1.8 memory caps in compose; chaos test (Chroma OOM) green.
10. T1.9 cost-breaker behavior pinned, chaos test green.
11. T1.10 PIT enforcement at ingest shipped.
12. T1.11 markdown decision log + Backtest reflection wired; every advice has a markdown entry.
13. T1.12 walk-forward CI gate live.
14. v2.1 acceptance criteria still green: prompt-drift CI, advice-ledger hash chain, NAS dry-run.

## v2.5 (T0 + T1 + T2) acceptance

Above plus:

1. T2.0 NATS request-reply substrate shipped; morning brief runs identically over either transport.
2. T2.1 Event-Triage Gate live; synthetic 10% drop fires the trading-room within 60 s.
3. T2.2 plan.v1 schema + validators shipped.
4. T2.3 every analysis team emits plan.v1.
5. T2.4 Investment Board operational; ≥ 30 trading-room runs in production with non-empty dissent records on at least 30% of them.
6. T2.5 live benchmarking surface live; per-team and per-plan scorecards visible in dashboard.
7. T2.6 Trading Room Brief delivered to user including chosen + rejected plans.
8. T2.7 FUTU read-only across ≥ 2 Futu IDs; static-check + runtime-check + network-firewall all enforce read-only; audit log hash-chain verified.
9. T2.8 trading-room DAG end-to-end SLA: < 4 min wall-clock for the median event.
10. T2.9 + T2.10 prompt upgrades shipped, walk-forward CI gate green.
11. C9 cost-cap chaos test green.
12. C10 FUTU audit chain anchored to OpenTimestamps daily.

## v3 (T3) acceptance

T3 items ship individually under their own feature flags. No bundle gate — each item ships when ready and walk-forward green.

---

# Section 7 — Architecture rework summary

This section answers the user's "plan any complete rework" prompt. Rather than a from-scratch rebuild, the rework is **additive + refactor**: keep v2.1's substrate, add three new layers (Event-Triage, Investment Board, FUTU), refactor the orchestrator's transport (T2.0), and close the silent-drop gaps (T1.5).

## 7.1 What stays — the v2.1 substrate

The architecture review found v2.1's substrate to be production-shaped:

- Hash-chained immutable advice ledger (Postgres + SQL trigger + revoked UPDATE/DELETE).
- LangGraph-shaped StateGraph orchestrator with per-node SLA + idempotency + ULID trace.
- Bind-mount-everything storage policy → trivial NAS migration.
- sqlglot-based PIT enforcement on the read side.
- Multi-provider LLM router with cache, fallback, rate limit, cost meter, circuit breaker.
- Pydantic-strict schema package with multi-layer disclaimer enforcement.
- Pro-tier slot semaphore on Redis.

These are kept as-is. T1 hardens them; T2 builds on them.

## 7.2 What's new — three new layers

**Layer 1: Event-Triage Gate (T2.1).** Sits between Intel and the analysis teams. Promotes IIC from cron-driven to event-driven. The architectural significance is that the **trigger surface** of the system is now: cron schedule (heartbeats only) + `intel.event.high_impact.v1` (the real action). This changes the system from "wakes up four times a day" to "wakes up when something interesting happens."

**Layer 2: Investment Board (T2.4).** Sits between the analysis teams and the user. Adds a structured debate + tribunal layer that produces a single chosen plan + a public dissent record. Architecturally, the Board is *another agent service* with its own container, its own LLM budget, its own decision schema, and its own audit trail. The teams remain authoritative for their plans; the Board is authoritative for which plan ships.

**Layer 3: FUTU portfolio oracle (T2.7).** Sits parallel to the data lake; not in the trigger path. Architecturally, the FUTU agent is **the only IIC service that talks to a third-party with potential for state mutation**, so it's the most security-sensitive component. Defense in depth: never `unlock_trade()` + wrapper class + mypy enforcement + network firewall + audit log + OpenTimestamps anchor.

## 7.3 What's refactored — transport + DAG coverage

**Refactor 1: Agent transport (T2.0).** Today every orchestrator → agent call is HTTP. T2.0 adds a NATS request-reply substrate and a feature flag to switch transports per DAG. The HTTP path stays as fallback; new DAGs can ride NATS for tighter latency + native trace propagation. Future T3.x (tick-driven plans, multi-modal events) lives natively on NATS.

**Refactor 2: DAG coverage (T1.5).** Close the silent-drop surface — every cron entry has a DAG, every NATS subscription has a DAG. CI fails if not.

## 7.4 What is NOT a complete rework

The user prompt invited "any complete rework." Three options were considered:

- **Option 1 (rejected): Rewrite on LangGraph.** The current StateGraph runner is LangGraph-shaped specifically to allow this. The cost is a heavy LangChain transitive dep + losing the `mypy --strict` typing benefits IIC's hand-rolled runner has. The benefit is sharing prompt templates with TradingAgents directly. **Verdict:** not worth it — the architecture review found the current runner production-shaped, and `T2.0` already plans the abstraction needed if a future swap is desired.
- **Option 2 (rejected): Move to a queue-based actor model (Temporal / Cadence).** Would give first-class durable workflow execution at the cost of a heavy new dependency and a learning curve. Today's idempotency + APScheduler-with-coalesce + StateGraph + `_active_dags` covers ≥ 90 % of what Temporal would buy us, at zero ops cost. **Verdict:** not worth it for a single-engineer single-host system.
- **Option 3 (rejected): Move from monorepo to per-agent microservices with separate repos.** Would give independent deploy cadence at the cost of cross-cutting refactors becoming PR-coordination problems. v2.1's monorepo has zero downside for one engineer. **Verdict:** not worth it.

The **chosen** rework is additive + refactor. Total scope: 3 new services, 3 refactor passes (transport, DAG coverage, persona-source-of-truth), 1 schema add (`plan.v1`).

## 7.5 Open architectural questions for Ziwei

These are decisions Ziwei should make explicitly, not the engineer:

1. **Path A vs Path B for LLM tier (T3.9).** Stays portable (Path A) or commits to Mac mini (Path B)? Default Path A.
2. **How many Futu IDs at launch?** The architecture supports N; the deployment burden is per-OpenD container. Recommend launching with 1 (Ziwei's primary), validating multi-account on a second test account in week 2, opening to family in T3.7c.
3. **How aggressive should the Event-Triage Gate be?** A loose gate wakes the Board too often (cost). A tight gate misses tail events. Recommend starting tight (z > 4 for sudden moves; news must be classified as `high_impact` by the gate LLM) and loosening based on observed Board hit rate.
4. **Family read-only mode (T3.7c) — when?** Likely after T3 stabilizes; not part of v2.5. But if Ziwei wants it earlier, it's small (~5 engineer-days) and primarily a UX item.

---

# Appendix A — Investment Board prompt skeletons

Sketches; final prompts live in `packages/prompts/registry/board.*` and are versioned with the rest. Each fragment includes the IIC disclaimer pipeline.

## A.1 Bull Researcher (board.bull.v1)

```
You are the Bull Researcher on the Investment Board. You have read N team
investment plans about ticker {{ticker}} triggered by event:
{{trigger_summary}}.

Your job: argue WHY the most aggressive buy plan is the right call.

Inputs:
- All team plans (JSON, plan.v1 envelope)
- The portfolio context: {{portfolio_context_summary}}
- Past Board decisions for this ticker: {{past_context_excerpt}}

Output: 3-5 sentence argument. Cite specific plan IDs you're championing.
End with one sentence on what evidence would change your mind.

Disclaimer: This is research for personal use only. Not financial advice.
```

## A.2 Bear Researcher (board.bear.v1)

Mirror of bull; argues the most conservative hold/sell plan.

## A.3 Three-way Risk Debators (board.risk.aggressive/conservative/neutral.v1)

```
You are the {{role}} Risk Debator on the Investment Board.

You have read:
- The Bull Researcher's argument
- The Bear Researcher's argument
- All team plans
- The portfolio context

Your job: in 2-3 sentences, take a position on which plan ships, weighted by
your role's risk preference. Aggressive favors bigger positions and wider
stops; Conservative favors smaller positions and tighter stops; Neutral
synthesizes.

Disclaimer: ...
```

## A.4 Board Chair (board.chair.v1)

```
You are the Board Chair, a deep-thinking LLM. You have read everything:
- All team plans (with portfolio_context attached)
- Bull/Bear debate transcript
- 3-way Risk debate transcript
- The N most recent Board decisions for this ticker (past_context)

Your job: produce a structured BoardDecisionV1 JSON output.
- Pick exactly one chosen_plan_id (or null if no plan should ship).
- Write a 4-6 sentence executive_summary.
- Write a 6-10 sentence investment_thesis.
- For every plan NOT chosen, write a Dissent with rejected_because and
  optional minority_view.
- Set rating to one of {Buy, Overweight, Hold, Underweight, Sell}.
- Set confidence in [0, 1] reflecting consensus strength after the debates.

Constraints:
- If two or more team plans agreed on action+ticker, prefer one of them.
- If teams disagreed strongly, set confidence ≤ 0.5 and explain in summary.
- Never recommend an action that violates the portfolio_context's risk
  cap (e.g., already 15% NAV in this ticker → prefer Hold).
- Write in plain English; no jargon; family-readable.

Disclaimer: ...
```

---

# Appendix B — FUTU OpenD deployment topology

```
                    ┌───────────────────────────────────────┐
                    │   IIC host (Mac mini / Linux mini-PC) │
                    │                                        │
                    │   ┌────────────────────────────────┐  │
                    │   │  agent_futu container          │  │
                    │   │  (Python; FutuReadOnlyClient)  │  │
                    │   └──────────┬───────────────┬─────┘  │
                    │              │               │        │
                    │              ▼               ▼        │
                    │   ┌──────────────────┐ ┌──────────┐   │
                    │   │ futu-opend-1     │ │ ...      │   │
                    │   │ (Futu ID #1)     │ │          │   │
                    │   │ port 11111       │ │          │   │
                    │   └──────────────────┘ └──────────┘   │
                    │              │                         │
                    │              ▼                         │
                    │   ┌────────────────────────────────┐  │
                    │   │  outbound firewall:            │  │
                    │   │  ALLOW: openapi.futu market    │  │
                    │   │  DENY:  openapi.futu trade-route│  │
                    │   └────────────────────────────────┘  │
                    └───────────────────────────────────────┘
                                   │
                                   ▼
                       FUTU servers (cloud)
```

**Why one OpenD per Futu ID.** OpenD authenticates per Futu account at startup; one OpenD process can hold one logged-in session at a time. Multi-account = multiple OpenD instances on different ports. We run them in Docker for lifecycle parity with the rest of IIC.

**Bind-mount layout** (added to NAS migration script):

```
/srv/iic/futu/
├── futu_id_<hash1>/
│   ├── openD-config/      # encrypted credentials (sops + age)
│   ├── openD-logs/
│   └── snapshots/         # last-known good portfolio snapshot
├── futu_id_<hash2>/
└── futu_audit/            # hash-chained Postgres dump (mirrored under MinIO too)
```

**Adding a new Futu ID.**
1. Generate a hash via `tools/futu/add_id.sh <futu_id>` (creates the bind-mount, sops-encrypts the credentials).
2. Append to `agents/agent_futu/config/futu_ids.yaml`.
3. `docker compose up -d futu-opend-<n> agent_futu`.
No code change; no service restart elsewhere; no orchestrator reconfiguration.

---

# Appendix C — Live benchmarking schema

`lake.plan_scorecard` (Postgres) — mirrors `lake.advice` but at the plan level:

```sql
CREATE TABLE lake.plan_scorecard (
    plan_id            text PRIMARY KEY,
    team               text NOT NULL,
    persona_slug       text,
    asset_kind         text NOT NULL,
    ticker             text NOT NULL,
    issued_at          timestamptz NOT NULL,
    action             text NOT NULL,
    entry_price        numeric NOT NULL,
    target_price       numeric NOT NULL,
    stop_loss          numeric NOT NULL,
    horizon_days       int NOT NULL,
    max_drawdown_pct   numeric NOT NULL,
    -- live-market grades
    realized_entry_at  timestamptz,
    realized_exit_at   timestamptz,
    exit_reason        text CHECK (exit_reason IN ('target','stop','timeout','superseded')),
    realized_pnl_pct   numeric,
    realized_alpha_vs_spy_pct numeric,
    realized_max_dd_pct numeric,
    time_to_target_days numeric,
    -- audit
    last_updated_at    timestamptz NOT NULL DEFAULT now(),
    chained_to_advice  text REFERENCES lake.advice(id)
);
CREATE INDEX plan_scorecard_team_idx ON lake.plan_scorecard(team, issued_at);
CREATE INDEX plan_scorecard_ticker_idx ON lake.plan_scorecard(ticker, issued_at);
```

**Per-team rollups** (materialized view, refreshed nightly):

```sql
CREATE MATERIALIZED VIEW lake.team_scorecard_30d AS
SELECT
    team,
    persona_slug,
    count(*) AS plans_n,
    avg(realized_pnl_pct) FILTER (WHERE realized_pnl_pct IS NOT NULL) AS avg_pnl,
    avg(realized_alpha_vs_spy_pct) FILTER (WHERE realized_alpha_vs_spy_pct IS NOT NULL) AS avg_alpha,
    avg(realized_max_dd_pct) FILTER (WHERE realized_max_dd_pct IS NOT NULL) AS avg_realized_dd,
    avg(realized_max_dd_pct - max_drawdown_pct) FILTER (WHERE realized_max_dd_pct IS NOT NULL) AS dd_overshoot,
    sum(CASE WHEN exit_reason = 'target' THEN 1 ELSE 0 END)::float / nullif(count(*), 0) AS hit_rate
FROM lake.plan_scorecard
WHERE issued_at > now() - interval '30 days'
GROUP BY team, persona_slug;
```

**Dashboard tabs** under `/leaderboard`:
- `team` — Quant / Fundamental / Persona / Intel / Board (chosen-plan composite)
- `plan` — every plan, sortable by team, age, alpha, hit-rate
- `persona` — break out the 8 personas
- `agent` — legacy v2.1 agent leaderboard (kept for continuity)

---

**End of Deliverable 4. Plan v2.5.**
