# Workflow 02 — Data Layer

> **Depends On:** `01_INFRASTRUCTURE_AND_HOST.md` (substrate must be live).
> **Owns:** Postgres + TimescaleDB schemas, ChromaDB collections, MinIO buckets, Redis cache, retention policy, schema migrations, point-in-time correctness rules.
> **Status:** Final.

---

## 1. Purpose

Make the data layer the system's spine. Everything else (intelligence, fundamental, quant, persona, backtest, secretary) reads or writes here, so the contract must be tight, the schemas must be migration-friendly, and PIT (point-in-time) correctness must be enforceable in tests.

Two principles drive the design:

1. **Append-only where it matters.** `lake.advice` and `lake.backtest.fills` are immutable ledgers. The leaderboard cannot be retroactively edited.
2. **PIT correctness is the foundation of credibility.** If a backtest sees data that wasn't available at the time, the leaderboard becomes a fairy tale. Every ingest pipeline records `as_of` separately from `event_ts`.

---

## 2. Ground Truth — Stores

📌 **The seven stores. Names are stable.**

| Store | Purpose | Tech | Path | Retention |
|-------|---------|------|------|-----------|
| `lake.events` | Raw ingest from sources | Postgres JSONB | `/srv/iic/pg` | 365 d |
| `lake.timeseries` | OHLCV, factors, macro | Timescale hypertable | `/srv/iic/pg` | 10 yr |
| `lake.docs` | Chunked filings, articles | Postgres + Chroma | `/srv/iic/pg` + `/srv/iic/chroma` | 5 yr |
| `lake.advice` | All `advice.v1` ever | Postgres, append-only | `/srv/iic/pg` | forever |
| `lake.backtest` | Fills, P&L, attribution | Postgres | `/srv/iic/pg` | forever |
| `cache` | Hot queries, dedupe | Redis (AOF on) | `/srv/iic/redis` | 24 h |
| `objects` | PDFs, raw HTML, Parquet snapshots | MinIO (S3-compat) | `/srv/iic/minio` | 5 yr |

📌 **Disk budget for the 1 TB NVMe (Year-1 / Year-3):**

| Store | Y1 | Y3 |
|-------|-----|-----|
| Postgres + Timescale | 60 GB | 220 GB |
| ChromaDB | 20 GB | 70 GB |
| MinIO | 80 GB | 300 GB |
| NATS JetStream | 5 GB | 15 GB |
| restic local repo | 30 GB | 80 GB |
| Loki | 15 GB | 40 GB |
| **Total** | **~210 GB** | **~725 GB** |

Year-3 is the trigger to either move `minio` to NAS or prune object lifecycle to 3 yr.

---

## 3. Architecture

```
            ┌────────────────────────────────────────┐
            │         apps/* (agents, orch)          │
            └──────────────────┬─────────────────────┘
                               │
               packages/data-lake (typed clients)
                               │
   ┌─────────────┬─────────────┼─────────────┬───────────┐
   ▼             ▼             ▼             ▼           ▼
┌────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ ┌────────┐
│ PG +   │ │ Chroma   │ │  MinIO   │ │ Redis   │ │ NATS   │
│ Timesc.│ │          │ │          │ │ (cache) │ │ JetStr.│
└────────┘ └──────────┘ └──────────┘ └─────────┘ └────────┘
    bind: /srv/iic/pg, chroma, minio, redis, nats
```

Every agent goes through `packages/data-lake`. No agent talks to Postgres or Chroma directly — this is what lets us swap clients later without scattering import refactors.

---

## 4. Module Layout

```
packages/data-lake/
├── pyproject.toml
├── data_lake/
│   ├── __init__.py
│   ├── config.py             # reads env, returns DSNs
│   ├── postgres.py           # SQLAlchemy 2 engine + sessionmaker
│   ├── timescale.py          # hypertable helpers
│   ├── chroma.py             # ChromaDB client + collection helpers
│   ├── minio.py              # boto3 / minio-py wrappers
│   ├── redis.py              # cache helpers w/ TTL conventions
│   ├── pit.py                # PIT correctness checks (asserts as_of < now)
│   ├── advice_ledger.py      # hash-chained append-only writer
│   └── migrations/           # Alembic
│       ├── alembic.ini
│       ├── env.py
│       └── versions/
│           ├── 0001_init_lake.py
│           ├── 0002_advice_ledger.py
│           └── ...
└── tests/
    ├── test_pit_correctness.py
    ├── test_advice_ledger_chain.py
    └── test_chroma_smoke.py
```

---

## 5. Schemas

### 5.1 Postgres — `lake.events`

```sql
CREATE SCHEMA IF NOT EXISTS lake;

CREATE TABLE lake.events (
  id            BIGSERIAL PRIMARY KEY,
  source_id     TEXT      NOT NULL,            -- 'rss:reuters', 'tg:zerohedge', etc.
  source_lean   TEXT,                          -- 'left'|'center'|'right'|'state'|'unknown'
  source_region TEXT,                          -- ISO-3166 alpha-2 or 'GLOBAL'
  event_ts      TIMESTAMPTZ NOT NULL,          -- when the event happened in the world
  ingest_ts     TIMESTAMPTZ NOT NULL DEFAULT now(), -- when we saw it
  url           TEXT,
  title         TEXT,
  body          TEXT,
  lang          TEXT,
  raw           JSONB NOT NULL,
  hash          BYTEA UNIQUE NOT NULL          -- sha256 over (source_id, url|title, event_ts)
);

CREATE INDEX events_event_ts_idx     ON lake.events (event_ts DESC);
CREATE INDEX events_source_idx       ON lake.events (source_id, event_ts DESC);
CREATE INDEX events_raw_gin          ON lake.events USING gin (raw jsonb_path_ops);
```

📌 **Retention:** rolling 365 d via `pg_partman` monthly partitions on `event_ts`. Drops older partitions automatically.

### 5.2 TimescaleDB — `lake.timeseries`

```sql
CREATE TABLE lake.timeseries (
  symbol     TEXT        NOT NULL,
  ts         TIMESTAMPTZ NOT NULL,
  open       DOUBLE PRECISION,
  high       DOUBLE PRECISION,
  low        DOUBLE PRECISION,
  close      DOUBLE PRECISION,
  volume     DOUBLE PRECISION,
  source     TEXT        NOT NULL,             -- 'polygon'|'tiingo'|'tushare'|'fred'
  as_of      TIMESTAMPTZ NOT NULL,             -- when this row was authoritative
  PRIMARY KEY (symbol, ts, source)
);

SELECT create_hypertable('lake.timeseries', 'ts', chunk_time_interval => INTERVAL '7 days');
SELECT add_retention_policy('lake.timeseries', INTERVAL '10 years');
CREATE INDEX timeseries_symbol_ts ON lake.timeseries (symbol, ts DESC);
```

⚠️ **PIT rule:** any read for backtests must filter `WHERE as_of <= :asof_ts`. The helper `data_lake.pit.assert_pit_safe(query)` greps the SQL string for the `as_of` predicate and raises if missing.

### 5.3 Postgres — `lake.docs`

```sql
CREATE TABLE lake.docs (
  doc_id     UUID        PRIMARY KEY,
  kind       TEXT        NOT NULL,             -- '10K'|'10Q'|'8K'|'20F'|'A_ANNUAL'|'HK_ANNUAL'|'NEWS'
  ticker     TEXT,
  filed_at   TIMESTAMPTZ NOT NULL,
  source_url TEXT,
  raw_path   TEXT,                             -- s3://iic/objects/...
  parsed     BOOLEAN     NOT NULL DEFAULT false,
  parse_err  TEXT
);

CREATE TABLE lake.doc_chunks (
  chunk_id   UUID        PRIMARY KEY,
  doc_id     UUID        REFERENCES lake.docs(doc_id) ON DELETE CASCADE,
  chunk_idx  INT         NOT NULL,
  text       TEXT        NOT NULL,
  token_count INT,
  embedding_id TEXT                            -- ChromaDB record id
);
```

ChromaDB collection: `docs_v1`, embedding model `bge-m3`.

### 5.4 Postgres — `lake.advice` (the immutable ledger)

```sql
CREATE TABLE lake.advice (
  id              TEXT        PRIMARY KEY,    -- ULID
  schema          TEXT        NOT NULL,       -- 'advice.v1'
  agent           TEXT        NOT NULL,       -- 'fundamental' | 'quant' | 'persona.rogers' ...
  issued_at       TIMESTAMPTZ NOT NULL,
  asset_kind      TEXT        NOT NULL,
  asset_ticker    TEXT        NOT NULL,
  asset_venue     TEXT,
  asset_name      TEXT,
  thesis          TEXT        NOT NULL,
  direction       TEXT        NOT NULL CHECK (direction IN ('long','short','flat')),
  confidence      DOUBLE PRECISION NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  entry_low       DOUBLE PRECISION NOT NULL,
  entry_high      DOUBLE PRECISION NOT NULL,
  target_low      DOUBLE PRECISION NOT NULL,
  target_high     DOUBLE PRECISION NOT NULL,
  stop_loss       DOUBLE PRECISION NOT NULL,
  horizon_days    INT         NOT NULL,
  max_drawdown_pct DOUBLE PRECISION NOT NULL,
  sizing_hint_pct_nav DOUBLE PRECISION,
  expires_at      TIMESTAMPTZ NOT NULL,
  evidence        JSONB       NOT NULL,
  payload         JSONB       NOT NULL,        -- full advice.v1 envelope
  prev_hash       BYTEA,                       -- hash of preceding row for THIS agent
  row_hash        BYTEA       NOT NULL,        -- sha256(prev_hash || payload_canonical_json)
  CONSTRAINT advice_id_format CHECK (id ~ '^[0-9A-HJKMNP-TV-Z]{26}$')
);

CREATE UNIQUE INDEX advice_agent_chain_idx ON lake.advice (agent, issued_at, id);
CREATE INDEX advice_ticker_idx ON lake.advice (asset_ticker, issued_at DESC);
```

📌 **Append-only enforcement:** revoke `UPDATE` and `DELETE` from the `iic_app` role on `lake.advice`. The DB rejects anything but inserts.

📌 **Hash chain rule:** before insert, `data_lake.advice_ledger.append(advice)` reads the latest `row_hash` for that agent, computes `sha256(prev_hash || canonical_json(payload))`, and inserts. Backtester verifies the chain on each daily aggregation; a broken chain is a `ops.alert.v1` of severity `CRITICAL`.

### 5.5 Postgres — `lake.backtest.*`

```sql
CREATE TABLE lake.backtest_positions (
  id           BIGSERIAL PRIMARY KEY,
  advice_id    TEXT        NOT NULL REFERENCES lake.advice(id),
  agent        TEXT        NOT NULL,
  ticker       TEXT        NOT NULL,
  opened_at    TIMESTAMPTZ NOT NULL,
  entry_px     DOUBLE PRECISION NOT NULL,
  size_usd     DOUBLE PRECISION NOT NULL,
  stop_loss    DOUBLE PRECISION NOT NULL,
  target_low   DOUBLE PRECISION NOT NULL,
  target_high  DOUBLE PRECISION NOT NULL,
  state        TEXT        NOT NULL CHECK (state IN ('open','closed')),
  closed_at    TIMESTAMPTZ,
  exit_px      DOUBLE PRECISION,
  exit_reason  TEXT,
  pnl_usd      DOUBLE PRECISION,
  pnl_r        DOUBLE PRECISION,
  max_dd_pct   DOUBLE PRECISION
);

CREATE TABLE lake.backtest_marks (
  position_id  BIGINT      NOT NULL REFERENCES lake.backtest_positions(id) ON DELETE CASCADE,
  ts           TIMESTAMPTZ NOT NULL,
  mark_px      DOUBLE PRECISION NOT NULL,
  pnl_usd      DOUBLE PRECISION NOT NULL,
  PRIMARY KEY (position_id, ts)
);
SELECT create_hypertable('lake.backtest_marks', 'ts', chunk_time_interval => INTERVAL '14 days');

CREATE TABLE lake.backtest_attribution_daily (
  agent     TEXT        NOT NULL,
  date      DATE        NOT NULL,
  trades    INT         NOT NULL,
  pnl_usd   DOUBLE PRECISION NOT NULL,
  hit_rate  DOUBLE PRECISION,
  r_avg     DOUBLE PRECISION,
  sharpe    DOUBLE PRECISION,
  max_dd    DOUBLE PRECISION,
  notes     TEXT,
  PRIMARY KEY (agent, date)
);
```

### 5.6 ChromaDB collections

| Collection | Embedding | Purpose |
|------------|-----------|---------|
| `news` | `bge-m3` | Dedupe + retrieve semantically similar headlines |
| `filings` | `bge-m3` | RAG over 10-Ks etc. |
| `persona_memory_<slug>` | `bge-m3` | Each persona's running memory |
| `me` (future) | `bge-m3` | Personal research notes (Phase post-v2.1) |

Helpers in `data_lake/chroma.py`:
```python
def get_or_create(name: str, metadata: dict | None = None) -> Collection: ...
def upsert_doc(collection_name: str, doc_id: str, text: str, meta: dict): ...
def query(collection_name: str, text: str, k: int = 8, where: dict | None = None) -> list[Hit]: ...
```

### 5.7 MinIO buckets

| Bucket | Lifecycle |
|--------|-----------|
| `iic-filings` | Glacier-style: hot 90 d, cold thereafter via lifecycle rule |
| `iic-news-html` | 365 d then expire |
| `iic-snapshots-parquet` | forever (factor matrices, weekly snapshots) |
| `iic-charts` | 180 d (rendered chart PNGs that get embedded in WeChat briefs) |

### 5.8 Redis usage conventions

| Key prefix | TTL | Purpose |
|------------|-----|---------|
| `dedupe:hash:<sha256>` | 7 d | Article dedupe gate |
| `cache:llm:<route>:<hash>` | 1 h | Prompt-result cache (Flash-only) |
| `ratelimit:<provider>:<key>` | sliding | API rate-limit tokens |
| `lock:<resource>` | 60 s | Distributed locks (Redlock) |
| `last_seen:<feed_id>` | forever | Crawler resume cursor |

---

## 6. PIT Correctness Rules

📌 Three rules. Tested in CI on every PR.

1. **Every row in `lake.timeseries` has `as_of` ≤ `now()` at insert time.** A test fixture inserts a row with `as_of` in the future and expects the insert to fail.
2. **Backtest reads must filter `as_of <= :asof_ts`.** `data_lake.pit.assert_pit_safe(stmt)` greps the SQL string; missing `as_of` raises.
3. **Survivorship-corrected universe.** When a backtest names "S&P 500 in 2018," the universe must come from the historical-membership table, not today's index. Build from Tiingo + Polygon delisted feed.

🧪 **VIBE-PROMPT — PIT enforcement:**
> Implement `packages/data-lake/data_lake/pit.py`. Function `assert_pit_safe(query: Union[str, Select]) -> None` raises `PITViolation` if the SQL doesn't reference `as_of`. Function `historical_universe(index: str, asof: date) -> list[str]` returns the constituents of `index` on `asof`, joining `lake.universe_membership` with PIT. Add tests with golden cases for SPX in 2008 (Lehman should be present), in 2009 (Lehman absent), and a custom watchlist.

---

## 7. Workflow Steps

### Step 7.1 — Bring up Postgres & TimescaleDB

1. Compose the `postgres` service per `01_INFRASTRUCTURE_AND_HOST.md` §5.3 (already done).
2. Inside the container, install Timescale extension: `CREATE EXTENSION IF NOT EXISTS timescaledb;` and `pg_partman`.
3. Initialize roles: `iic_app` (read/write app data), `iic_ro` (read-only for dashboards), `iic_migration` (alembic only).
4. Author Alembic env: `data_lake/migrations/env.py` reads `POSTGRES_DSN_MIGRATION` and applies versions in order.

### Step 7.2 — Apply baseline migration

`0001_init_lake.py` creates the `lake` schema and every table in §5. `0002_advice_ledger.py` adds the hash-chain trigger. Run `alembic upgrade head` from the migration container in CI.

### Step 7.3 — Seed reference data

- `lake.universe_membership(index TEXT, ticker TEXT, in_from DATE, in_to DATE NULL)` — populated from Polygon delisted + Tiingo historical constituents.
- `lake.calendar_events(ticker, kind, ts)` — earnings dates for the watchlist.
- `lake.macro_releases(series_id, schedule_cron)` — when each FRED/BLS release lands.

### Step 7.4 — ChromaDB collections

Provision the four collections at boot via `data_lake/chroma.py:bootstrap_collections()` called by the orchestrator on startup. Collections are idempotent — recreating is a no-op.

### Step 7.5 — MinIO buckets + lifecycle

Author `infra/minio/init-buckets.sh` to create the four buckets, set lifecycle rules, and create an `iic-app` user with bucket-scoped access.

### Step 7.6 — Backups for the data layer

Postgres-specific:
- `pg_dump --format=custom` weekly to `/srv/iic/pg/dumps/`. Restic includes this.
- WAL archiving daily to `/srv/iic/pg/wal-archive` (retain 14 d).

ChromaDB-specific:
- `cp -a /srv/iic/chroma /srv/iic/chroma-snapshot-$(date +%F)` weekly. Restic includes the snapshot dir.

MinIO-specific:
- `mc mirror minio/iic-snapshots-parquet /srv/iic/minio-mirror/snapshots-parquet` daily. Restic includes the mirror.

### Step 7.7 — Health endpoints

Each store has a `/health/<store>` endpoint exposed by `apps/orchestrator`:
- `pg`: `SELECT 1` round-trip, return rowcount of `lake.advice` and chain integrity (`ok|broken`).
- `chroma`: `client.heartbeat()` and collection presence check.
- `minio`: `head_bucket` for each of the four buckets.
- `redis`: `PING`.

These feed the **Operations** Grafana dashboard.

---

## 8. Vibe Prompts (paste-ready)

🧪 **Migration scaffold:**
> Build `packages/data-lake/data_lake/migrations/` per `02_DATA_LAYER.md` §7.1–§7.2. Alembic on Python 3.12. `0001_init_lake.py` creates everything in §5.1–§5.5 verbatim, including the Timescale `create_hypertable` calls and the partman partitioning on `lake.events`. `0002_advice_ledger.py` adds an INSERT trigger that computes `row_hash` and rejects writes that don't update `prev_hash` to the previous chain head. Tests in `tests/test_advice_ledger_chain.py` insert 100 advices and verify chain integrity end-to-end.

🧪 **Typed clients:**
> Implement `data_lake/postgres.py`, `timescale.py`, `chroma.py`, `minio.py`, `redis.py` per §4. Use SQLAlchemy 2 async, Pydantic v2 for row models, `pyrate_limiter` for the cache layer, and the official `chromadb` and `minio` SDKs. Every public function has type hints, every error path raises a typed exception (`DataLakeError` subclass).

🧪 **Hash-chained ledger writer:**
> Implement `data_lake/advice_ledger.py:append(advice: AdviceV1) -> None`. Read latest row_hash for `advice.agent` under SELECT FOR UPDATE. Compute `row_hash = sha256(prev_hash || canonical_json(advice))` and INSERT. Also expose `verify_chain(agent: str) -> ChainStatus` returning `ok|broken_at_id|empty`. Test: corrupt one row mid-chain, expect `verify_chain` to point at the bad id.

🧪 **PIT helper:**
> Implement `data_lake/pit.py` per §6. `assert_pit_safe` accepts both raw SQL and SQLAlchemy Select. Use sqlglot to parse, then check the WHERE clause references `as_of`. Tests cover: passes for `WHERE as_of <= :asof_ts`, fails for `WHERE ts <= :asof_ts`, fails for missing predicate, fails for `as_of >= now()`.

---

## 9. Acceptance Criteria

- [ ] `alembic upgrade head` succeeds from a fresh DB and is idempotent (`alembic current` matches `head`).
- [ ] `pytest packages/data-lake -q` is green, including `test_pit_correctness.py` and `test_advice_ledger_chain.py`.
- [ ] `psql -U iic_app -c "DELETE FROM lake.advice"` fails with permission denied.
- [ ] `psql -c "SELECT extname FROM pg_extension"` shows `timescaledb` and `pg_partman`.
- [ ] `lake.timeseries` is a hypertable: `SELECT * FROM timescaledb_information.hypertables` lists it.
- [ ] ChromaDB has the four collections (`news`, `filings`, `persona_memory_*` ready as templates, `me` reserved).
- [ ] MinIO has the four buckets with correct lifecycle rules.
- [ ] Inserting an `advice.v1` and then querying `verify_chain('test')` returns `ok`.
- [ ] PIT test: factor build at `as_of=2024-06-01` returns no rows whose `as_of > 2024-06-01`.
- [ ] Backup job creates a Postgres dump + Chroma snapshot + MinIO mirror, all included in the next restic snapshot.

---

## 10. Risks & Gotchas

⚠️ **Postgres on NFS.** Future NAS migration: keep Postgres on local NVMe by default. Hybrid layout supported by `01_INFRASTRUCTURE_AND_HOST.md` §5.6 NAS migrate script.

⚠️ **Alembic + Timescale.** Hypertables must be created via raw SQL (`op.execute("SELECT create_hypertable(...)")`), not via Alembic's `create_table`. Document in migration comments.

⚠️ **ChromaDB version churn.** ChromaDB pre-1.0 has migration hiccups. Pin the version in `docker-compose.yml`, never use `:latest`. When upgrading, snapshot first.

⚠️ **MinIO lifecycle vs. backups.** If lifecycle expires an object, restic still has it for the retention window. Document the asymmetry — restoring from MinIO + restic is the source of truth.

⚠️ **Redis is a cache, not a store.** Reboots are tolerable; do not put any data here that the system cannot rebuild from PG/Chroma/MinIO.

⚠️ **Universe membership backfill.** Initial population of `lake.universe_membership` is a one-time scripted job; don't try to do it at startup. It's a separate Make target (`make seed-universes`).

⚠️ **JSONB vs. discrete columns in `lake.advice`.** We duplicate the most-queried fields (`agent`, `asset_ticker`, `direction`) as discrete columns; the full envelope is in `payload`. Don't read `payload` for hot queries — use the discrete columns.

---

## 11. Cross-References

- `advice.v1` schema definition: `05_DATA_BUS_AND_SCHEMAS.md` §3.
- Backups & restore: `01_INFRASTRUCTURE_AND_HOST.md` §5.5 and `31_PRODUCTION_HARDENING.md` §5.
- PIT use cases: `12_AGENT_QUANT.md` §5 (factor builder), `14_AGENT_BACKTEST.md` §5 (historical replay).
- Bias-balance metric uses `lake.events.source_lean` + `source_region`: `10_AGENT_INTELLIGENCE.md` §6.
- Migration on NAS: `01_INFRASTRUCTURE_AND_HOST.md` §5.6 (Postgres-stays-local hybrid).

---

## Changelog

- **v1.0** — Extracted from `PLAN_v2.1` §6, plus PIT correctness rules promoted from the Quant section. Schemas tightened (NOT NULLs, CHECK constraints, hash chain explicit). Calendar-week sequencing removed.
