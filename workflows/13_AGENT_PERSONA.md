# Workflow 13 — Persona Agent ("Trader Ghosts")

> **Depends On:** `02_DATA_LAYER.md`, `03_LLM_CLIENT.md`, `04_PROMPT_REGISTRY.md`, `05_DATA_BUS_AND_SCHEMAS.md`, `10_AGENT_INTELLIGENCE.md`, `14_AGENT_BACKTEST.md`.
> **Owns:** `apps/agent_persona/` — style-mimic strategists driven by named investors' public writings.
> **Status:** Final.

---

## 1. Purpose

Bring the *style* and *psychology* of named investors to the desk. **Not** their actual portfolios — their thinking pattern as evidenced by their public writing and interviews.

Each persona is a **prompt + memory + bias-vector** combination, hot-loaded from a YAML at boot. The personas disagree productively; disagreement is one of the system's success metrics.

---

## 2. Ground Truth

### 2.1 Initial roster

📌 **Slugs are stable** — every other doc references them.

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

The agent runs one process per persona slug. Adding a persona = adding a YAML file + (optional) seed memory.

### 2.2 Persona file format

📌 **GROUND TRUTH** — `docs/prompts/persona/<slug>.yaml`:

```yaml
slug: rogers
display_name: Jim Rogers
priors:
  - "Buy what's hated; sell what's loved."
  - "Commodities lead inflation."
  - "Patience is the edge most strategists lack."
canonical_trades:
  - era: 1980s
    asset: gold
    action: long
    lesson: "Patience pays even when consensus calls you a fossil."
  - era: 1998
    asset: agriculture commodities
    action: long
    lesson: "Cycles are longer than careers."
universe_weights:
  commodities: 0.50
  em_equities: 0.25
  fx: 0.15
  us_largecap: 0.05
  bonds: 0.05
prompt_template_ref: persona.daily.base@1.0.0      # references registry version
memory_scope:
  retain_days: 365
  bias_categories: [contrarian, commodity_cycle, em_focus]
guardrails:
  - "Never claim to be the real Jim Rogers."
  - "Disclaimer required on every output."
  - "Avoid US-mega-cap unless extreme value."
disclaimer: "Stylized agent inspired by public writings; not Mr. Rogers."
```

### 2.3 Memory model

Each persona has a ChromaDB collection `persona_memory_<slug>` storing:

- **Decisions:** every advice this persona has emitted, with the resulting fill outcome from `backtest.fill.v1`.
- **Reasoning artifacts:** the actual prompts and Pro responses that produced the advice.
- **Lessons:** Pro-distilled "what would the persona learn?" notes after each closed trade.

Retrieval: at advice time, the persona retrieves k=8 most-similar past decisions to the current setup and includes them in the prompt as "your prior reasoning on similar setups."

### 2.4 Disclaimer rule

📌 **Hard.** Every `advice.persona.<slug>.v1` must carry:

```
disclaimer: "Stylized agent inspired by public writings; not Mr. {name}."
```

Two lines of defense:
1. The persona's prompt template includes the disclaimer instruction explicitly.
2. `output_validator.py` rejects any payload missing the disclaimer; the orchestrator quarantines it.

### 2.5 Triggers

| Trigger | Frequency |
|---------|-----------|
| `intel.digest.v1` | Daily run on each digest publish (Flash) |
| `cron:weekly_persona` | Weekly deep dive per persona (Pro) |
| `event:earnings_release` | Buffett, Burry only (they care about specific names) |
| `event:macro_release_major` | Soros, Druckenmiller, Dalio, Rogers |

---

## 3. Architecture

```
   intel.digest.v1 ─────┬─► persona.rogers.process()  ─► advice.persona.rogers.v1
                        ├─► persona.buffett.process() ─► advice.persona.buffett.v1
                        ├─► ...                       ─► advice.persona.<slug>.v1
                        │
                        ▼
                personal_memory_<slug> retrieval (Chroma)
                        │
                        ▼
                persona prompt = base @ persona YAML @ retrieved memories
                        │
                        ▼
                  llm_client.chat (Flash daily, Pro weekly)
                        │
                        ▼
                output_validator → publish + persist
```

---

## 4. Module Layout

```
apps/agent_persona/
├── pyproject.toml
├── Dockerfile
├── persona/
│   ├── __init__.py
│   ├── main.py                       # FastAPI; multiplexes one process per slug via env PERSONA_SLUG
│   ├── loader.py                     # reads YAML + base prompt
│   ├── memory.py                     # Chroma read/write per slug
│   ├── reasoner.py                   # the core daily/weekly call
│   ├── output_validator.py           # disclaimer + AdviceV1 validation
│   ├── feedback.py                   # consumes backtest.fill.v1, distills lessons
│   └── publish.py
└── tests/
    ├── test_disclaimer_validator.py
    ├── test_memory_retrieval.py
    ├── test_loader_schema.py
    └── test_style_classifier.py      # offline: ensure outputs read like the persona
```

---

## 5. Workflow Steps

### Step 5.1 — Persona loader

`loader.py` reads `docs/prompts/persona/<slug>.yaml`, validates with a Pydantic model, fetches `prompt_template_ref` from the prompt registry, and composes the runtime prompt template. Loader fails the container at boot if any persona's YAML is malformed — fail loud, fail early.

### Step 5.2 — Daily run

On `intel.digest.v1` arrival:

1. Fetch the digest's top events plus today's universe candidates filtered by the persona's `universe_weights` (e.g., Rogers ignores most US large-cap names).
2. Retrieve k=8 prior decisions from `persona_memory_<slug>`.
3. Compose the prompt: base template → persona YAML interpolation → retrieved memories → today's events.
4. Call `llm_client.chat(caller_id=f"persona.{slug}.daily")` (Flash).
5. Parse JSON output → `AdviceV1`.
6. Validate disclaimer + schema.
7. Publish + persist + write the reasoning artifact to memory.

### Step 5.3 — Weekly deep dive

`cron:weekly_persona` (e.g., Sunday 14:00 PT for Rogers, Wednesday for Buffett — staggered to spread Pro cost):

- Same flow as daily, but Pro tier and fuller context (k=16 memories, longer max_tokens).
- Output is allowed up to 3 advices per persona vs. the daily 1.

### Step 5.4 — Feedback loop

`feedback.py` subscribes to `backtest.fill.v1` and routes by `advice.agent`. For each closed trade owned by this persona:

1. Append the fill outcome to the matching memory record (Chroma metadata update).
2. Run a short Pro distillation: "what would the persona learn from this outcome? In ≤ 30 words." Store as a separate memory entry tagged `lesson`.
3. The next daily/weekly run retrieves lessons preferentially when the current setup is similar.

### Step 5.5 — Output validator

`output_validator.py` enforces:

- `advice.agent == f"persona.{slug}"`
- `advice.disclaimer` present and matches the YAML's disclaimer string.
- `AdviceV1.validate(advice)` passes (band consistency, evidence, etc.).
- Universe check: `advice.asset.kind/ticker` is allowed by `universe_weights` (ignore zero-weight slices).

### Step 5.6 — Style audit (CI)

Add a `tests/test_style_classifier.py` that uses Pro to grade 20 historical outputs of each persona on a 5-point rubric: ("Sounds like the persona", "Cites the persona's known principles", "Avoids forbidden moves"). Score < 4.0 average → fail CI. This is what catches prompt drift that the eval harness's golden set may miss.

---

## 6. HTTP API (per process)

```
POST /run/daily            → run a daily pass on demand (orchestrator DAG A)
POST /run/weekly           → run a weekly deep dive on demand
GET  /health               → {slug, advices_24h, memory_size, last_lesson_at}
GET  /memory/recent?k=20   → admin
```

---

## 7. Vibe Prompts (paste-ready)

🧪 **Scaffold the agent (single binary, slug from env):**
> Implement `apps/agent_persona/` per `13_AGENT_PERSONA.md`. One Docker image; runtime selects slug via `PERSONA_SLUG` env. Loader reads `docs/prompts/persona/<slug>.yaml` and validates. Memory layer uses ChromaDB collection `persona_memory_<slug>` (auto-create on first run). Reasoner daily uses Flash, weekly uses Pro per the routing matrix. Output validator enforces the disclaimer rule and `AdviceV1` validation. Tests cover loader-on-malformed-yaml (boot fails), disclaimer-missing (validator rejects), memory retrieval ordering (most-recent + most-similar mixed).

🧪 **Persona base prompt template (`packages/prompts/registry/persona.daily.base/1.0.0.md`):**
> *System:* You are reasoning AS {{ display_name }} would, drawing on your public writings and interviews. Style: {{ priors | join(", ") }}.
> Prior decisions you've made on similar setups (most recent first): {{ memory_excerpts }}.
> Today's intelligence digest events relevant to your style: {{ relevant_events }}.
> Universe constraint: {{ universe_filter }}.
> Output one or zero `advice.v1` JSON objects. If no setup meets your standards today, output an empty list with a one-line explanation. Always end your thesis with this exact disclaimer line: "{{ disclaimer }}".

🧪 **Style audit harness:**
> Build `tests/test_style_classifier.py` per §5.6. For each persona, sample 20 historical advices from `lake.advice` (or fixtures pre-runs). Pro-as-judge rubric: (1) reads like the persona's voice, (2) cites at least one of the persona's known principles, (3) avoids forbidden moves listed in the YAML. Mean score < 4.0 fails. Add a CLI `python -m persona.style_audit --slug rogers --window 30d`.

---

## 8. Acceptance Criteria

- [ ] `pytest apps/agent_persona -q` is green for every persona's loader + validator.
- [ ] Boot the container with `PERSONA_SLUG=rogers`; `GET /health` returns `{slug:"rogers", ...}`.
- [ ] On a real `intel.digest.v1`, each of the 8 personas emits ≤ 1 advice.
- [ ] Every emitted advice has the disclaimer string verbatim from the YAML.
- [ ] An adversarial test that strips the disclaimer in the LLM mock causes the validator to quarantine the advice (no publish).
- [ ] Style audit returns mean score ≥ 4.0 across all 8 personas on a 30-day sample.
- [ ] After a `backtest.fill.v1` is consumed, the persona's memory contains a `lesson` entry referencing the fill outcome.
- [ ] Weekly run uses Pro (verified via `lake.llm_calls.tier`).

---

## 9. Risks & Gotchas

⚠️ **Impersonation drift.** The model may slip into "I am Jim Rogers." The disclaimer rule + style audit + prompt instruction together hold the line; don't relax any of them.

⚠️ **Memory pollution.** Bad advice gets stored as memory and influences future runs. Mitigation: tag memories with the eventual `pnl_r`; retrieval down-weights losing memories with `pnl_r < -1`.

⚠️ **Universe filter too aggressive.** If Rogers's filter excludes everything for a week, the agent emits zero advice — which is fine. But monitor: `advices_emitted_7d == 0` is alert-worthy after the first month, suggesting the filter is broken.

⚠️ **Pro cost concentration on weekly Sunday.** All 8 personas hitting Pro on Sunday could spike cost. Stagger the weekly cron across days.

⚠️ **Memory growth.** Each persona accumulates memory forever by default. The YAML's `retain_days` enforces a soft expiry; lessons (high-value entries) are exempt.

⚠️ **Lookalike-persona tension with brand/legal.** We're stylizing public figures. Stay defensive: never quote them verbatim, never claim authorship. The disclaimer + the YAML's `guardrails` enforce this.

⚠️ **Memory retrieval staleness vs. recency.** Pure cosine retrieval can return 5-year-old memories that no longer match current conditions. Combine cosine with a recency boost (`score = cos_sim * (0.5 + 0.5 * exp(-days/365))`).

⚠️ **Adding a new persona later.** New persona → new YAML, new ChromaDB collection, new container instance via `docker-compose.override.yml`. Backtester picks up the new agent automatically because it consumes `advice.persona.>` wildcard.

---

## 10. Cross-References

- Roster slugs referenced everywhere: this doc is the source of truth.
- Backtest feedback subscription: `14_AGENT_BACKTEST.md` §5 publishes per-agent fills.
- Persona YAML lives in `docs/prompts/persona/`, registered by `04_PROMPT_REGISTRY.md` §2.3.
- Disclaimer line is mirrored in `advice.v1` schema validation in `05_DATA_BUS_AND_SCHEMAS.md` §3.

---

## Changelog

- **v1.0** — Extracted from `PLAN_v2.1` §4.4. Style-audit CI gate added; memory retrieval recency boost specified.
