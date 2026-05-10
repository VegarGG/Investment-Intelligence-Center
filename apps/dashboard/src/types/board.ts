// v2.5 N3.3 / T2.4 — TypeScript mirror of `apps.agent_board.board.schema.BoardDecisionV1`.
//
// Manual port. Keep field names + value constraints in sync with
// `apps/agent_board/board/schema.py` — the test_e2e_board test serialises
// BoardDecisionV1 to JSON; the dashboard consumes that shape.

export interface BoardDecisionV1 {
  schema: "board.decision.v1";
  id: string;
  trigger_event_id: string;
  considered_plan_ids: string[];
  chosen_plan_id: string;
  chair_rationale: string;
  dissent_record: string;
  risk_view: string;
  confidence: number; // [0, 1]
  issued_at: string;
}

export interface TradingRoomBriefV1 {
  ticker: string;
  issued_at: string;
  decision: BoardDecisionV1;
  markdown: string;
}
