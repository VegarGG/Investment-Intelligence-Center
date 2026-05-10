# Workflow 43 — Investment Board (v2.5 N3.3 / T2.4)

**Owner:** agent_board · **Plan ref:** `plan/D5_IIC_Prototype_Review_and_Next_Iteration.md` §N3.3 · **License attribution:** [ADR-0005](../docs/adr/ADR-0005-investment-board-tradingagents-prompts.md) (TradingAgents Apache-2.0)

## 1. Ground truth

The Investment Board is the headline of v2.5: it watches the analysis
teams' `plan.v1` outputs and arbitrates **one** chosen plan per
trigger event, with a documented dissent record and a 3-way risk view.
Its decision is persisted to `lake.advice` under `agent='board'` so
the same hash chain that protects every other agent's advice protects
the Board's.

## 2. Module layout

```
apps/agent_board/
  board/__init__.py
  board/main.py             # FastAPI /decide
  board/bull_bear.py        # Bull/Bear research debate (≤ 2 rounds)
  board/risk_panel.py       # 3-way Aggressive/Conservative/Neutral
  board/chair.py            # Chair LLM-synthesizes BoardDecisionV1
  board/schema.py           # BoardDecisionV1 Pydantic model
  board/persist.py          # writes board.decision.v1 → lake.advice
  tests/test_bull_bear.py
  tests/test_risk_panel.py
  tests/test_chair.py
  tests/test_e2e_board.py
```

Prompts live under `packages/prompts/registry/board.{bull,bear,risk_*,chair}/`.
LLM matrix entries: 5 Flash callers + 1 Pro caller (Chair).

## 3. Workflow steps (per `/decide` call)

1. Receive `{trigger_event_id, plans: [PlanV1 ...], persist}`.
2. Run **Bull/Bear** debate (max 2 rounds). Each turn is a `chat_or_skip`
   Flash call. Cost-skipped turns flip `transcript.degraded=True`.
3. Run **Risk Panel** (Aggressive → Conservative → Neutral, one turn each).
4. **Chair** synthesises one Pro-tier call returning JSON with
   `{chosen_plan_id, chair_rationale, dissent_record, risk_view, confidence}`.
   Hard validators: `chosen_plan_id ∈ considered_plan_ids`; dissent
   non-empty when `len(plans) > 1`.
5. Fallback paths:
   - Bull/Bear degraded → Chair skipped, deterministic highest-confidence pick.
   - Chair returned junk JSON or unknown plan id → same deterministic fallback.
6. If `persist=True`, project `BoardDecisionV1` → `AdviceV1` and append to
   `lake.advice` under `agent='board'`. The migration-0002 trigger enforces
   chain linkage.

## 4. Cost discipline

| Caller | Tier | Calls / decision | Budget |
|--------|------|------------------|--------|
| `board.bull` | Flash | up to 2 | $0.005 each |
| `board.bear` | Flash | up to 2 | $0.005 each |
| `board.risk_aggressive` | Flash | 1 | $0.005 |
| `board.risk_conservative` | Flash | 1 | $0.005 |
| `board.risk_neutral` | Flash | 1 | $0.005 |
| `board.chair` | Pro | 1 | $0.025 |
| **Per-decision ceiling** | | | **≤ $0.05** |

## 5. Acceptance criteria

- `apps/agent_board/tests/test_bull_bear.py` — 3 cases.
- `apps/agent_board/tests/test_risk_panel.py` — 3 cases.
- `apps/agent_board/tests/test_chair.py` — 5 cases (incl. fallback paths).
- `apps/agent_board/tests/test_e2e_board.py` — happy path, degraded path, validator rejection.

## 6. Risks

| Risk | Mitigation |
|------|------------|
| Chair always picks the same team. | Walk-forward gate (workflow 33) replays board prompts on every prompt change in `packages/prompts/registry/board/`. |
| LLM cost runaway in burn-in. | `chat_or_skip` everywhere except Chair; Pro tier capped at 1 call/decision. |
| Stale `BoardDecisionV1` projected to AdviceV1 with wrong direction. | `persist.board_decision_to_advice` covered by `test_e2e_board::test_board_e2e_emits_one_decision_with_chosen_in_considered`. |

## 7. Cross-references

- 34 — [Trading Room DAG](34_TRADING_ROOM_DAG.md)
- 40 — [Trading Room Overview](40_TRADING_ROOM_OVERVIEW.md)
- 02 — Data Lake (chain trigger reused)
- ADR-0005 — TradingAgents prompt attribution
