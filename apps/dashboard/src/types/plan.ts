// v2.5 T2.2 / B3.2 — TypeScript mirror of `schema.plan.PlanV1`.
//
// Manual port. Dashboard reads `plan.v1` events from the NATS-WS bridge
// and renders the trading-room view. Keep these field names + value
// constraints in sync with `packages/schema/schema/plan.py` — the
// `test_goldens_set_loads_and_validates` test in `test_plan_v1.py`
// exercises the same fixture both languages must agree on.

export type Team = "quant" | "fundamental" | "persona" | "intel";
export type Action = "buy" | "sell" | "hold";
export type AssetKind = "equity" | "etf" | "future" | "option" | "fx" | "crypto" | "bond";

export interface Asset {
  kind: AssetKind;
  ticker: string;
  venue: string;
  name?: string;
}

export interface Evidence {
  kind: "news" | "filing" | "factor" | "macro" | "social" | "filing_url";
  ref?: string;
  url?: string;
}

export interface PortfolioContextV1 {
  current_position_pct_nav: number; // [-100, 100]
  open_orders_count: number;
  cost_basis_per_share?: number | null;
  base_currency: string;
}

export interface PlanV1 {
  schema: "plan.v1";
  id: string; // ULID, 26 chars
  team: Team;
  persona_slug?: string | null;
  issued_at: string; // ISO 8601 datetime with timezone
  asset: Asset;
  action: Action;
  entry_price: number;
  entry_window_open: string;
  entry_window_close: string;
  target_price: number;
  stop_loss: number;
  max_drawdown_pct: number; // [0, 100]
  horizon_days: number; // [1, 365]
  sizing_pct_nav: number; // [0, 100]
  confidence: number; // [0, 1]
  thesis: string;
  evidence: Evidence[];
  portfolio_context?: PortfolioContextV1 | null;
  expires_at: string;
  disclaimer?: string | null;
}

/**
 * Lightweight runtime guard — checks the must-hold invariants the
 * Python validators enforce server-side. Used by the dashboard to
 * refuse rendering a malformed plan rather than silently misdisplaying.
 */
export function isValidPlanV1(p: unknown): p is PlanV1 {
  if (typeof p !== "object" || p === null) return false;
  const x = p as PlanV1;
  if (x.schema !== "plan.v1") return false;
  if (!/^[0-9A-HJKMNP-TV-Z]{26}$/.test(x.id)) return false;
  if (!["quant", "fundamental", "persona", "intel"].includes(x.team)) return false;
  if (!["buy", "sell", "hold"].includes(x.action)) return false;
  if (x.team === "persona" && !x.persona_slug) return false;
  if (x.team !== "persona" && x.persona_slug) return false;
  if (x.team === "persona" && !x.disclaimer) return false;

  const open = Date.parse(x.entry_window_open);
  const close = Date.parse(x.entry_window_close);
  if (!(close > open)) return false;

  if (x.action === "buy") {
    if (!(x.target_price > x.entry_price && x.entry_price > x.stop_loss)) return false;
  } else if (x.action === "sell") {
    if (!(x.stop_loss > x.entry_price && x.entry_price > x.target_price)) return false;
  }

  if (x.action !== "hold" && x.evidence.length === 0) return false;
  if (x.confidence < 0 || x.confidence > 1) return false;
  if (x.max_drawdown_pct < 0 || x.max_drawdown_pct > 100) return false;
  if (x.horizon_days < 1 || x.horizon_days > 365) return false;
  if (x.sizing_pct_nav < 0 || x.sizing_pct_nav > 100) return false;

  return true;
}
