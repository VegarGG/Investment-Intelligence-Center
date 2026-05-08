# Investment Intelligence Center — System Plan v2.1

> Codename: **IIC** (Investment Intelligence Center)
> Replaces: Plan v2.0 (2026-05-06) — same day rev to v2.1
> Author: Ziwei + Claude
> Last revised: 2026-05-06
> Status: **Specification — ready for implementation**
> Implementation style: **Vibe-coding friendly** (sections are AI-readable; prompts and snippets are inline; file/module names are stable; "ground truth" tables are explicitly marked).

**What changed in v2.1**

1. **Host platform locked to Linux** (Ubuntu 24.04 LTS Server, native Docker — no VM tax).
2. **Hardware is a single mini PC** (no NAS at launch). All persistent state lives under `/srv/iic/<service>` so a NAS can be added later as an NFS mount with **zero changes to `docker-compose.yml`**.
3. **WeChat is the primary push channel** (WeCom group bot for outbound, WeCom self-built app for inbound chat). Server酱 is the fallback; ntfy + email are the deeper tier.
4. Data freshness, message-bus, observability, and DR all re-validated against the single-box constraint.

---

## 0. How to Read This Document (For Humans and AI Coding Agents)

This document is the single source of truth for IIC. It is intentionally written so that a future Claude / Cursor / Codex / Aider session can be pointed at this file and start scaffolding code with minimal additional context.

**Conventions**

- 📌 **GROUND TRUTH** blocks are immutable contracts (file names, schemas, env-var names). Do not rename without bumping the document version.
- 🧪 **VIBE-PROMPT** blocks are ready-made prompts you can paste into a coding agent.
- 🟢 **PHASE** tags mark when a feature is built. If your current code disagrees, the code wins (verify before asserting).
- ⚠️ **RISK** blocks call out fragile assumptions.
- 🔁 **NAS-READY** blocks call out paths and conventions that exist specifically to make adding a NAS later painless.
- All times are local (America/Los_Angeles unless stated). All prices are USD.
- `[TBD]` means "decide during implementation."

**Project root layout (📌 GROUND TRUTH)**

```
intelligence-center/
├── docker-compose.yml
├── .env.example
├── PLAN_v2.1_Investment_Intelligence_Center.md   ← this file
├── EXECUTIVE_SUMMARY_bilingual.pdf
├── EXECUTIVE_SUMMARY_bilingual.md                ← source for the PDF
├── apps/
│   ├── orchestrator/          # Top-level controller (Python, FastAPI)
│   ├── agent_intelligence/    # News + macro + sentiment (forked from WorldMonitor)
│   ├── agent_fundamental/     # Fundamental analysis
│   ├── agent_quant/           # Quant signals
│   ├── agent_persona/         # Human-trader mimics (Rogers, Buffett, Soros, …)
│   ├── agent_backtest/        # Always-on virtual portfolio + leaderboard
│   ├── agent_secretary/       # Chatbot + progress monitor (web + WeChat)
│   └── dashboard/             # Web UI (TS + Vite + React)
├── packages/
│   ├── llm-client/            # DeepSeek v4 wrapper (Pro + Flash routing)
│   ├── data-bus/              # NATS JetStream adapter
│   ├── data-lake/             # Postgres + TimescaleDB + ChromaDB clients
│   ├── prompts/               # Prompt registry, versioned
│   ├── notifier/              # WeCom bot + WeCom app + Server酱 + ntfy + SMTP adapters
│   └── schema/                # Pydantic + TS shared types (codegen)
├── infra/
│   ├── linux/                 # Ubuntu 24.04 LTS host setup, systemd units, restic
│   ├── nas/                   # Future NAS migration scripts (dry-run from day 1)
│   └── observability/         # Grafana, Loki, Prometheus dashboards
└── docs/
    ├── runbooks/
    ├── adr/                   # Architecture Decision Records
    └── prompts/               # Per-agent persona files
```

📌 **GROUND TRUTH — host filesystem layout** (defines NAS-readiness):

```
/srv/iic/                      ← single root for ALL persistent state
├── pg/                        # Postgres + TimescaleDB data dir
├── chroma/                    # Vector store
├── nats/                      # JetStream durable storage
├── minio/                     # Object store (filings, snapshots, parquet)
├── redis/                     # If used as cache; AOF on
├── grafana/, loki/, prometheus/
├── prompts_versioned/         # Append-only prompt history
├── advice_ledger/             # Hash-chained advice records (defense-in-depth)
└── backup/                    # restic repo target (mirrored offsite to B2)
```

🔁 **NAS-READY:** every container's volume mount is `/srv/iic/<service>:/var/lib/<service>`. Migrating to a NAS = (a) `rsync /srv/iic/ nas:/volume1/iic/`, (b) `umount /srv/iic && mount -t nfs nas:/volume1/iic /srv/iic`, (c) `docker compose up -d`. Compose file is **untouched**.

---

## 1. Vision and Mission

**Vision.** Build a personal, always-on, agentic investment-advisory system that mirrors a real-world investment shop: an intelligence desk, a fundamentals desk, a quant desk, a roster of style-mimicking strategists, a live performance-evaluation desk, and a chief-of-staff who explains it all to the principal (you). The system **does not place trades**. It generates concrete, actionable suggestions at the security level (ticker, price band, time horizon, max drawdown), then grades itself in real time so you know whose voice to trust.

**Mission for v2.1.**

1. **Decouple intelligence from advice.** The Intelligence Center is now one agent inside a fleet — the news/macro desk — and emits two streams: a human-readable dashboard/brief, and a machine-friendly digest for downstream agents.
2. **Many minds, one principal.** Run 4–8 advisory agents in parallel with diverse priors (fundamental, quant, persona-driven). Disagreement is a feature.
3. **Self-grading.** A backtesting agent runs continuously, paper-trading every recommendation, attributing P&L, and surfacing a leaderboard.
4. **API-first, hardware-light.** Replace the original local-LLM-first plan with **DeepSeek v4 (Pro + Flash)** API calls. The home machine is now an orchestration host, not a GPU farm.
5. **Single-box at home, NAS-ready.** Run the entire stack on one Linux mini PC; design storage so a NAS is a drop-in upgrade.
6. **WeChat-native delivery.** Briefs, alerts, and conversational Q&A flow through WeChat. The dashboard is for deep dives.

**Non-goals (v2.1).**

- ❌ Auto-trading / broker integration (suggestion only).
- ❌ Tax optimization, options Greeks engine (stretch goals, post-v2).
- ❌ Multi-user / SaaS productization (single-tenant, family use only).
- ❌ Local LLM hosting (out-of-scope until DeepSeek-V4-distill ships open weights, then re-evaluate).

---

## 2. System Overview

```
                ┌───────────────────────────────────────────────────────┐
                │                  SECRETARY AGENT                      │
                │  (web chat · WeChat conversation · explain mode)      │
                └───────────────▲────────────────────────▲──────────────┘
                                │                        │
                  questions, updates              chat, briefs (WeChat)
                                │                        │
┌───────────────────────────────┴────────────────────────┴──────────────┐
│                        ORCHESTRATOR (DeepSeek v4 Pro)                 │
│   plans · routes · merges · enforces SLAs · holds shared context      │
└──┬─────────┬───────────┬───────────┬───────────────┬─────────┬────────┘
   │         │           │           │               │         │
   ▼         ▼           ▼           ▼               ▼         ▼
 ┌────┐   ┌────┐     ┌────────┐   ┌──────┐      ┌─────────┐  ┌──────┐
 │INT │   │FUN │     │QUANT   │   │PERSO │      │BACKTEST │  │OBSERV│
 │EL  │   │DA  │     │TRADER  │   │NA #1 │ … #N │ENGINE   │  │ABILITY│
 └─┬──┘   └─┬──┘     └───┬────┘   └──┬───┘      └────┬────┘  └──────┘
   │        │            │           │                │
   ▼        ▼            ▼           ▼                ▼
   ───────  Data Bus (NATS JetStream on the same host)   ───────
            │
            ▼
   Data Lake (all on local NVMe, mounted from /srv/iic):
   Postgres+TimescaleDB · ChromaDB · MinIO · Redis cache
            │
            ▼
   Backups: restic → /srv/iic/backup → Backblaze B2 nightly
```

**Key flows.**

- **Morning brief flow (06:30 local):** Intelligence agent runs an overnight sweep → publishes `intel.digest.v1` event → Fundamental, Quant, Persona agents subscribe → each emits `advice.v1` events → Backtest agent paper-opens positions → Secretary composes the morning brief and pushes it to your **WeChat**.
- **Hourly heartbeat:** Intelligence Flash-summarizes new events. Persona agents only re-run when an event scores ≥ 0.7 on the "regime-change likelihood" detector.
- **Continuous backtest:** Every open virtual position is marked-to-market every minute (during market hours) or every 15 min (off hours). Stop-outs and target hits trigger feedback events; key fills are pushed to your WeChat.

---

## 3. Agent Fleet — Roles, Inputs, Outputs

The fleet has six **canonical roles**. Some roles can have multiple instances (especially Persona).

| # | Agent | Role | LLM Tier | Trigger | Output topic |
|---|-------|------|----------|---------|--------------|
| 1 | **Intelligence**       | News, macro, sentiment, filings ingest & synthesis | Flash for ingest, Pro for synthesis | Cron + event-driven | `intel.digest.v1`, `intel.dashboard.v1`, `intel.brief.v1` |
| 2 | **Fundamental**        | Bottoms-up valuation, DCF, comps, filings reading | Pro                                  | On `intel.digest.v1` + earnings cal. | `advice.fundamental.v1` |
| 3 | **Quant**              | Factor / momentum / mean-reversion / vol signals  | Flash for compute, Pro for narrative | 5-min bars (intraday), daily close   | `advice.quant.v1` |
| 4 | **Persona** (multiple) | Style-mimic strategists: Rogers, Buffett, Soros, Druckenmiller, Wood, Dalio, Burry, retail-degen | Pro | On `intel.digest.v1` and on weekly scheduler | `advice.persona.{name}.v1` |
| 5 | **Backtest**           | Paper-portfolio per agent, attribution, leaderboard | Flash for narration, none for math | Continuous | `backtest.fill.v1`, `backtest.daily.v1`, `backtest.leaderboard.v1` |
| 6 | **Secretary**          | Chatbot, system narrator, "explain like I'm five" | Flash (default), Pro (deep questions) | User chat / scheduler | UI + WeChat push |

📌 **GROUND TRUTH — `advice.v1` schema (shared across agents 2/3/4):**

```jsonc
{
  "schema": "advice.v1",
  "id": "ulid",
  "agent": "fundamental | quant | persona.rogers | …",
  "issued_at": "2026-05-06T13:30:00-07:00",
  "asset": {
    "kind": "equity | etf | future | option | fx | crypto | bond",
    "ticker": "INTC",
    "venue": "NASDAQ",
    "name": "Intel Corp"
  },
  "thesis": "≤500 words, plain English",
  "direction": "long | short | flat",
  "confidence": 0.62,           // 0–1
  "entry_band": [89.0, 91.5],   // USD
  "target_band": [95.0, 100.0],
  "stop_loss": 85.0,
  "horizon_days": 7,
  "max_drawdown_pct": 6.0,
  "sizing_hint_pct_nav": 2.5,   // % of NAV
  "expires_at": "2026-05-13T13:30:00-07:00",
  "evidence": [
    {"kind":"news","ref":"intel.digest.v1#evt-7"},
    {"kind":"filing","url":"sec.gov/…"}
  ]
}
```

This contract is the heart of the system. Every advisory agent emits it; the backtester consumes it; the secretary explains it; the dashboard renders it. Treat it like an API.

---

## 4. Detailed Agent Specifications

### 4.1 Intelligence Agent (formerly the Intelligence Center, now one node)

**Mandate.** Be the "global desk." Pull, dedupe, translate, summarize, and tag the world's relevant signals. Emit two human deliverables (dashboard, WeChat brief) and one agent-friendly digest.

**Sub-agents (internal fleet of 5):**

- `intel.crawler` — RSS, Atom, Telegram (read-only), X/Twitter, Reddit, Truth Social, Weibo, Xiaohongshu (heavy throttling), state-broadcaster scrapers. Reuse 90 verified Wave-1 feeds from v1.1.
- `intel.translator` — Languages → English. DeepSeek Flash is fluent in EN, ZH, JP, KR, FR, DE, RU, AR.
- `intel.macro` — Pulls macro releases (BLS, BEA, ECB, PBoC, Eurostat, IMF, World Bank), calendars, commodity dashboards (oil, copper, gold, freight rates BDI), credit spreads.
- `intel.sentiment` — VADER + DeepSeek Flash classifier. Outputs valence per-event and per-asset.
- `intel.synth` — Pro-tier synthesizer. Produces the *digest*: the 30 events that matter, ranked, with a regime-change score.

**Data sources (📌 GROUND TRUTH — env keys):**

| Source | Env key | Plan needed | Notes |
|--------|---------|-------------|-------|
| Polygon.io | `POLYGON_API_KEY` | Stocks Starter ($29/mo) | EOD + intraday US equities, news |
| Alpha Vantage | `ALPHAV_API_KEY` | Free 25 req/day or $50/mo | Macro fallback |
| Tiingo | `TIINGO_API_KEY` | Power $30/mo | Fundamentals + news |
| FRED | `FRED_API_KEY` | Free | US macro |
| Tushare Pro | `TUSHARE_TOKEN` | ¥200/yr | A-shares, HK, futures |
| EDGAR | (no key) | Free | SEC filings |
| HKEXnews | (no key) | Free | HKEX filings |
| OpenBB | `OPENBB_PAT` | Free w/ account | Aggregator |
| Telegram MTProto | `TG_API_ID`, `TG_API_HASH` | Free | Channels (read-only) |
| X/Twitter | `X_BEARER` | Basic $100/mo or scrape | Optional |
| RSS bundle | (none) | Free | 90 Wave-1 feeds |
| Reddit | `REDDIT_CLIENT_ID/SECRET` | Free | r/wallstreetbets, r/stocks, r/options |
| Weibo / Xiaohongshu | `[TBD]` | Scraped | Throttled, treat as low-priority |

**Outputs.**

- `intel.dashboard.v1` — JSON for the web UI (heatmap, headline ticker, country-risk dial, BDI/oil/VIX gauges).
- `intel.brief.v1` — 200–400 word morning brief; rendered in **WeCom markdown** for WeChat push.
- `intel.digest.v1` — agent-friendly: ranked event list, each with `{id, headline, asset_links[], regime_change_score, sentiment, novelty, recency, sources[]}`.

**LLM allocation.**

- **Flash** for ~20k events/day of ingest, dedupe-by-embedding, cheap classification.
- **Pro** for the 1 synthesis call producing the digest (≈ 12k tokens out, 4–6 calls/day).

🧪 **VIBE-PROMPT — `intel.synth`:**
> *System:* You are the chief intelligence officer for a personal investment desk. From the candidate event list (provided as JSON), select the 25–35 events that most plausibly affect liquid markets in the next 30 days. For each, emit `{rank, headline, why_it_matters_2_sentences, primary_asset_links, regime_change_score 0-1, novelty 0-1}`. Penalize duplicates. Reward cross-source confirmation. End with one paragraph titled "Today's macro thesis."

⚠️ **RISK:** Source bias. Maintain a manifest with `region_weight` and `lean` per source; the digest must include `bias_balance` metrics.

---

### 4.2 Fundamental Analysis Agent

**Mandate.** Bottoms-up: read filings, build a quick valuation, compare with peers, output stock-level recommendations.

**Sub-agents:**

- `fund.filings` — fetch + chunk + vectorize 10-K, 10-Q, 8-K, 20-F, A-share annuals, HK annuals.
- `fund.valuation` — runs lightweight DCF, P/E vs sector, EV/EBITDA, FCF yield. Pulls peer data from Tiingo.
- `fund.linker` — links macro events from `intel.digest.v1` to specific tickers.
- `fund.writer` — composes the `advice.fundamental.v1` payload.

**Inputs.** `intel.digest.v1`, EDGAR/HKEX, Tiingo fundamentals, FRED macro.
**Trigger.** On every digest (≥ 4×/day), plus on each new filing in the watchlist.
**Coverage policy.** Watchlist of 50 names (you-curated) + an opportunistic "long tail" pass weekly.
**LLM allocation.** Pro for DCF reasoning + thesis; Flash for filing-chunk extraction.

🧪 **VIBE-PROMPT — `fund.valuation`:**
> *System:* You are a sell-side analyst with a value bias but pragmatic about cyclicals. Given fundamentals JSON for {ticker} and 5 peer tickers, propose a fair-value range and 12-month target. Output `{base, bull, bear}` cases with explicit assumptions and a one-line catalyst list. Refuse if data is missing > 30%.

⚠️ **RISK:** Hallucinated multiples. The agent must cite a `data_source_id` for each numeric claim. Backtester rejects advice missing citations.

---

### 4.3 Quant Trading Agent

**Mandate.** Statistical signals. Not a black box: every signal has a one-sentence explanation suitable for the brief.

**Factor library (initial v2.1 set):**

1. 12-1 cross-sectional momentum (US large-cap, A50, HSI50)
2. 5-day mean-reversion residual (post-news)
3. Volatility risk premium (front-month IV − 20-day RV)
4. Earnings drift (PEAD)
5. Insider buying clusters (Form 4)
6. Sector relative strength (RRG)
7. Crypto basis (perp − spot, top 10)
8. FX carry, top 6 G10 pairs

**Sub-agents:**

- `quant.feature` — builds factor matrix nightly + every 15 min for intraday subset.
- `quant.signal` — combines factors per regime (regime detected from `intel.digest.v1`'s `macro_regime` field).
- `quant.risk` — vol targeting, position sizing, correlation cap.
- `quant.writer` — composes `advice.quant.v1`.

**LLM allocation.** Math is Python (pandas, polars, numpy, statsmodels, vectorbt, scikit-learn). LLM is only for the *narrative* of the trade. Use Flash for narrative; Pro is overkill here.

⚠️ **RISK:** Lookahead bias. Factor builds must use `as_of < now` strictly; the backtester enforces this and quarantines offending advice.

📐 **Single-box capacity check.** On a Beelink SER8 (8C/16T Ryzen 7 8845HS, 32 GB RAM), the full factor matrix for SPX 500 + HSI 50 + A50 builds in ≈ 90 s nightly using polars. The 15-min intraday delta is ≈ 6 s. Comfortable headroom.

---

### 4.4 Persona Agents — "Trader Ghosts"

**Mandate.** Bring the *style* and *psychology* of named investors. Not their actual portfolios; their **thinking pattern** as evidenced by their public writing/interviews.

**Initial roster (v2.1):**

| Slug | Persona | Style essence | Time horizon | Universe |
|------|---------|---------------|--------------|----------|
| `rogers` | Jim Rogers | Contrarian commodity macro; ride megatrends | 1–10 yr | Commodities, EM equities, FX |
| `buffett` | Warren Buffett | Quality + moat + low turnover | 5–20 yr | US large-cap, BRK style |
| `soros` | George Soros | Reflexivity, regime-change bets | weeks–months | Macro, FX, indices |
| `druckenmiller` | Stanley Druckenmiller | Top-down macro, concentrated | months | Liquid macro |
| `wood` | Cathie Wood | Disruptive innovation, high beta | 5+ yr | Growth tech, biotech |
| `dalio` | Ray Dalio | All-weather, debt cycles | years | Diversified macro |
| `burry` | Michael Burry | Deep-value contrarian, bubble shorting | 1–5 yr | Special situations |
| `degen` | Anonymous retail | Momentum-chasing, social-driven | days | Meme stocks, crypto |

Each persona is a **prompt + memory + bias-vector**. The prompt includes the principle list and a few canonical past trades. The memory is a vector store (ChromaDB collection `persona_memory_{slug}`) of that persona's decisions over the project's life. The bias-vector tilts allocation defaults.

📌 **GROUND TRUTH — persona file format** (`docs/prompts/persona/{slug}.yaml`):

```yaml
slug: rogers
display_name: Jim Rogers
priors:
  - "Buy what's hated; sell what's loved."
  - "Commodities lead inflation."
canonical_trades:
  - { era: 1980s, asset: gold, action: long, lesson: "Patience pays" }
universe_weights:
  commodities: 0.50
  em_equities: 0.25
  fx: 0.15
  us_largecap: 0.05
  bonds: 0.05
prompt_template: |
  You are reasoning AS JIM ROGERS would. Think in megatrends and contrarian
  positioning. Avoid US-mega-cap unless extreme value. …
guardrails:
  - "Never claim to be the real Jim Rogers."
  - "Disclaimer required on every output."
```

⚠️ **RISK & ETHICS:** Personas are *style mimicry*, not impersonation. Each `advice.persona.*.v1` must carry `disclaimer: "Stylized agent inspired by public writings; not Mr. {name}."` Enforced in `agent_persona/output_validator.py`.

---

### 4.5 Backtesting Agent — The "Live Judge"

**Mandate.** Continuously evaluate every advisory agent and rank them. Loop the verdict back to the source agent for self-improvement.

**Capabilities.**

1. **Forward paper trading** — Every `advice.v1` opens a virtual position the moment it is published. Fills assumed at midpoint of `entry_band` with slippage model. Stops/targets monitored intraday.
2. **Historical backtesting** — On agent prompt or strategy change, replay against the last N years on liquid symbols.
3. **Live benchmark** — Equal-weight SPY+ACWI+GLD+IEF as the passive benchmark; risk-parity as the smart-passive benchmark.
4. **Attribution** — Per-agent: hit rate, avg R-multiple, Sharpe, Sortino, Calmar, max DD, time-in-market, hold time, turnover.
5. **Feedback loop** — Each closed trade publishes `backtest.fill.v1` *back to the originating agent*, plus a per-week digest the agent uses as memory in subsequent calls.
6. **Leaderboard** — Public-to-you ranking, with stat-sig flags.

**Architecture.** Pure Python service. No LLM in the math path. LLM (Flash) is used only to generate the human-readable post-trade narrative.

**Storage.** TimescaleDB hypertable `lake.timeseries` (`/srv/iic/pg/`); Postgres tables `lake.backtest.*` for fills, positions, attribution.

📐 **Single-box capacity check.** Mark-to-market 200 open virtual positions every 60 s on local Postgres: ~80 ms per cycle. CPU is rarely above 5%. Long historical replay (10 yr × 500 names) runs in a separate one-shot container so it doesn't compete with live services.

📌 **GROUND TRUTH — `backtest.fill.v1`:**
```jsonc
{
  "schema": "backtest.fill.v1",
  "advice_id": "ulid-of-source",
  "agent": "persona.rogers",
  "opened_at": "2026-05-06T20:30:00Z",
  "closed_at": "2026-05-13T17:55:00Z",
  "entry_px": 90.25,
  "exit_px": 96.10,
  "exit_reason": "target | stop | expiry | early_close",
  "pnl_usd": 5850,
  "pnl_r": 1.4,
  "max_dd_during_trade_pct": 3.1,
  "narrative": "Filled mid-band; news-driven gap on day 3 …"
}
```

⚠️ **RISK:** Survivorship bias in historical mode. The dataset must be PIT (point-in-time) for delisted names — Tiingo + Polygon delisted feed, validated in tests.

---

### 4.6 Secretary Agent

**Mandate.** Be the chief-of-staff. Two faces:

1. **Outbound:** at scheduled times, produces the morning brief, mid-day check, and evening recap. Push channels:
   - **WeCom group bot webhook (primary).** Free, markdown-friendly. Endpoint: `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=…`. One bot per channel (briefs, alerts, fills). Env: `WECOM_BOT_BRIEFS_KEY`, `WECOM_BOT_ALERTS_KEY`, `WECOM_BOT_FILLS_KEY`.
   - **Server酱 Turbo (fallback).** Pushes to your personal WeChat through 服务号. Env: `SERVERCHAN_SENDKEY`. Cost ¥18/yr.
   - **ntfy + SMTP (deeper backups).** Used when WeChat is unreachable.
2. **Inbound (chatbot):** users ask "What is `persona.rogers` saying about copper?" or "Why did the quant agent flat NVDA today?"
   - **WeCom self-built app (primary).** OAuth callback from 企业微信 to `/notifier/wecom/callback`. Two-way chat lives in the WeChat-family ecosystem.
   - **Web UI (secondary).** Same `/chat` SSE endpoint, used for deep dives at the laptop.

**LLM allocation.** Flash by default (chat is high-volume). Pro for the morning brief and for "deep explain" mode.

**Personality knob.** `tone: terse | conversational | educational`. Default `conversational`. `educational` triggers more analogies for non-technical family use. Language: zh / en auto-detected from user input.

🧪 **VIBE-PROMPT — Secretary deep explain:**
> *System:* Translate the user question into an internal plan: which agent or which data table answers it? Produce a step-by-step trace `→ retrieve → reason → answer` with citations. If multiple agents disagree, present the disagreement as a table, not a single answer.

📌 **GROUND TRUTH — WeCom bot payload (markdown):**
```json
{
  "msgtype": "markdown",
  "markdown": {
    "content": "## Morning Brief — 2026-05-06\n> 3 high-conviction moves, 1 macro alert\n\n**1. INTC long $89–91.5 → $95–100, 7d** _(persona.rogers, conf 0.62)_\n…"
  }
}
```

---

## 5. LLM Strategy — DeepSeek v4 Pro and Flash Allocation

DeepSeek v4 ships two production tiers in 2026:

- **DeepSeek-V4-Pro** — flagship reasoning model. Higher cost per token, deeper synthesis, tool-use reliable. Use for: orchestration plan, persona reasoning, fundamental valuation, intel synthesis, deep secretary answers.
- **DeepSeek-V4-Flash** — fast, cheap, strong-enough. Use for: bulk ingest classification, translation, embeddings narration, factor narrative, secretary chat default, dedupe/sentiment.

📌 **GROUND TRUTH — routing matrix** (`packages/llm-client/router.py`):

| Caller | Default | Escalate-to-Pro when |
|--------|---------|----------------------|
| `intel.crawler/translator/sentiment` | Flash | Never |
| `intel.synth` | Pro | Always |
| `fund.filings` chunk-extract | Flash | Filing > 200 pages |
| `fund.valuation/writer` | Pro | Always |
| `quant.signal/writer` | Flash | Regime change detected (Pro re-narrate) |
| `persona.*` daily | Flash | Weekly deep-dive (Pro) |
| `backtest.narrate` | Flash | Never |
| `secretary.chat` | Flash | User says "explain deeply" or asks multi-step Q |
| `orchestrator.plan` | Pro | Always |

**Cost envelope (target).** ≤ $90/month at sustained load (≈ 3M Flash tokens/day + 200k Pro tokens/day). Hard cap enforced in `llm-client` with circuit breaker.

**Prompt management.** All prompts live in `packages/prompts/registry/` with semantic versioning, mirrored to `/srv/iic/prompts_versioned/`. CI verifies that any prompt change bumps the version.

**Fallback.** If DeepSeek API is down, route Pro → Anthropic Claude Sonnet 4.6, Flash → Groq Llama-3.3-70B. Both adapters live in `llm-client/adapters/`.

⚠️ **RISK:** Model drift between Pro and Flash. The eval harness (Phase 8) runs a frozen 60-prompt golden set weekly and alerts on > 10% regression on any caller.

---

## 6. Data Layer

**Stores (all on local NVMe, mounted from `/srv/iic`).**

| Store | Purpose | Tech | Retention | Volume |
|-------|---------|------|-----------|--------|
| `lake.events` | Raw ingest from sources | Postgres (JSONB) | 365 d | `/srv/iic/pg` |
| `lake.timeseries` | OHLCV, factors, macro | TimescaleDB hypertable | 10 yr | `/srv/iic/pg` |
| `lake.docs` | Chunked filings, articles | Postgres + ChromaDB embeddings | 5 yr | `/srv/iic/pg` + `/srv/iic/chroma` |
| `lake.advice` | All `advice.v1` ever | Postgres, append-only | forever | `/srv/iic/pg` |
| `lake.backtest` | Fills, P&L, attribution | Postgres | forever | `/srv/iic/pg` |
| `cache` | Hot queries, dedupe | Redis (AOF on) | 24 h | `/srv/iic/redis` |
| `objects` | PDFs, raw HTML, Parquet snapshots | MinIO (S3-compatible) | 5 yr | `/srv/iic/minio` |

**Schema highlights.**

- `lake.advice` is the *immutable ledger*. Append-only, hash-chained per agent. The leaderboard cannot be retroactively edited.
- `lake.events` carries `source_id`, `region`, `lean` to compute bias balance.
- `lake.timeseries` Timescale hypertables partitioned by `(symbol, ts)`.
- ChromaDB collections: `news`, `filings`, `persona_memory_{slug}`. Embedding model: `bge-m3` via DeepSeek's embedding endpoint.

**Disk budget on the mini PC (1 TB NVMe):**

| Store | Year-1 size | Year-3 projection |
|-------|-------------|-------------------|
| `pg` (Postgres + Timescale) | 60 GB | 220 GB |
| `chroma` | 20 GB | 70 GB |
| `minio` (objects) | 80 GB | 300 GB |
| `nats` JetStream | 5 GB | 15 GB |
| `backup` (local restic) | 30 GB | 80 GB |
| Logs (loki) | 15 GB | 40 GB |
| **Total** | **~210 GB** | **~725 GB** |

Year-3 is the trigger to either (a) move `minio` to a NAS, or (b) prune object lifecycle to 3 yr.

**Backups (📌 GROUND TRUTH — restic plan):**

- `restic` runs daily at 03:00 local on `/srv/iic` (excluding `pg/wal` because Postgres has its own WAL archive).
- Local repo at `/srv/iic/backup`.
- Offsite to **Backblaze B2** (`B2_ACCOUNT_ID`, `B2_ACCOUNT_KEY`), encrypted by restic. Cost ~$6/TB/mo.
- Postgres uses logical `pg_dump` weekly + WAL archiving daily.
- ChromaDB snapshots weekly to `/srv/iic/backup/chroma-snapshots/`.
- Retention: 7 daily, 4 weekly, 12 monthly, 3 yearly.

🔁 **NAS-READY:** when a NAS arrives, point restic at the NAS instead of `/srv/iic/backup` (`RESTIC_REPOSITORY=/mnt/nas/iic-restic`). All other settings unchanged.

---

## 7. Orchestration and Communication

**Bus.** **NATS JetStream**, single-node, on-host. (We previously considered Redis Streams as the lighter option; on a 32 GB mini PC NATS JetStream is comfortable and gives durable streams + KV store + clean fan-out semantics.)

**Topics (📌 GROUND TRUTH — names are stable):**

```
intel.digest.v1
intel.dashboard.v1
intel.brief.v1
advice.fundamental.v1
advice.quant.v1
advice.persona.{slug}.v1
backtest.fill.v1
backtest.daily.v1
backtest.leaderboard.v1
secretary.notify.v1
ops.heartbeat.v1
ops.alert.v1
```

**Orchestrator.** Python service running LangGraph (or a custom asyncio state machine). Responsibilities:

1. **Plan** — Given an event, build the DAG of agent calls.
2. **Route** — Send work via NATS subjects.
3. **Merge** — Collect agent outputs, deduplicate, normalize, persist to `lake.advice`.
4. **SLAs** — Each agent has a soft + hard timeout. Hard timeout cancels and emits `ops.alert.v1` (which the WeCom alerts bot picks up).
5. **Concurrency** — Max 4 Pro calls concurrent (cost), unlimited Flash (within rate limit).
6. **Idempotency** — Every event carries an idempotency key.

📐 **Single-box capacity.** With 6 agents + orchestrator + dashboard + DBs, expect ~3–5 GB RAM resident, peaking to ~10 GB during persona Pro fan-out. Beelink SER8 with 32 GB DDR5 leaves headroom for 2× growth.

---

## 8. Hardware Plan — Single Linux Mini PC, NAS-Ready

The home box is an orchestration host, not a model host. CPU, RAM, NVMe, and 24×7 reliability matter; a GPU does not.

📌 **Minimum spec to run everything:** 4-core modern CPU, 16 GB RAM (24 GB comfortable, 32 GB recommended), 1 TB NVMe + 4 TB external HDD, 1 Gb (preferably 2.5 Gb) Ethernet, < 30 W idle, UPS.

### 8.1 Hardware Tiers

| Tier | What | Indicative price | Pros | Cons |
|------|------|------------------|------|------|
| **Tier 0** | Repurpose existing PC ≥ 16 GB RAM | $0–$200 | Cheapest start | Not 24×7-rated; for Phase 0–1 only |
| **Tier 1 ⭐ value** | Used HP EliteDesk 800 Mini / Dell OptiPlex Micro / Lenovo ThinkCentre Tiny — i5/i7 Gen 9-12, 32 GB DDR4, 1 TB NVMe, vPro | $200–$450 | Built for fleet 24×7; vPro remote mgmt; <10 W idle | Older platforms; DDR4; consumer-grade SSDs need replacing |
| **Tier 2 ⭐ recommended** | **Beelink SER8** (Ryzen 7 8845HS, 32 GB DDR5, 1 TB NVMe, dual M.2, dual 2.5 GbE) — or Minisforum UM870 | $650–$900 | Modern Zen 4; quiet; ~10 W idle; 96 GB RAM ceiling; room for local model later | Consumer warranty; non-ECC RAM |
| **Tier 3** | Intel NUC 13/14 Pro, ASUS NUC 14 Pro, Framework Desktop | $900–$1,400 | Polished firmware; better warranty | Pricier per spec |
| **Tier 4** | DIY mini-ITX (Ryzen 7 8700G, 32 GB ECC, 2 TB NVMe + 4 TB HDD) | $900–$1,500 | Upgradeable; ECC option; can add single-slot GPU | Build time |
| **Tier 5** | Workstation hybrid (Ryzen 9 9950X, 96 GB ECC, RTX 5090) | $2,500+ | Local model hosting | Power, noise; only if leaving API-first |

### 8.2 Recommended Build for v2.1 Launch

**Beelink SER8 (Ryzen 7 8845HS, 32 GB DDR5, 1 TB NVMe), $700**

- CPU: AMD Ryzen 7 8845HS (8C/16T, Zen 4, 5.1 GHz boost)
- RAM: 32 GB DDR5-5600 (upgradeable to 96 GB)
- Storage: 1 TB NVMe M.2 (slot 1) + empty NVMe slot 2 (free upgrade later)
- Network: 2 × 2.5 GbE + Wi-Fi 6E + BT 5.3
- I/O: USB4, 2× HDMI 2.1, 1× DP1.4
- Idle power: ~10 W; load: ~35 W
- Dimensions: 136 × 135 × 39 mm — fits in a drawer

**Accessories**

- 4 TB external USB-C HDD (Seagate Backup Plus or WD Elements) — $110. Mounted at `/srv/iic/backup-hdd` for restic local repo.
- UPS: CyberPower CP1500PFCLCD (1000 W, AVR, USB to host) — $180. Ride out 5–10 min outages cleanly.
- Cat 6 short patch cables, Wi-Fi 6 router slot.

**Total: ~$990 for hardware. Subtract $180 if you already own a UPS.**

### 8.3 Operating System & Host Setup

📌 **GROUND TRUTH — host setup script:** `infra/linux/bootstrap.sh`

- **OS:** Ubuntu 24.04 LTS Server (or Debian 12). Headless install, OpenSSH only.
- **User:** `iic` with `sudo` (no password sudo for `docker compose`); root login disabled.
- **Hardening:** `ufw allow 22, 80, 443 from 192.168.0.0/16`, `fail2ban`, automatic security updates via `unattended-upgrades`.
- **Time:** `chrony` synced to local-region NTP pool.
- **Docker:** Engine + Compose v2 from official Docker apt repo, not the distro package.
- **Filesystem:** Single ext4 partition on NVMe; `/srv/iic` is a directory (not its own partition for v2.1 — easier resize).
- **Swap:** 8 GB zram-swap (kernel-managed compressed RAM swap; saves NVMe writes).
- **Auto-boot services:** `systemd` unit `iic.service` runs `docker compose -f /opt/iic/docker-compose.yml up -d`; `Restart=always`.
- **Remote access:** Tailscale (preferred) or WireGuard, hard-coded device key, MagicDNS.
- **Power resilience:** UPS daemon (`apcupsd` or `nut`) signals shutdown at 20% battery.
- **Logging:** `journald` to disk + Loki container for app logs.
- **Hardware sensors:** `node_exporter` exposes CPU temp, NVMe SMART, fan RPM to Prometheus; alert rule fires if NVMe wear > 80% or CPU sustained > 90 °C.

🧪 **VIBE-PROMPT — host bootstrap:**
> Generate `infra/linux/bootstrap.sh` for Ubuntu 24.04 LTS Server. Steps in order: apt update, install docker-ce + compose-plugin from official repo, create user `iic` with docker group membership, install tailscale, install restic, install ufw + fail2ban, install chrony + apcupsd, install node_exporter, configure unattended-upgrades, create `/srv/iic/{pg,chroma,nats,minio,redis,grafana,loki,prometheus,prompts_versioned,advice_ledger,backup}` with `chown iic:iic`, write `/etc/systemd/system/iic.service` to start docker compose at boot. The script must be idempotent (re-runnable).

### 8.4 Future NAS Upgrade Path

🔁 **NAS-READY playbook** (`infra/nas/migrate.sh` — built and dry-run-tested in Phase 8):

1. Provision NAS (Synology DS923+ ≈ $600 diskless or QNAP TS-464 ≈ $650). Populate with 2 × 8 TB IronWolf ($170 each) in SHR-1 / RAID-1.
2. On NAS: enable NFS, create shared folder `iic` at `/volume1/iic`, allow squash to `iic` UID/GID, no_root_squash for migration window only.
3. On mini PC: `docker compose down` → `rsync -aHAX --info=progress2 /srv/iic/ nas:/volume1/iic/` (~30 GB over 2.5 GbE ≈ 3–4 min).
4. Edit `/etc/fstab`: `nas:/volume1/iic /srv/iic nfs vers=4.1,_netdev,hard,timeo=600,retrans=2 0 0`.
5. `mount -a` — `/srv/iic` is now NAS-backed.
6. `docker compose up -d` — every container picks up its volumes from the same paths. Compose file unchanged.
7. Update `RESTIC_REPOSITORY` to `/srv/iic/backup` (now NAS) and re-init B2 offsite.

The compose file's `volumes` section uses *bind mounts*, not Docker named volumes — this is the key NAS-ready decision.

⚠️ **RISK on NFS:** Postgres on NFS is fine on NFSv4.1+ with `hard,nolock` semantics, but only if the NAS storage layer is reliable. If unsure, keep Postgres on local NVMe (a hybrid config: Postgres data dir stays at `/srv/iic-local/pg`, everything else moves to `/srv/iic` on NAS). The migrate script supports both modes.

### 8.5 Network and Security

- Static internal IP for the mini PC (e.g., 192.168.1.50) reserved on router DHCP.
- No port-forwarding to the internet. Remote access exclusively via Tailscale or WireGuard.
- Optional Cloudflare Tunnel for the dashboard (TLS-terminated at Cloudflare, no inbound holes).
- Secrets via `sops` + age, `.env` decrypted at boot by `iic.service` ExecStartPre.
- 1Password / Bitwarden master password rotated quarterly.
- WeCom credentials (corp_id, app secrets, bot keys) live in `.env`, encrypted at rest.

---

## 9. Implementation Phases (8 phases, ~16 weeks elapsed at part-time pace)

Each phase has: scope, exit criteria, ground-truth deliverables. **Do not skip exit criteria.**

### Phase 0 — Foundations (1 week)

**Scope.** Mini PC online; Ubuntu 24.04 LTS Server installed and hardened; `infra/linux/bootstrap.sh` idempotent; Docker Compose stack baseline (NATS JetStream, Postgres+TimescaleDB, ChromaDB, MinIO, Redis, Grafana, Loki, Prometheus, node_exporter, cadvisor); CI on GitHub Actions; restic backups nightly to local + B2; Tailscale; UPS shutdown tested.

**Exit.** `docker compose up` brings everything green; the orchestrator can publish/consume an `ops.heartbeat.v1` round-trip; restic restore drill from B2 < 30 min on a scratch directory; SMART monitoring alerts wired.

🟢 **PHASE 0 deliverables:** repo skeleton, ADR-0001 (DeepSeek v4 routing), ADR-0002 (NATS JetStream), ADR-0003 (mini-PC Linux + NAS-ready filesystem), `.env.example`, `infra/linux/bootstrap.sh`, `infra/nas/migrate.sh` (dry-run only).

### Phase 1 — Intelligence Agent MVP (2 weeks)

**Scope.** Fork WorldMonitor; strip non-essential UI; rewire feeds; emit `intel.digest.v1`; **WeCom group bot pushes `intel.brief.v1`** morning + evening.

**Exit.** Two weeks of digests stored; brief arrives on WeChat reliably; ≥ 90 Wave-1 feeds active; bias-balance metric computed; Server酱 fallback verified.

⚠️ Bias check from v1.1 carries forward.

### Phase 2 — Data Lake & Market Pipeline (1 week)

**Scope.** OHLCV ingest, fundamentals snapshot, factor computation, PIT-correctness tests. Polygon + Tiingo + Tushare + FRED.

**Exit.** Factor matrix for SPX 500 + HSI 50 + A50 builds nightly in < 5 min; tests prove no lookahead; Grafana panel shows freshness lag.

### Phase 3 — Fundamental Agent (2 weeks)

**Scope.** Filings ingest + chunking, valuation engine, `advice.fundamental.v1` emission. Watchlist of 50 names.

**Exit.** Daily run produces ≥ 5 advices; backtester (running in shadow) shows valid `advice.v1` schema 100%; citations present 100%.

### Phase 4 — Quant Agent (2 weeks)

**Scope.** 8 factors live, regime detector hooked to `intel.digest.v1.macro_regime`, `advice.quant.v1` emission, position sizing & risk caps.

**Exit.** Walk-forward backtest of last 3 years shows positive expectancy on a 60/40 in-sample/out-sample split; live shadow trading for 5 sessions consistent with backtest.

### Phase 5 — Persona Fleet (2 weeks)

**Scope.** 4 personas live (Rogers, Buffett, Soros, Druckenmiller). Persona memory + bias vectors. Disclaimer-validator gate.

**Exit.** Each persona produces ≥ 2 advices/week; outputs pass linguistic-style classifier (Pro grades a sample of 20 outputs as ≥ 80% on-style); disclaimer present 100%.

### Phase 6 — Backtesting Engine (2 weeks)

**Scope.** Forward paper trading from t=0 (already running in shadow since Phase 3). Historical replay, attribution, leaderboard, feedback events. Significant fills push to **WeCom alerts bot**.

**Exit.** Leaderboard renders in dashboard and is queryable via WeChat (`/leaderboard` command); per-agent attribution columns reconcile to ledger ($ exact); feedback events show up in agent prompts.

### Phase 7 — Secretary + Chatbot UI (2 weeks)

**Scope.** Web chatbot, **WeCom self-built app inbound chat**, push channels (WeCom bots + Server酱 fallback + ntfy + email), "explain mode," scheduled briefs, family-friendly tone with zh/en auto-detect.

**Exit.** Non-technical user (e.g., a parent) can ask in WeChat "今天系统有什么建议？" and get a sensible answer in Chinese. Tone slider works. WeCom OAuth round-trip works on cellular and Wi-Fi.

### Phase 8 — Production Hardening (2 weeks)

**Scope.** Eval harness (frozen 60-prompt golden set), Grafana dashboards, Loki logs, alert rules (CPU, NVMe wear, NVMe temp, disk free, container restart count, NAT health), runbooks, **DR drill: restore from B2 onto a scratch USB SSD**, security review, **`infra/nas/migrate.sh` dry-run on a virtual NAS (Synology VirtualDSM in a VM)**.

**Exit.** DR drill: kill `/srv/iic/pg`, restore from restic, all agents resume within 1 hour. Eval harness gates prompt changes in CI. NAS migration script completes dry-run with zero compose changes.

---

## 10. Tech Stack — Concrete Choices

- **OS:** Ubuntu 24.04 LTS Server (Debian 12 acceptable).
- **Container runtime:** Docker Engine 26+ with Compose v2.
- **Language(s).** Python 3.12 backend; TypeScript 5 + React 19 + Vite for dashboard; SQL for analytics; YAML for config.
- **Frameworks.** FastAPI, Pydantic v2, LangGraph (orchestration), Polars + Pandas (data), Vectorbt (backtest math), DuckDB (ad-hoc analytics), SQLAlchemy 2 (ORM), Alembic (migrations).
- **Frontend.** React + Tailwind + Recharts.
- **LLM client.** `packages/llm-client` with adapters for DeepSeek (default), Anthropic, Groq.
- **Embeddings.** `bge-m3` via DeepSeek embedding endpoint.
- **Observability.** Prometheus + Grafana + Loki + Alertmanager. `node_exporter` + `cadvisor` + `postgres_exporter` + `nats_exporter`. OpenTelemetry traces.
- **CI/CD.** GitHub Actions; self-hosted runner on the mini PC for deploy.
- **Secrets.** `.env` files in dev; `sops` + age in prod (encrypted in repo, decrypted at boot).
- **Notification:** `packages/notifier` with adapters: WeCom bot, WeCom app, Server酱, ntfy, SMTP.

---

## 11. API Inventory

| Provider | What we use | Plan | Monthly $ |
|----------|-------------|------|-----------|
| DeepSeek | Pro + Flash + bge-m3 | PAYG | ≤ $90 |
| Polygon | Stocks Starter | $29 | $29 |
| Tiingo | Power | $30 | $30 |
| Tushare Pro | A-shares | ¥200/yr | ~$3 |
| FRED | Macro | Free | $0 |
| Reddit | API | Free | $0 |
| Telegram | MTProto (read-only ingest) | Free | $0 |
| **WeCom** (企业微信) | Group bot + self-built app | Free | $0 |
| **Server酱 Turbo** | WeChat 服务号 fallback | ¥18/yr | ~$0.20 |
| ntfy.sh | Push fallback | Free (self-host on box) | $0 |
| Backblaze B2 | Offsite backup | ~$6/TB | ~$6 |
| Cloudflare | Tunnel + DNS | Free | $0 |
| Tailscale | VPN | Free (personal) | $0 |
| Anthropic (fallback) | Claude Sonnet 4.6 | PAYG | < $20 spillover |
| Groq (fallback) | Llama-3.3-70B | Free tier | $0 |
| **Total target** | | | **≤ $160/mo** |

---

## 12. Push Notifications — WeChat First

📌 **GROUND TRUTH — channels and priorities:**

| Channel | Direction | Use case | Cost | Failure mode |
|---------|-----------|----------|------|--------------|
| **WeCom group bot** | outbound | morning brief, alerts, fills | free | falls back to Server酱 |
| **WeCom self-built app** | bidirectional | conversational chat with Secretary | free | falls back to web UI |
| **Server酱 Turbo** | outbound | personal-WeChat fallback when WeCom down | ¥18/yr | falls back to ntfy |
| **ntfy** | outbound | tertiary push | free (self-host) | falls back to email |
| **SMTP email** | outbound | last resort + weekly digest | ~$0 | n/a |

**WeCom setup checklist** (Phase 1 + Phase 7):

1. Create a free 企业微信 (WeCom) corporation if you don't have one (single-person corp is fine).
2. In Corporation Admin → 应用管理:
   - Create three group bots (briefs, alerts, fills); copy webhook URLs.
   - Create a self-built app "IIC-Secretary"; record `corp_id`, `agent_id`, `app_secret`.
3. Set the self-built app's "可信域名" to the Tailscale or Cloudflare Tunnel hostname of the mini PC.
4. Implement `/notifier/wecom/callback` for inbound messages (signed by WeCom; signature verified using `app_secret`).
5. Add `WECOM_*` env vars to `.env.example`.

**Brief format conventions:**

- Markdown only (WeCom rejects HTML in markdown body).
- ≤ 4096 chars per message; the Secretary truncates with a "more on dashboard →" link.
- Each item carries `confidence`, `agent`, `entry_band`, `target_band`, `stop_loss`.
- Disclaimer footer: *"仅供个人研究，不构成投资建议 / For personal research only. Not investment advice."*

🧪 **VIBE-PROMPT — `notifier.wecom`:**
> Implement `packages/notifier/wecom_bot.py`. Function `send_markdown(channel: Literal["briefs","alerts","fills"], content: str, mentioned_list: list[str] | None = None)`. POST to the channel's webhook URL with `{"msgtype":"markdown","markdown":{"content":content},"mentioned_list":mentioned_list}`. Retry with exponential back-off on 5xx; on 429, sleep until rate-limit window resets (WeCom limit is 20 msgs/min/bot). On hard failure, raise `NotifierError` so the orchestrator can fall back.

---

## 13. Security, Privacy, Risk

- **No real-money trading.** No broker keys in the system.
- **Personal data minimization.** No PII in events. Watchlist is the most sensitive object; encrypted at rest by sops.
- **Source verification.** Every advice carries citations; backtester rejects uncited.
- **Persona ethics.** Disclaimer required; never claim to be the real person.
- **Network.** Tailscale-only remote access. No public ports, no port-forwarding. Cloudflare Tunnel optional for dashboard.
- **WeChat enclave.** WeCom OAuth callback verifies signatures; messages carry user-id checks; only whitelisted user-ids may issue commands.
- **Secrets rotation.** Quarterly. CI gate that fails if a key is older than 120 days.
- **Compliance.** Personal research system. **Not a registered investment advisor.**

---

## 14. Observability, Eval, and the Leaderboard

**Dashboards (Grafana).**

1. *Operations* — heartbeat per agent, queue depth, error rate, LLM cost burndown, API rate-limit headroom.
2. *Host* — CPU temp, NVMe SMART (writes, wear, temp), RAM, fan RPM, UPS battery.
3. *Data freshness* — feed lag, ingest counts, dedupe ratio, bias-balance.
4. *Investment leaderboard* — per agent: hit rate, R-multiple, Sharpe, max DD, vs benchmark, since-inception.
5. *Trade tape* — live virtual fills.

**Eval harness.** 60-prompt golden set across all callers. Run weekly. Compare outputs to canonical answers via Pro-as-judge with rubric. Alert on > 10% regression — pushed to WeCom alerts bot.

**Leaderboard math (📌 GROUND TRUTH):**

```
score(agent) = w1 * Sharpe + w2 * hit_rate + w3 * R_avg + w4 * (1 / (1 + max_DD))
              - w5 * turnover_penalty - w6 * stale_advice_penalty
defaults: w1=0.30, w2=0.20, w3=0.25, w4=0.15, w5=0.05, w6=0.05
min N for ranking: 20 closed trades, 60 days live
```

⚠️ **RISK:** Sharpe with N<20 is noise. Display "provisional" tag until threshold met.

---

## 15. Success Metrics

- **R1 — Brief reliability.** WeChat morning brief delivered ≥ 95% of trading days within 5 min of schedule.
- **R2 — Agent disagreement.** ≥ 30% of advice events contradict at least one other agent.
- **R3 — Net positive paper P&L.** At least 2 of 8 agents beat the smart-passive benchmark over 6 months.
- **R4 — Cost.** < $160/month all-in.
- **R5 — Family-friendly.** A non-technical family member can ask the WeChat chatbot a question in Chinese and understand the answer.
- **R6 — Recoverability.** Full DR restore < 60 min from cold backup.
- **R7 — Mini-PC uptime ≥ 99.5%** over rolling 30 days, measured by Tailscale online + heartbeat.
- **R8 — NAS-readiness.** `infra/nas/migrate.sh --dry-run` exits zero in CI on every commit.

---

## 16. Open Questions & Future Work

1. **Options engine.** v3 candidate. Greeks via QuantLib.
2. **Realtime broker hookup.** Only after 12 months of robust paper P&L and explicit consent.
3. **Personal research RAG over your own notes.** ChromaDB collection `me`.
4. **Multi-portfolio policy.** Simulate "what if you ran agent X with $50k and agent Y with $50k?"
5. **On-device DeepSeek-V4-distill.** When DeepSeek releases an open-weights distill, evaluate replacing Flash for non-time-critical paths to cut API costs.
6. **NAS upgrade.** Trigger when NVMe is > 70% full or when dataset retention pressure grows.
7. **WeChat richer interactions.** WeCom message cards with action buttons (👍/👎 as feedback signals) once Phase 7 ships.

---

## 17. Appendix A — Vibe-Coding Quickstart Prompts

🧪 **Prompt — Repo bootstrap**
> Create the project scaffold from §0 of `PLAN_v2.1_Investment_Intelligence_Center.md`. Python 3.12 monorepo (Poetry), `apps/` and `packages/`. Wire Ruff, Black, Mypy strict. Stub each agent with `health()` and `process(event)`. `docker-compose.yml` with NATS JetStream, Postgres 16 + Timescale, ChromaDB, MinIO, Redis, Grafana, Loki, Prometheus, node_exporter, cadvisor, postgres_exporter, nats_exporter. ALL volumes are bind-mounts under `/srv/iic/<service>` — no Docker named volumes. Read `.env.example` for keys.

🧪 **Prompt — Linux host bootstrap**
> Generate `infra/linux/bootstrap.sh` per §8.3. Idempotent, runnable from a fresh Ubuntu 24.04 install. Includes Docker engine, Tailscale, restic, ufw, fail2ban, chrony, apcupsd, node_exporter, unattended-upgrades, the `iic` user, and the `/srv/iic/...` directory tree. Write a matching `infra/linux/uninstall.sh` for clean rollback.

🧪 **Prompt — NAS-migrate dry-run**
> Generate `infra/nas/migrate.sh` per §8.4. Supports `--dry-run` (default) and `--apply`. Steps: pre-flight check (NFS reachable? mount point free? compose down clean?), rsync with checksum verification, fstab edit, mount, compose up, post-flight check (every container healthy). On `--dry-run` it must exit 0 even if no NAS exists, simulating the migration in `/tmp`.

🧪 **Prompt — Add the LLM router**
> Implement `packages/llm-client/router.py` per §5. `chat(caller_id, messages, force_tier=None)`. Pro path logs token usage to `lake.advice.llm_calls`. Rate-limit → exponential back-off + circuit breaker. Adapters for DeepSeek, Anthropic, Groq.

🧪 **Prompt — `advice.v1` contract**
> In `packages/schema/`, define `advice.v1` per §3 with Pydantic v2. Generate TS types via `datamodel-code-generator`. `validate_advice` rejects missing citations or expired horizons.

🧪 **Prompt — Build the backtester**
> Implement `apps/agent_backtest` per §4.5. Subscribe to all `advice.*.v1`. Open virtual position at `entry_band` mid + slippage. Mark-to-market every 60 s during market hours, 15 min off-hours. On stop/target → `backtest.fill.v1`, append to `lake.backtest.fills`. Persist daily attribution. Expose `/leaderboard`.

🧪 **Prompt — Persona scaffolding**
> Create `apps/agent_persona/` with one process per persona (slug-driven). Load `docs/prompts/persona/{slug}.yaml`, hydrate from ChromaDB collection `persona_memory_{slug}`. On `intel.digest.v1` → Pro reasoning chain → `advice.persona.{slug}.v1`. Reject outputs missing the disclaimer.

🧪 **Prompt — Secretary + WeChat**
> Build `apps/agent_secretary/` as a FastAPI service. `/chat` (SSE-streamed), `/notifier/wecom/callback` (WeCom signature-verified inbound). Default Flash; switch to Pro on "explain deeply" or multi-agent fan-out. `/notify` callable by orchestrator, fans out via `packages/notifier` to WeCom bot → Server酱 → ntfy → email in priority order.

🧪 **Prompt — Notifier package**
> Build `packages/notifier/` with adapters: `wecom_bot.py`, `wecom_app.py`, `serverchan.py`, `ntfy.py`, `smtp.py`. Each implements `Notifier` protocol with `send(channel, content)`. `Notifier.priority()` chain wires fall-back. Expose `notify(content, severity)`; severity maps to channel set.

🧪 **Prompt — Dashboard MVP**
> Scaffold `apps/dashboard/` with Vite + React + Tailwind + Recharts. Pages: Home (today's brief), Leaderboard, Agent (per-agent feed), Trade tape, Health (host + container metrics). Subscribe to NATS via WebSocket bridge. Tone slider in header.

---

## 18. Appendix B — `docker-compose.yml` skeleton (illustrative, NAS-ready)

```yaml
version: "3.9"

x-iic-base: &iic-base
  restart: unless-stopped
  env_file: .env

services:
  nats:
    <<: *iic-base
    image: nats:2.10-alpine
    command: ["-js", "-sd", "/data"]
    volumes:
      - /srv/iic/nats:/data            # bind-mount; NAS-ready
    ports: ["4222:4222", "8222:8222"]

  postgres:
    <<: *iic-base
    image: timescale/timescaledb-ha:pg16
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/pg_pw
    volumes:
      - /srv/iic/pg:/var/lib/postgresql/data
    ports: ["5432:5432"]

  chroma:
    <<: *iic-base
    image: chromadb/chroma:0.5
    volumes:
      - /srv/iic/chroma:/chroma/.chroma
    ports: ["8000:8000"]

  minio:
    <<: *iic-base
    image: minio/minio:RELEASE.2026-04-01T00-00-00Z
    command: server /data --console-address ":9001"
    volumes:
      - /srv/iic/minio:/data
    ports: ["9000:9000", "9001:9001"]

  redis:
    <<: *iic-base
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "yes"]
    volumes:
      - /srv/iic/redis:/data

  orchestrator:
    <<: *iic-base
    build: ./apps/orchestrator
    depends_on: [nats, postgres, chroma]

  agent_intelligence: { <<: *iic-base, build: ./apps/agent_intelligence, depends_on: [nats, postgres] }
  agent_fundamental:  { <<: *iic-base, build: ./apps/agent_fundamental,  depends_on: [nats, postgres] }
  agent_quant:        { <<: *iic-base, build: ./apps/agent_quant,        depends_on: [nats, postgres] }
  agent_persona:      { <<: *iic-base, build: ./apps/agent_persona,      depends_on: [nats, postgres, chroma] }
  agent_backtest:     { <<: *iic-base, build: ./apps/agent_backtest,     depends_on: [nats, postgres] }
  agent_secretary:    { <<: *iic-base, build: ./apps/agent_secretary,    depends_on: [nats, postgres] }

  grafana:
    <<: *iic-base
    image: grafana/grafana:11
    ports: ["3000:3000"]
    volumes:
      - /srv/iic/grafana:/var/lib/grafana

  loki:
    <<: *iic-base
    image: grafana/loki:3
    ports: ["3100:3100"]
    volumes:
      - /srv/iic/loki:/loki

  prometheus:
    <<: *iic-base
    image: prom/prometheus:v2.55
    volumes:
      - ./infra/observability/prometheus.yml:/etc/prometheus/prometheus.yml
      - /srv/iic/prometheus:/prometheus

  node_exporter:
    <<: *iic-base
    image: prom/node-exporter:v1.8
    pid: host
    network_mode: host
    volumes:
      - /:/host:ro,rslave

  cadvisor:
    <<: *iic-base
    image: gcr.io/cadvisor/cadvisor:v0.49.1
    privileged: true
    volumes:
      - /:/rootfs:ro
      - /var/run:/var/run:ro
      - /sys:/sys:ro
      - /var/lib/docker:/var/lib/docker:ro
```

🔁 **NAS-READY note:** The only system-level change required to switch to a NAS is making `/srv/iic` a bind/NFS mount. Compose itself stays as-is.

---

## 19. Appendix C — `infra/nas/migrate.sh` outline (dry-run by default)

```bash
#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---dry-run}"
NAS_HOST="${NAS_HOST:-nas.local}"
NAS_PATH="${NAS_PATH:-/volume1/iic}"
SRV="/srv/iic"

preflight() {
  command -v rsync >/dev/null
  command -v showmount >/dev/null
  if [[ "$MODE" == "--apply" ]]; then
    showmount -e "$NAS_HOST" | grep -q "$NAS_PATH" || { echo "NFS export not found"; exit 1; }
    df --output=avail "$SRV" | tail -1
  fi
}

stop_stack() { docker compose -f /opt/iic/docker-compose.yml down; }
start_stack(){ docker compose -f /opt/iic/docker-compose.yml up -d; }

migrate() {
  if [[ "$MODE" == "--dry-run" ]]; then
    rsync -aHAX --dry-run --info=progress2 "$SRV/" "/tmp/iic-dryrun/"
  else
    rsync -aHAX --info=progress2 "$SRV/" "$NAS_HOST:$NAS_PATH/"
    grep -q "$NAS_PATH" /etc/fstab || \
      echo "$NAS_HOST:$NAS_PATH $SRV nfs vers=4.1,_netdev,hard,timeo=600,retrans=2 0 0" | sudo tee -a /etc/fstab
    sudo umount "$SRV" || true
    sudo mount "$SRV"
  fi
}

postflight() {
  for c in nats postgres chroma minio redis orchestrator agent_intelligence \
           agent_fundamental agent_quant agent_persona agent_backtest agent_secretary; do
    docker compose -f /opt/iic/docker-compose.yml ps "$c" | grep -q "Up"
  done
}

preflight
stop_stack
migrate
[[ "$MODE" == "--apply" ]] && start_stack && postflight || true
echo "Done in mode: $MODE"
```

---

## 20. Appendix D — Glossary

- **PIT** — Point-in-time. As-of correctness for backtests.
- **R-multiple** — `(exit − entry) / |entry − stop|`.
- **Regime** — A market-state classification (risk-on, risk-off, stagflation, recession, crisis).
- **Reflexivity** — Soros's principle that prices change fundamentals.
- **Bias balance** — Distribution of news sources across regions and political lean.
- **Smart-passive benchmark** — Risk-parity blend used as the leaderboard's neutral comparator.
- **WeCom (企业微信)** — WeChat Work; provides webhooks and OAuth-based self-built apps.
- **Server酱** — Service that pushes messages to a personal WeChat 服务号.

---

## 21. Versioning & Change Log

- **v2.1** (2026-05-06) — Linux mini-PC default, NAS-ready storage layout, WeChat-first push (WeCom + Server酱 + ntfy + email), restic + B2 backups, host hardening playbook, NAS migration script with dry-run gate in CI.
- v2.0 (2026-05-06) — Major: agentic workflow, DeepSeek v4 API-first, hardware tiers, six-agent fleet, backtest leaderboard, secretary chatbot.
- v1.1 (2026-04-04) — Intelligence Center, 7 phases, local-LLM-first.
- v1.0 (2026-04-01) — initial fork plan.

Bumps to **§3 contracts** require a major version. Bumps to phase scope require a minor version. Editorial edits require none.

— end of plan —
