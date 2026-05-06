# Investment Intelligence Center (IIC) v2.1

> Personal, always-on, agentic investment-advisory system. Six AI agents (Intelligence, Fundamental, Quant, Persona, Backtest, Secretary) collaborate and compete on a single Linux mini-PC. Suggestion-only — no real-money trading.

## Specs

- [`EXECUTIVE_SUMMARY_bilingual.md`](EXECUTIVE_SUMMARY_bilingual.md) — bilingual elevator pitch.
- [`PLAN_v2.1_Investment_Intelligence_Center.md`](PLAN_v2.1_Investment_Intelligence_Center.md) — full spec (single source of truth).
- [`workflows/`](workflows/) — 16 self-contained, vibe-coding-friendly briefs (`00_INDEX_AND_CONVENTIONS.md` first).

## Build order

Workflow docs are numbered for dependency order. Pick the lowest-numbered doc whose dependencies are complete. Phase mapping:

| Phase | Workflow docs | Outcome |
|-------|---------------|---------|
| 0 — Foundations | 01, 02, 03, 04, 05, 06 | Substrate, data lake, LLM router, prompts, bus, orchestrator |
| 1 — Intelligence MVP | 10 | News + macro + WeChat brief |
| 2 — Data Pipeline | 02 (extends) | OHLCV + factor matrix |
| 3 — Fundamental | 11 | Filings + valuation + advice |
| 4 — Quant | 12 | 8-factor library + signals |
| 5 — Persona Fleet | 13 | Style-mimic strategists |
| 6 — Backtest | 14 | Live judge + leaderboard |
| 7 — Secretary | 15, 20, 21 | Chatbot + WeChat + dashboard |
| 8 — Hardening | 30, 31 | DR drill, NAS migrate dry-run, eval harness |

## Disclaimer

For personal research only. Not investment advice. IIC is not a registered investment advisor.
