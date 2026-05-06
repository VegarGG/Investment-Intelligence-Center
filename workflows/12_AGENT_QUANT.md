# Workflow 12 — Quant Agent

> **Depends On:** `02_DATA_LAYER.md`, `03_LLM_CLIENT.md`, `04_PROMPT_REGISTRY.md`, `05_DATA_BUS_AND_SCHEMAS.md`, `10_AGENT_INTELLIGENCE.md`.
> **Owns:** `apps/agent_quant/` — factor library, regime-aware signal combination, vol-targeted sizing, `advice.quant.v1`.
> **Status:** Final.

---

## 1. Purpose

Run statistical signals. Not a black box: every signal carries a one-sentence explanation suitable for the brief. Math is Python; LLM is only used for the trade narrative.

---

## 2. Ground Truth

### 2.1 Factor library (initial set)

| # | Factor | Universe | Frequency |
|---|--------|----------|-----------|
| 1 | 12-1 cross-sectional momentum | US large-cap (S&P 500), A50, HSI 50 | Daily close |
| 2 | 5-day mean-reversion residual (post-news) | Same as #1 | Daily |
| 3 | Volatility risk premium (front-month IV − 20-day RV) | Liquid optionable names | Daily |
| 4 | Earnings drift (PEAD) | Names with earnings T-1 to T+5 | Daily |
| 5 | Insider buying clusters (Form 4) | US universe | Weekly |
| 6 | Sector relative strength (RRG) | GICS sector ETFs | Daily |
| 7 | Crypto basis (perp − spot) | Top 10 by volume | Hourly |
| 8 | FX carry | G10 pairs (top 6) | Daily |

### 2.2 Sub-agents

| Sub-agent | Role | LLM tier |
|-----------|------|----------|
| `quant.feature` | Builds factor matrix nightly + every 15 min for intraday subset | none |
| `quant.signal` | Combines factors per regime (regime from `intel.digest.v1.macro_regime`) | none |
| `quant.risk` | Vol targeting, position sizing, correlation cap | none |
| `quant.writer` | Composes `advice.quant.v1` narrative | Flash (Pro on regime change) |

### 2.3 Regime-aware combination

📌 The `quant.signal` step reads `iic_state.macro_regime` (from KV) and applies a per-regime weighting:

| Regime | Momentum | Mean-rev | Vol prem | PEAD | Insider | Sector RS | Crypto basis | FX carry |
|--------|---------:|---------:|---------:|-----:|--------:|----------:|-------------:|---------:|
| `risk_on` | 0.30 | 0.10 | 0.15 | 0.10 | 0.05 | 0.20 | 0.05 | 0.05 |
| `risk_off` | 0.10 | 0.20 | 0.30 | 0.05 | 0.10 | 0.15 | 0.00 | 0.10 |
| `rate_cut` | 0.25 | 0.15 | 0.10 | 0.10 | 0.05 | 0.20 | 0.05 | 0.10 |
| `stagflation` | 0.05 | 0.10 | 0.20 | 0.05 | 0.10 | 0.10 | 0.00 | 0.40 |
| `recession` | 0.05 | 0.30 | 0.30 | 0.10 | 0.10 | 0.10 | 0.00 | 0.05 |
| `crisis` | 0.05 | 0.20 | 0.40 | 0.05 | 0.05 | 0.05 | 0.00 | 0.20 |
| `unknown` | 0.20 | 0.15 | 0.15 | 0.10 | 0.10 | 0.15 | 0.05 | 0.10 |

These are first-cut weights — `quant.risk` enforces gross/net caps so any regime stays tradeable.

### 2.4 Risk caps

📌 **Stable.**

- Vol target: 12% annualized portfolio vol.
- Per-position max: 5% NAV.
- Single-name correlation cap: rolling 60-day correlation > 0.85 with another open position → reduce or skip.
- Sector cap: 25% gross exposure per GICS sector.
- Region cap: 50% gross exposure per region (US, EU, CN, EM).

### 2.5 PIT correctness

Factor builds **must** filter `as_of <= now()` (see `02_DATA_LAYER.md` §6). The backtester quarantines advice tied to a factor build that fails the PIT check.

---

## 3. Architecture

```
       lake.timeseries (PIT) ── feature builder ──► factor matrix (parquet, MinIO)
                                                          │
       lake.events (filings) ──► PEAD / insider feeders ──┤
                                                          │
       intel.digest.v1.macro_regime ──► signal weights ──►│
                                                          ▼
                                                  combined signal
                                                          │
                                                          ▼
                                                  risk shaping
                                                          │
                                                          ▼
                                                advice.quant.v1
```

---

## 4. Module Layout

```
apps/agent_quant/
├── pyproject.toml
├── Dockerfile
├── quant/
│   ├── __init__.py
│   ├── main.py                    # FastAPI + cron + NATS sub
│   ├── universe.py                # PIT-correct universe builder
│   ├── factors/
│   │   ├── momentum.py
│   │   ├── mean_reversion.py
│   │   ├── vol_risk_premium.py
│   │   ├── pead.py
│   │   ├── insider.py
│   │   ├── sector_rs.py
│   │   ├── crypto_basis.py
│   │   └── fx_carry.py
│   ├── feature_matrix.py
│   ├── signal.py
│   ├── risk.py
│   ├── writer.py
│   └── publish.py
└── tests/
    ├── test_pit_factor_build.py
    ├── test_regime_weights.py
    ├── test_risk_caps.py
    └── test_walk_forward.py
```

---

## 5. Workflow Steps

### Step 5.1 — Universe builder

`universe.py` returns the PIT-correct constituents of S&P 500, HSI 50, A50 for any `asof`. Joins `lake.universe_membership` with the asof predicate.

### Step 5.2 — Factor matrix builder

`feature_matrix.py` runs nightly + every 15 min for intraday-relevant factors. Output:

```
lake.factor_matrix
  asof TIMESTAMPTZ, ticker TEXT, factor_id TEXT, value DOUBLE, rank DOUBLE
  PRIMARY KEY (asof, ticker, factor_id)
SELECT create_hypertable('lake.factor_matrix', 'asof', chunk_time_interval => INTERVAL '7 days');
```

📐 **Capacity check.** On Beelink SER8: full nightly build (SPX 500 + HSI 50 + A50) ≈ 90 s using polars; intraday delta ≈ 6 s. Comfortable.

🧪 **VIBE-PROMPT — feature matrix:**
> Implement `quant/feature_matrix.py` using polars for performance. Build factors in parallel via `asyncio.gather` over a worker pool. Each factor module exposes `compute(universe, asof, history) -> pl.DataFrame[ticker, value]`. The matrix builder normalizes (z-score by sector × date), ranks (1..N), and writes to `lake.factor_matrix`. Add an `as_of` column on every row matching the build timestamp. Tests use a synthetic OHLCV fixture and assert PIT correctness (changing today's data does not retroactively change yesterday's matrix).

### Step 5.3 — Signal combination

`signal.py` reads `iic_state.macro_regime`, applies the §2.3 weights, produces a per-ticker score. Top-N longs and bottom-N shorts (default N=10 per universe) become candidate trades.

### Step 5.4 — Risk shaping

`risk.py` solves a small QP / heuristic:
- Vol-target sizing per position using 60-day realized vol.
- Apply correlation cap by rejecting correlated pairs greedily.
- Apply sector and region caps.
- Output `{ticker, weight_pct_nav, entry_band, target_band, stop_loss}` per surviving candidate.

📌 Bands: entry from 5-min ATR around current mid; target 2× ATR; stop 1.2× ATR. Override per-factor (mean-rev shorter horizon, momentum longer).

### Step 5.5 — Writer

`writer.py` composes `advice.quant.v1`:
- `direction = long | short` per signal sign.
- `confidence = sigmoid(combined_z_score)` clipped to [0.05, 0.95].
- `thesis` = Flash narration (Pro on regime change in the last 24 h).
- `evidence` = `[{kind: "data", ref: "lake.factor_matrix:asof=...,ticker=..."}, {kind: "news", ref: "..."}]`.
- `horizon_days` from factor metadata (momentum 30, mean-rev 5, PEAD 10).

🧪 **VIBE-PROMPT — `quant.writer` narrative:**
> *System:* In ≤ 60 words, narrate why this factor combo flagged this ticker. State the dominant factor by name, the secondary factor, and the regime context. End with the time horizon. No hedging language; if the model isn't sure, lower confidence rather than soften the text.

### Step 5.6 — Publish + persist

`publish.py` validates via `AdviceV1`, publishes to `advice.quant.v1`, persists via `data_lake.advice_ledger.append`.

### Step 5.7 — Walk-forward harness

A separate one-shot container runs walk-forward backtests against the last N years. Used for prompt/factor changes. Splits data 60/40 in/out-of-sample on a rolling window. Stores results to `lake.backtest_walkforward` for the dashboard.

---

## 6. HTTP API

```
POST /run/factors          → rebuild matrix on demand
POST /run/signal           → re-run signal & emit advice
POST /run/walk_forward     → kick a walk-forward (long-running)
GET  /health
GET  /factors/explain/{ticker}/{asof}  → list factor values + ranks
```

---

## 7. Vibe Prompts (paste-ready)

🧪 **Scaffold the agent:**
> Implement `apps/agent_quant/` per `12_AGENT_QUANT.md`. Math in polars + numpy + statsmodels. Universe and factor builds are PIT-correct (`assert_pit_safe` in tests). Regime weights table from §2.3 hard-coded as a Python dict; expose `signal.regime_weights(regime)` for dashboard introspection. Risk caps per §2.4. Tests: walk-forward backtest of momentum+mean-rev on synthetic data shows positive expectancy on a 60/40 in/out split (deterministic seed); risk caps reject a portfolio that violates correlation > 0.85.

🧪 **Insider feeder:**
> Build `quant/factors/insider.py`. Pull SEC Form 4 from EDGAR via the official JSON endpoint. A "cluster" is ≥ 3 distinct insiders buying within 10 trading days, net buy value > $1 M. Output `(ticker, cluster_score 0..1)`. Stale clusters (>30 d old) decay linearly to zero.

🧪 **Crypto basis:**
> Build `quant/factors/crypto_basis.py`. Pull perp funding rate + spot from Polygon (or Binance/OKX public APIs) for top 10 by volume. Basis = `(perp_mark - spot) / spot`. Z-score normalize over 30-day window. Tag direction: extreme positive basis suggests short-perp / long-spot, extreme negative the inverse.

---

## 8. Acceptance Criteria

- [ ] `pytest apps/agent_quant -q` is green; PIT test, walk-forward test, risk-cap test all pass.
- [ ] Nightly `POST /run/factors` builds the matrix in < 5 min and writes to `lake.factor_matrix`.
- [ ] `POST /run/signal` produces ≥ 5 valid `advice.quant.v1` events.
- [ ] Grafana panel "Factor freshness" shows the latest `asof` per factor within 1 hour of the schedule.
- [ ] Manually injecting a regime change (write `iic_state.macro_regime=crisis`) shifts the next signal's weights to the crisis row of §2.3 and triggers a Pro re-narration.
- [ ] Backtester reports per-factor attribution (which factor drove the win/loss).
- [ ] An attempt to query `lake.factor_matrix` without an `as_of` predicate is caught by `assert_pit_safe` in tests.

---

## 9. Risks & Gotchas

⚠️ **Lookahead bias.** The most pernicious bug. Tests must include a fixture that injects future data and asserts factor values for past `asof` are unchanged.

⚠️ **Survivorship bias.** Universe must come from `lake.universe_membership`, not today's index. Verified by `tests/test_pit_factor_build.py`.

⚠️ **Regime detector noise.** A single digest can flip `macro_regime` and re-narrate every advice. Throttle: only re-narrate if the regime has been stable for ≥ 6 hours OR the orchestrator explicitly requests it.

⚠️ **Liquidity assumption.** Don't size positions where 5-day median dollar volume < 10× the implied trade value. Liquidity filter in `risk.py`.

⚠️ **Form 4 timing.** Insider trades have 2-business-day disclosure delay. Filter at the data layer; don't accept Form 4 timestamps inside the disclosure window.

⚠️ **Crypto basis on illiquid hours.** Weekend basis is noisy. Restrict the factor to UTC business hours unless backtested against weekend specifically.

⚠️ **Walk-forward over-fit.** A walk-forward that rebalances weights per window is itself a hyperparameter. Lock the regime weights from §2.3; don't optimize them via the walk-forward (that's tuning to the future).

⚠️ **FX carry tail risk.** Carry blowups happen fast. Hard stop at 1.5× implied vol of the pair, not just 1.2× ATR.

---

## 10. Cross-References

- Regime source: `10_AGENT_INTELLIGENCE.md` §5.8 + `06_ORCHESTRATOR.md` §6.2 (orchestrator writes the KV key from the digest).
- PIT helper: `02_DATA_LAYER.md` §6.
- Walk-forward UI: `21_DASHBOARD_UI.md` §6 (Quant tab).
- Backtester per-factor attribution: `14_AGENT_BACKTEST.md` §5.

---

## Changelog

- **v1.0** — Extracted from `PLAN_v2.1` §4.3. Regime weights table promoted to GROUND TRUTH; risk caps formalized; PIT testing made non-optional.
