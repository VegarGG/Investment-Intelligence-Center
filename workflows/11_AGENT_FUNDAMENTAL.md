# Workflow 11 — Fundamental Agent

> **Depends On:** `02_DATA_LAYER.md`, `03_LLM_CLIENT.md`, `04_PROMPT_REGISTRY.md`, `05_DATA_BUS_AND_SCHEMAS.md`, `10_AGENT_INTELLIGENCE.md`.
> **Owns:** `apps/agent_fundamental/` — bottoms-up valuation, filings reading, watchlist coverage, `advice.fundamental.v1` emission.
> **Status:** Final.

---

## 1. Purpose

Read filings, build a quick valuation, compare with peers, and output stock-level recommendations grounded in citations. This agent owns the "value desk" lens — patient, peer-aware, allergic to hand-waving.

Coverage policy: a curated **watchlist of 50 names** plus an opportunistic long-tail pass weekly. The agent does not chase every ticker; it goes deep on the 50.

---

## 2. Ground Truth

### 2.1 Sub-agents

| Sub-agent | Role | LLM tier |
|-----------|------|----------|
| `fund.filings` | Fetch + chunk + vectorize 10-K, 10-Q, 8-K, 20-F, A-share annuals, HK annuals | Flash for chunk extract |
| `fund.valuation` | Lightweight DCF, P/E vs sector, EV/EBITDA, FCF yield. Pulls peer data from Tiingo | Pro |
| `fund.linker` | Links macro events from `intel.digest.v1` to specific tickers in the watchlist | Flash |
| `fund.writer` | Composes the `advice.fundamental.v1` payload | Pro |

### 2.2 Watchlist

📌 **Authoritative source:** `apps/agent_fundamental/watchlist.yaml`. User-curated. Re-loaded on every run.

```yaml
- ticker: INTC
  venue: NASDAQ
  sector: Semiconductors
  thesis_tag: turnaround
  peers: [AMD, NVDA, QCOM, AVGO, TXN]
- ticker: 0700.HK
  venue: HKEX
  sector: Internet
  thesis_tag: dominant_platform
  peers: [9988.HK, BABA, JD, PDD]
- ticker: BHP
  venue: NYSE
  sector: Mining
  thesis_tag: commodity_cycle
  peers: [RIO, VALE, GLEN.LSE]
# … 50 total
```

### 2.3 Triggers

| Trigger | Frequency / condition |
|---------|----------------------|
| `intel.digest.v1` | Every digest publish (≥ 4×/day) — re-rank watchlist by relevance to the digest |
| `event:filing` | New filing for any watchlist ticker → refresh that ticker's analysis |
| `cron:longtail_weekly` | Sundays 14:00 PT → opportunistic pass on top movers outside the watchlist |
| `event:earnings_release` | Earnings calendar hit → pre-earnings + post-earnings advice consideration |

### 2.4 Filings handled

| Form | Source | Cadence |
|------|--------|---------|
| 10-K, 10-Q, 8-K, 20-F | EDGAR | within 1 h of filing |
| A-share annual / interim / quarterly | Tushare Pro / SSE / SZSE | on release |
| HK annual / interim | HKEXnews | within 1 h |
| Earnings transcripts | Tiingo / scraped | T+1 |

### 2.5 Citation rule

📌 **Hard.** Every numeric claim in the thesis cites a source. The validator (in `packages/schema/`) rejects an `advice.fundamental.v1` whose `evidence` array is empty or whose thesis contains numbers not paired with at least one citation. Backtester quarantines uncited advice.

---

## 3. Architecture

```
   intel.digest.v1 ──┐
   filing events ────┼──► fund.linker ──► relevance-ranked tickers
   earnings cal  ────┘                       │
                                             ▼
                                  fund.filings.refresh
                                             │
                                             ▼
                              fund.valuation (Pro)
                                             │
                                             ▼
                              fund.writer (Pro)
                                             │
                                             ▼
                                advice.fundamental.v1
```

---

## 4. Module Layout

```
apps/agent_fundamental/
├── pyproject.toml
├── Dockerfile
├── watchlist.yaml
├── fund/
│   ├── __init__.py
│   ├── main.py                 # FastAPI + scheduler + NATS subscriber
│   ├── filings/
│   │   ├── edgar.py
│   │   ├── hkex.py
│   │   ├── tushare.py
│   │   ├── chunker.py
│   │   └── embedder.py         # writes to ChromaDB collection 'filings'
│   ├── linker.py               # match digest events ↔ watchlist tickers
│   ├── valuation/
│   │   ├── dcf.py
│   │   ├── multiples.py
│   │   ├── peer_pull.py        # Tiingo
│   │   └── catalysts.py
│   ├── writer.py               # composes advice.fundamental.v1
│   ├── coverage.py             # picks today's tickers based on triggers
│   └── publish.py
└── tests/
    ├── test_dcf.py
    ├── test_citation_required.py
    ├── test_linker.py
    └── test_pipeline.py
```

---

## 5. Workflow Steps

### Step 5.1 — Filings ingest

`fund.filings.edgar.py` polls EDGAR's RSS for the watchlist's CIKs. New filings → fetch PDF/HTML → store in MinIO `iic-filings/<ticker>/<accession>/` → `chunker.py` splits into ~1 k-token chunks → `embedder.py` writes to ChromaDB `filings` collection with metadata `{ticker, form, filed_at, accession}`.

Same pattern for HKEX (`hkex.py`) and A-shares (`tushare.py`).

🧪 **VIBE-PROMPT — chunker:**
> Implement `fund/filings/chunker.py` using a hierarchical splitter: first by Item (10-K Items 1, 1A, 7, 7A, 8); within an Item, by sentences with 200-token overlap. Token counter via tiktoken with the DeepSeek tokenizer compatibility. Store chunk metadata `{section, parent_doc, chunk_idx, token_count}` so retrieval can prefer Item 7 (MD&A) and Item 1A (Risks).

### Step 5.2 — Linker

For each digest event (`intel.digest.v1.events[]`), the linker scores relevance to each watchlist ticker:

```
score = α * sector_match + β * primary_asset_link_overlap + γ * peer_mention
```

Top-K (default 10) tickers per digest become the day's coverage candidates. Events that are pure macro (no asset_links) are skipped at the linker stage — quant agent handles macro, not fundamental.

### Step 5.3 — Valuation

`valuation/dcf.py`: light DCF — 5-year FCF projection, terminal growth, WACC. Inputs from `lake.timeseries` (PIT-correct).
`valuation/multiples.py`: P/E vs sector, EV/EBITDA, FCF yield, against the peer set in `watchlist.yaml`.
`valuation/peer_pull.py`: pulls comps from Tiingo via `data_lake.timeseries`.
`valuation/catalysts.py`: extracts upcoming catalysts (next earnings date, planned product launches found in 10-K Item 1 or news).

The Pro call composes a `{base, bull, bear}` fair-value range with explicit assumptions and a 1-line catalyst list. **Refuse if inputs missing > 30%** — emit `ops.heartbeat.v1` with code `INSUFFICIENT_DATA` and skip the ticker.

🧪 **VIBE-PROMPT — `fund.valuation` (also seeded into prompt registry):**
> *System:* You are a sell-side analyst with a value bias but pragmatic about cyclicals. Given fundamentals JSON for {ticker} and 5 peer tickers, propose a fair-value range and 12-month target. Output `{base, bull, bear}` cases with explicit assumptions and a one-line catalyst list. Refuse if data is missing > 30%.

### Step 5.4 — Writer

`writer.py` composes the `advice.fundamental.v1`:

```python
advice = AdviceV1(
    schema="advice.v1",
    id=ulid.new(),
    agent="fundamental",
    issued_at=now,
    asset=Asset(kind="equity", ticker=ticker, venue=venue, name=name),
    thesis=thesis_text,
    direction=direction,                          # long if mid_target / current > 1.10, short < 0.90, flat else
    confidence=confidence,
    entry_band=[entry_low, entry_high],
    target_band=[target_low, target_high],
    stop_loss=stop_loss,
    horizon_days=90,                              # fundamentals run multi-month
    max_drawdown_pct=12.0,
    sizing_hint_pct_nav=2.5,
    expires_at=now + timedelta(days=90),
    evidence=[
        Evidence(kind="filing", url=filing_url, ref=f"chunk_id={chunk_id}"),
        Evidence(kind="news", ref=f"intel.digest.v1#{event_id}"),
        Evidence(kind="data", ref=f"lake.timeseries:{ticker}@{asof}"),
    ],
)
schema.AdviceV1.validate(advice)                 # raises if uncited or band-inconsistent
```

### Step 5.5 — Coverage policy

The agent runs at most 8 valuations per digest cycle (cost cap). If linker produces > 8 candidates, it picks: (a) highest relevance score, (b) tickers without an active advice in the last 14 d (freshness preference), (c) ties broken by alphabetical ticker.

The weekly long-tail pass (Sunday) picks 5 tickers outside the watchlist that scored in the top decile of `intel.dashboard.v1` mentions over the past week.

### Step 5.6 — Health endpoint

```
GET /health → {watchlist_size, last_run_at, advices_emitted_24h, valuation_failures_24h}
```

---

## 6. HTTP API

```
POST /run/cover/{ticker}     → on-demand single-ticker pass (used by orchestrator)
POST /run/digest             → process latest digest (kicked from orchestrator DAG A)
GET  /health
GET  /watchlist
```

---

## 7. Vibe Prompts (paste-ready)

🧪 **Scaffold the agent:**
> Implement `apps/agent_fundamental/` per `11_AGENT_FUNDAMENTAL.md`. FastAPI service. Subscribe to `intel.digest.v1` and (later) `event:filing`. Filings ingest writes to MinIO + ChromaDB. Valuation uses Tiingo for peers, FRED for risk-free rate. Writer enforces the `AdviceV1` validator and refuses uncited advice. Tests cover: DCF math against a known case (e.g., reproduce a vetted 2024 INTC base case within 5%), citation enforcement (mock thesis with bare numbers fails), linker scoring (digest event mentioning "semiconductors" links to INTC/AMD/NVDA at high score), and a full pipeline with mocked LLM.

🧪 **Filings retrieval RAG:**
> Implement `fund/filings/embedder.py` and a retrieval helper `retrieve(ticker, query, k=8) -> list[Chunk]`. Use ChromaDB `filings` collection. Default retrieval prefers Item 7 (MD&A) and Item 1A (Risks) chunks via the `section` metadata field. The Pro valuation prompt includes the retrieved chunks as context with `<filing_excerpt section="..." accession="..." chunk_idx="...">...</filing_excerpt>` tags so the LLM can cite back to chunk_id.

🧪 **Citation guard:**
> Add a post-LLM validator `writer.guard_citations(advice)` that scans the thesis for numbers (regex: percentages, multiples, $ amounts) and asserts each is followed within 50 characters by a citation marker. If not, run a one-shot Pro re-prompt asking to add citations; if still missing, drop the advice.

---

## 8. Acceptance Criteria

- [ ] `pytest apps/agent_fundamental -q` is green.
- [ ] `POST /run/cover/INTC` (with EDGAR + Tiingo keys live) produces a valid `advice.fundamental.v1` event on the bus, persisted to `lake.advice` with chain integrity intact.
- [ ] `advice.evidence` always non-empty and `direction != flat` when emitted.
- [ ] Citation guard fails the writer for thesis "INTC trades at 20× earnings vs sector 14×" without any `[ref]` markers; passes when references are appended.
- [ ] Watchlist of 50 produces ≥ 5 advices/day on average (over 7-day window).
- [ ] Valuation refusal (`INSUFFICIENT_DATA`) is observable in Grafana — at least one panel for "skipped tickers per day".
- [ ] One filing arrival → MinIO file, ChromaDB chunks, and (within 30 min) a re-emitted advice for that ticker.

---

## 9. Risks & Gotchas

⚠️ **Hallucinated multiples.** Pro models occasionally invent peer multiples. Always feed peer numbers as structured input; never let the model invent them.

⚠️ **Stale fundamentals.** Tiingo daily snapshots can lag. Always check `as_of` and refuse if > 7 days stale for fast-moving names.

⚠️ **Currency mismatches.** A-shares are CNY, HK is HKD. Convert to USD at the asof FX rate from `lake.timeseries` before peer comparisons. Don't compare P/E across currencies without normalization.

⚠️ **Survivorship bias in peers.** Watchlist peers should be PIT-correct historical comparables. The peer list is editable by the user; the agent doesn't auto-discover peers (avoids drift).

⚠️ **Filing scrape brittleness.** EDGAR HTML changes. Pin to the SEC's full-text submission JSON endpoint (more stable). HKEX and SSE are scraped; cache snapshots so a layout change doesn't lose data.

⚠️ **Item-classification errors.** The chunker's heuristic for "Item 7" vs "Item 1A" can mis-tag short filings (8-Ks). Apply per-form rules.

⚠️ **Catalyst over-confidence.** "Catalyst" extraction is shallow. Tag confidence per catalyst; the writer can include only catalysts with `confidence >= 0.5`.

⚠️ **Pro cost explosion on weekly long-tail.** Cap the long-tail pass at 5 tickers; don't let it balloon.

---

## 10. Cross-References

- Watchlist editing UX: `21_DASHBOARD_UI.md` §6 (admin-only page).
- Backtester citation reject behavior: `14_AGENT_BACKTEST.md` §6.
- ChromaDB filings collection: `02_DATA_LAYER.md` §5.6.
- Currency normalization helpers: `02_DATA_LAYER.md` §5.2 + a future `data_lake/fx.py`.

---

## Changelog

- **v1.0** — Extracted from `PLAN_v2.1` §4.2. Citation guard formalized; coverage policy and refusal rules made explicit.
