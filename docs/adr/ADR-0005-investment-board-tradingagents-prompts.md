# ADR-0005 — Investment Board prompts adapted from TradingAgents (Apache-2.0)

- **Status:** Accepted
- **Date:** 2026-05-10
- **Plan reference:** `plan/D5_IIC_Prototype_Review_and_Next_Iteration.md` §N3.3 + §N3.8
- **Supersedes:** none
- **Superseded by:** none

## Context

The Investment Board (workflow 43) is the headline of v2.5 N3 — Bull/Bear
research debate, 3-way Risk Panel, and a Chair LLM that picks one plan
and writes a `BoardDecisionV1` per high-impact event. The role-play
debate-then-arbitrate prompt structure is well-explored in the
TradingAgents project (Apache-2.0 license), and reusing the public
prompts as a seed shortcuts months of prompt-engineering experiments.

We needed to decide: (a) write fresh prompts from scratch, (b) seed
from TradingAgents and adapt for IIC's `plan.v1` envelope, or (c)
license-blend with another open multi-agent prompt library (e.g.
AutoGen, CrewAI examples).

## Decision

We **adapt TradingAgents' Apache-2.0 prompts** as the seed for the six
board sub-agents (`board.bull`, `board.bear`, `board.risk_aggressive`,
`board.risk_conservative`, `board.risk_neutral`, `board.chair`).

The IIC adaptations:

1. **Plan envelopes, not free-form theses.** Every prompt receives the
   candidate plans as serialized `PlanV1` envelopes (id, team, action,
   prices, confidence) rather than narrative paragraphs. Chair returns
   strict JSON keyed by `chosen_plan_id` so the deterministic projection
   to `AdviceV1` works without LLM-side parsing surprises.
2. **Cost discipline.** Bull/Bear and Risk panel use `chat_or_skip`
   (DeepSeek Flash); Chair is the only Pro-tier call per board
   decision. Per-decision ceiling: $0.05.
3. **Citation requirement.** Each prompt instructs the LLM to cite
   plan ids; the `_dissent_when_multiple` validator on
   `BoardDecisionV1` rejects empty dissent records when more than one
   plan is considered.
4. **No order-placement language.** Board prompts are scrubbed of any
   verbiage that implies trade execution; the Board recommends one
   plan, the wrapper persists the decision, and that's where the
   suggestion-only chain ends.

## License attribution

- TradingAgents prompts are licensed under Apache-2.0.
- Each `packages/prompts/registry/board.*/1.0.0.md` carries an
  `attribution:` field in its YAML frontmatter pointing back to this ADR.
- A NOTICE entry will be added to the project root before the
  `agent_board` Docker image is published outside this repo.

## Consequences

- We get a battle-tested prompt structure on day 1 of the iteration.
- Future prompt versions (`board.*/2.0.0.md`) may diverge fully — the
  walk-forward CI gate (workflow 33) flags any regression.
- The Apache-2.0 license is permissive enough that downstream
  re-licensing of IIC stays unconstrained provided the NOTICE entry
  is preserved.
- We commit to keeping the attribution metadata up-to-date as prompts
  evolve; CI doesn't currently enforce it but `tests/test_board_prompt_attribution.py`
  is the obvious follow-up if drift becomes a problem.
