# Workflow 10 — Intelligence Agent

> **Depends On:** `02_DATA_LAYER.md`, `03_LLM_CLIENT.md`, `04_PROMPT_REGISTRY.md`, `05_DATA_BUS_AND_SCHEMAS.md`.
> **Owns:** `apps/agent_intelligence/` — the news/macro/sentiment desk. Forks WorldMonitor, strips UI, emits `intel.digest.v1`, `intel.brief.v1`, `intel.dashboard.v1`.
> **Status:** Final.

---

## 1. Purpose

Be the global desk. Pull, dedupe, translate, summarize, tag, and rank the world's market-relevant signals. Two human-readable outputs (dashboard, WeChat brief) and one agent-friendly digest that downstream advisors consume.

The Intelligence Agent is the only agent that talks to the outside world (RSS, Telegram, X, Reddit, EDGAR, etc.). Every other agent reads from the data lake or the bus.

---

## 2. Ground Truth

### 2.1 Sub-agents (internal fleet)

| Sub-agent | Role | LLM tier |
|-----------|------|----------|
| `intel.crawler` | RSS, Atom, Telegram (read-only), X/Twitter, Reddit, Truth Social, Weibo, Xiaohongshu, state broadcasters | none |
| `intel.translator` | Non-English → English | Flash |
| `intel.macro` | Macro releases (BLS, BEA, ECB, PBoC, Eurostat, IMF, World Bank), commodity & freight dashboards (oil, copper, gold, BDI), credit spreads | none (pure data fetch) |
| `intel.sentiment` | VADER + DeepSeek Flash classifier per-event valence | Flash |
| `intel.synth` | Pro-tier synthesizer producing the digest (top events ranked, regime-change score) | Pro |

### 2.2 Outputs

📌 **Three publish subjects.**

- `intel.dashboard.v1` — JSON for the web UI (heatmap, headline ticker, country-risk dial, BDI / oil / VIX gauges).
- `intel.brief.v1` — 200–400 word morning brief, WeCom-markdown formatted.
- `intel.digest.v1` — agent-friendly: ranked event list with `{id, headline, asset_links[], regime_change_score, sentiment, novelty, recency, sources[]}`.

### 2.3 Data sources (env keys)

📌 **Stable.** Never rename without updating every doc that references them.

| Source | Env key | Plan | Notes |
|--------|---------|------|-------|
| Polygon.io | `POLYGON_API_KEY` | Stocks Starter $29/mo | EOD + intraday US equities, news |
| Alpha Vantage | `ALPHAV_API_KEY` | Free 25/day or $50/mo | Macro fallback |
| Tiingo | `TIINGO_API_KEY` | Power $30/mo | Fundamentals + news |
| FRED | `FRED_API_KEY` | Free | US macro |
| Tushare Pro | `TUSHARE_TOKEN` | ¥200/yr | A-shares, HK, futures |
| EDGAR | (none) | Free | SEC filings |
| HKEXnews | (none) | Free | HKEX filings |
| OpenBB | `OPENBB_PAT` | Free w/ account | Aggregator |
| Telegram MTProto | `TG_API_ID`, `TG_API_HASH` | Free | Channels (read-only) |
| X / Twitter | `X_BEARER` | Basic $100/mo or scrape | Optional |
| RSS bundle | (none) | Free | 90 Wave-1 feeds (carried from WorldMonitor v1.1) |
| Reddit | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` | Free | r/wallstreetbets, r/stocks, r/options |
| Weibo / Xiaohongshu | `[TBD]` | Scraped | Throttled, low-priority |

### 2.4 Source manifest (bias-balance metadata)

📌 **Required for every source.** Stored in `apps/agent_intelligence/sources.yaml`:

```yaml
- id: rss:reuters_business
  url: https://feeds.reuters.com/reuters/businessNews
  region: GLOBAL
  lean: center
  region_weight: 1.0
  rate_limit: 60_per_hour
  language: en
- id: tg:zerohedge_channel
  channel: zerohedge
  region: US
  lean: right
  region_weight: 0.5
  rate_limit: unlimited
  language: en
- id: scrape:cctv_news
  url: https://news.cctv.com/...
  region: CN
  lean: state
  region_weight: 1.0
  rate_limit: 30_per_hour
  language: zh
```

The `bias_balance` block in `intel.digest.v1` is computed from this manifest. Geographic balance is one of Ziwei's explicit project goals — Western source dominance is reduced by capping the contribution of any single region/lean combination.

---

## 3. Architecture

```
                ┌────────────────────────────────────────────┐
                │            apps/agent_intelligence         │
                │                                            │
   feeds  ──▶   │  crawler  →  dedupe  →  translator         │
                │     │                       │              │
                │     │                       ▼              │
                │     │                  sentiment           │
                │     │                       │              │
                │     ▼                       ▼              │
                │  lake.events ──────────────►│              │
                │                             ▼              │
                │  macro pull ───────────►  synth (Pro)      │
                │                             │              │
                │                             ▼              │
                │                  intel.digest.v1           │
                │                  intel.dashboard.v1        │
                │                  intel.brief.v1            │
                └────────────────────────────────────────────┘
                                              │
                                              ▼
                                          NATS bus
```

---

## 4. Module Layout

```
apps/agent_intelligence/
├── pyproject.toml
├── Dockerfile
├── sources.yaml                         # the manifest in §2.4
├── intel/
│   ├── __init__.py
│   ├── main.py                          # FastAPI service + scheduler
│   ├── crawler/
│   │   ├── rss.py
│   │   ├── atom.py
│   │   ├── telegram.py
│   │   ├── x_twitter.py
│   │   ├── reddit.py
│   │   ├── truthsocial.py
│   │   ├── weibo.py
│   │   ├── xiaohongshu.py
│   │   ├── edgar.py
│   │   ├── hkex.py
│   │   └── state_broadcasters.py
│   ├── dedupe/
│   │   ├── hash_gate.py                 # 7-day Redis dedupe
│   │   └── semantic_gate.py             # ChromaDB cosine threshold
│   ├── translate.py                     # llm-client caller_id=intel.crawler.translate
│   ├── sentiment.py                     # VADER + Flash classifier
│   ├── macro/
│   │   ├── fred.py
│   │   ├── ecb.py
│   │   ├── pboc.py
│   │   ├── bls.py
│   │   ├── bea.py
│   │   ├── eurostat.py
│   │   ├── imf.py
│   │   ├── worldbank.py
│   │   ├── commodities.py               # oil, copper, gold, BDI
│   │   └── credit_spreads.py
│   ├── synth.py                         # Pro caller, produces digest
│   ├── brief.py                         # Pro caller, produces WeChat brief
│   ├── dashboard.py                     # produces dashboard JSON
│   ├── bias_balance.py
│   ├── persistence.py                   # writes lake.events
│   └── publish.py                       # publishes the three subjects
└── tests/
    ├── test_dedupe.py
    ├── test_bias_balance.py
    ├── test_synth_smoke.py              # mocked LLM
    └── test_pipeline_end_to_end.py
```

---

## 5. Workflow Steps

### Step 5.1 — Fork WorldMonitor's feed list

Carry over the 90 Wave-1 verified feeds from v1.1. Write them into `sources.yaml` with the new manifest format. Strip non-essential UI from the original repo (we use the IIC dashboard, not WorldMonitor's).

### Step 5.2 — Crawler

Each crawler module implements the same protocol:

```python
class CrawlerProtocol(Protocol):
    async def fetch(self, source: SourceCfg) -> AsyncIterator[RawEvent]: ...
```

`RawEvent` is `{source_id, event_ts, ingest_ts, url, title, body, lang, raw}`. Crawlers honor per-source rate limits and store a resume cursor in Redis (`last_seen:<source_id>`).

### Step 5.3 — Dedupe (two gates)

1. **Hash gate** (`hash_gate.py`): `sha256(source_id, url|title, event_ts)` against Redis with 7-day TTL. Cheap, catches retries and republishes.
2. **Semantic gate** (`semantic_gate.py`): embed via DeepSeek `bge-m3`, query ChromaDB `news` collection with k=5; if max cosine > 0.92 within the last 24 h, treat as duplicate (link to the existing event but don't insert a new row).

### Step 5.4 — Translate

Non-English titles + bodies → English via `llm_client.chat(caller_id="intel.crawler.translate")`. Cache key in Redis = `sha256(text)` with 24 h TTL. Skip translation when `lang == "en"`.

### Step 5.5 — Sentiment

Two-stage: VADER for a fast baseline, then DeepSeek Flash for finance-aware classification (asset-level sentiment when the article mentions a ticker). Output is `{valence: -1..1, target_assets: ["INTC", ...]}`.

### Step 5.6 — Macro pulls

Cron-driven (FRED daily, ECB on release schedules, PBoC weekly, etc.). Result rows go into `lake.timeseries` with `source` set appropriately. Commodity dashboards are scraped from public quote pages — fall back to Tiingo when scraping breaks.

### Step 5.7 — Persist

Every accepted (post-dedupe) event writes one row to `lake.events`. Before insert, attach `source_lean` and `source_region` from `sources.yaml`. Insert is `ON CONFLICT (hash) DO NOTHING`.

### Step 5.8 — Synthesize the digest

`synth.py` runs four times a day (06:00, 12:00, 16:30, 22:00 PT) plus on demand from the orchestrator.

```python
async def synthesize(asof: datetime) -> IntelDigestV1:
    candidates = await load_candidate_events(window=timedelta(hours=24), asof=asof)
    macro_pulls = await load_macro_release_summaries(asof)
    rendered = prompts.get(
        "intel.synth",
        events_json=canonical_json(candidates),
        macro_regime=await kv.get("macro_regime") or "unknown",
    )
    response = await chat(
        caller_id="intel.synth",
        messages=[ChatMessage(role="system", content=rendered.system),
                  ChatMessage(role="user", content=rendered.user)],
        max_tokens=4096,
        temperature=0.2,
    )
    digest = parse_digest(response.text, schema=IntelDigestV1)
    digest.bias_balance = compute_bias_balance(candidates)
    return digest
```

🧪 **VIBE-PROMPT (also seeded into `packages/prompts/registry/intel.synth/1.0.0.md`):**
> *System:* You are the chief intelligence officer for a personal investment desk. From the candidate event list (provided as JSON), select the 25–35 events that most plausibly affect liquid markets in the next 30 days. For each, emit `{rank, headline, why_it_matters_2_sentences, primary_asset_links, regime_change_score 0-1, novelty 0-1}`. Penalize duplicates. Reward cross-source confirmation. End with one paragraph titled "Today's macro thesis."

### Step 5.9 — Compose the brief

`brief.py` takes the digest + (later) the day's emitted advices and produces a 200–400 word, WeCom-markdown brief. Audience modes: `principal` (default, terse, financial) and `family` (educational tone, fewer numbers).

📌 **Brief format conventions:**
- Markdown only (WeCom rejects HTML).
- ≤ 4096 chars; truncate with "more on dashboard →" link.
- Footer: *仅供个人研究，不构成投资建议 / For personal research only. Not investment advice.*

### Step 5.10 — Bias balance

```python
def compute_bias_balance(events: list[Event]) -> BiasBalance:
    by_region = defaultdict(float)
    by_lean   = defaultdict(float)
    total = 0.0
    for e in events:
        w = SOURCE_WEIGHT[e.source_id]      # region_weight from sources.yaml
        by_region[e.source_region] += w
        by_lean  [e.source_lean]   += w
        total += w
    return BiasBalance(
        by_region={k: v/total for k, v in by_region.items()},
        by_lean  ={k: v/total for k, v in by_lean.items()},
    )
```

📌 **Hard rule:** if any region's share > 0.55 in a daily digest, the synthesizer is re-prompted with an instruction to surface non-dominant-region events. If still > 0.55 after re-prompt, emit `ops.alert.v1` of severity `warn`.

### Step 5.11 — Publish

```python
await data_bus.publish("intel.digest.v1", digest)
await data_bus.publish("intel.dashboard.v1", dashboard)
await data_bus.publish("intel.brief.v1", brief)
```

---

## 6. HTTP API

```
POST /run/synthesize       → triggers a synth on demand (used by orchestrator manual kick)
GET  /health               → {feeds_active, last_synth_at, last_brief_at, bias_balance}
GET  /events               → paged read of lake.events (admin only)
```

---

## 7. Vibe Prompts (paste-ready)

🧪 **Scaffold the agent:**
> Implement `apps/agent_intelligence/` per `10_AGENT_INTELLIGENCE.md`. FastAPI service. Crawlers per §5.2 implementing `CrawlerProtocol`. Dedupe per §5.3 (Redis hash gate + ChromaDB semantic gate). Translation/sentiment via `llm_client`. Synth/brief/dashboard producers per §5.8–§5.10. Tests cover dedupe edge cases (same headline different timestamp, near-duplicate by embedding, exact retransmission), bias-balance math, and end-to-end pipeline with mocked LLM.

🧪 **Source manifest seed:**
> Build `sources.yaml` per §2.4 with the 90 Wave-1 feeds carried over from WorldMonitor v1.1 (find them in `PLAN-intelligence-center-v1.1.md` if needed). Distribute region_weights so the manifest's by-region distribution skews ≤ 50% Western at default weights. Include at least 10 each from CN/EU/EM and the major state broadcasters.

🧪 **Synth re-prompt loop:**
> Implement `intel/synth.py` with a re-prompt step per §5.10. If the first synth's underlying candidate set is too lopsided by region, append an instruction to the user message ("Surface at least N events from <under-represented regions>") and call again. Cap at 2 re-prompts. Log every re-prompt as a `ops.heartbeat.v1` event with code `BIAS_REBALANCE`.

🧪 **Brief composer (zh/en):**
> Implement `intel/brief.py`. Auto-detect language from a `language` flag (default `en` for principal mode, `zh` for family mode if user prefers). Use `prompts.get("intel.brief", language=...)`. Output is WeCom-markdown — no HTML tags, no nested code blocks, ≤ 4096 chars. Footer is the disclaimer in the user's language.

---

## 8. Acceptance Criteria

- [ ] `pytest apps/agent_intelligence -q` is green.
- [ ] `GET /health` shows `feeds_active >= 90` once `sources.yaml` is populated.
- [ ] One full pipeline run (manual: `POST /run/synthesize`) produces all three output events on the bus and one brief is delivered to the WeCom briefs bot.
- [ ] `bias_balance` block of the digest never has any region > 0.55 over a rolling 7-day average; spot anomalies fire the alert.
- [ ] Dedupe stops repeated retransmissions from showing up as new events (verified by replaying yesterday's RSS data and asserting zero new rows in `lake.events`).
- [ ] Translation is cached: a second crawl of the same article doesn't bill a translation token (cost meter).
- [ ] Synth output validates against `IntelDigestV1`; failure to parse triggers a retry with a stricter schema-prompt suffix.

---

## 9. Risks & Gotchas

⚠️ **Source bias.** v1.1 carry-forward risk. The bias-balance metric AND the manifest's `region_weight` together must keep dominance in check; check the metric weekly.

⚠️ **Rate-limit traps.** Reddit and X have aggressive caps. Build a circuit breaker per source — if a source 429s thrice in a window, pause it for 30 min and emit a warning.

⚠️ **Telegram private channels.** MTProto can read public channels read-only. Don't ever post; the agent's API keys must be on a session that has joined no private chats it shouldn't be in.

⚠️ **State broadcaster scrapers.** Pages change. Snapshots stored in MinIO `iic-news-html` for 365 d so we can replay scrapes when format breaks.

⚠️ **Synth hallucination of asset links.** The Pro model sometimes invents tickers. Validate `primary_asset_links` against `lake.symbol_master` post-synth and drop unknowns. Don't let invented tickers reach downstream advisors.

⚠️ **Embedding cost creep.** ChromaDB semantic dedupe runs per ingested event; throttle by hashing the title first — if the hash is already in `news` collection, skip the embedding call.

⚠️ **Family-mode brief content.** Don't just translate — actually simplify. The Pro prompt for family mode includes "use no acronyms; explain percent-of-NAV in plain words; avoid ticker symbols, use company names."

⚠️ **WeChat 4096-char limit.** Truncation must be character-aware, not byte-aware (CJK!). Use `len(text)` not `len(text.encode())`. The "more on dashboard →" link is appended after truncation, so account for its length too.

---

## 10. Cross-References

- Subscribers of `intel.digest.v1`: `11_AGENT_FUNDAMENTAL.md`, `12_AGENT_QUANT.md`, `13_AGENT_PERSONA.md`.
- KV `macro_regime` write: `06_ORCHESTRATOR.md` §6.2 (orchestrator sets it from this digest).
- WeCom delivery: `20_NOTIFIER_WECHAT.md`.
- Dashboard JSON shape: `21_DASHBOARD_UI.md` §4.

---

## Changelog

- **v1.0** — Extracted from `PLAN_v2.1` §4.1. Bias-balance hard rule promoted to GROUND TRUTH. Source manifest format formalized.
