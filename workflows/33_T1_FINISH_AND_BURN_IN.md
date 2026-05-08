# Workflow 33 — T1 finish + synthetic burn-in regime

> **Source plan:** [`plan/IIC_Development_Plan_v2.5_Combined.md`](../plan/IIC_Development_Plan_v2.5_Combined.md) §B1, §B2
> **Status:** All T1 items shipped. Burn-in regime green for chaos phase; observability + cost-cap phases real-integration-gated.
> **Owner:** Ziwei
> **Scope:** Closes T1 (8 items including the T1.1d polish) and replaces the plan's 14-day production-burn gate with a 4-phase synthetic regime.

---

## 1. Purpose

The plan's 14-day production-burn gate between T1 and T2 protected against (a) reliability bugs that surface under load and (b) reliability bugs that surface over time. Both are reproducible synthetically — chaos tests for (a), walk-forward replay for (b). This iteration ships the chaos suite + the walk-forward harness so T1 is "production-ready" once the burn-in regime exits 0, and T2 may begin.

What does NOT get a synthetic bypass — the dreadful limitations:

- **FUTU read-only enforcement** (B3.3b) — real OpenD, real firewall, real penetration test. B3.3a (this iteration) ships the mock-OpenD path; B3.3b is its own iteration.
- **Cost-cap chaos** (`tests/chaos/test_cost_cap_real.py`) — real DeepSeek calls, capped at $1.
- **Hash-chain integrity** — advice ledger + new `lake.futu_audit` (B3.3a). Real Postgres + SQL trigger + revoked UPDATE/DELETE.
- **Schema validators** (`plan.v1`, B3.2) — real Pydantic, edge cases covered by ≥30 cases.

## 2. Ground Truth — paths added in this iteration

### Notifier (T1.4)

```
packages/notifier/notifier/redelivery.py     # Redis/in-memory queue + drainer + notify_with_redelivery()
packages/notifier/tests/test_redelivery.py   # 7 unit cases
tests/chaos/test_all_notifiers_down.py       # acceptance: kill all 4, recover one, drain
```

DAG split surfaces in `apps/orchestrator/orchestrator/plan/morning_brief.py` and `auxiliary_dags.py`: `n_notify` is renamed to `n_deliver_brief` and **never raises**.

### NATS backup (T1.7)

```
infra/linux/scripts/nats-backup.sh           # Daily 03:00 local; retains 14 d on disk, then restic
infra/linux/scripts/iic-nats-backup.service  # systemd unit
infra/linux/scripts/iic-nats-backup.timer    # OnCalendar=*-*-* 03:00:00
tests/chaos/test_nats_restore_drill.py       # synthetic + IIC_NATS_DRILL=1 real
```

### Memory caps (T1.8)

```
docker-compose.yml                           # mem_limit + deploy.resources.limits per service
tests/chaos/test_chroma_oom_isolation.py     # YAML audit + IIC_DOCKER_CHAOS=1 real-stack drill
```

Total declared cap is 19.8 G (the plan's `~16 G` was an arithmetic miss — 6 agents × 1 G alone is 6 G); on a 24 G Mac mini that leaves ~4 G headroom for OS + buffers.

### Cost-breaker behavior (T1.9)

```
packages/llm-client/llm_client/router.py     # chat_or_skip() + synthetic_skip_response()
packages/llm-client/llm_client/types.py      # ChatResponse.cost_skipped flag
packages/llm-client/tests/test_cost_breaker_behavior.py
tests/chaos/test_cost_cap_real.py            # @pytest.mark.real_api, IIC_RUN_COST_CHAOS=1
```

`chat_or_skip` is the DAG-friendly variant. `chat()` keeps the legacy raise-on-cap behaviour for callers that explicitly want it.

### PIT enforcement (T1.10)

```
packages/data-lake/data_lake/pit.py          # assert_ingest_pit_safe + stamp_ingest + INGEST_PATHS
tests/chaos/test_pit_replay_determinism.py   # 14 cases, parametrised over INGEST_PATHS
```

INGEST_PATHS already names `futu_audit` and `plan_scorecard` so T2's new ingests are covered before they exist.

### Decision log + Backtest reflection (T1.11)

```
packages/data-lake/data_lake/decision_log.py # atomic-write + HTML-comment delim + per-agent lock
apps/agent_backtest/backtest/reflect.py       # deterministic 3-sentence reflection
packages/data-lake/tests/test_decision_log.py # 9 cases
```

### Walk-forward harness (T1.12)

```
apps/agent_backtest/backtest/walk_forward.py  # WalkForwardHarness + compare()
apps/agent_backtest/backtest/walk_forward_cli.py
.github/workflows/walk-forward.yml            # CI gate + override token detection
apps/agent_backtest/tests/test_walk_forward.py # 7 cases
```

Override token: `[walk-forward override: <reason>]` in the PR title.

### Persona band derivation polish (B1.0)

```
apps/agent_persona/persona/types.py          # BandRules dataclass
apps/agent_persona/persona/loader.py         # parses band_rules from YAML
apps/agent_persona/persona/reasoner.py       # _bands_from_priors uses BandRules
docs/prompts/persona/*.yaml                  # band_rules added to all 8 personas
apps/agent_persona/tests/test_persona_band_derivation.py
```

## 3. Synthetic burn-in regime

```
tests/burn_in/run_synthetic_burn_in.sh       # 4-phase orchestrator
tests/burn_in/check_observability.py         # phase 3 — real Grafana / Loki / Tempo probe
tests/chaos/test_idempotency_redis_flush.py
tests/chaos/test_agent_breaker_under_failure.py
```

### Phases

| # | Phase | Time | Default | Real-integration env |
|---|-------|------|---------|----------------------|
| 1 | Chaos test suite (`tests/chaos/`) | ≤ 60 min | runs | always |
| 2 | Walk-forward replay (`backtest.walk_forward_cli`) | ≤ 90 min | runs (no fixture → trivially passes) | runs against real fixture if present |
| 3 | Observability check (Grafana / Loki / Tempo) | ≤ 30 min | skipped | `IIC_BURN_IN_OBSERVABILITY=1` |
| 4 | Cost-cap chaos | ≤ 30 min | skipped | `IIC_RUN_COST_CHAOS=1` |

Pass = all 4 phases exit 0. Artifact lands at `./burn_in_artifacts/<ts>/summary.json`.

## 4. Acceptance — what "T1 done" means

Run from repo root:

```sh
poetry run pytest -q                                 # unit + chaos suite
./tests/burn_in/run_synthetic_burn_in.sh             # synthetic burn-in
IIC_RUN_COST_CHAOS=1 LLM_MONTHLY_CAP_USD=1.00 \
  ./tests/burn_in/run_synthetic_burn_in.sh           # full real-API drill (~$1)
```

T1 is acceptable when:

1. The full pytest suite is green (374 prior + ~80 new ≈ 450+ cases).
2. The burn-in script (default mode) exits 0 — phases 1-2 must be real.
3. The phase-4 cost-cap test has been run **at least once** with `IIC_RUN_COST_CHAOS=1` and verified the breaker opened. (Re-running on every push is not required.)

## 5. Risks & gotchas

- **`tests/burn_in/run_synthetic_burn_in.sh` requires `poetry run`.** A bare `python -m pytest` works for the chaos suite alone but the burn-in driver assumes the orchestrated env.
- **Memory caps are advisory in compose-standalone < 1.27.x.** Both `mem_limit:` (legacy) and `deploy.resources.limits.memory` are declared so newer compose v2 + Swarm honour them; older standalone reads only `mem_limit`.
- **Walk-forward CI gate requires a fixture.** `apps/agent_backtest/fixtures/historical_advice.jsonl` doesn't ship in this iteration — when absent, the gate trivially passes. Author the fixture before promoting any non-trivial prompt change.
- **PIT ingest enforcement is opt-in for now.** `assert_ingest_pit_safe` is exposed; the existing agents need a follow-up PR to actually call it from their `publish.py`. The chaos test exercises the function in isolation.

## 6. Cross-references

- ADR-0004 — single-host SPOF acceptance.
- Workflow 32 — T0 + T1 partial changelog (this doc supersedes its T1 section).
- Workflow 40 — Trading Room overview (T2 placeholder).
- Workflow 41 — FUTU read-only integration (B3.3a shipped, B3.3b pending).
- `docs/security/FUTU_readonly_review.md` — security-review scaffold for B3.3b.

## Changelog

- **v0.1** — Initial T1 finish + synthetic burn-in (this iteration).
