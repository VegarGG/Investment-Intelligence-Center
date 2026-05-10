# Workflow 34 — Trading-Room DAG (v2.5 N3.5 / T2.8)

**Owner:** orchestrator · **Plan ref:** `plan/D5_IIC_Prototype_Review_and_Next_Iteration.md` §N3.5 · **Sibling docs:** [40_TRADING_ROOM_OVERVIEW.md](40_TRADING_ROOM_OVERVIEW.md), [43_INVESTMENT_BOARD.md](43_INVESTMENT_BOARD.md)

## 1. Ground truth

Wires the full event-driven trading-room flow:

```
intel.event.high_impact.v1
  → Event-Triage Gate (orchestrator.plan.event_triage.triage)
  → fan-out to {agent_quant, agent_fundamental, agent_persona} /team_plan
  → Investment Board (Bull/Bear → Risk → Chair) — agent_board /decide
  → Trading-room brief (agent_secretary, severity=ALERT)
  → Notify
```

Idempotency key: `(trigger_event_id)`. The orchestrator's existing
idempotency cache deduplicates re-runs of the same event.

## 2. Module layout

| Path | Role |
|------|------|
| `apps/orchestrator/orchestrator/plan/event_triage.py` | Numeric + LLM tie-break gate. Emits `triage.decision.v1`. |
| `apps/orchestrator/orchestrator/plan/trading_room.py` | The DAG itself: `n_triage → n_fanout → n_board → n_brief → n_notify`. |
| `apps/agent_board/board/main.py` | `/decide` endpoint — Bull/Bear, Risk, Chair, persist to `lake.advice` under `agent='board'`. |
| `apps/agent_secretary/secretary/outbound/trading_room_brief.py` | Pure-function Markdown composer; pinned by snapshot test. |
| `apps/dashboard/src/routes/TradingRoom.tsx` | Inline brief + dissent expander. |

## 3. Workflow steps

1. NATS subject `intel.event.high_impact.v1` arrives → orchestrator
   trigger constructs `TradingRoomState`.
2. `n_triage` calls `event_triage.triage(payload)`. Emits a
   `triage.decision.v1` envelope (route ∈ {trading_room,
   morning_brief_only, drop}) and short-circuits when route ≠
   trading_room.
3. `n_fanout` calls each of the three team `/team_plan` endpoints in
   sequence. Per-team breaker-open responses are collected as
   `state.team_failures`; the brief notes degraded state but the DAG
   continues.
4. `n_board` calls `agent_board /decide` with the surviving plans +
   `persist=true`. Board-side LLM cost-skipped paths fall back to
   highest-confidence plan; the response carries `degraded=True`.
5. `n_brief` calls `agent_secretary` with the decision, the considered
   plans, and the degraded flag. The composer is deterministic — no
   LLM cost; format is pinned in `tests/fixtures/trading_room/`.
6. `n_notify` pushes the markdown at severity=ALERT.

## 4. Vibe prompts (per workflow ground-truth methodology)

```
You are extending the trading-room DAG. The state shape is
TradingRoomState (apps/orchestrator/orchestrator/plan/trading_room.py).
Failure isolation rule: any single failed agent must NOT block the DAG;
mark `state.degraded=True`, append to `state.degraded_reasons`, and let
downstream nodes see what happened.

When you add a new node, also extend tests/test_trading_room_dag_e2e.py
with the corresponding case.
```

## 5. Acceptance criteria

- `tests/test_trading_room_dag_e2e.py` — 3 cases: happy path, one team
  breakered, board degraded. All green.
- `tests/test_trading_room_brief_format.py` — snapshot vs golden
  markdown (whitespace-tolerant). Green.
- `apps/agent_board/tests/test_e2e_board.py` — board emits valid
  BoardDecisionV1; `chosen_plan_id ∈ considered_plan_ids`; projected
  AdviceV1 schema-valid.

## 6. Risks

| Risk | Mitigation |
|------|------------|
| Spurious wakes during low-impact news bursts. | Numeric triage thresholds are tuned for `regime_change_score >= 0.85`; medium signals route to `morning_brief_only`. |
| LLM cost spikes when many events arrive in burst. | Chair budget capped at $0.05/decision; `chat_or_skip` fall-through; total board-decision cost ceiling per iteration in `pyproject.toml`. |
| Board persist failure leaves brief without ledger anchor. | `persist_decision` returns the row hash; failure is logged and surfaced in the response payload, but the brief still ships (degraded). |

## 7. Cross-references

- 40 — [Trading Room Overview](40_TRADING_ROOM_OVERVIEW.md)
- 43 — [Investment Board](43_INVESTMENT_BOARD.md)
- 06 — Orchestrator (DAG runner + StateGraph)
- 02 — Data Lake (advice ledger, hash-chain trigger)
