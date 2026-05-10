# D5 — IIC Prototype Review & Next-Iteration Vibe-Coding Brief

**Date:** 2026-05-09 · **Reviewer:** ai-engineer agent (Claude) · **Repo:** [VegarGG/Investment-Intelligence-Center](https://github.com/VegarGG/Investment-Intelligence-Center) @ commit `5e64575` (HEAD) · **Plan refs:** `D4_IIC_Development_Plan_v2.5_Combined.md`, `ITERATION_v2_5_finish_T1_open_T2.md` (B0–F)

---

## 1. Executive verdict

**Construction quality:** strong. **Validation quality:** strong-with-one-real-gap. **Greenlight to next iteration:** yes, with clear scope below.

The repo is exactly what the plan promised. v2.1 substrate (workflows 00–31), T0 rollback substrate, all 13 T1 items including the T1.1d polish, the 4-phase synthetic burn-in regime, and three of the T2 parallel-kickoff items (B3.1 NATS request-reply substrate, B3.2 `plan.v1` schema, B3.3a FUTU mock-OpenD path) are all on disk, tested, and wired into CI. 488 files, 293 Python files, 280 test functions across 11 packages, 6 GitHub Actions workflows, 8 personas, 18 docker-compose services. The two iteration commits (`545c2f8` T0+T1 partial, `5e64575` T1 finish + burn-in + T2 kickoff) line up with the iteration brief commit-for-commit.

The audit found one substantive divergence between plan and code (FUTU audit chain is currently in-memory-only; the plan calls for `lake.futu_audit` Postgres table with SQL trigger and revoked UPDATE/DELETE) and four smaller deltas worth tracking. None of them break the iteration's acceptance — the in-memory chain is honestly labeled "production swaps this for `lake.futu_audit` in B3.3b" — but they need to land in the next iteration so the dreadful-limitation column stays honest.

---

## 2. Construction evaluation — what's been built well

### 2.1 T0 rollback substrate — solid

- **`packages/featureflags/`** (3 modules, 9 test cases, 81-line registry): mtime-cached YAML loader, thread-safe with explicit `_LOCK`, registered-flag typo guard, `set_for_test`/`reset_for_test` API, and 8 canonical v2.5 flags pre-registered (`iic.featureflags.bootstrap`, `persona.live_mark.enabled`, `notifier.durable_redelivery.enabled`, `orchestrator.agent_breaker.enabled`, `orchestrator.use_nats_for_agent_calls`, `trading_room.event_triage.enabled`, `trading_room.investment_board.enabled`, `agent_futu.enabled`). Crucially, the T2 flags (event_triage, investment_board) ship **default OFF** so the substrate is in place for next iteration without exposing partial work.
- **`apps/orchestrator/orchestrator/plan/personas.py`** is the single source of truth. CI test `test_persona_source_of_truth.py` enforces 1:1 between YAMLs and what the morning_brief fans out to. Buffett/Burry/Soros inconsistency closed.
- **ADR-0004** names all four SPOFs (orchestrator, Postgres, NATS, dashboard), gives concrete RPO/RTO numbers, lists four explicit promotion triggers, and cross-references the runbooks. Honest about its tradeoffs.

### 2.2 T1 correctness/reliability — all 13 items shipped

| Item | Path | Verdict |
|---|---|---|
| T1.1a live mark | `packages/data-lake/data_lake/quotes.py` (275L) | Three-tier resolver (mem 30s → Redis 30s → fetcher → Postgres). `Mark.stale_seconds` exposed for refusal. Graceful degrade. |
| T1.1c relevant events | `apps/agent_persona/persona/reasoner.py:_relevant_events` | Filters by `universe_weights`; coarse classifier `_asset_bucket` covers crypto/commodities/fx/bonds/em_equities/us_largecap; macro events pass through. |
| **T1.1d band derivation** (the previously-stubbed item) | `_bands_from_priors` in same file (264L total) | **Real.** Reads `BandRules` per persona (long/short/flat default, target_pct_over_mark, stop_pct_under_mark, entry_band_pct, macro_regime_modulation). 8-key `_REGIME_MULTIPLIER` covers rate_cut/risk_on/bull/stagflation/risk_off/recession/bear/crisis/neutral/unknown. `direction=flat` fallback preserved as a chaos-drill safety net. 126-line `test_persona_band_derivation.py` covers all 8 personas. |
| T1.2 missing personas | `docs/prompts/persona/` | All 8 present: buffett, burry, dalio, druckenmiller, retail_degen, rogers, soros, wood. |
| T1.3 intel startup | `apps/agent_intelligence/intel/factory.py` (113L) | `build_pipeline(IntelConfig)` deterministic factory; `INTEL_AUTOSTART=1` binds at boot via `@app.on_event("startup")`; `/health/deep` endpoint runs 1-doc dry-run; `/health` stays cheap for liveness. |
| T1.4 notifier durable redelivery | `packages/notifier/notifier/redelivery.py` (334L) | InMemory + Redis backends; severity-based TTLs (CRITICAL 1h / ALERT 6h / WARN 12h / INFO 24h); 60s drain loop; CRITICAL ntfy-on-Tailscale fallback; `n_compose_brief` / `n_deliver_brief` split — DAG never fails on notifier outage. |
| T1.5 DAG coverage | `apps/orchestrator/orchestrator/plan/auxiliary_dags.py` (311L) | Four cron DAGs (midday_pulse, evening_recap, hourly_intel, weekly_eval) + three NATS-event DAGs (intel.digest.v1, backtest.fill.v1, ops.alert.v1). `test_registered_dags_match_cron.py` parametrizes over `CRON_JOBS` and `ORCH_SUBSCRIPTIONS` and **fails closed** — silent-drop surface eliminated. |
| T1.6 agent breaker | `apps/orchestrator/orchestrator/plan/breaker.py` (159L) | Hand-rolled three-state (closed/open/half-open), `failure_threshold=5`, `cooldown_s=60`, single-flight half-open probe, `on_change` hook for telemetry, async-safe per-state `asyncio.Lock`. `BreakerOpen` short-circuits with `{"_breaker_open": True, "advices": []}`. |
| T1.7 NATS backup | `infra/linux/scripts/nats-backup.sh` + systemd timer | Daily 03:00 backup; 14d on-disk retention; restic to MinIO. `tests/chaos/test_nats_restore_drill.py` is the acceptance — synthetic drill, real with `IIC_NATS_DRILL=1`. |
| T1.8 memory caps | `docker-compose.yml` | `deploy.resources.limits.memory` per service; `tests/chaos/test_chroma_oom_isolation.py` audits the YAML. |
| T1.9 cost-breaker behavior | `packages/llm-client/llm_client/router.py` + `tests/chaos/test_cost_cap_real.py` | `chat_or_skip()` + `synthetic_skip_response()`; `_cost_skipped=True` propagates; `with_signals(cost_breaker_open=True)` taints downstream nodes; **real-DeepSeek chaos test** gated on `IIC_RUN_COST_CHAOS=1` with $1 hard cap. |
| T1.10 PIT enforcement | `packages/data-lake/data_lake/pit.py` (196L) | `assert_ingest_pit_safe`, `stamp_ingest`, `INGEST_PATHS` already names `futu_audit` and `plan_scorecard` so T2's new ingests are covered before they exist. |
| T1.11 decision log + reflection | `packages/data-lake/data_lake/decision_log.py` (215L) + `apps/agent_backtest/backtest/reflect.py` (96L) | Atomic-write per-agent markdown with HTML-comment delimiters; `Reflector` writes 3-sentence post-hoc reflection back into the source agent's entry. |
| T1.12 walk-forward | `apps/agent_backtest/backtest/walk_forward.py` (205L) + `.github/workflows/walk-forward.yml` | CI gate fires on `packages/prompts/registry/**`; PR title token `[walk-forward override: <reason>]` for one-per-quarter overrides. Override is detected via regex; default behavior is fail-closed on materially-negative delta. |

### 2.3 Synthetic burn-in regime — shipped and exit-coded

`tests/burn_in/run_synthetic_burn_in.sh` orchestrates the 4 phases the iteration brief asked for. Phases 1–2 default-on; phases 3 (observability) and 4 (real DeepSeek cost cap) gated on `IIC_BURN_IN_OBSERVABILITY=1` and `IIC_RUN_COST_CHAOS=1`. Output: `burn_in_artifacts/<ts>/summary.json` with `phases:[]` and `pass:0|1`. `tests/burn_in/check_observability.py` is a real Grafana/Loki/Tempo HTTP probe (131L) — not a stub.

This is exactly the engineering trade the brief wanted: 4 hours synthetic instead of 14 days calendar, with the real-API drills carved out.

### 2.4 T2 parallel kickoff — three of three shipped

- **B3.1 — NATS request-reply substrate.** `packages/data-bus/data_bus/request_reply.py` (136L) ships `nats_call(subject, payload, timeout_s)` plus `register_handler` for the agent side. `HttpxAgentClient.call` now branches on `flag('orchestrator.use_nats_for_agent_calls')` (default OFF). `test_nats_request_reply_shim.py` in orchestrator tests verifies parity.
- **B3.2 — `plan.v1` schema.** `packages/schema/schema/plan.py` (151L) — `PlanV1` Pydantic model with all the validators the plan called for: ULID id, entry_window monotone (`_entry_window_monotone`), buy/sell action-direction price ordering (`_action_price_ordering`), evidence non-empty unless action=hold, persona-team requires both `persona_slug` and `disclaimer`, expires_at > issued_at and ≤ 365d. `PortfolioContextV1` slice attaches the FUTU-derived portfolio context. `tests/test_plan_v1.py` ships **34 test cases** (target was ≥30). Goldens fixture at `tests/fixtures/plan_v1_examples.json`. TypeScript mirror at `apps/dashboard/src/types/plan.ts`.
- **B3.3a — FUTU mock-OpenD.** `apps/agent_futu/` (8 files): `readonly_client.py` (194L) with `ALLOWED_METHODS={get_acc_list, accinfo_query, position_list_query, order_list_query, history_order_list_query, history_deal_list_query, get_market_state}` and `FORBIDDEN_METHODS={place_order, modify_order, cancel_order, unlock_trade, deal_list_query_realtime}` enforced at `__getattr__` time. `audit.py` (142L) hash-chained log with `verify_chain()`. `aggregator.py` (112L) aggregates across N OpenD endpoints into `PortfolioSnapshotV1`. `fake_opend.py` deterministic test fixture. **19 test cases** between `test_readonly_enforcement.py` and `test_audit_chain.py` — including the static-source-scan test that fails CI if any non-test file references a forbidden method by name. `docs/security/FUTU_readonly_review.md` is a 107-line scaffold with the B3.3a checklist ticked and B3.3b checklist (real OpenD, paper account, firewall, penetration test, OpenTimestamps anchor, Ziwei sign-off) clearly listed.

### 2.5 What's clean across the whole codebase

- **Lint suite enforced in CI.** ruff + black + mypy strict run on every push/PR. `pyproject.toml` selects bandit-basics (`S`), bugbear (`B`), pyupgrade (`UP`), simplify (`SIM`), async (`ASYNC`).
- **Six GitHub Actions workflows.** `python-ci.yml`, `walk-forward.yml`, `prompt-eval.yml`, `prompt-drift-weekly.yml`, `nas-dryrun.yml`, `secret-age-check.yml`. The drift / nas / sops workflows are not glamorous but they catch the boring regressions the project would otherwise hit at month 6.
- **Eight ADRs / runbooks / postmortems** under `docs/`. Decision history is captured.
- **20-document workflows/ directory** — every package has its own self-contained vibe-coding brief with Ground Truth, Module Layout, Workflow Steps, Vibe Prompts, Acceptance Criteria, Risks, Cross-References. This is exactly what the project's ground-truth methodology asked for.

---

## 3. Validation evaluation — gaps and concerns

### 3.1 The one substantive divergence — FUTU audit chain still in-memory

The `D4` plan §C10 + `ITERATION` §C list "Hash-chain integrity (existing + B3.3a `lake.futu_audit`) — Real Postgres + real trigger + revoked UPDATE/DELETE" as a dreadful limitation that "is real or it isn't." The shipped `apps/agent_futu/futu/audit.py:FutuAuditLog` is an in-memory `dataclass` with `verify_chain()` only. The file's own docstring is honest about it: *"This module ships the in-memory implementation used by tests; the production Postgres-backed implementation will land alongside the schema migration in B3.3b."*

Compare to the **advice** ledger, where `packages/data-lake/data_lake/migrations/versions/0002_advice_ledger.py` ships a real Postgres `BEFORE INSERT` trigger that enforces chain linkage and `REVOKE UPDATE, DELETE ON lake.advice FROM iic_app`. That's the standard the plan set; FUTU should match it.

**Severity:** medium. The B3.3a iteration acceptance was correctly scoped — mock OpenD, no production FUTU traffic, audit chain in tests only. Nothing is currently exposed to risk. But the next iteration must include the `lake.futu_audit` migration before B3.3b lights up real OpenD, otherwise the dreadful-limitation table is wrong.

### 3.2 Smaller deltas

- **`agent_board/` does not exist yet.** Correct per scope (T2.4 explicitly deferred to next iteration), but the codebase has no skeleton, no schema for `BoardDecisionV1`, and no NATS subjects reserved. Mention here so it's not a surprise on next-iteration day 1.
- **Walk-forward CI gate is a no-op without a fixture.** `.github/workflows/walk-forward.yml` runs `python -m backtest.walk_forward_cli ...` but `apps/agent_backtest/fixtures/historical_advice.jsonl` doesn't ship. When absent, the gate trivially passes. The risk doc (workflow 33 §5) flags this. Action: author the fixture before promoting any non-trivial prompt change.
- **PIT ingest enforcement is opt-in.** `assert_ingest_pit_safe` exists; the existing 4 agents' `publish.py` files don't call it yet. The chaos test exercises the function in isolation. Acceptable for T1, but T2 work should make it required for the new ingest paths (`futu_audit`, `plan_scorecard`).
- **Burn-in script has no test of its own.** `run_synthetic_burn_in.sh` summarizes phases as `pass:N` where `N` is the cumulative `EXIT_CODE` (0=all pass, 1=any fail). A trivial smoke test that sources the helpers and runs each phase against a known-good vs known-bad fixture would prevent the script from silently regressing.
- **No integration test of the FastAPI `/run` ↔ NATS request-reply parity at the end-to-end level.** `test_nats_request_reply_shim.py` covers the shim itself; an end-to-end test that runs morning_brief with the flag both ways and diffs the resulting advice ledger would close the loop. The plan called for this; it's missing.

### 3.3 What's solidly validated

- **Defense-in-depth on FUTU read-only.** The `test_no_non_test_code_imports_forbidden_methods` test walks `apps/` and `packages/`, scans every `.py` file for `.place_order(` / ` place_order(` (and equivalents for the other 4 forbidden methods), excludes `tests/` + `readonly_client.py` + `fake_opend.py`, and asserts `not offenders`. Real static analysis as a pytest. This catches a future commit that imports the wrong method.
- **Schema validators on `plan.v1` and `advice.v1`.** Real Pydantic `model_validator(mode="after")` chains, real edge cases. `_action_price_ordering` enforces buy: `target > entry > stop`, sell: `stop > entry > target`. `_persona_team_requires_disclaimer` is the workflow-13 §6 ethics rule reified as a validator.
- **Hash-chain for advice ledger (the existing one).** Postgres trigger + revoked UPDATE/DELETE + Python-side `verify_chain` (`packages/data-lake/data_lake/advice_ledger.py`, 199L). This is the gold standard the FUTU audit needs to match.
- **Cost-cap real-DeepSeek chaos test.** `tests/chaos/test_cost_cap_real.py` is genuinely real-API: spins up a `LlmRouter` with a real `DeepSeekAdapter`, drives spend toward 95% of cap, asserts the breaker opens, asserts the synthetic-skip marker shows up in the brief markdown, hard-caps at $1. Gated on `IIC_RUN_COST_CHAOS=1` so it doesn't burn money on every CI run.
- **Ledger immutability.** `iic_app` role's UPDATE and DELETE are revoked at migration time. Tamper-evidence is real, not aspirational.

---

## 4. Validation: how well does the product honor its own constraints

The four hard constraints in `MEMORY.md` and the v2.0+ plans are:

| Constraint | Evidence | Status |
|---|---|---|
| Suggestion-only, no broker integration | No `place_order` / `unlock_trade` in any non-test file (test enforces this); `agent_futu.enabled` flag default OFF; FUTU wrapper raises on every mutating method | ✅ Real |
| Every advice carries citations; backtester rejects uncited | `AdviceV1.evidence: list[Evidence]`; `PlanV1` validator `_evidence_required_unless_hold` raises if `evidence == [] and action != "hold"` | ✅ Real |
| Persona disclaimer mandatory | `PlanV1` validator `_persona_team_requires_disclaimer`; `PersonaSpec.disclaimer` propagates into every `AdviceV1`; `apps/agent_persona/tests/test_disclaimer_validator.py` covers the negative path | ✅ Real |
| `advice.v1` schema immutable | `packages/schema/schema/advice.py` + `test_advice_validators.py`; ledger schema enforced by Pydantic + Postgres trigger + revoked UPDATE/DELETE | ✅ Real |

All four hold up under inspection. The product earns its "suggestion-only, citation-required, persona-disclaimed" claim.

---

## 5. Iteration-status summary table

| Tier | Scope | Repo state | Honest status |
|---|---|---|---|
| **T0** | featureflags, persona SoT, ADR-0004 | ✅ All 3 items shipped | Done |
| **T1** | 13 reliability/correctness items | ✅ All 13 shipped, including T1.1d polish | Done |
| **Synthetic burn-in** | 4-phase regime replacing 14-d gate | ✅ Script + fixtures + observability probe shipped | Done — phases 3+4 require env flags to actually run real |
| **T2.0** NATS req/reply | B3.1 | ✅ Shipped, flag-gated | Done |
| **T2.2** `plan.v1` schema | B3.2 | ✅ Shipped, 34 tests, goldens | Done |
| **T2.7 Phase A** FUTU mock | B3.3a | ✅ Shipped except: audit chain in-memory only | Done with caveat (§3.1) |
| **T2.1** Event-Triage Gate | B3 next | ⏳ Flag registered (default OFF), no code | Next iteration |
| **T2.3** team_plan endpoints | T2 next | ⏳ Not started | Next iteration |
| **T2.4** Investment Board | T2 next | ⏳ Not started; flag registered | Next iteration |
| **T2.5** live benchmarking | T2 next | ⏳ Not started | Next iteration |
| **T2.6** trading-room brief | T2 next | ⏳ Not started | Next iteration |
| **T2.7 Phase B** real OpenD | B3.3b | ⏳ Security-review doc scaffolded, awaits sign-off | Next iteration (gated on Ziwei) |
| **T2.8** trading-room DAG end-to-end | T2 next | ⏳ Not started | Iteration after next |
| **T2.9 / T2.10** prompt upgrades | T2 next | ⏳ Not started | Iteration after next |
| **T3** research depth | All items | ⏳ Not started, gated on T2 + 30-d soak | Out of scope |

Test count: **280** test functions across **77 test files**. Burn-in: 7 chaos tests + 1 burn-in driver + 1 observability probe.

---

## 6. Next-iteration vibe-coding brief

Copy the section below verbatim into the next vibe-coding session.

---

### Iteration v2.5-N3 — Investment Board + Event-Triage + FUTU Phase B

You are picking up after the iteration that shipped T1 finish + synthetic burn-in + T2 parallel kickoff (B3.1 NATS, B3.2 plan.v1 schema, B3.3a FUTU mock-OpenD). The full plan is `plan/IIC_Development_Plan_v2.5_Combined.md`. The iteration before this one is `ITERATION_v2_5_finish_T1_open_T2.md`. Read both before starting.

This iteration closes T2's user-visible product shift: the **trading room** wakes on a high-impact event, fans out to analysis teams, the **Investment Board** debates and picks one plan, and the user gets a brief showing the winning plan + the dissent record + every plan (per plan §T2.6). It also lights up real FUTU OpenD against a paper account behind a security review.

#### N3.0 — Pre-flight + close the in-memory FUTU audit gap (≤ 30 min)

Before any new feature work, fix the §3.1 gap from the D5 review:

- **Add `lake.futu_audit` migration** at `packages/data-lake/data_lake/migrations/versions/0005_futu_audit.py`. Schema: `(id BIGSERIAL PK, futu_id_hash TEXT NOT NULL, method TEXT NOT NULL, args_repr TEXT, kwargs_repr TEXT, issued_at TIMESTAMPTZ NOT NULL, prev_hash TEXT NOT NULL, entry_hash TEXT NOT NULL UNIQUE, status TEXT NOT NULL DEFAULT 'pending', summary TEXT, error TEXT)`. Add a `BEFORE INSERT` trigger `lake.futu_audit_chain_check` that mirrors `lake.advice_chain_check` from migration 0002. Revoke UPDATE, DELETE from `iic_app`.
- **Swap `apps/agent_futu/futu/audit.py:FutuAuditLog` to a Postgres-backed implementation** behind a Protocol. Keep the in-memory variant for tests (the existing `FutuAuditLog` becomes `InMemoryFutuAuditLog`). Update `test_audit_chain.py` to parametrize over both backends.
- **OpenTimestamps anchor cron.** `infra/linux/scripts/futu-audit-anchor.sh` calls `nc -nv` (or the `opentimestamps-client` CLI) on the chain head; systemd timer `OnCalendar=*-*-* 04:00:00`. Acceptance: `tests/chaos/test_futu_audit_anchor.py` runs the script against a synthetic chain head and asserts a `.ots` artifact lands under `/srv/iic/futu-audit-anchors/`.

After the gap is closed, run pre-flight:

```bash
poetry run pytest -q                          # ~280 → ~310 cases after migration tests
./tests/burn_in/run_synthetic_burn_in.sh      # synthetic-burn 4-phase, baseline
test -f packages/data-lake/data_lake/migrations/versions/0005_futu_audit.py
test -f infra/linux/scripts/futu-audit-anchor.sh
```

If any fail, STOP and report.

#### N3.1 — T2.1 Event-Triage Gate (parallelizable)

**File:** `apps/orchestrator/orchestrator/plan/event_triage.py` (new), edit `apps/orchestrator/orchestrator/triggers/nats_events.py`.

- Listen on `intel.event.high_impact.v1`. For each event, classify via a lightweight LLM prompt + numeric thresholds: `regime_change_score`, `surprise_factor`, `affected_universe_overlap`. Emit one of: `route=trading_room` | `route=morning_brief_only` | `route=drop`.
- Output a `triage.decision.v1` event for traceability (subject `triage.decision.v1`; persisted with the same hash-chain pattern as `advice.v1`).
- Feature-flag-gated on `trading_room.event_triage.enabled` (already registered, default OFF).

**Acceptance:** `tests/test_event_triage.py` — 8 cases covering each route, 1 case for the LLM-misclassification fallback (default to `morning_brief_only`), 1 case for the cost-breaker-open fallback (default to `drop` so we don't fan out spuriously when the LLM is unavailable).

#### N3.2 — T2.3 Analysis teams emit `plan.v1` (parallelizable)

**Files:** `apps/agent_quant/quant/team_plan.py`, `apps/agent_fundamental/fundamental/team_plan.py`, `apps/agent_persona/persona/team_plan.py`. Each adds a `/team_plan` FastAPI endpoint that takes a triage event + ticker + horizon and returns one `PlanV1` per team per ticker (per plan §T2.3).

- Persona team's writer: synthesize the 8 personas' `AdviceV1` outputs into ONE `PlanV1` with `persona_slug='consensus'`. Action = majority direction; entry = median; target = mean; stop = max stop_loss; thesis = LLM-synthesized 3-paragraph rollup with citations to each persona's reflection.
- Quant team's writer: aggregate factor scores across the 8-factor library into one numeric `PlanV1` (action = sign of net z-score, sizing = capped at 5% NAV).
- Fundamental team's writer: pick the highest-conviction filing-based thesis from the watchlist and emit one `PlanV1` per ticker.

**Acceptance:** end-to-end test `tests/test_team_plan_e2e.py` — fires a synthetic triage event, asserts each team produces exactly one schema-valid `PlanV1`, asserts the Persona plan has a non-empty disclaimer, asserts the Quant plan has empty disclaimer (only Persona team is required to disclaim).

#### N3.3 — T2.4 Investment Board (the headline)

**New service:** `apps/agent_board/`. Directory layout:

```
apps/agent_board/
  board/__init__.py
  board/main.py             # FastAPI app
  board/bull_bear.py        # Bull/Bear research debate (max 2 rounds)
  board/risk_panel.py       # 3-way Aggressive/Conservative/Neutral risk debate (max 3 turns)
  board/chair.py            # Board Chair LLM-synthesizes the BoardDecision
  board/schema.py           # BoardDecisionV1 Pydantic model
  board/persist.py          # writes board.decision.v1 to advice ledger as agent='board'
  tests/test_bull_bear.py
  tests/test_risk_panel.py
  tests/test_chair.py
  tests/test_e2e_board.py
```

- **`BoardDecisionV1`** schema: `{id (ULID), trigger_event_id, considered_plan_ids[], chosen_plan_id, chair_rationale, dissent_record (markdown), risk_view (markdown), confidence, issued_at}`. Validators: `chosen_plan_id ∈ considered_plan_ids`, `confidence ∈ [0,1]`, dissent_record non-empty if `len(considered_plan_ids) > 1`.
- **Prompts** under `packages/prompts/registry/board/{bull,bear,risk_aggressive,risk_conservative,risk_neutral,chair}/v1.yaml`. Reuse TradingAgents' Apache-2.0 prompts as the seed (per plan §C4 attribution; add a NOTICE entry).
- **Persist** to advice ledger as a new `agent='board'` entry chained on the same hash chain as agent advice. The trigger from migration 0002 already enforces chain linkage; no new SQL needed.
- **Feature-flag-gated** on `trading_room.investment_board.enabled` (already registered, default OFF).
- **Cost discipline:** Bull/Bear and Risk-panel use `chat_or_skip` (DeepSeek Flash); Chair uses `chat` (DeepSeek Pro) — exactly one Pro call per board decision. Budget per decision ≤ $0.05.

**Acceptance:**
- Unit: each sub-agent (`bull_bear`, `risk_panel`, `chair`) has its own test file with positive + negative paths.
- E2E: `test_e2e_board.py` fires a synthetic triage event, asserts the Board produces exactly one `BoardDecisionV1`, asserts `chosen_plan_id ∈ considered_plan_ids`, asserts the dissent_record cites at least 2 of the considered plans by id, asserts the entry persisted to `lake.advice` with `agent='board'` and the hash chain still verifies.

#### N3.4 — T2.6 Trading-room brief (user-visible piece)

**Files:** `apps/agent_secretary/secretary/trading_room_brief.py` (new), edit `apps/dashboard/src/pages/TradingRoom.tsx`.

- Markdown brief format:
  ```
  # Trading Room — {ticker}, {YYYY-MM-DD HH:MM TZ}
  ## Winning plan ({team} — confidence {conf})
  Action: {action}; entry {entry_lo}–{entry_hi}; target {target_lo}–{target_hi}; stop {stop_loss}; horizon {horizon_days}d
  Thesis: {thesis}
  Evidence: {evidence_links}
  ## Dissent ({n_dissenting} plans disagreed)
  ...
  ## Risk view
  Aggressive: {a_position}
  Conservative: {c_position}
  Neutral: {n_position}
  ## All plans considered
  | Team | Action | Entry | Target | Stop | Conf |
  ...
  ## Disclaimer
  This is research, not investment advice. ...
  ```
- Push via existing notifier with severity=ALERT (lower than CRITICAL — this is interesting, not urgent).
- Dashboard surface at `/trading-room` shows the brief inline + a "what was the dissent" expander.

**Acceptance:** snapshot-test `tests/test_trading_room_brief_format.py` — pin a fixture board decision, assert the markdown matches a golden file (whitespace-tolerant). Dashboard E2E: cypress/playwright test renders the page from a fixture event and asserts the dissent expander toggles.

#### N3.5 — T2.8 Trading-room DAG end-to-end

**File:** `apps/orchestrator/orchestrator/plan/trading_room.py` (new). Wire the DAG: `intel.event.high_impact.v1` → Event-Triage → fan-out to {Quant, Fundamental, Persona} team_plan endpoints → collect all `PlanV1` envelopes → fire Investment Board → write Board decision → write trading-room brief → Notify.

- Use the `_active_dags` reconciliation surface (existing in `orchestrator/state`). Record `trace_id` everywhere — every span on the path must carry the same trace.
- Idempotency key: `(trigger_event_id)`. Re-runs of the same event are no-ops (compute is cached in MinIO; only the brief gets re-pushed if the user requested).
- Failure isolation: if Bull/Bear breaks, the DAG falls back to "any single team's plan" mode and the brief notes the degraded state. If a single team breaks, its slot in the brief is "team unavailable" and the Board considers the remaining plans.

**Acceptance:** `tests/test_trading_room_dag_e2e.py` — 3 cases:
1. Happy path: synthetic high-impact event in, brief out, all paths green.
2. One team is breakered open: brief shows N-1 plans considered, Board still emits a decision.
3. Bull/Bear LLM call returns junk: Board falls back to "any single team's plan" mode and the brief notes the degraded state.

#### N3.6 — T2.7 Phase B real OpenD (FUTU Phase B3.3b — gated on Ziwei)

This is the **dreadful-limitation real-integration** lap of FUTU. Do not start until §3.1's `lake.futu_audit` migration is in (N3.0) and the security-review doc is signed. Specifically:

- **Real OpenD container per Futu ID.** `infra/linux/iic-opend@.service` systemd template; one instance per `/srv/iic/futu/<futu_id_hash>/openD-config/`. Bind-mount the sops-decrypted credential file as a tmpfs.
- **TrdEnv.SIMULATE only.** Refuse to start an OpenD container with a `LIVE` env. Acceptance: `tests/integration/test_opend_refuses_live.py` (gated on `IIC_RUN_FUTU_LIVE=1`).
- **Outbound firewall rules.** `infra/linux/iptables/futu.rules` per the security-review table. Allow market endpoints; deny trade endpoints. Acceptance: `tests/integration/test_futu_firewall.py` runs `nft list ruleset` and asserts the deny rule is present (skipped on macOS/CI runners; must run on the actual Mac mini host).
- **Penetration test.** `tests/penetration/test_futu_readonly_pentest.py` — try to call `place_order` via every plausible bypass (direct attribute on the underlying SDK, dynamic `getattr`, raw socket, dynamic import). Each path must fail. Marker `@pytest.mark.real_api`.
- **OpenTimestamps anchor verification.** Daily cron from N3.0 anchors the chain head; this iteration adds `tests/chaos/test_audit_chain_otp_anchor.py` that runs the verifier against the last 7 daily anchors and asserts they all verify against `commits.opentimestamps.org`.
- **Sign-off.** `docs/security/FUTU_readonly_review.md` § 5 has Ziwei's signature and date.

**Acceptance for B3.3b:** the security-review doc is signed; `agent_futu.enabled` flag flips to ON in flags.yaml; one full morning_brief run with FUTU portfolio context attached to every persona's `AdviceV1`.

#### N3.7 — Burn-in regime extension

Extend `tests/burn_in/run_synthetic_burn_in.sh` with two new phases:
- **Phase 5 — Trading-room replay (≤ 60 min).** Replay 30 days of historical `intel.event.high_impact.v1` events through the trading-room DAG; assert each emits exactly one `BoardDecisionV1`; assert the brief markdowns are diffable against a golden directory.
- **Phase 6 — FUTU read-only enforcement (≤ 5 min).** Run the pentest suite against a fresh OpenD container; gated on `IIC_RUN_FUTU_LIVE=1`.

Update `phase_walk_forward` to also run a delta report on Bull/Bear/Risk prompts (any change to `packages/prompts/registry/board/**` triggers the existing `walk-forward.yml` gate).

#### N3.8 — Workflow + ADR docs

- `workflows/34_TRADING_ROOM_DAG.md` — N3.5 wire-up + acceptance.
- `workflows/42_FUTU_PHASE_B_REAL_OPEND.md` — N3.6 real-integration runbook + signed security review.
- `workflows/43_INVESTMENT_BOARD.md` — N3.3 architecture, prompts, attribution under TradingAgents Apache-2.0.
- `docs/adr/ADR-0005-investment-board-tradingagents-prompts.md` — license attribution + the chosen IIC adaptations.

#### N3.9 — Acceptance for this iteration

Iteration is done when:

1. Pre-flight + N3.0 audit gap closed; `lake.futu_audit` migration runs cleanly on a fresh Postgres.
2. Event-Triage Gate (N3.1) shipped + flag-gated.
3. Three teams emit `plan.v1` (N3.2); per-team E2E test green.
4. Investment Board (N3.3) shipped; `BoardDecisionV1` lands in `lake.advice` with chain still verifying.
5. Trading-room brief (N3.4) renders; dashboard surface live behind the flag.
6. Trading-room DAG (N3.5) E2E green for happy path + 2 degraded paths.
7. FUTU Phase B (N3.6) — security review signed; pentest green; `agent_futu.enabled` ON; one morning_brief run with portfolio context attached.
8. Burn-in extended (N3.7); 6-phase regime exits 0.
9. Test count: ~280 → ~400+ cases.
10. `git commit + git push origin main`.

#### N3.10 — Cost ceiling

- N3.0 + N3.1 + N3.2 + N3.5 + N3.7 + N3.8: 0 LLM cost (synthetic + tests).
- N3.3 Investment Board E2E test: ≤ $0.50 (10 board decisions × $0.05 each).
- N3.6 FUTU Phase B drills: 0 LLM cost.
- Real-API drills (cost-cap chaos): hard-capped at $1.
- **Iteration LLM ceiling: $5.** If you trip $5, stop and report.

#### N3.11 — Dreadful limitations (still no synthetic bypass)

Same list as the previous iteration, plus:

| Item | Why no mock | What real acceptance means |
|---|---|---|
| FUTU audit chain in Postgres (N3.0) | Tamper-evidence is real or it isn't | Real Postgres + real `BEFORE INSERT` trigger + revoked UPDATE/DELETE on `iic_app` |
| OpenTimestamps anchor (N3.6) | A mocked anchor proves nothing | Real `commits.opentimestamps.org` calls + 7-day verification |
| FUTU Phase B real OpenD (N3.6) | Read-only is the load-bearing safety | Real OpenD, real paper account, real firewall, real pentest |
| Board decision persisted to advice ledger (N3.3) | Hash-chain has to actually link | Real Postgres + real verify_chain after N runs |

#### N3.12 — Reporting back

At iteration end, post a tight summary:
- Pre-flight pass/fail.
- N3.0 audit gap closed: yes/no.
- N3.1–N3.5 trading-room items: shipped or blocked.
- N3.6 FUTU Phase B: signed off + green.
- Burn-in: 6-phase regime, which phases real-integration-gated, artifact URL.
- Test count delta.
- Any dreadful-limitation deviations with reasons.
- Next-iteration recommendation (likely T2.5 live benchmarking, T2.9 Bull/Bear at fundamental layer, T2.10 indicator-taxonomy block for Quant; first real T3 candidates).

---

## 7. Sources

- [VegarGG/Investment-Intelligence-Center](https://github.com/VegarGG/Investment-Intelligence-Center) @ HEAD `5e64575`
- `plan/IIC_Development_Plan_v2.5_Combined.md` (D4 in project folder)
- `ITERATION_v2_5_finish_T1_open_T2.md` (in project folder)
- `workflows/00_INDEX_AND_CONVENTIONS.md` through `workflows/41_FUTU_READONLY_INTEGRATION.md`
- `docs/security/FUTU_readonly_review.md`
- `docs/adr/ADR-0001` through `ADR-0004`
