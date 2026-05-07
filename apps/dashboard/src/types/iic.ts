/**
 * Frontend mirror of `packages/schema/` Pydantic models. When the schema
 * package adds TS codegen, this file becomes the import target.
 */

export type Direction = "long" | "short" | "flat";
export type AssetKind = "equity" | "etf" | "future" | "option" | "fx" | "crypto" | "bond";

export type EvidenceKind = "news" | "filing" | "factor" | "macro" | "social" | "filing_url";

export interface Asset {
  kind: AssetKind;
  ticker: string;
  venue: string;
  name?: string | null;
}

export interface Evidence {
  kind: EvidenceKind;
  ref?: string | null;
  url?: string | null;
}

export interface AdviceV1 {
  schema: "advice.v1";
  id: string;
  agent: string;
  issued_at: string;
  asset: Asset;
  thesis: string;
  direction: Direction;
  confidence: number;
  entry_band: [number, number];
  target_band: [number, number];
  stop_loss: number;
  horizon_days: number;
  max_drawdown_pct: number;
  sizing_hint_pct_nav: number;
  expires_at: string;
  evidence: Evidence[];
  disclaimer?: string | null;
}

export type MacroRegime =
  | "rate_cut"
  | "risk_on"
  | "risk_off"
  | "stagflation"
  | "recession"
  | "crisis"
  | "unknown";

export interface IntelEvent {
  id: string;
  rank: number;
  headline: string;
  why_it_matters: string;
  primary_asset_links: string[];
  regime_change_score: number;
  novelty: number;
  sentiment?: number;
}

export interface BiasBalance {
  by_region: Record<string, number>;
  by_lean: Record<string, number>;
}

export interface IntelDigestV1 {
  schema: "intel.digest.v1";
  id: string;
  issued_at: string;
  macro_regime: MacroRegime;
  events: IntelEvent[];
  bias_balance: BiasBalance;
  macro_thesis: string;
}

export interface IntelBriefV1 {
  schema: "intel.brief.v1";
  issued_at: string;
  audience: "principal" | "family";
  language: "en" | "zh";
  markdown: string;
  char_count: number;
  wechat_safe: boolean;
}

export interface LeaderboardEntry {
  agent: string;
  trades_closed: number;
  hit_rate: number;
  r_avg: number;
  sharpe: number;
  sortino: number;
  calmar: number;
  max_dd_pct: number;
  vs_smart_passive_pct: number;
  score: number;
  provisional: boolean;
}

export interface BacktestLeaderboardV1 {
  schema: "backtest.leaderboard.v1";
  as_of: string;
  entries: LeaderboardEntry[];
}

export interface OpenPositionRow {
  advice_id: string;
  agent: string;
  ticker: string;
  venue: string;
  direction: Direction;
  entry_px: number;
  mark_px: number | null;
  target_band: [number, number];
  stop_loss: number;
  unrealized_pnl_usd: number;
  opened_at: string;
}

export interface ClosedPositionRow extends OpenPositionRow {
  exit_px: number;
  exit_reason: "target" | "stop" | "expiry" | "early_close";
  closed_at: string;
  pnl_usd: number;
  pnl_r: number;
}

export interface HostMetrics {
  cpu_temp_c: number | null;
  cpu_pct: number | null;
  ram_pct: number | null;
  nvme_temp_c: number | null;
  nvme_wear_pct: number | null;
  disk_free_gb: number | null;
  ups_battery_pct: number | null;
}

export interface ContainerStatus {
  name: string;
  state: "running" | "exited" | "restarting" | "unknown";
  uptime_s: number;
}

export interface LlmSpendSnapshot {
  month_to_date_usd: number;
  monthly_cap_usd: number;
  breaker_state: "open" | "closed" | "half_open";
  by_caller_24h_usd: Record<string, number>;
}

export type Tone = "terse" | "conv" | "edu";
