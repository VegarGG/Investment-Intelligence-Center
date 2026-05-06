# Workflow 03 — LLM Client

> **Depends On:** `01_INFRASTRUCTURE_AND_HOST.md`, `02_DATA_LAYER.md`.
> **Owns:** `packages/llm-client/` — DeepSeek v4 wrapper, model routing matrix, fallback chain, cost gating, telemetry.
> **Status:** Final.

---

## 1. Purpose

Every LLM call in IIC goes through one library. That library:

1. Routes to **DeepSeek-V4-Pro** or **DeepSeek-V4-Flash** based on caller, with rules in a single matrix.
2. Falls back to **Claude Sonnet 4.6** (Pro role) or **Groq Llama-3.3-70B** (Flash role) if DeepSeek is unavailable.
3. Tracks token usage per caller and enforces a **monthly cost cap** with a circuit breaker.
4. Caches Flash results for prompts that are deterministic (translation, classification, narration of stable inputs).
5. Records every call to `lake.advice.llm_calls` for telemetry, billing, and the eval harness.

No other code in the system knows about API keys, rate limits, or model names.

---

## 2. Ground Truth — Routing Matrix

📌 **Stable.** This is the contract every caller depends on.

| Caller ID | Default tier | Escalate to Pro when | Cache eligible |
|-----------|--------------|----------------------|----------------|
| `intel.crawler.translate` | Flash | never | yes (24 h, key=hash(text)) |
| `intel.sentiment.classify` | Flash | never | yes (1 h) |
| `intel.dedupe.embed` | Flash (embed only) | never | yes (forever) |
| `intel.synth` | Pro | always | no |
| `fund.filings.extract` | Flash | filing > 200 pages → Pro | yes (per chunk) |
| `fund.valuation` | Pro | always | no |
| `fund.writer` | Pro | always | no |
| `quant.signal` | (no LLM in math path) | n/a | n/a |
| `quant.writer` | Flash | regime change detected → Pro | no |
| `persona.<slug>.daily` | Flash | weekly deep-dive flag → Pro | no |
| `persona.<slug>.weekly` | Pro | always | no |
| `backtest.narrate` | Flash | never | no |
| `secretary.chat` | Flash | user says "explain deeply" or multi-step Q | no |
| `secretary.brief.morning` | Pro | always | no |
| `secretary.brief.midday` | Flash | never | no |
| `orchestrator.plan` | Pro | always | no |

📌 **Cost envelope.** ≤ $90/month at sustained load (≈ 3 M Flash tokens/day + 200 k Pro tokens/day). Hard cap enforced.

---

## 3. Architecture

```
            caller (apps/agent_*, orchestrator)
                       │
                       ▼
        ┌─────────────────────────────────┐
        │       packages/llm-client       │
        │                                 │
        │  router.py  →  rate_limiter.py  │
        │      │             │            │
        │      ▼             ▼            │
        │  adapters/         cache.py     │
        │   ├─ deepseek.py   (Redis)      │
        │   ├─ anthropic.py               │
        │   └─ groq.py                    │
        │      │                          │
        │      ▼                          │
        │  cost_meter.py → lake.llm_calls │
        └─────────────────────────────────┘
                       │
                       ▼
              external API providers
```

---

## 4. Module Layout

```
packages/llm-client/
├── pyproject.toml
├── llm_client/
│   ├── __init__.py
│   ├── types.py              # ChatMessage, ChatResponse, EmbedResponse, LlmTier
│   ├── router.py             # public surface: chat(), embed(), score()
│   ├── rate_limiter.py       # token-bucket per provider
│   ├── cost_meter.py         # rolling spend tracker, circuit breaker
│   ├── cache.py              # Redis-backed prompt cache
│   ├── telemetry.py          # writes lake.llm_calls
│   ├── fallback.py           # Pro→Sonnet, Flash→Groq decision
│   └── adapters/
│       ├── __init__.py
│       ├── base.py           # Adapter ABC
│       ├── deepseek.py       # default
│       ├── anthropic.py      # Claude Sonnet 4.6 fallback
│       └── groq.py           # Llama-3.3-70B fallback
└── tests/
    ├── test_router_matrix.py
    ├── test_rate_limit.py
    ├── test_cost_breaker.py
    ├── test_cache.py
    └── test_fallback.py
```

---

## 5. Public Surface

```python
# llm_client/types.py
from typing import Literal
from pydantic import BaseModel

LlmTier = Literal["flash", "pro", "embed"]

class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str

class ChatResponse(BaseModel):
    text: str
    model: str
    tier: LlmTier
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    cached: bool
    request_id: str

class EmbedResponse(BaseModel):
    vectors: list[list[float]]
    model: str
    cost_usd: float
```

```python
# llm_client/router.py
async def chat(
    caller_id: str,
    messages: list[ChatMessage],
    *,
    force_tier: LlmTier | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.4,
    timeout_s: float = 30.0,
) -> ChatResponse: ...

async def embed(
    caller_id: str,
    texts: list[str],
) -> EmbedResponse: ...
```

Callers pass their `caller_id` — the router consults the matrix in §2 to pick the tier. `force_tier` is for tests and the eval harness.

---

## 6. Routing Decision (router.py)

```python
async def chat(caller_id, messages, *, force_tier=None, ...):
    tier = force_tier or _matrix_lookup(caller_id, runtime_signals())
    cache_key = _cache_key(caller_id, messages, tier)
    if _matrix_cache_eligible(caller_id) and (hit := await cache.get(cache_key)):
        return _mark_cached(hit)

    await rate_limiter.acquire(provider="deepseek", tier=tier)
    if not await cost_meter.allow():
        raise CostBudgetExceeded()

    try:
        result = await deepseek.chat(messages, tier=tier, ...)
    except (DeepSeekDown, ProviderTimeout) as exc:
        result = await fallback.chat(messages, tier=tier, exc=exc)

    await cost_meter.record(result)
    await telemetry.write_call(caller_id, messages, result)
    if _matrix_cache_eligible(caller_id):
        await cache.set(cache_key, result, ttl=_matrix_cache_ttl(caller_id))
    return result
```

**Runtime signals** (the second argument to `_matrix_lookup`) is a small dict with values like `{"filing_pages": 240}` or `{"regime_change": True}`. Callers pass it via a context-var so the matrix can branch without fattening the public signature.

---

## 7. Cost Meter

📌 **Rules:**

- Rolling 30-day spend tracked in Postgres (`lake.llm_spend_daily`).
- Hard cap: `LLM_MONTHLY_CAP_USD` env, default `90`.
- Soft cap at 80% → emit `ops.alert.v1` with severity `WARN`.
- Hard cap at 100% → circuit breaker `OPEN` for 1 h, then half-open. While open, all callers get `CostBudgetExceeded`. Secretary catches this and tells the user via WeCom.
- Per-caller daily budgets configurable; default uniform.

📌 **Provider pricing table** lives in `llm_client/pricing.py` and is the single source of truth for cost math. Updates here are audit-logged.

```python
# llm_client/pricing.py (illustrative)
PRICING = {
    "deepseek-v4-pro":   {"in": 0.55, "out": 2.20},   # USD per 1M tokens
    "deepseek-v4-flash": {"in": 0.07, "out": 0.28},
    "deepseek-bge-m3":   {"in": 0.02, "out": 0.0},
    "claude-sonnet-4.6": {"in": 3.00, "out": 15.00},  # fallback Pro
    "groq-llama-3.3-70b":{"in": 0.0,  "out": 0.0},    # free tier
}
```

⚠️ Prices change. If a provider raises prices and the monthly cap can't be honored at current load, the circuit breaker opens; the runbook in `31_PRODUCTION_HARDENING.md` §6 has the manual override.

---

## 8. Rate Limiter

- Token-bucket per `(provider, tier)`.
- Defaults: DeepSeek 60 RPS Flash, 6 RPS Pro. Anthropic 5 RPS. Groq 20 RPS.
- On 429 from provider: parse `Retry-After`; back off; record `ops.alert.v1` if the wait exceeds 30 s.
- Concurrency cap: max 4 Pro calls in flight (cost reasons), unlimited Flash within RPS.

---

## 9. Cache (Flash-only, deterministic callers)

- Backend: Redis at `cache:llm:<route>:<hash>` (see `02_DATA_LAYER.md` §5.8).
- Key: `sha256(caller_id || tier || canonical_json(messages))`.
- TTL: 24 h for translation; 1 h for sentiment; forever for embeddings.
- Hit returns `cached=True` so the caller knows.

---

## 10. Fallback Chain

📌 **Decision tree.**

```
DeepSeek Pro down  →  Anthropic Claude Sonnet 4.6
DeepSeek Flash down →  Groq Llama-3.3-70B
Both down          →  raise NoLLMAvailable; orchestrator quarantines the event;
                       Secretary pushes ops.alert.v1
```

Detection of "down":
- `httpx.ConnectError` or `ReadTimeout` after 2 retries with jittered backoff.
- HTTP 5xx for 3 consecutive calls in a 5-minute window → mark provider unhealthy for 10 min.
- HTTP 401/403 → never retry; alert immediately.

⚠️ **Cost shift on fallback.** Sonnet 4.6 is ~5× DeepSeek Pro cost. The fallback updates a flag in `cost_meter` so spending while in fallback counts against a separate `LLM_FALLBACK_CAP_USD` (default $20/month). Beyond that cap, Pro calls return `CostBudgetExceeded` even though the primary cap isn't hit.

---

## 11. Telemetry

📌 **Every call writes one row to `lake.llm_calls`:**

```sql
CREATE TABLE lake.llm_calls (
  id              UUID PRIMARY KEY,
  ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
  caller_id       TEXT NOT NULL,
  tier            TEXT NOT NULL,
  model           TEXT NOT NULL,
  prompt_tokens   INT NOT NULL,
  completion_tokens INT NOT NULL,
  cost_usd        DOUBLE PRECISION NOT NULL,
  latency_ms      INT NOT NULL,
  cached          BOOLEAN NOT NULL,
  fallback_used   BOOLEAN NOT NULL,
  outcome         TEXT NOT NULL CHECK (outcome IN ('ok','error','timeout','rate_limit')),
  error           TEXT,
  request_hash    BYTEA,                       -- sha256 of canonical request
  response_hash   BYTEA
);
SELECT create_hypertable('lake.llm_calls', 'ts', chunk_time_interval => INTERVAL '7 days');
```

Grafana panels (defined in `30_OBSERVABILITY_AND_EVAL.md`):
- Tokens/day per caller, last 30 d.
- Spend/day per tier, with cap line.
- Latency p50/p95 per caller.
- Cache hit rate per caller.
- Fallback frequency.

---

## 12. Workflow Steps

### Step 12.1 — Stub the package

Build the file tree from §4 with empty function bodies but full type signatures. Pass `mypy --strict` immediately.

### Step 12.2 — Implement adapters in order

1. `adapters/deepseek.py` — POST to `https://api.deepseek.com/v1/chat/completions` (or v4 endpoint per provider docs at the time of build). Two model strings: `deepseek-v4-pro`, `deepseek-v4-flash`. Streaming optional but **off by default** (most callers want the full response).
2. `adapters/anthropic.py` — POST to `https://api.anthropic.com/v1/messages`. Model: `claude-sonnet-4-6`. Map roles correctly (Anthropic uses `system` as a top-level field, not in messages).
3. `adapters/groq.py` — POST to `https://api.groq.com/openai/v1/chat/completions`. Model: `llama-3.3-70b-versatile`. OpenAI-compatible.

Each adapter implements the `Adapter` ABC: `chat()`, `embed()` (DeepSeek only), `health()`.

### Step 12.3 — Router and runtime signals

Implement `router.py` per §6. Use a `ContextVar` for runtime signals so callers don't have to thread them through every function:

```python
from contextvars import ContextVar
runtime_signals: ContextVar[dict] = ContextVar("runtime_signals", default={})

@asynccontextmanager
async def with_signals(**kwargs):
    token = runtime_signals.set({**runtime_signals.get(), **kwargs})
    try:
        yield
    finally:
        runtime_signals.reset(token)
```

### Step 12.4 — Cost meter and circuit breaker

Postgres-backed (`lake.llm_spend_daily`). Use `aiocircuitbreaker` or roll your own simple state machine: CLOSED → OPEN at cap → HALF_OPEN after 1 h cooldown.

### Step 12.5 — Cache

Redis with TTLs from §9. Cache miss path is the normal route; cache hit returns a synthetic `ChatResponse` with `cached=True` and `cost_usd=0`.

### Step 12.6 — Telemetry

`telemetry.py:write_call()` is fire-and-forget — wrap with `asyncio.create_task` so a slow Postgres write doesn't block the caller. If telemetry fails, log a warning; do not fail the request.

### Step 12.7 — Tests

- Matrix unit tests: every entry in §2 has a test that the right tier is picked.
- Cost breaker: simulate $89.99 of spend, then make one more call → blocked.
- Fallback: mock DeepSeek to raise `ConnectError`, expect Anthropic call.
- Cache: same prompt twice, second call returns `cached=True`.
- Rate limiter: 100 concurrent Flash calls → no more than the configured RPS hits the wire (verify via mock).

---

## 13. Vibe Prompts (paste-ready)

🧪 **Build the package:**
> Implement `packages/llm-client/` per `03_LLM_CLIENT.md`. Python 3.12, async, httpx for HTTP, structlog for logging, redis-py async, asyncpg for telemetry writes. Public surface in `router.py` matches §5 verbatim. Routing matrix in `_matrix.py` is a literal Python dict mirroring §2 — typo-free against the doc. Cost meter uses Postgres `lake.llm_spend_daily` and a Redis lock for atomic increments. Tests in `tests/` cover matrix lookup, cost breaker, fallback, cache, rate limit. All public functions typed; mypy --strict passes.

🧪 **Pricing audit log:**
> Add `llm_client/pricing.py` per §7. Any change to PRICING must be recorded as a row in `lake.llm_pricing_history` via an Alembic migration so we have an audit trail when monthly costs change.

🧪 **Eval-harness hook:**
> Expose `llm_client.eval_mode(force_tier: LlmTier | None, snapshot_path: Path)` — a context manager that pins a tier and writes every (request, response) pair to a JSONL snapshot. The eval harness in `30_OBSERVABILITY_AND_EVAL.md` uses this to replay the golden 60-prompt set deterministically.

---

## 14. Acceptance Criteria

- [ ] `pytest packages/llm-client -q` is green with > 90% line coverage.
- [ ] `mypy --strict packages/llm-client` passes.
- [ ] A round-trip `chat("intel.synth", [...])` against real DeepSeek returns `tier="pro"` and writes one row to `lake.llm_calls`.
- [ ] A round-trip `chat("intel.crawler.translate", [...])` against real DeepSeek returns `tier="flash"`, populates the cache, and the second call returns `cached=True`.
- [ ] Stopping DeepSeek (point `DEEPSEEK_BASE_URL` at a 502 echo server) causes Pro calls to fall back to Anthropic with `fallback_used=True`.
- [ ] Setting `LLM_MONTHLY_CAP_USD=0.01` and making one Pro call trips the breaker; subsequent calls raise `CostBudgetExceeded`.
- [ ] Grafana panel "LLM spend (rolling 30 d)" updates within 60 s of a call.

---

## 15. Risks & Gotchas

⚠️ **API drift.** DeepSeek may change endpoint paths or model strings. Pin the version of `deepseek-v4-pro` and `deepseek-v4-flash` exactly. The adapter has a `health()` that does a 1-token round trip — alarms fire if the model name 404s.

⚠️ **Streaming and partial responses.** Default OFF. If a caller turns it on, telemetry must wait until the stream closes before computing token counts. Don't write partial telemetry rows.

⚠️ **Token counting accuracy.** Different providers count tokens differently. Use the provider's own `usage` block in the response, not a local tokenizer estimate.

⚠️ **Embeddings cost is tiny but non-zero.** Don't accidentally re-embed the same news article 10 times — Redis cache is `forever` for embeddings, keyed by content hash.

⚠️ **Sonnet fallback raises legal concerns?** No — same vendor terms apply. But the cost line item shows up under a different provider in billing, so the cost meter must attribute properly.

⚠️ **Region-locked APIs.** DeepSeek may rate-limit non-CN traffic differently. If you see consistent 429s, adjust the rate limiter defaults in `.env` (`DEEPSEEK_RPS_FLASH`, `DEEPSEEK_RPS_PRO`).

⚠️ **Caching nondeterministic prompts.** Don't cache `intel.synth` or `fund.valuation` — temperature > 0 + time-sensitive context = stale answers. Matrix already handles this; resist the temptation to "save costs" by caching Pro routes.

---

## 16. Cross-References

- Cost telemetry table: `02_DATA_LAYER.md` (this doc adds `lake.llm_calls` and `lake.llm_spend_daily`).
- Caller IDs: every `apps/agent_*` doc declares its caller IDs in its module-layout section.
- Eval harness usage: `30_OBSERVABILITY_AND_EVAL.md` §4.
- Cost-breaker user notification: `15_AGENT_SECRETARY.md` §6 (the secretary explains why the system went quiet).

---

## Changelog

- **v1.0** — Extracted from `PLAN_v2.1` §5 + appendix vibe prompt. Routing matrix promoted to GROUND TRUTH. Fallback cost cap added. Telemetry table schema specified.
