# Workflow 06 — Orchestrator

> **Depends On:** `03_LLM_CLIENT.md`, `04_PROMPT_REGISTRY.md`, `05_DATA_BUS_AND_SCHEMAS.md`.
> **Owns:** `apps/orchestrator/` — DAG planning, agent fan-out/in, SLA enforcement, idempotency, shared runtime state, health endpoints.
> **Status:** Final.

---

## 1. Purpose

The orchestrator is the chief-of-staff at the system level (the *Secretary* is the chief-of-staff at the human level — different role). It decides:

1. **What runs when.** Translate triggers (cron, events, user requests) into a DAG of agent calls.
2. **What runs together.** Fan out an `intel.digest.v1` to fundamental + quant + persona × N concurrently, then fan in the responses.
3. **What gets dropped.** Enforce SLA timeouts. A persona that takes > 90 s on a daily run is canceled.
4. **What concurrency rules apply.** Max 4 Pro calls in flight at once (cost reasons).
5. **What state agents share.** `macro_regime` lives in NATS KV; the orchestrator is the writer.

The orchestrator does **not** know how to value a stock or read a filing. It knows how to **route**.

---

## 2. Ground Truth

### 2.1 Triggers

| Trigger | Source | Frequency / condition |
|---------|--------|-----------------------|
| `cron:morning_brief` | systemd timer in container | 06:30 PT daily |
| `cron:midday_check` | timer | 12:00 PT daily |
| `cron:evening_recap` | timer | 16:30 PT daily |
| `cron:hourly_intel` | timer | every hour, 06:00–22:00 PT |
| `cron:weekly_eval` | timer | Monday 09:00 PT |
| `event:intel.digest.v1` | NATS subscription | every digest publish |
| `event:earnings_release` | scheduled from `lake.calendar_events` | per-ticker timestamps |
| `event:filing` | EDGAR/HKEX webhook → bus | as filings arrive |
| `request:user` | secretary `/chat` calls | user-driven |

### 2.2 DAGs

📌 The orchestrator owns four canonical DAGs.

**DAG A — Morning Brief** (the most important):
```
                             cron:morning_brief
                                       │
                                       ▼
                       intel.synth (Pro)  ──► intel.digest.v1
                                       │
            ┌──────────────────┬───────┼────────────────┬──────────┐
            ▼                  ▼       ▼                ▼          ▼
       fundamental.run   quant.run   persona.rogers ... persona.degen
            │                  │       │                │          │
            └──────────────────┴───────┴────────────────┴──────────┘
                                       │ advice.*.v1 (fan-in)
                                       ▼
                                secretary.compose_brief (Pro)
                                       │ intel.brief.v1
                                       ▼
                                packages/notifier → WeCom briefs bot
```

**DAG B — Hourly Intel** (cheap, Flash-only): `intel.crawler.run` → `intel.synth_lite (Flash)` → `intel.dashboard.v1`. No advisor fan-out.

**DAG C — Earnings Reaction**: `event:earnings_release(TICKER)` → `fund.filings.refresh(TICKER)` → `fund.valuation(TICKER)` → `advice.fundamental.v1`.

**DAG D — Continuous Backtest**: independent loop in the backtest agent, not orchestrated. Marks-to-market every 60 s. Orchestrator only listens for `backtest.fill.v1` to surface significant fills via the secretary.

### 2.3 Concurrency rules

📌 **Stable.**

- Max 4 in-flight Pro calls system-wide. Enforced via a Redis semaphore `lock:pro_concurrency:N` (where N = 1..4).
- Unlimited Flash within the rate limiter's RPS cap.
- Per-agent max-in-flight: 1 (an agent does one thing at a time; multiple instances of the *same* persona slug do not exist).

### 2.4 SLA timeouts

| Agent call | Soft (warn) | Hard (cancel) |
|------------|-------------|---------------|
| `intel.synth` | 60 s | 120 s |
| `fundamental.run` | 45 s | 90 s |
| `quant.run` | 30 s | 60 s |
| `persona.daily` | 30 s | 90 s |
| `persona.weekly` | 60 s | 180 s |
| `secretary.compose_brief` | 30 s | 60 s |
| `secretary.chat` | 8 s | 20 s |

Soft = log a warning, continue. Hard = cancel the call, emit `ops.alert.v1` with severity `warn`, fall back to a stub message ("agent X did not respond in time — see dashboard for partial").

### 2.5 Shared state (NATS KV `iic_state`)

| Key | Writer | Readers | Update frequency |
|-----|--------|---------|------------------|
| `macro_regime` | orchestrator (from `intel.digest.v1.macro_regime`) | quant, persona | per digest |
| `vix_quintile` | quant agent | orchestrator (logging) | hourly |
| `cost_breaker_state` | llm-client | orchestrator (planning) | event-driven |
| `eval_drift_flag` | prompt-eval cron | secretary | weekly |
| `last_brief_at` | orchestrator | secretary | per brief |

Orchestrator's planning step reads `cost_breaker_state` — if `OPEN`, swap Pro callers to Flash where the matrix permits, or skip the DAG entirely and notify the user.

---

## 3. Architecture

```
                cron timers + NATS subjects + HTTP /run
                               │
                               ▼
                ┌──────────────────────────────┐
                │      apps/orchestrator       │
                │                              │
                │   trigger_router → planner   │
                │           │                  │
                │           ▼                  │
                │      DAG executor            │
                │  (asyncio + Redis semaphore) │
                │           │                  │
                │           ▼                  │
                │   data-bus publish/subscribe │
                │           │                  │
                │           ▼                  │
                │   merger → lake.advice       │
                │           │                  │
                │           ▼                  │
                │   secretary trigger          │
                └──────────────────────────────┘
```

**Implementation choice.** LangGraph or a custom asyncio state machine. The plan recommends LangGraph for the morning-brief DAG because nodes-as-async-functions and conditional edges are first-class. For the hourly cheap loop, a hand-rolled coroutine is simpler. Pick LangGraph and use it for both for consistency.

---

## 4. Module Layout

```
apps/orchestrator/
├── pyproject.toml
├── Dockerfile
├── orchestrator/
│   ├── __init__.py
│   ├── main.py                # FastAPI app + scheduler + NATS subscriber wiring
│   ├── triggers/
│   │   ├── cron.py            # systemd-timer-equivalent in-process
│   │   ├── nats_events.py
│   │   └── http.py            # POST /run/{dag} for manual kicks
│   ├── plan/
│   │   ├── __init__.py
│   │   ├── morning_brief.py   # DAG A
│   │   ├── hourly_intel.py    # DAG B
│   │   ├── earnings.py        # DAG C
│   │   └── chat_fanout.py     # secretary multi-agent question
│   ├── execute/
│   │   ├── runner.py          # async DAG runner (LangGraph)
│   │   ├── concurrency.py     # Redis semaphore wrapper
│   │   └── sla.py             # soft/hard timeout enforcement
│   ├── merge/
│   │   ├── advice_merger.py   # writes to lake.advice via ledger
│   │   └── normalizer.py      # asset normalization (INTC vs intc)
│   ├── state/
│   │   ├── kv.py              # NATS KV reads/writes for §2.5 keys
│   │   └── regime.py          # extract macro_regime from digest
│   ├── observability.py       # OpenTelemetry tracing
│   └── health.py              # /health endpoint
└── tests/
    ├── test_morning_brief_dag.py   # mocks every agent call
    ├── test_sla_cancellation.py
    ├── test_concurrency_semaphore.py
    └── test_idempotency.py
```

---

## 5. Public Surface

```python
# orchestrator/plan/morning_brief.py
async def run() -> MorningBriefResult: ...

# orchestrator/execute/runner.py
async def execute(dag: Graph, *, trace_id: str | None = None, timeout_s: float = 600) -> DagResult: ...

# orchestrator/main.py — HTTP
@app.post("/run/{dag_id}")
async def kick(dag_id: str, body: dict) -> DagResult: ...

@app.get("/health")
async def health() -> HealthSnapshot: ...
```

---

## 6. Workflow Steps

### Step 6.1 — Scaffold the FastAPI app

`main.py` boots:
1. Connect to NATS.
2. Subscribe `intel.digest.v1`, `backtest.fill.v1`, `ops.alert.v1`.
3. Start the in-process scheduler with the cron triggers from §2.1.
4. Mount HTTP routes.
5. Emit `ops.heartbeat.v1` every 60 s.

### Step 6.2 — Implement the morning-brief DAG (DAG A)

Use LangGraph. Nodes:

- `n_intel_synth`: call `apps/agent_intelligence` via HTTP (or direct in-process call if same container; we run separate containers per `01_INFRASTRUCTURE_AND_HOST.md`, so HTTP).
- `n_update_kv`: write `macro_regime` and `vix_quintile`.
- `n_fundamental`, `n_quant`, parallel `n_persona_<slug>` x N.
- `n_collect_advice`: gather `advice.*.v1` events with timeout.
- `n_secretary_brief`: call `apps/agent_secretary/compose_brief`.
- `n_notify`: call `packages/notifier` to send to WeCom.

Edges with `add_edge` for sequential, `add_conditional_edges` for the persona fan-out (skip personas whose weekly cadence isn't due today).

📌 The DAG carries a single `trace_id` (ULID generated at trigger time). All NATS publishes carry it as a header. All log lines include it.

### Step 6.3 — SLA enforcement

`execute/sla.py` wraps each node call in `asyncio.wait_for`:

```python
try:
    result = await asyncio.wait_for(node_fn(state), timeout=hard_s)
except asyncio.TimeoutError:
    await alert_bus.publish("ops.alert.v1", {
        "severity": "warn",
        "service": "orchestrator",
        "code": "AGENT_HARD_TIMEOUT",
        "message": f"{node_name} exceeded {hard_s}s",
        "context": {"trace_id": state.trace_id},
    })
    return SLAStub(node_name)
```

`SLAStub` carries a "did not respond" marker. Downstream nodes (e.g., `n_secretary_brief`) handle stubs gracefully — they include a "(N agents timed out)" note in the brief.

### Step 6.4 — Concurrency

Redis semaphore. On Pro-tier call:

```python
async with redis_lock("lock:pro_concurrency", capacity=4, timeout_s=300):
    return await llm_client.chat(...)
```

The wrapper ensures FIFO fairness. If saturated, secondary callers wait up to 300 s before failing.

### Step 6.5 — Advice merger

When `advice.*.v1` events arrive in the merging window:

1. Validate via `schema.AdviceV1`.
2. Normalize asset: `INTC` ≡ `intc` ≡ `Intel Corp` → canonical `INTC` via `normalizer.py` (uses Polygon's symbol-master).
3. Persist via `data_lake.advice_ledger.append`.
4. Stash into the DAG state for downstream nodes.

The merger emits `ops.alert.v1` if any agent's advice fails validation (e.g., persona missing disclaimer) — that's a code bug, not a market event.

### Step 6.6 — Idempotency

Every DAG run is keyed by `(dag_id, trigger_kind, trigger_at)`. Stored in Redis with 24 h TTL. If the same key fires twice (e.g., container restart re-running the cron), the second run is a no-op.

### Step 6.7 — Health endpoint

```jsonc
GET /health → {
  "service": "orchestrator",
  "uptime_s": 12345,
  "nats": "connected",
  "kv_state": {"macro_regime": "rate_cut", "cost_breaker_state": "closed"},
  "active_dags": [{"id": "morning_brief.2026-05-06", "started_at": "...", "stage": "n_persona_rogers"}],
  "last_completed": {"id": "hourly_intel.2026-05-06T13:00", "result": "ok"}
}
```

### Step 6.8 — Observability

OpenTelemetry spans for each node. Span tags: `dag_id`, `node_name`, `trace_id`, `agent`. Errors raised inside a node are captured into the span so Tempo/Jaeger shows the actual exception.

### Step 6.9 — HTTP `/run/{dag_id}` for manual kicks

Useful for debugging and for the "run brief now" button in the dashboard. POST with optional `{ "args": {...} }`. Returns the `DagResult`.

---

## 7. Vibe Prompts (paste-ready)

🧪 **Scaffold the orchestrator app:**
> Implement `apps/orchestrator/` per `06_ORCHESTRATOR.md`. FastAPI + LangGraph. Subscribe to NATS subjects per §6.1. Implement DAG A (morning brief) per §6.2 — start with mocked agent calls so the DAG can run end-to-end without the agents existing. SLA wrapper per §6.3. Redis semaphore per §6.4. Health endpoint per §6.7. Tests in `tests/` mock every agent call and assert the DAG visits nodes in the right order, that timeouts produce SLAStubs, and that idempotency keys block repeat runs.

🧪 **Trigger router:**
> Build `orchestrator/triggers/cron.py` per §2.1 using APScheduler (in-process, persistent jobstore in Redis so a container restart doesn't re-run jobs that already fired). `orchestrator/triggers/nats_events.py` subscribes to `intel.digest.v1`, `backtest.fill.v1`, `ops.alert.v1`. Each trigger funnels into the same `route(trigger)` function which emits a `Trigger` dataclass, looked up against the DAG registry.

🧪 **Advice merger:**
> Implement `orchestrator/merge/advice_merger.py` per §6.5. Validate via `schema.AdviceV1`. Normalize via `normalizer.py` using a Polygon symbol-master cached in `lake.symbol_master`. Persist via `data_lake.advice_ledger.append`. On validation failure, emit `ops.alert.v1` and write the offending payload to `/srv/iic/advice_ledger/quarantine/<ulid>.json` for human review. Tests cover normalization edge cases (lowercased, with venue suffix, ADRs, dual-listed CN tickers).

---

## 8. Acceptance Criteria

- [ ] `pytest apps/orchestrator -q` is green; the morning-brief DAG test runs end-to-end with mocked agents.
- [ ] Manually invoking `POST /run/morning_brief` triggers the DAG and (with all real agents up) produces a brief delivered to the WeCom briefs bot.
- [ ] Killing one persona container mid-run triggers an SLA timeout and emits a `ops.alert.v1` of severity `warn` within `hard_s + 5 s`.
- [ ] `redis-cli` shows `lock:pro_concurrency:*` keys when Pro fan-out is active; never exceeds 4 simultaneously.
- [ ] Restarting the orchestrator does not re-run a DAG whose idempotency key is still in Redis.
- [ ] Tracing UI shows a span tree for one morning-brief run with all nodes visible and timings sensible.
- [ ] `GET /health` returns 200 with the snapshot in §6.7.

---

## 9. Risks & Gotchas

⚠️ **APScheduler + container restarts.** Persist the jobstore in Redis (not in-memory) and use `coalesce=True` so missed runs fire at most once at recovery.

⚠️ **LangGraph state size.** State carries every advice + every digest. Don't pass full event bodies as state values — store in PG/MinIO and pass IDs.

⚠️ **Cron drift.** Container time vs. host time. Ensure the orchestrator container reads `TZ=America/Los_Angeles` from `.env` and NTP-syncs via the host (Docker default).

⚠️ **Cost breaker bypass.** When `cost_breaker_state=OPEN`, the orchestrator must skip Pro DAGs *before* attempting them — otherwise every node call fails individually and we waste agent boot time. Check the breaker at planner entry.

⚠️ **Idempotency window vs. legitimate re-runs.** A user clicking "regenerate brief" is a legitimate re-run. Provide a `force=true` query param on `/run/{dag_id}` that bypasses the idempotency cache.

⚠️ **Persona schedule drift.** Some personas run weekly; missed weeks should NOT silently disappear. The cron job for `cron:weekly_persona` queries `lake.advice` for last persona advice per slug; if > 9 days have passed, force a run regardless of weekday.

⚠️ **Trace-id propagation across HTTP.** Outgoing HTTP calls to agent containers must inject `Traceparent`/`X-Trace-Id`. Use `httpx` with an OpenTelemetry instrumentation hook.

⚠️ **Advice bombs.** If a misconfigured persona emits 1000 advices in a minute, the merger must throttle. Per-agent rate limit: max 10 advices per minute. Excess is dropped + alerted.

---

## 10. Cross-References

- Agent HTTP endpoints (`/run`, `/health`): each agent doc declares them in its module-layout section.
- KV bucket conventions: `05_DATA_BUS_AND_SCHEMAS.md` §2.
- Notifier wiring: `20_NOTIFIER_WECHAT.md` §6.
- Tracing dashboards: `30_OBSERVABILITY_AND_EVAL.md` §3.
- Cost breaker behavior: `03_LLM_CLIENT.md` §7.

---

## Changelog

- **v1.0** — Extracted from `PLAN_v2.1` §7. Concrete DAGs, SLA tables, and idempotency keys formalized. LangGraph adopted as the executor.
