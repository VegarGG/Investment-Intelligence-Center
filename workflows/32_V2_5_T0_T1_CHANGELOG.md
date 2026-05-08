# Workflow 32 — IIC v2.5 T0 + T1 changelog

> **Source plan:** [`plan/IIC_Development_Plan_v2.5_Combined.md`](../plan/IIC_Development_Plan_v2.5_Combined.md)
> **Status:** T0 complete + T1 partial (T1.1, T1.2, T1.3, T1.5, T1.6 shipped)
> **Owner:** Ziwei
> **Scope:** What changed between v2.1 (workflows 00–31) and v2.5 T0+T1.

---

## 1. Purpose

Plan v2.5 is a tier-staged iteration on the v2.1 prototype. **Tier 0 is the rollback substrate that must be in place before any T1 work begins; Tier 1 is correctness + reliability + DAG coverage; Tier 2 is the Investment Board + event-flow workflow + FUTU integration; Tier 3 is research depth.**

This workflow doc captures *what's already shipped* in this iteration. Workflow 33 (TBD) will document T1's remaining items (T1.4 notifier durable redelivery, T1.7 NATS backup cron, T1.8 memory caps, T1.9 cost-breaker pin-down, T1.10 PIT enforcement, T1.11 markdown decision log, T1.12 walk-forward CI). Workflows 40–49 are reserved for T2; 50–69 for T3 (per plan §C6).

## 2. Ground Truth

### New / changed paths

```
packages/featureflags/                    # T0.1 — YAML-backed feature flags + hot reload
  featureflags/__init__.py
  featureflags/core.py
  featureflags/registry.py                # canonical v2.5 flag list

packages/data-lake/data_lake/quotes.py    # T1.1a — get_mark + Redis cache + PIT-honouring fetcher
packages/data-lake/tests/test_quotes.py

apps/orchestrator/orchestrator/plan/personas.py     # T0.2 — list_personas() source-of-truth
apps/orchestrator/orchestrator/plan/auxiliary_dags.py  # T1.5 — midday/evening/hourly/weekly + 3 NATS DAGs
apps/orchestrator/orchestrator/plan/breaker.py      # T1.6 — per-target circuit breaker
apps/orchestrator/tests/test_persona_source_of_truth.py
apps/orchestrator/tests/test_registered_dags_match_cron.py
apps/orchestrator/tests/test_agent_breaker.py
apps/orchestrator/tests/test_breaker_chaos_morning_brief.py

apps/agent_intelligence/intel/factory.py            # T1.3 — build_pipeline(config)
apps/agent_intelligence/tests/test_startup_binding.py

apps/agent_persona/tests/test_mark_resolution.py    # T1.1 — persona ⇢ live-mark anchor

docs/adr/ADR-0004-single-host-acceptance.md         # T0.3 — SPOF acceptance ADR
docs/featureflags.md                                # T0.1 — feature-flag registry doc
docs/prompts/persona/soros.yaml                     # T1.2 — author missing personas
docs/prompts/persona/wood.yaml
docs/prompts/persona/dalio.yaml
docs/prompts/persona/retail_degen.yaml
```

### New env vars / config

| Var | Default | Purpose |
|---|---|---|
| `IIC_FEATUREFLAGS_PATH` | `/srv/iic/featureflags/flags.yaml` | YAML location for hot-reloadable flags. |
| `IIC_PERSONA_DIR` | `<repo>/docs/prompts/persona` | Source-of-truth dir for persona YAMLs. |
| `INTEL_AUTOSTART` | unset | When `=1`, `_startup` binds the IntelPipeline at boot. |
| `INTEL_HASH_STORE_BACKEND` | `inmemory` | `redis` switches the hash gate to `data_lake.redis`. |
| `INTEL_CRAWLER_BACKEND` | `inmemory` | `rss` starts the live RSS crawler. |
| `IIC_QUOTES_FAKE_PRICE` | unset | Test backdoor returning a fixed price from `get_mark`. |

### New canonical feature flags

| Flag | Default | Owner | Purpose |
|---|---|---|---|
| `iic.featureflags.bootstrap` | false | platform | Acceptance gate for T0.1 chaos test. |
| `persona.live_mark.enabled` | true | persona | Use `data_lake.quotes.get_mark` instead of the legacy `100.0` placeholder. |
| `notifier.durable_redelivery.enabled` | false | notifier | Reserved for T1.4. |
| `orchestrator.agent_breaker.enabled` | true | orchestrator | Per-agent breaker (T1.6). |
| `orchestrator.use_nats_for_agent_calls` | false | orchestrator | Reserved for T2.0. |
| `trading_room.event_triage.enabled` | false | trading_room | Reserved for T2.1. |
| `trading_room.investment_board.enabled` | false | board | Reserved for T2.4. |
| `agent_futu.enabled` | false | agent_futu | Reserved for T2.7. |

## 3. Architecture

```
                     ┌────────────────────────────┐
                     │  YAML flags.yaml           │   ← /srv/iic/featureflags/
                     └──────────────┬─────────────┘
                                    │  mtime-cached
                                    ▼
                       packages/featureflags  ──── used by orchestrator, persona,
                                                   notifier, trading_room (T2)


   docs/prompts/persona/*.yaml ──► orchestrator.plan.personas:list_personas()
                                          │
                                          │  (sole source of truth)
                                          ▼
                       morning_brief.py   app.py:_bootstrap   trading_room (T2)


   morning_brief / midday_pulse / evening_recap / hourly_intel / weekly_eval
   + event:intel.digest.v1 / event:backtest.fill.v1 / event:ops.alert.v1
                                          │
                                          ▼
              orchestrator.plan.registry  (CI: every cron + every NATS sub
                                            must have a registered DAG)


   HttpxAgentClient  ──► CircuitBreakerRegistry  ──► returns degraded
                                                     {"_breaker_open": true,
                                                      "advices": []}
                                                     when state=OPEN

   IntelPipeline   ── build_pipeline(IntelConfig)
                       │
                       └─ /health/deep dry-runs 1 doc through the pipeline


   Persona reasoner ── data_lake.quotes.get_mark(asset, asof) ──► Mark(price, stale_seconds)
                                          │
                                          └── _relevant_events filters digest by spec.universe_weights
```

## 4. Workflow Steps (already done in this iteration)

- **T0.1 Build `packages/featureflags`** — YAML-backed hot-reload, per-test isolation, canonical registry, `docs/featureflags.md` keeps the table in sync.
- **T0.2 Persona source-of-truth** — `list_personas()` + `list_persona_slugs()` reading `docs/prompts/persona/*.yaml`. `morning_brief.py` and `app.py:_bootstrap` consume it; `test_persona_source_of_truth.py` blocks PRs that re-introduce hard-coded slug tuples.
- **T0.3 SPOF acceptance ADR** — [`ADR-0004`](../docs/adr/ADR-0004-single-host-acceptance.md) names the four SPOFs (orchestrator, Postgres, NATS, dashboard), states explicit RPO/RTO and the four promotion triggers that would force a re-evaluation.
- **T1.1 Live mark + persona events filter** — `data_lake.quotes.get_mark(asset, asof) -> Mark`, mtime + Redis cached for 30 s, with PIT-honouring Postgres fallback. `_relevant_events` filters Intel events by `spec.universe_weights`. The `100.0` placeholder is the explicit fallback when the feature flag is off.
- **T1.2 Missing personas** — `soros.yaml`, `wood.yaml`, `dalio.yaml`, `retail_degen.yaml`. Existing `burry.yaml` retained.
- **T1.3 Pipeline at startup** — `intel.factory.build_pipeline(config)` is the deterministic factory. `INTEL_AUTOSTART=1` binds at boot. `/health/deep` runs a 1-doc dry-run for smoke tests + DR drill.
- **T1.5 DAG coverage** — `auxiliary_dags.py` registers `cron:midday_check`, `cron:evening_recap`, `cron:hourly_intel`, `cron:weekly_eval`, plus `event:intel.digest.v1`, `event:backtest.fill.v1`, `event:ops.alert.v1`. CI test `test_registered_dags_match_cron.py` fails closed if a future cron entry has no DAG.
- **T1.6 Per-agent circuit breaker** — `CircuitBreakerRegistry` (closed/open/half-open) wraps every `HttpxAgentClient.call`; degraded calls return `{"advices": [], "_breaker_open": True}` so DAG fan-out continues. Threshold: 5 consecutive failures, 60 s cooldown.

## 5. Acceptance Criteria

Run from repo root:

```sh
poetry run pytest -q                               # 374 passed, 8 integration skipped
poetry run pytest packages/featureflags/tests -q   # T0.1 (9 cases)
poetry run pytest apps/orchestrator/tests -q       # T0.2 + T1.5 + T1.6 (44 cases)
poetry run pytest apps/agent_persona/tests -q      # T1.1 + T1.2 (17 cases)
poetry run pytest apps/agent_intelligence/tests -q # T1.3 (16 cases)
poetry run pytest packages/data-lake/tests/test_quotes.py -q  # T1.1a (5 cases)
```

Per-T-item acceptance reproducing plan §6:

| T-item | Acceptance | How to verify |
|---|---|---|
| T0.1 | Flag flip via YAML edit; service responds within 2 s. | `test_yaml_hot_reload_within_2s` green. |
| T0.2 | Adding `<slug>.yaml` is picked up by morning brief without code change. | `test_persona_source_of_truth.py` enforces 1:1; orchestrator boot reads YAML. |
| T0.3 | ADR merged, referenced from runbooks + README. | `docs/adr/README.md` lists ADR-0004. |
| T1.1 | Persona advice JSON has bands derived from live mark; weekend stale flagged. | `test_mark_resolution.py` covers flag-on, flag-off, no-bar fallback. |
| T1.2 | Morning brief runs end-to-end with no missing-persona errors. | `test_morning_brief_dag.py` dynamic over `list_persona_slugs()`. |
| T1.3 | `/health/deep` returns 200 < 30 s after boot. | `test_startup_binding.py` covers bound/unbound. |
| T1.5 | No `"no DAG registered"` log lines. | `test_registered_dags_match_cron.py` fails closed. |
| T1.6 | Stop one agent → brief still completes. | `test_breaker_chaos_morning_brief.py::test_morning_brief_completes_when_one_persona_is_offline`. |

## 6. Risks & Gotchas

- **`featureflags.registry` is import-side-effecting.** Tests that clear `_REGISTRY` between runs must `importlib.reload(featureflags.registry)` to repopulate. The conftest already does this.
- **Persona drift via the YAML directory.** Adding a YAML with a `slug:` key that doesn't match the filename stem causes `test_persona_source_of_truth.py` to fail. Keep them aligned (e.g., `soros.yaml` → `slug: soros`).
- **`IIC_QUOTES_FAKE_PRICE`** is honoured by `_default_fetcher` only — overriding via `set_fetcher_for_test` always wins.
- **`auxiliary_dags.py` SLA fallbacks.** When a key isn't in `SLA_TABLE` the DAG falls back to a generous `(60, 90)` so a typo doesn't make a node run unbounded. Production should add the proper key.
- **Circuit-breaker chaos test acceptance.** Failure threshold of 5 means a flaky agent's first 4 failed calls still raise to the caller (the DAG runner converts them to node-failures). The brief still ships because the persona fan-out has independent edges; if you reduce the persona count to 1 the chaos test no longer demonstrates degradation.

## 7. Cross-References

- Plan: [`plan/IIC_Development_Plan_v2.5_Combined.md`](../plan/IIC_Development_Plan_v2.5_Combined.md) §T0, §T1.
- ADR: [`docs/adr/ADR-0004-single-host-acceptance.md`](../docs/adr/ADR-0004-single-host-acceptance.md).
- Feature flags doc: [`docs/featureflags.md`](../docs/featureflags.md).
- Predecessor docs: workflows 06 (orchestrator), 10 (intel), 13 (persona).

## Changelog

- **v0.1** — Initial T0 + T1 partial. T1.4, T1.7–T1.12 to follow in workflow 33.
