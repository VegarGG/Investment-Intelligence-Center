# Workflow 04 — Prompt Registry

> **Depends On:** `02_DATA_LAYER.md`, `03_LLM_CLIENT.md`.
> **Owns:** `packages/prompts/` — versioned prompt storage, persona YAMLs, golden eval set, drift detection, CI gates.
> **Status:** Final.

---

## 1. Purpose

Treat prompts like code: version them, diff them, gate changes on regression tests. Every prompt that ships a real LLM call:

1. Lives in `packages/prompts/registry/<caller_id>/<semver>.md`.
2. Has a frontmatter block declaring caller, model tier, and the schema of variables it expects.
3. Is materialized at runtime by the `prompts` library — callers ask `get("fund.valuation")`, never read files directly.
4. Is mirrored to `/srv/iic/prompts_versioned/` (append-only) so historical prompts can be replayed exactly.
5. Has at least three entries in the golden eval set, scored by Pro-as-judge, with a regression alarm if scores drop > 10%.

This is what stops the system from silently degrading because someone tweaked a prompt.

---

## 2. Ground Truth

### 2.1 File layout

```
packages/prompts/
├── pyproject.toml
├── prompts/
│   ├── __init__.py
│   ├── registry.py            # public surface: get(caller_id, **vars)
│   ├── frontmatter.py         # parses the YAML header
│   ├── render.py              # variable substitution
│   ├── publisher.py           # writes to /srv/iic/prompts_versioned on import
│   ├── eval/
│   │   ├── golden_set.yaml    # 60 prompts, ground-truth answers, rubrics
│   │   ├── runner.py
│   │   └── judge.py           # Pro-as-judge scoring
│   └── registry/
│       ├── intel.synth/
│       │   ├── 1.0.0.md
│       │   └── 1.1.0.md
│       ├── fund.valuation/
│       │   └── 1.0.0.md
│       ├── ... (one folder per caller_id)
└── tests/
    ├── test_frontmatter.py
    ├── test_render.py
    ├── test_eval_smoke.py
    └── test_versioning_gate.py
```

### 2.2 Prompt file format

```markdown
---
caller_id: intel.synth
version: 1.0.0
tier: pro
description: Chief intelligence officer — distills 24 h news into the digest
variables:
  - name: events_json
    type: string
    required: true
  - name: macro_regime
    type: string
    required: false
    default: "unknown"
expected_output_schema: intel.digest.v1
---
You are the chief intelligence officer for a personal investment desk.

From the candidate event list (provided as JSON), select the 25–35 events
that most plausibly affect liquid markets in the next 30 days. For each, emit
{rank, headline, why_it_matters_2_sentences, primary_asset_links,
regime_change_score 0-1, novelty 0-1}. Penalize duplicates. Reward
cross-source confirmation. End with one paragraph titled "Today's macro
thesis."

Macro regime hint (may be wrong): {{ macro_regime }}

Candidate events:
```json
{{ events_json }}
```
```

### 2.3 Persona files (separate from prompts)

Persona files use the same registry mechanic but live in `docs/prompts/persona/<slug>.yaml`. Format defined in `13_AGENT_PERSONA.md` §3. The registry treats them as data; the persona agent composes the runtime prompt by combining persona YAML + a base prompt template.

### 2.4 Versioning rules

- **SemVer** on the `version:` frontmatter.
- **Patch (1.0.0 → 1.0.1):** typo fixes, no behavior change. Eval scores must not regress > 1%.
- **Minor (1.0.0 → 1.1.0):** wording change that may shift outputs. Eval scores must not regress > 5%.
- **Major (1.0.0 → 2.0.0):** restructured ask, different output schema. Eval scores can change freely; new golden answers required.
- A change with no version bump fails CI.

### 2.5 Active version selection

`packages/prompts/registry.py:get(caller_id)` returns the **highest version with `status: stable`** in the frontmatter. Versions can be `stable | beta | deprecated`. Beta versions are addressable by explicit version: `get("intel.synth", version="1.2.0-beta")`.

---

## 3. Public Surface

```python
# packages/prompts/prompts/registry.py

from pydantic import BaseModel
from typing import Any

class RenderedPrompt(BaseModel):
    caller_id: str
    version: str
    tier: str                    # 'flash' | 'pro' | 'embed'
    system: str | None
    user: str
    raw_template_path: str

def get(
    caller_id: str,
    *,
    version: str | None = None,
    **variables: Any,
) -> RenderedPrompt: ...
```

Callers do:
```python
from prompts.registry import get
from llm_client.router import chat
from llm_client.types import ChatMessage

prompt = get("fund.valuation", ticker="INTC", peers=peers)
resp = await chat(
    caller_id="fund.valuation",
    messages=[ChatMessage(role="system", content=prompt.system),
              ChatMessage(role="user", content=prompt.user)],
)
```

---

## 4. Architecture

```
        callers ──────┐
                      ▼
           prompts.registry.get()
                      │
                      ▼
         frontmatter.parse() ── render.substitute()
                      │
                      ▼
              RenderedPrompt
                      │
                      ▼
           publisher.persist()  → /srv/iic/prompts_versioned/<caller>/<sha>.md
                      │
                      ▼
          (passed to llm_client.chat)
```

`publisher.persist()` is idempotent and append-only: same `(caller_id, version)` pair never overwrites; if the source file changes without a version bump, an exception is raised at import time. This is what enforces §2.4.

---

## 5. Eval Harness

### 5.1 Golden set

`prompts/eval/golden_set.yaml` (60 entries). Format:

```yaml
- id: intel.synth.001
  caller_id: intel.synth
  inputs:
    events_json: |
      [{"id":"e1","title":"Fed cuts 25 bp","source":"reuters",...}, ...]
    macro_regime: "rate_cut"
  rubric:
    - "Names the rate cut as the top event"
    - "Identifies USD weakness as a likely transmission"
    - "regime_change_score for top item is >= 0.7"
  reference_answer_excerpt: |
    1. {"rank":1,"headline":"Fed cuts 25 bp ..."} ...
```

The harness does not require an exact reference answer — it uses Pro-as-judge with the rubric. Scores 0–1 per rubric item, averaged.

### 5.2 Runner

```python
# prompts/eval/runner.py
async def run(
    caller_id: str | None = None,           # filter; None = all callers
    version: str | None = None,             # filter; None = current stable
    tier_override: str | None = None,
    snapshot_dir: Path | None = None,
) -> EvalReport: ...
```

Outputs `EvalReport` with per-prompt score, per-caller mean, regression vs. last passing run.

### 5.3 Judge

`prompts/eval/judge.py` calls DeepSeek-V4-Pro (or fallback) with a fixed judge prompt. The judge prompt itself is versioned (`prompts/registry/eval.judge/1.0.0.md`) — its drift would invalidate the entire harness, so it is locked except by explicit major-version bump signed off by Ziwei.

### 5.4 CI gate

`.github/workflows/prompt-eval.yml`:
1. Runs on PRs that touch `packages/prompts/registry/`.
2. Detects bumped versions; for each, runs the eval against the new version + the previous stable.
3. Compares mean scores. Fail if regression exceeds the band defined by the bump kind (§2.4).
4. Posts a comment on the PR with the per-rubric diff.

### 5.5 Weekly drift watch

A scheduled job (cron in `01_INFRASTRUCTURE_AND_HOST.md` §5.2 systemd timer) runs the full golden set against current stable versions every Monday. Regression > 10% emits `ops.alert.v1` to the WeCom alerts bot.

---

## 6. Workflow Steps

### Step 6.1 — Stub the package and parser

`frontmatter.py` parses YAML between `---` delimiters; `render.py` does Jinja2-style variable substitution. Reject prompts where required variables aren't passed.

### Step 6.2 — Implement `registry.get()`

- Walk `packages/prompts/registry/<caller_id>/`.
- Pick the highest `status: stable` version.
- Parse frontmatter, validate variables, render.
- Persist a hash-named copy to `/srv/iic/prompts_versioned/<caller_id>/<version>__<sha>.md` (idempotent).

### Step 6.3 — Author seed prompts

Create stable v1.0.0 prompts for every caller listed in the §2 routing matrix of `03_LLM_CLIENT.md`. Each is sourced from a `🧪 VIBE-PROMPT` block in the corresponding agent's workflow doc — when an agent doc has a vibe prompt for an LLM call, that prompt goes here, with frontmatter.

Initial seed list (each gets one `1.0.0.md`):
- `intel.synth`, `intel.crawler.translate`, `intel.sentiment.classify`
- `fund.valuation`, `fund.writer`, `fund.filings.extract`
- `quant.writer`
- `persona.daily.base` (per-persona files override sections)
- `persona.weekly.base`
- `backtest.narrate`
- `secretary.chat`, `secretary.brief.morning`, `secretary.deep_explain`
- `orchestrator.plan`
- `eval.judge` (the judge prompt itself)

### Step 6.4 — Author the golden set

60 entries, distributed roughly 8/8/4/8/8/4/8/12 across the 8 caller groups above. Each entry has 3–6 rubric items.

### Step 6.5 — Implement runner + judge

Runner replays each entry through `llm_client.chat` with `force_tier` set per the caller's matrix. Judge scores via DeepSeek Pro.

### Step 6.6 — Wire CI

Two GitHub Actions:

1. `.github/workflows/prompt-eval.yml` — gates PRs that touch the registry.
2. `.github/workflows/prompt-drift-weekly.yml` — Monday at 09:00 PT, runs full eval, posts to WeCom alerts on regression.

### Step 6.7 — Wire the publisher

On agent boot, `prompts.registry` walks the registry and writes any new versions to `/srv/iic/prompts_versioned/`. Verifies that nothing previously published has been mutated (file diff ≠ 0 with same path → fatal).

---

## 7. Vibe Prompts (paste-ready)

🧪 **Build the package:**
> Implement `packages/prompts/` per `04_PROMPT_REGISTRY.md`. `registry.get(caller_id, version=None, **vars)` returns a `RenderedPrompt`. Frontmatter schema enforced by Pydantic v2. Render uses Jinja2 with `StrictUndefined`. Publisher writes to `/srv/iic/prompts_versioned/` and refuses to overwrite. Tests cover: missing required var → raises; unknown caller → raises; version mismatch → raises; persistence is idempotent.

🧪 **Eval runner:**
> Build `prompts/eval/runner.py` and `judge.py` per §5. Runner accepts `caller_id`, `version`, `tier_override`, `snapshot_dir`. Judge calls Pro with the locked judge prompt (`prompts/registry/eval.judge/1.0.0.md`). Output `EvalReport` is a Pydantic model serializable to JSON. Add a CLI `python -m prompts.eval.runner --caller intel.synth --against-version 1.0.0` that prints a table.

🧪 **CI gates:**
> Author `.github/workflows/prompt-eval.yml` (PR gate) and `prompt-drift-weekly.yml` (Monday). Both use the runner. PR gate compares mean rubric scores between the bumped version and the previous stable; fails per the §2.4 bands. Weekly posts a Markdown summary to the WeCom alerts bot via `packages/notifier/`.

🧪 **Seed the registry:**
> For every `🧪 VIBE-PROMPT` block in workflow docs 10–15 and 03/06, author a corresponding `<caller_id>/1.0.0.md` in `packages/prompts/registry/`. Frontmatter must declare `caller_id`, `tier` (matching the routing matrix), `variables`, `expected_output_schema` where applicable. Status defaults to `stable`. Add 3–6 golden eval entries per prompt in `prompts/eval/golden_set.yaml`.

---

## 8. Acceptance Criteria

- [ ] `pytest packages/prompts -q` is green.
- [ ] `python -m prompts.eval.runner --caller intel.synth` runs end-to-end against real DeepSeek and prints a per-rubric table.
- [ ] Editing `packages/prompts/registry/intel.synth/1.0.0.md` without bumping the version fails the publisher import (`ImmutablePromptError`).
- [ ] PR that bumps a prompt version triggers `prompt-eval.yml`; regression > the band fails the build.
- [ ] `/srv/iic/prompts_versioned/` shows one entry per caller_id × version × hash.
- [ ] Weekly drift cron has run at least once and posted (or no-opped) without errors.
- [ ] Golden set has ≥ 60 entries; coverage report shows ≥ 3 entries per active caller.

---

## 9. Risks & Gotchas

⚠️ **Pro-as-judge bias.** Pro can favor verbose answers. Rubrics must be specific (e.g., "Names a numeric stop-loss") not vague ("Answer is high quality").

⚠️ **Determinism.** Set `temperature=0` for the judge prompt. Replay-able. For evaluated prompts, use the temperature they'd use in production — testing at `t=0` masks real-world variance.

⚠️ **Persona prompts overlap.** Persona daily/weekly prompts have a base template + per-persona override. Don't duplicate; use Jinja2 `{% include %}` or compose at runtime in the persona agent.

⚠️ **Cost of weekly eval.** 60 prompts × DeepSeek Pro judge ≈ ~$0.40–$0.80 per run. Budget for it in `LLM_MONTHLY_CAP_USD`.

⚠️ **Snapshot-dir pollution.** When `snapshot_dir` is passed, every (request, response) pair is written. Useful for debugging but big — gitignore the directory.

⚠️ **Persona disclaimer must be in the prompt.** Don't rely on post-hoc validators alone — embed the disclaimer instruction in the persona prompt itself. The validator (in `13_AGENT_PERSONA.md` §6) is defense-in-depth.

⚠️ **Frontmatter drift.** If you add a new frontmatter field (e.g., `max_tokens`), update the parser, the test fixtures, and every existing prompt in one PR. Otherwise old prompts silently fail validation.

---

## 10. Cross-References

- Routing matrix that callers reference: `03_LLM_CLIENT.md` §2.
- Persona YAML format (separate from prompts but related): `13_AGENT_PERSONA.md` §3.
- WeCom alerts bot used by drift watcher: `20_NOTIFIER_WECHAT.md`.
- Eval harness in dashboards: `30_OBSERVABILITY_AND_EVAL.md` §4.

---

## Changelog

- **v1.0** — Extracted from `PLAN_v2.1` §5 (prompt management) + §14 (eval). Versioning rules formalized; CI gates specified; persona file format cross-referenced rather than duplicated.
