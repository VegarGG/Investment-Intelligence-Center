# `infra/observability/` — Workflow 30

Idempotent provisioning for Prometheus, Loki, Tempo, OTel Collector,
Grafana datasources + dashboards, and Alertmanager routing.

## Layout

```
infra/observability/
├── prometheus.yml              # scrape topology + rule_files
├── alertmanager.yml            # routes to agent_secretary:/notifier/alertmanager
├── loki-config.yml             # 14-day retention
├── promtail-config.yml         # ships docker container logs
├── tempo-config.yml            # OTLP receivers + 7d block retention
├── otel-collector.yml          # tail-sampling, forward to Tempo
├── alerts/
│   ├── host.yml                # HOST_DOWN, NVMe wear, disk free, UPS
│   ├── llm.yml                 # cost breaker, latency, heartbeats
│   ├── data.yml                # bias, mark feed, ledger integrity
│   └── investment.yml          # eval drift
└── grafana/
    ├── provisioning/
    │   ├── datasources/        # Prometheus, Loki, Tempo, IIC-Postgres
    │   └── dashboards/files.yml
    └── dashboards/
        ├── iic-001-ops.json
        ├── iic-002-host.json
        ├── iic-003-data-freshness.json
        ├── iic-004-investment.json
        ├── iic-005-trade-tape.json
        └── iic-006-eval.json
```

## Editing

Per workflow 30 §6.4, **don't edit dashboards in the Grafana UI** — the
file provisioner is read-only at startup, so any UI edits are lost on
restart. Workflow:

1. Open the dashboard in Grafana.
2. Save → "Save as JSON" → drop the file in `infra/observability/grafana/dashboards/`.
3. Commit.
4. Restart Grafana (or rely on the 30s provisioner refresh).

## Mandatory span attributes (workflow 30 §2.4)

- `trace_id` (auto)
- `dag_id` (orchestrator-wired)
- `caller_id` (LLM client)
- `agent` (e.g., `persona.rogers`)
- `advice_id` (when applicable)

## Alert routing

```
service → /metrics → Prometheus → Alertmanager → POST agent_secretary:8086/notifier/alertmanager
                                                       ↓
                                                 SecretaryNotifyV1
                                                       ↓
                                            packages/notifier (workflow 20)
                                                       ↓
                              WeCom alerts bot · Server酱 · ntfy · SMTP
```
