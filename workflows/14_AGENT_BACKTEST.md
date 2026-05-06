# Workflow 14 — Backtest Agent ("The Live Judge")

> **Depends On:** `02_DATA_LAYER.md`, `05_DATA_BUS_AND_SCHEMAS.md`, plus subscribers from `11_AGENT_FUNDAMENTAL.md`, `12_AGENT_QUANT.md`, `13_AGENT_PERSONA.md`.
> **Owns:** `apps/agent_backtest/` — paper trading every advice from the moment it's published, mark-to-market, attribution, leaderboard, feedback events.
> **Status:** Final.

---

## 1. Purpose

Continuously evaluate every advisory agent and rank them on real outcomes. Loop the verdict back to the source agent for self-improvement. The backtester is the system's epistemic spine — without it, the leaderboard is fairy tale.

There is **no LLM in the math path** here. LLM is used only to write a human-readable narrative for closed trades.

---

## 2. Ground Truth

### 2.1 Capabilities

1. **Forward paper trading.** Every `advice.v1` opens a virtual position the moment it is published. Fills assumed at midpoint of `entry_band` with a slippage model. Stops/targets monitored intraday.
2. **Historical backtesting.** On agent-prompt or strategy change, replay against the last N years on liquid symbols.
3. **Live benchmark.** Equal-weight SPY+ACWI+GLD+IEF as the passive benchmark; risk-parity as the smart-passive benchmark.
4. **Attribution.** Per-agent: hit rate, avg R-multiple, Sharpe, Sortino, Calmar, max DD, time-in-market, hold time, turnover.
5. **Feedback loop.** Each closed trade publishes `backtest.fill.v1` *back to the originating agent*, plus a per-week digest the agent uses as memory in subsequent calls.
6. **Leaderboard.** Per-agent ranking with stat-sig flags.

### 2.2 Slippage model

```
fill_px = midpoint(entry_band) * (1 + sign(direction) * slip_bps / 10_000)
slip_bps = base + size_factor + volatility_factor
  base       = 5 bps for liquid US/HK/A-share large-cap; 15 bps else
  size_factor= 5 bps if size_usd > 0.5% of 5-day median dollar volume; else 0
  volatility_factor = 0.05 * 20-day realized vol in bps
```

### 2.3 Mark-to-market cadence

| Phase | Frequency |
|-------|-----------|
| Market hours (per asset's primary venue) | every 60 s |
| Off hours | every 15 min |
| Weekend / holiday | every 60 min |

Marks persisted in the `lake.backtest_marks` hypertable. Old marks compacted to 5-minute aggregates after 30 d.

### 2.4 Exit rules

- `target_band` reached → exit at the **low** of the band.
- `stop_loss` breached → exit at the **stop_loss** value (not market).
- `expires_at` reached without target/stop → exit at last close.
- `early_close` only via explicit human override (admin endpoint). Logged and audited.

### 2.5 Leaderboard math

📌 **GROUND TRUTH:**

```
score(agent) = w1 * Sharpe + w2 * hit_rate + w3 * R_avg + w4 * (1 / (1 + max_DD))
              - w5 * turnover_penalty - w6 * stale_advice_penalty
defaults: w1=0.30, w2=0.20, w3=0.25, w4=0.15, w5=0.05, w6=0.05
min N for ranking: 20 closed trades, 60 days live
```

Until both thresholds are met, the leaderboard tags the agent `provisional`. Provisional agents are still ranked but with a strikethrough or tag in the UI.

### 2.6 Stat-sig flag

For each agent's Sharpe, run a bootstrap CI (1000 resamples). If `lower_95 > 0`, mark `stat_sig = True`. Used in the dashboard to dampen noisy ranking churn.

---

## 3. Architecture

```
   advice.*.v1 ─────► position opener ─────► lake.backtest_positions (state=open)
                                                       │
                                                       ▼
                                              mark_to_market (60s / 15min)
                                                       │
                       ┌───────────────────────────────┤
                       ▼                               ▼
              exit detector (stop/target/expiry)   lake.backtest_marks (hypertable)
                       │
                       ▼
              close position → lake.backtest_positions (state=closed)
                       │
                       ▼
              narrate (Flash) → backtest.fill.v1
                       │
            ┌──────────┴──────────┐
            ▼                     ▼
   originating agent         attribution daily
   (memory loop)             → lake.backtest_attribution_daily
                                       │
                                       ▼
                            leaderboard weekly
                            → backtest.leaderboard.v1
```

---

## 4. Module Layout

```
apps/agent_backtest/
├── pyproject.toml
├── Dockerfile
├── backtest/
│   ├── __init__.py
│   ├── main.py                # FastAPI + scheduler + NATS subscribers
│   ├── opener.py              # advice → position
│   ├── slippage.py            # §2.2 model
│   ├── mtm/
│   │   ├── pricer.py          # pulls latest mark from lake.timeseries / live feed
│   │   ├── scheduler.py       # 60s/15m/60m cadence
│   │   └── compactor.py       # rolls old marks to 5-min aggregates
│   ├── exits.py               # stop/target/expiry detection
│   ├── narrate.py             # Flash post-trade narrative
│   ├── attribution/
│   │   ├── daily.py
│   │   ├── leaderboard.py
│   │   └── stats.py           # Sharpe, Sortino, Calmar, bootstrap CI
│   ├── benchmark.py           # passive + smart-passive
│   ├── historical/
│   │   ├── runner.py          # one-shot replay over last N years
│   │   └── universe.py        # PIT-correct historical universe
│   └── publish.py
└── tests/
    ├── test_slippage.py
    ├── test_exits.py
    ├── test_attribution_math.py
    ├── test_leaderboard_provisional.py
    └── test_chain_integrity.py
```

---

## 5. Workflow Steps

### Step 5.1 — Subscribe to advice topics

`main.py` subscribes to `advice.>` (wildcard). Each message:
1. Validate via `AdviceV1`. Reject uncited (`evidence` empty for `direction != flat`).
2. Compute fill: `slippage.compute_fill_px(advice)`.
3. Insert into `lake.backtest_positions` (state=`open`). Use the advice's ULID as a deterministic foreign key.
4. Idempotent: if a position for this advice already exists, no-op.

### Step 5.2 — Mark-to-market loop

`mtm/scheduler.py` is an asyncio loop that wakes per-position based on the asset's primary venue's market hours (helper: `is_market_open(venue, ts)`). Pulls latest price from `lake.timeseries` (PIT-correct using `as_of <= now()`). Writes a row to `lake.backtest_marks` and updates `lake.backtest_positions.unrealized_pnl_usd` (denormalized for fast reads).

Use a single coroutine that batches per minute: pull all open positions, dedupe price queries by symbol, parallelize the price fetch, then write back.

### Step 5.3 — Exit detection

After each mark, `exits.py` checks:
- `direction=long`: `mark_px >= target_low` → exit; `mark_px <= stop_loss` → exit.
- `direction=short`: `mark_px <= target_high` → exit; `mark_px >= stop_loss` → exit.
- `now >= expires_at` and still open → exit at last close, reason `expiry`.

Exit writes:
- `lake.backtest_positions.state = "closed"` plus exit_px, exit_reason, pnl_usd, pnl_r, max_dd_pct.
- `narrate.write(closed_position)` → Flash → narrative string.
- Publish `backtest.fill.v1`.

### Step 5.4 — Daily attribution

End-of-day cron (00:30 UTC, asof = trading day end in each region's primary tz):

1. Aggregate per-agent: closed trades today, P&L, hit rate, R-avg, Sharpe (rolling 60d), max DD.
2. Compute benchmark P&L (passive + smart-passive) for the same day.
3. Write to `lake.backtest_attribution_daily`.
4. Publish `backtest.daily.v1` for the dashboard.

### Step 5.5 — Weekly leaderboard

Sunday 23:00 UTC:

1. For each agent with ≥ 20 closed trades AND ≥ 60 live days, compute the leaderboard score per §2.5.
2. Bootstrap Sharpe CI per §2.6.
3. Mark provisional otherwise.
4. Publish `backtest.leaderboard.v1`.
5. Secretary references this in the next morning brief.

### Step 5.6 — Feedback to the source agent

`backtest.fill.v1` carries the `agent` field. The persona agent's `feedback.py` (per `13_AGENT_PERSONA.md` §5.4) consumes these for memory updates. Fundamental and Quant agents subscribe similarly: closed-trade lessons feed into their next thesis/narrative.

### Step 5.7 — Historical replay (one-shot)

`historical/runner.py` is a separate container, kicked manually:

```
docker compose run --rm agent_backtest python -m backtest.historical.runner \
  --strategy advice.quant.v1 --start 2018-01-01 --end 2025-01-01 \
  --universe SPX,HSI50,A50
```

Uses PIT-correct universe and PIT-correct factor matrices. Output goes to `lake.backtest_walkforward` for the dashboard.

### Step 5.8 — Chain integrity audit

Daily, `attribution/daily.py` verifies the hash chain in `lake.advice` for every agent (`data_lake.advice_ledger.verify_chain`). A broken chain emits `ops.alert.v1` of severity `critical` and pauses leaderboard publication until resolved.

---

## 6. HTTP API

```
POST /run/historical          → kick a historical replay
GET  /positions/open
GET  /positions/closed?agent=...&since=...
GET  /leaderboard
GET  /attribution/daily?date=...
GET  /health
```

---

## 7. Vibe Prompts (paste-ready)

🧪 **Scaffold the backtester:**
> Implement `apps/agent_backtest/` per `14_AGENT_BACKTEST.md`. Subscribe to `advice.>` and open virtual positions with the §2.2 slippage model. Mark-to-market via the §2.3 cadence using `lake.timeseries` PIT-correct reads. Exits per §2.4. Closed trades narrate via Flash and publish `backtest.fill.v1`. Daily and weekly aggregations per §5.4–§5.5. Tests cover: slippage on liquid vs illiquid names, target hit on long, stop hit on short, expiry exit, attribution math (Sharpe / R-avg with a known fixture), provisional flagging on N<20, chain integrity check.

🧪 **MTM scheduler:**
> Build `backtest/mtm/scheduler.py` to wake every 60 s during market hours per venue, every 15 min off-hours. Use a single coroutine that batches all open positions per tick: pull distinct symbols, parallel-fetch latest mark from `lake.timeseries`, write per-position rows to `lake.backtest_marks`. CPU target: < 5% on Beelink SER8 with 200 open positions.

🧪 **Stat-sig bootstrap:**
> Implement `backtest/attribution/stats.py:sharpe_ci(returns, alpha=0.05, n_boot=1000) -> (point, lower, upper)` using numpy bootstrap. Use a fixed seed for reproducibility in tests. Add a Pro-as-judge sanity check at PR time that the CI matches scipy's expectation on a known distribution.

🧪 **Narrative composer:**
> Implement `backtest/narrate.py:compose(closed_position) -> str`. Flash call. Inputs: the original advice, the fill outcome, mark trajectory summary (entry, max_dd, exit). Output ≤ 80 words, factual, no hyperbole. Tests assert no banned words ("crushed", "epic", "moonshot") sneak in.

---

## 8. Acceptance Criteria

- [ ] `pytest apps/agent_backtest -q` is green.
- [ ] Publishing a synthetic `advice.fundamental.v1` to the bus opens a position visible in `lake.backtest_positions` within 5 s.
- [ ] Setting the synthetic asset's price at `target_low` triggers an exit and emits `backtest.fill.v1` with `exit_reason="target"`.
- [ ] `GET /leaderboard` returns the correct ranking on a fixture with two agents, one with 25 trades (real) and one with 10 (provisional).
- [ ] CPU on the Beelink SER8 with 200 open positions stays < 10% during the MTM tick.
- [ ] Chain integrity audit passes on a healthy DB; corrupting one row in tests yields a `ops.alert.v1` of severity `critical`.
- [ ] Historical replay runs against 2 years of SPX 500 in < 30 minutes on the SER8.
- [ ] Per-agent attribution surfaces in Grafana within 1 minute of a fill closing.

---

## 9. Risks & Gotchas

⚠️ **Survivorship bias in historical mode.** Universe must be PIT (`02_DATA_LAYER.md` §6). Test fixtures must include a delisting case (e.g., LEH 2008) to verify the universe drops it on/before delisting.

⚠️ **Market-hours definitions.** Half-days and futures sessions break naive `09:30–16:00` rules. Use a venue calendar (e.g., `pandas-market-calendars`).

⚠️ **Stop fills that gap through.** A stop at $85 with the asset gapping open at $80 → fill at $80, not $85. Track gaps and adjust `slip_bps` accordingly so the leaderboard isn't artificially generous.

⚠️ **Mark feed latency.** If `lake.timeseries` doesn't have a mark for the last minute, fall back to last available — but the position's `mark_age_s` exposed in the dashboard alerts when staleness exceeds 5 min.

⚠️ **Pessimistic fills bias.** The slippage model is conservative on purpose; the leaderboard penalizes high-turnover agents naturally. If reality outperforms backtest, that's fine. If reality underperforms backtest, increase `base` slip — never decrease.

⚠️ **Idempotency.** Advice retries (NATS at-least-once) must not open duplicate positions. Use the advice ULID as an idempotency key on `lake.backtest_positions`.

⚠️ **Leaderboard freshness vs. churn.** Weekly recomputation is intentional — daily ranking churn would mislead. Don't yield to the temptation of a "real-time leaderboard."

⚠️ **Cost of narration.** 100 closed trades/week × Flash narrate ≈ negligible, but 10 000 historical replays in narrate-mode is not. Historical replays default to **no narration**; add `--narrate` opt-in flag.

⚠️ **Exit at expiry on illiquid weekend.** If `expires_at` falls on a weekend, exit at next trading day's open, not last weekday close. Defensive default.

---

## 10. Cross-References

- `advice.v1` validators: `05_DATA_BUS_AND_SCHEMAS.md` §3.
- Per-agent feedback consumption: `13_AGENT_PERSONA.md` §5.4 (and equivalent for fundamental/quant via prompt-context injection).
- Leaderboard rendering: `21_DASHBOARD_UI.md` §6 + `15_AGENT_SECRETARY.md` §6 (`/leaderboard` chat command).
- Significant-fill push to WeCom alerts: `20_NOTIFIER_WECHAT.md` §7.

---

## Changelog

- **v1.0** — Extracted from `PLAN_v2.1` §4.5 + §14. Slippage model formalized; stat-sig flag and provisional rule made explicit; historical-replay narration cost guard added.
