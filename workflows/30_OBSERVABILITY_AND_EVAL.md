# Workflow 30 — Observability & Eval

> **Depends On:** `01_INFRASTRUCTURE_AND_HOST.md`, `02_DATA_LAYER.md`, `03_LLM_CLIENT.md`, `04_PROMPT_REGISTRY.md`, `05_DATA_BUS_AND_SCHEMAS.md`, `14_AGENT_BACKTEST.md`.
> **Owns:** `infra/observability/` — Grafana dashboards, Loki log shipping, Prometheus rules, Alertmanager routing, OpenTelemetry tracing, plus the eval harness wiring in production.
> **Status:** Final.

---

## 1. Purpose

Make the system legible. Three concerns, one workflow:

1. **Operational health.** Is everything up? Where is queue depth growing? Is the host on fire?
2. **Investment health.** What's the leaderboard saying? Where is the bias-balance trending? Is one factor decaying?
3. **Eval health.** Are the prompts drifting? Is Pro returning lower-quality answers than last month?

Everything is exposed in **one Grafana** instance with five canonical dashboards. Alertmanager routes high-severity alerts to the WeCom alerts bot via the notifier package.

---

## 2. Ground Truth

### 2.1 Stack

- **Prometheus** (metrics) + **node_exporter** + **cadvisor** + **postgres_exporter** + **nats_exporter** + custom service `/metrics` endpoints.
- **Loki** (logs) + **promtail** (log shipping).
- **OpenTelemetry Collector** (traces) → **Tempo** (storage) — Tempo runs alongside Grafana.
- **Grafana** for dashboards + Alertmanager.
- **All bind-mounts** under `/srv/iic/{prometheus,loki,grafana,tempo}` (see `01_INFRASTRUCTURE_AND_HOST.md` §2.6).

### 2.2 Five canonical dashboards

📌 **Stable.** Dashboards live under `infra/observability/grafana/dashboards/<id>.json`. JSON is committed; provisioned at boot via Grafana's file provisioner.

| ID | Title | Owns |
|----|-------|------|
| `iic-001-ops` | Operations | service heartbeats, queue depth, error rates, LLM cost burn, API rate-limit headroom |
| `iic-002-host` | Host | CPU temp, NVMe SMART (writes, wear, temp), RAM, fan RPM, UPS battery, disk free, NIC counters |
| `iic-003-data-freshness` | Data Freshness | feed lag, ingest counts, dedupe ratio, bias-balance, factor freshness, mark feed staleness |
| `iic-004-investment` | Investment Leaderboard | per agent: hit rate, R-multiple, Sharpe (with CI), max DD, vs benchmark, since-inception |
| `iic-005-trade-tape` | Trade Tape | live virtual fills + open positions table |

A separate `iic-006-eval` dashboard tracks prompt drift but is gated for power users.

### 2.3 Alert rules (Alertmanager → WeCom alerts bot)

📌 **Stable.** Severity → WeChat fanout per `20_NOTIFIER_WECHAT.md` §6.

| Code | Severity | Condition | Cooldown |
|------|----------|-----------|----------|
| `HOST_DOWN` | critical | scrape failure for `node_exporter` > 3 min | 30 min |
| `NVME_WEAR_HIGH` | warn | wear > 70% | 24 h |
| `NVME_WEAR_CRITICAL` | critical | wear > 80% | 6 h |
| `NVME_TEMP_HIGH` | warn | sustained > 70 °C for 5 min | 60 min |
| `CPU_TEMP_HIGH` | warn | sustained > 90 °C for 5 min | 60 min |
| `DISK_FREE_LOW` | warn | `/srv/iic` < 15% free | 6 h |
| `DISK_FREE_CRITICAL` | critical | < 5% free | 30 min |
| `UPS_BATTERY_LOW` | critical | battery < 50% AND `apcaccess STATUS != ONLINE` | 5 min |
| `LLM_COST_BREAKER_OPEN` | alert | breaker state OPEN | 60 min |
| `LLM_LATENCY_P95_HIGH` | warn | Pro p95 > 60 s for 10 min | 30 min |
| `AGENT_HEARTBEAT_MISSED` | alert | no `ops.heartbeat.v1` from a service for 5 min | 15 min |
| `PROMPT_EVAL_REGRESSION` | alert | weekly drift > 10% on any caller | 24 h |
| `BIAS_BALANCE_SKEW` | warn | any region > 0.55 in 7-day rolling avg | 24 h |
| `MARK_FEED_STALE` | warn | mark age > 5 min for any open position during market hours | 15 min |
| `ADVICE_LEDGER_BROKEN` | critical | chain integrity verify failed | none (paged immediately) |
| `BACKUP_FAILED` | alert | restic last backup > 36 h ago | none |

### 2.4 Tracing

OpenTelemetry instrumentation in every Python service via `opentelemetry-instrumentation-fastapi`, `instrumentation-asyncpg`, and a custom `instrumentation-nats` shim. Traces exported via OTLP to Tempo. Service names match container names.

📌 **Mandatory span attributes:**
- `trace_id` (auto)
- `dag_id` when available
- `caller_id` (for LLM calls — comes from llm-client)
- `agent` (e.g., `persona.rogers`)
- `advice_id` (when applicable)

---

## 3. Architecture

```
       services
          │
    /metrics & logs & traces
          │
   ┌──────┼─────────────┐
   ▼      ▼             ▼
 Prom   Loki          Tempo
   │     │             │
   └─────┴─────┬───────┘
               ▼
            Grafana ── Alertmanager ── WeCom alerts (via notifier)
```

---

## 4. Eval Harness in Production

Built in `04_PROMPT_REGISTRY.md` §5, but its **production wiring** lives here:

1. Weekly job: `prompt-drift-weekly.yml` Action runs the full golden set against each caller's current stable version using DeepSeek (or fallback) and writes a `lake.eval_runs` row with mean per-caller score.
2. The `iic-006-eval` Grafana dashboard reads from `lake.eval_runs` via the postgres datasource.
3. If any caller regresses > 10% versus its 4-week rolling baseline, fire `PROMPT_EVAL_REGRESSION`.

`lake.eval_runs` schema:

```sql
CREATE TABLE lake.eval_runs (
  id           UUID PRIMARY KEY,
  ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
  caller_id    TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  judge_version  TEXT NOT NULL,
  mean_score   DOUBLE PRECISION NOT NULL,
  per_prompt   JSONB NOT NULL,
  baseline_score DOUBLE PRECISION,
  regression_flag BOOLEAN NOT NULL DEFAULT false
);
SELECT create_hypertable('lake.eval_runs', 'ts', chunk_time_interval => INTERVAL '30 days');
```

---

## 5. Module Layout

```
infra/observability/
├── prometheus.yml
├── alertmanager.yml
├── loki-config.yml
├── tempo-config.yml
├── promtail-config.yml
├── otel-collector.yml
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/
│   │   │   ├── prometheus.yml
│   │   │   ├── loki.yml
│   │   │   ├── tempo.yml
│   │   │   └── postgres.yml
│   │   └── dashboards/
│   │       └── files.yml
│   └── dashboards/
│       ├── iic-001-ops.json
│       ├── iic-002-host.json
│       ├── iic-003-data-freshness.json
│       ├── iic-004-investment.json
│       ├── iic-005-trade-tape.json
│       └── iic-006-eval.json
└── alerts/
    ├── host.yml
    ├── llm.yml
    ├── data.yml
    └── investment.yml
```

---

## 6. Workflow Steps

### Step 6.1 — Prometheus + exporters

Compose the exporters as containers (see Compose skeleton in `01_INFRASTRUCTURE_AND_HOST.md` §5.3). Add:
- `postgres_exporter` (with a read-only DB user).
- `nats_exporter`.
- `cadvisor` (already in skeleton).
- Each Python service exposes `/metrics` via `prometheus-fastapi-instrumentator`.

### Step 6.2 — Loki + promtail

Promtail as a sidecar reads `/var/lib/docker/containers/*/*.log` and ships to Loki. Labels: `service`, `agent`, `severity`. Use the structlog JSON formatter so logs are queryable structured.

### Step 6.3 — Tempo + OpenTelemetry

OTel Collector receives via OTLP (gRPC 4317), writes to Tempo. Each service ships traces with the §2.4 mandatory attributes.

### Step 6.4 — Grafana provisioning

Datasources and dashboards provisioned at boot via files in `infra/observability/grafana/provisioning/`. Dashboards committed as JSON. **Don't edit dashboards in the UI without exporting back to the JSON file** — code review is the gate.

### Step 6.5 — Alert rules

Author per-domain rule files under `infra/observability/alerts/`. Alertmanager routes via:

```yaml
route:
  group_by: ["alertname", "severity"]
  receiver: 'iic-secretary'
receivers:
  - name: 'iic-secretary'
    webhook_configs:
      - url: 'http://agent_secretary:8086/notifier/alertmanager'
        send_resolved: true
```

The Secretary's `/notifier/alertmanager` endpoint converts the Alertmanager payload into a `secretary.notify.v1` event with the right severity. The notifier handles fanout.

### Step 6.6 — Custom metrics in services

Each agent emits domain metrics:

| Metric | Labels | Source |
|--------|--------|--------|
| `iic_advices_emitted_total` | agent, direction | every advice publish |
| `iic_advices_quarantined_total` | agent, reason | output validator failures |
| `iic_brief_delivered_seconds` | type | secretary, on successful WeCom send |
| `iic_factor_build_seconds` | factor_id | quant |
| `iic_filing_processed_total` | form, ticker | fundamental |
| `iic_dedupe_dropped_total` | source_id | intelligence |
| `iic_bias_region_share` | region | intelligence (gauge) |
| `iic_llm_cost_usd_30d` | tier | llm-client |
| `iic_open_positions` | agent | backtest |

### Step 6.7 — DR drill telemetry

The DR drill in `31_PRODUCTION_HARDENING.md` §5 is observed too: drill runs are tagged with `tag=dr_drill` so dashboards can filter them out of normal stats.

### Step 6.8 — Eval drift dashboard

`iic-006-eval` panels:
- Mean rubric score per caller, last 12 weeks.
- Regression flags timeline.
- Per-rubric-item heatmap (which rubric items are slipping).

---

## 7. Vibe Prompts (paste-ready)

🧪 **Provision the observability stack:**
> Author every file in `infra/observability/` per §5. Prometheus scrapes node_exporter, cadvisor, postgres_exporter, nats_exporter, and each service's `/metrics`. Loki + promtail ingest container logs with structured labels. Tempo receives OTel traces. Grafana provisioned with the six dashboards listed in §2.2 — committed as JSON. Alertmanager routes alerts to `agent_secretary:/notifier/alertmanager`. Add the `infra/observability/alerts/*.yml` rule files per §2.3. Idempotent: re-provisioning produces no diffs unless committed JSON changes.

🧪 **Service `/metrics` instrumentation:**
> Add `prometheus-fastapi-instrumentator` to every `apps/*` service. Custom metrics listed in §6.6. Wire OpenTelemetry per `opentelemetry-instrumentation-fastapi`, `instrumentation-asyncpg`, and a NATS shim that wraps publish/subscribe. Mandatory span attributes per §2.4.

🧪 **Alertmanager → Secretary bridge:**
> In `apps/agent_secretary/` add `/notifier/alertmanager` accepting Alertmanager webhook payloads. Convert each alert into `secretary.notify.v1` with severity per §2.3. Tests use a captured Alertmanager fixture and assert correct mapping.

🧪 **Eval drift dashboard:**
> Build `iic-006-eval.json` Grafana dashboard. Panels: per-caller mean score over 12 weeks (line); regression timeline (markers); per-rubric heatmap (top 8 rubrics by recent variance). Datasource: postgres reading `lake.eval_runs`. Add a row of stat panels showing current vs 4-week baseline per caller.

---

## 8. Acceptance Criteria

- [ ] All six dashboards load in Grafana with real data within 10 minutes of stack boot.
- [ ] `curl iic-host:9090/api/v1/query?query=up` returns 200 with all targets healthy.
- [ ] Loki query for `{service="agent_intelligence"}` returns recent log lines.
- [ ] A trace from `intel.synth` → `advice.fundamental.v1` shows in Tempo with all spans linked by trace_id.
- [ ] Killing one agent triggers `AGENT_HEARTBEAT_MISSED` and arrives at the WeCom alerts bot within 6 min of kill.
- [ ] Forcing `disk_free < 5%` (via `truncate` on a scratch file) triggers `DISK_FREE_CRITICAL` and reaches WeCom + Server酱 + ntfy + email simultaneously.
- [ ] Weekly eval drift cron has run at least once and recorded a row in `lake.eval_runs`.
- [ ] PR that simulates an eval regression > 10% triggers `PROMPT_EVAL_REGRESSION`.

---

## 9. Risks & Gotchas

⚠️ **Cardinality explosion.** Don't label metrics with high-cardinality values (e.g., individual `advice_id` or `ulid`). Use them as trace attributes, not metrics labels. The agent label is fine; the per-event id is not.

⚠️ **Loki retention.** 14 d is the budget; bump only if needed. Promtail must drop debug-level lines except in dev.

⚠️ **Tempo storage growth.** Sample 100% in the first weeks; later, sample debug-level traces at 10%. Keep all error spans at 100%.

⚠️ **Grafana edits in UI lost on restart.** Provisioning is read-only at startup. Document this in the README; offer a "save → export JSON → commit" workflow.

⚠️ **Alert flapping.** Use Prometheus `for: 5m` clauses and Alertmanager `repeat_interval: 6h` to prevent paging on transient blips.

⚠️ **Postgres exporter perms.** Use a read-only DB role with explicit grants on `pg_stat_*`, not the app role.

⚠️ **WeCom rate vs alert volume.** A bad night could fire 30 alerts. The notifier rate-limits to 20/min/bot — alerts beyond that defer; the Secretary aggregates excess into a digest.

⚠️ **Eval cost cadence.** Drift watch is weekly to keep cost low. Daily was tempting but expensive. Weekly is sufficient.

---

## 10. Cross-References

- Alert routing payload format: `15_AGENT_SECRETARY.md` §5 + `20_NOTIFIER_WECHAT.md` §6.
- Eval harness internals: `04_PROMPT_REGISTRY.md` §5.
- Custom metrics emitted by each agent: their respective `apps/*` workflow docs §5.
- DR drill drill marker: `31_PRODUCTION_HARDENING.md` §5.

---

## Changelog

- **v1.0** — Extracted from `PLAN_v2.1` §14 plus references scattered in the DR sections. Alert codes promoted to GROUND TRUTH; eval drift dashboard formalized.
