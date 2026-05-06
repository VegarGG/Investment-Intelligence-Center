# Workflow 05 — Data Bus & Shared Schemas

> **Depends On:** `01_INFRASTRUCTURE_AND_HOST.md`, `02_DATA_LAYER.md`.
> **Owns:** NATS JetStream configuration, `packages/data-bus/`, `packages/schema/`, the `advice.v1` contract, all event schemas.
> **Status:** Final.

---

## 1. Purpose

The bus is the nervous system. Every cross-agent fact flows through NATS JetStream as a typed event. Schemas live in one package so producers and consumers cannot drift.

Three reasons NATS JetStream over alternatives:

1. **Durable streams + KV store** in one binary. We need both: events for fan-out, KV for shared state (e.g., "current macro regime").
2. **At-least-once delivery with acks.** Backtester cannot afford to lose `advice.v1` events.
3. **Single-process footprint.** ~50 MB RAM idle, fits on the mini-PC trivially.

---

## 2. Ground Truth — Topics (Subjects)

📌 **Stable subject names.** All schema-versioned. `.v{n}` is the schema version, never a JetStream stream name.

```
intel.digest.v1                     # Intelligence agent → world
intel.dashboard.v1                  # Intelligence → dashboard UI feed
intel.brief.v1                      # Intelligence → secretary, for WeChat morning brief

advice.fundamental.v1               # Fundamental → backtester, secretary, dashboard
advice.quant.v1                     # Quant → backtester, secretary, dashboard
advice.persona.<slug>.v1            # Persona → backtester, secretary, dashboard
                                     # slugs: rogers|buffett|soros|druckenmiller|wood|dalio|burry|degen

backtest.fill.v1                    # Backtester → originating agent (memory loop), secretary
backtest.daily.v1                   # Backtester → dashboard
backtest.leaderboard.v1             # Backtester → dashboard

secretary.notify.v1                 # Secretary → packages/notifier
ops.heartbeat.v1                    # All services → orchestrator
ops.alert.v1                        # All services → secretary → WeCom alerts bot
```

📌 **Streams (durable storage on disk at `/srv/iic/nats`):**

| Stream | Subjects bound | Retention | Replicas |
|--------|----------------|-----------|----------|
| `INTEL` | `intel.>` | 30 d | 1 |
| `ADVICE` | `advice.>` | forever (mirror to PG `lake.advice` is canonical) | 1 |
| `BACKTEST` | `backtest.>` | 365 d | 1 |
| `SECRETARY` | `secretary.>` | 7 d | 1 |
| `OPS` | `ops.>` | 14 d | 1 |

Subjects with no `.v{n}` suffix are **rejected** by a JetStream policy guard in `data_bus.publish()`.

📌 **KV buckets (NATS KV):**

| Bucket | Purpose | Sample keys |
|--------|---------|-------------|
| `iic_state` | Cross-agent runtime state | `macro_regime`, `vix_quintile`, `circuit_breaker_state` |
| `iic_locks` | Short-lived advisory locks | `daily_run.fundamental.2026-05-06` |
| `iic_versions` | Active prompt + schema versions | `prompt.intel.synth=1.0.0` |

---

## 3. Ground Truth — `advice.v1`

**The single most important contract in the system.** Every advisory agent emits this; the backtester consumes it; the secretary explains it; the dashboard renders it.

```jsonc
{
  "schema": "advice.v1",
  "id": "01HZ8KQ5W6Y3Q5T4R3M2N1B0A9",          // ULID
  "agent": "fundamental | quant | persona.rogers | …",
  "issued_at": "2026-05-06T13:30:00-07:00",
  "asset": {
    "kind": "equity | etf | future | option | fx | crypto | bond",
    "ticker": "INTC",
    "venue": "NASDAQ",
    "name": "Intel Corp"
  },
  "thesis": "≤500 words, plain English",
  "direction": "long | short | flat",
  "confidence": 0.62,                           // 0–1
  "entry_band": [89.0, 91.5],                   // [low, high] in asset's currency
  "target_band": [95.0, 100.0],
  "stop_loss": 85.0,
  "horizon_days": 7,
  "max_drawdown_pct": 6.0,
  "sizing_hint_pct_nav": 2.5,                   // suggested % of NAV
  "expires_at": "2026-05-13T13:30:00-07:00",
  "evidence": [
    {"kind": "news",   "ref": "intel.digest.v1#evt-7"},
    {"kind": "filing", "url": "https://www.sec.gov/..."}
  ],
  "disclaimer": "Stylized agent inspired by public writings; not Mr. Rogers."  // persona only
}
```

📌 **Hard validators** (in `packages/schema/`):

- `id` is a ULID.
- `confidence ∈ [0, 1]`.
- `entry_band[0] ≤ entry_band[1]`.
- For `direction=long`: `entry_band[1] < target_band[0]` AND `stop_loss < entry_band[0]`.
- For `direction=short`: mirrored — `target_band[1] < entry_band[0]` AND `stop_loss > entry_band[1]`.
- For `direction=flat`: `target_band == entry_band == [px, px]` and `stop_loss` ignored.
- `evidence` non-empty for `direction != flat`. Backtester rejects uncited advice.
- `expires_at - issued_at <= 365 days` (sanity).
- `agent.startswith("persona.")` ⇒ `disclaimer` non-empty.

---

## 4. Other Event Schemas

### 4.1 `intel.digest.v1`

```jsonc
{
  "schema": "intel.digest.v1",
  "id": "01HZ8KQ5...",
  "issued_at": "2026-05-06T06:30:00-07:00",
  "macro_regime": "rate_cut | risk_on | risk_off | stagflation | recession | crisis | unknown",
  "events": [
    {
      "id": "evt-7",
      "rank": 1,
      "headline": "Fed cuts 25 bp; signals two more in 2026",
      "why_it_matters": "...",
      "primary_asset_links": ["DXY", "TLT", "EWZ", "GLD"],
      "regime_change_score": 0.81,
      "novelty": 0.92,
      "sentiment": -0.1,
      "sources": [{"id": "rss:reuters", "url": "..."}, ...]
    }, ...
  ],
  "bias_balance": {
    "by_region": {"US": 0.35, "EU": 0.20, "CN": 0.20, "EM": 0.15, "OTHER": 0.10},
    "by_lean":   {"left": 0.30, "center": 0.45, "right": 0.10, "state": 0.15}
  },
  "macro_thesis": "One paragraph titled 'Today's macro thesis.'"
}
```

### 4.2 `intel.brief.v1`

```jsonc
{
  "schema": "intel.brief.v1",
  "issued_at": "2026-05-06T06:30:00-07:00",
  "audience": "principal | family",
  "language": "en | zh",
  "markdown": "## Morning Brief — 2026-05-06\n> 3 high-conviction moves, 1 macro alert\n\n**1. INTC long ...**",
  "char_count": 1240,
  "wechat_safe": true                         // <= 4096 chars, no HTML in markdown body
}
```

### 4.3 `intel.dashboard.v1`

JSON snapshot consumed by the dashboard. Full shape in `21_DASHBOARD_UI.md` §4.

### 4.4 `backtest.fill.v1`

```jsonc
{
  "schema": "backtest.fill.v1",
  "advice_id": "01HZ8KQ5...",
  "agent": "persona.rogers",
  "opened_at": "2026-05-06T20:30:00Z",
  "closed_at": "2026-05-13T17:55:00Z",
  "entry_px": 90.25,
  "exit_px": 96.10,
  "exit_reason": "target | stop | expiry | early_close",
  "pnl_usd": 5850,
  "pnl_r": 1.4,
  "max_dd_during_trade_pct": 3.1,
  "narrative": "Filled mid-band; news-driven gap on day 3 ..."
}
```

### 4.5 `backtest.daily.v1` and `backtest.leaderboard.v1`

```jsonc
// backtest.daily.v1 — emitted at market close
{
  "schema": "backtest.daily.v1",
  "date": "2026-05-06",
  "agent_pnl": {
    "fundamental":         {"pnl_usd": 1230.4,  "trades_closed": 2, "trades_open": 5},
    "quant":               {"pnl_usd": -440.1,  "trades_closed": 4, "trades_open": 9},
    "persona.rogers":      {"pnl_usd": 5850.0,  "trades_closed": 1, "trades_open": 3},
    "...":                 {}
  },
  "benchmark_pnl": {"passive": 540.0, "smart_passive": 612.5}
}

// backtest.leaderboard.v1 — emitted weekly
{
  "schema": "backtest.leaderboard.v1",
  "as_of": "2026-05-06",
  "entries": [
    {
      "agent": "persona.rogers",
      "trades_closed": 27,
      "hit_rate": 0.59,
      "r_avg": 0.41,
      "sharpe": 1.32,
      "sortino": 1.81,
      "calmar": 0.94,
      "max_dd_pct": 11.4,
      "vs_smart_passive_pct": 4.2,
      "score": 1.27,
      "provisional": false
    }, ...
  ]
}
```

### 4.6 `secretary.notify.v1`

```jsonc
{
  "schema": "secretary.notify.v1",
  "severity": "info | warn | alert | critical",
  "channel_hint": "briefs | alerts | fills | chat",
  "language": "en | zh",
  "markdown": "...",
  "mentioned_list": ["@all"]  // optional
}
```

### 4.7 `ops.heartbeat.v1` and `ops.alert.v1`

```jsonc
// heartbeat — every 60 s per service
{
  "schema": "ops.heartbeat.v1",
  "service": "agent_intelligence | agent_quant | ...",
  "ts": "2026-05-06T13:30:00Z",
  "uptime_s": 73215,
  "queue_depth": 4,
  "errors_last_5m": 0
}

// alert — anomaly raised
{
  "schema": "ops.alert.v1",
  "severity": "warn | alert | critical",
  "service": "...",
  "code": "LLM_COST_BREAKER_OPEN | NVME_WEAR_HIGH | PROMPT_DRIFT | ...",
  "message": "Free disk on /srv/iic dropped below 15%",
  "context": {...}
}
```

---

## 5. Module Layout — `packages/schema/`

```
packages/schema/
├── pyproject.toml
├── schema/
│   ├── __init__.py
│   ├── advice.py             # AdviceV1 + validator
│   ├── intel.py              # IntelDigestV1, IntelBriefV1, IntelDashboardV1
│   ├── backtest.py           # BacktestFillV1, BacktestDailyV1, BacktestLeaderboardV1
│   ├── secretary.py          # SecretaryNotifyV1
│   ├── ops.py                # OpsHeartbeatV1, OpsAlertV1
│   ├── canonical.py          # canonical JSON serialization (deterministic)
│   └── ts/                   # generated TypeScript via datamodel-code-generator
│       ├── advice.ts
│       └── ...
└── tests/
    ├── test_advice_validators.py
    ├── test_canonical_json.py
    └── test_persona_disclaimer.py
```

📌 **Generation flow.** Pydantic v2 is the source of truth. TypeScript types are generated by `datamodel-code-generator` in CI. Don't hand-edit the TS files.

---

## 6. Module Layout — `packages/data-bus/`

```
packages/data-bus/
├── pyproject.toml
├── data_bus/
│   ├── __init__.py
│   ├── client.py             # NatsClient wrapper
│   ├── streams.py            # stream provisioning
│   ├── subjects.py           # the §2 subject list as constants
│   ├── publish.py            # publish(subject, payload)
│   ├── subscribe.py          # subscribe(subject, durable_name, handler)
│   ├── kv.py                 # KV bucket helpers
│   └── tracing.py            # OpenTelemetry context propagation
└── tests/
    ├── test_publish_subscribe.py
    ├── test_versioned_subject_guard.py
    └── test_kv.py
```

Public surface:

```python
# data_bus/publish.py
async def publish(subject: str, payload: BaseModel | dict, *, idempotency_key: str | None = None) -> str: ...

# data_bus/subscribe.py
@dataclass
class Subscription:
    cancel: Callable[[], Awaitable[None]]

async def subscribe(
    subject: str,
    durable_name: str,
    handler: Callable[[Msg], Awaitable[None]],
    *,
    queue_group: str | None = None,
    max_deliver: int = 5,
) -> Subscription: ...
```

`durable_name` ensures redeliveries survive consumer restart.

---

## 7. Architecture

```
   producer agent ─── publish(subject, payload) ─── data_bus ──► NATS JetStream
                                                                     │
                                                                     ▼
                                                              durable consumer
                                                                     │
                                                                     ▼
                                                             handler(msg)
                                                                ack / nak
                                                                     │
                                                                     ▼
                                                       (sink: Postgres lake.* or
                                                        next-step processor)
```

**Idempotency:** `publish()` accepts an `idempotency_key`. JetStream's per-message dedupe window (60 s) catches retries. For longer-window dedupe (e.g., advice retries during a partition), the Postgres ledger uses ULID primary keys with `ON CONFLICT DO NOTHING` semantics in `data_lake.advice_ledger.append`.

**Observability:** every publish/consume call emits an OpenTelemetry span. Trace IDs propagate via the `Nats-Trace-Id` header so a single morning brief can be traced from `intel.synth` → fan-out to advisors → fan-in to secretary.

---

## 8. Workflow Steps

### Step 8.1 — Provision NATS JetStream

Author `infra/nats/init.sh` to call `nats stream add` for each of the five streams in §2. Subjects, retention, replicas all per the table. Add `nats kv add iic_state`, `iic_locks`, `iic_versions`.

Run via `docker compose exec nats nats stream add ...` from the bootstrap. Idempotent.

### Step 8.2 — Build `packages/schema/`

Pydantic v2 models for every event. `AdviceV1.validate()` enforces every rule in §3. Add custom validators for direction-aware band consistency. Tests cover the full validator matrix.

### Step 8.3 — Build `packages/data-bus/`

Use `nats-py` async client. The `publish()` wrapper:
- Asserts subject ends with `.v\d+`.
- Uses `payload.model_dump(by_alias=True)` if Pydantic; otherwise asserts dict.
- Adds `Nats-Msg-Id` header from `idempotency_key`.
- Emits OpenTelemetry span.

The `subscribe()` wrapper:
- Wraps user handler in try/except → nak with backoff on exception.
- Auto-acks on successful return.
- Deserializes payload to the appropriate Pydantic model based on `subject`.

### Step 8.4 — Generate TS types

Add CI step `make codegen-ts` that runs `datamodel-code-generator --input packages/schema/schema --output packages/schema/ts`. Dashboard imports from there.

### Step 8.5 — Smoke test

`packages/data-bus/tests/test_publish_subscribe.py` spins up a local NATS in a fixture (testcontainers), publishes one advice, asserts the subscriber receives it within 1 s, asserts validators reject malformed payloads.

---

## 9. Vibe Prompts (paste-ready)

🧪 **Schema package:**
> Implement `packages/schema/` per `05_DATA_BUS_AND_SCHEMAS.md` §3–§4 with Pydantic v2. AdviceV1 enforces every validator in §3 verbatim, including direction-aware band consistency, persona disclaimer requirement, and ULID format. Add `canonical.py:canonical_json(model)` that produces deterministic JSON (sorted keys, no whitespace, ISO-8601 UTC timestamps). Generate TS via datamodel-code-generator into `schema/ts/`. Tests in `tests/test_advice_validators.py` cover at least 15 cases (long ok, short ok, flat ok, evidence missing, persona missing disclaimer, band inverted, stop on wrong side, ULID malformed, expiry > 365 d, ...).

🧪 **Data-bus package:**
> Implement `packages/data-bus/` per §6. NATS async client with auto-reconnect. `publish(subject, payload, *, idempotency_key=None)` enforces the `.v\d+` suffix and serializes Pydantic models. `subscribe(subject, durable_name, handler, *, queue_group=None, max_deliver=5)` wraps the handler with ack/nak logic and OpenTelemetry. Provide `kv.get/put/watch` for the three KV buckets in §2. Tests use testcontainers-nats to run an in-process NATS for the smoke test.

🧪 **NATS provisioning:**
> Author `infra/nats/init.sh` per §8.1. Idempotent. Five streams + three KV buckets. Run on `iic.service` startup via an init container. Verify post-conditions with `nats stream info <name>` exits zero for each.

---

## 10. Acceptance Criteria

- [ ] `nats stream ls` shows INTEL, ADVICE, BACKTEST, SECRETARY, OPS with the right retention.
- [ ] `nats kv ls` shows iic_state, iic_locks, iic_versions.
- [ ] `pytest packages/schema -q` is green; ≥ 15 validator cases for advice.
- [ ] `pytest packages/data-bus -q` is green; smoke test publishes and receives within 1 s.
- [ ] Publishing to `advice.v0` (no `.v\d+` valid suffix... actually `.v0` matches — pick a deliberately bad case like `advice.beta`) fails with `InvalidSubject`.
- [ ] Generated TS types exist at `packages/schema/ts/advice.ts` and import cleanly into the dashboard scaffold.
- [ ] An OpenTelemetry trace from a `intel.synth` → `advice.fundamental.v1` chain is visible end-to-end in Grafana's Tempo/Jaeger panel (Phase pre-30).

---

## 11. Risks & Gotchas

⚠️ **Schema additions vs. additions of required fields.** Adding an optional field is a no-bump change. Adding a required field is a breaking change → `.v2`. Default to optional with sane defaults; promote later.

⚠️ **NATS message size.** Default 1 MB. `intel.digest.v1` can approach this when events have long bodies. Strip raw HTML from event payloads before publishing — keep links, drop boilerplate. Long fields go to MinIO with a URL reference in the event.

⚠️ **Durable name collisions.** Two consumers with the same `durable_name` form a load-balanced queue group, which is sometimes what you want and sometimes a foot-gun. Convention: durable names are `<service>.<purpose>` (e.g., `agent_backtest.fills_in`).

⚠️ **JetStream disk pressure.** OPS stream retention is 14 d, but heartbeats every 60 s × N services can balloon. Keep heartbeats minimal (no full state dumps) and monitor `/srv/iic/nats` size in the Host dashboard.

⚠️ **Pydantic v2 serializer quirks.** Datetime fields default to `2026-05-06T13:30:00.000000-07:00` micro precision. Canonical JSON normalizes to second precision. Use the canonical helper for hash chains.

⚠️ **TS regeneration drift.** If a Python schema change isn't followed by `make codegen-ts`, the dashboard silently breaks. CI should fail when generated TS is stale (`git diff --exit-code` on `packages/schema/ts`).

⚠️ **At-least-once means duplicates.** Consumers must be idempotent. `data_lake.advice_ledger.append` already uses `ON CONFLICT DO NOTHING` on the ULID primary key — that's the canonical pattern.

---

## 12. Cross-References

- Validators called from agent writers: `11_AGENT_FUNDAMENTAL.md` §6, `12_AGENT_QUANT.md` §6, `13_AGENT_PERSONA.md` §6.
- Backtester subscriptions: `14_AGENT_BACKTEST.md` §5.
- Secretary subscriptions and notifier mapping: `15_AGENT_SECRETARY.md` §5 and `20_NOTIFIER_WECHAT.md` §6.
- KV bucket consumers (orchestrator reading `macro_regime`): `06_ORCHESTRATOR.md` §5.

---

## Changelog

- **v1.0** — Extracted from `PLAN_v2.1` §3 (advice contract) + §7 (orchestration) + topic table from §6. Stream retention and KV buckets formalized; validator matrix made explicit.
