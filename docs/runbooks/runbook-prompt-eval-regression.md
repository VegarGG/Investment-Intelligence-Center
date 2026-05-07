# Runbook — PROMPT_EVAL_REGRESSION

`last_verified: 2026-05-07`

## What it means

The weekly drift watch found a caller's mean rubric score dropped >10%
versus its 4-week rolling baseline. The prompt is regressing — quality is
slipping faster than the noise floor.

## Likely causes (most → least likely)

1. Prompt template edit landed without a version bump.
2. Provider model swap (DeepSeek pushed a silent v4.1 update).
3. Judge prompt itself drifted (rare; quarterly audit catches this).
4. Golden-set fixtures stale and no longer reflect production needs.

## First-look checks (≤ 2 min)

- Grafana → IIC-006-Eval → "Mean rubric score" panel for the affected
  caller, last 12 weeks.
- `SELECT prompt_version, mean_score FROM lake.eval_runs WHERE caller_id = '<id>' ORDER BY ts DESC LIMIT 8;`
- Diff the registry: `git log -p packages/prompts/registry/<caller>/`.

## Resolution paths

- Path A — version regression: roll back to the prior version in the
  registry and bump the caller's resolution.
- Path B — provider drift: pin the model id in the routing matrix
  (`packages/llm-client/llm_client/_matrix.py`) to a snapshot date.
- Path C — judge audit needed: open a quarterly review issue per
  `workflows/31_PRODUCTION_HARDENING.md` §4.

## Verification

- Next weekly run posts a `mean_score` within 5% of baseline.
- `regression_flag` flips to false.

## Postmortem hook

If the regression caused user-visible quality drop, open a postmortem.
