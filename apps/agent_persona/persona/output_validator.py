"""Output validator (workflow 13 §5.5)."""

from __future__ import annotations

from schema import AdviceV1

from .types import PersonaSpec


class DisclaimerMismatch(ValueError):
    """The advice's disclaimer doesn't match the persona's YAML."""


class WrongAgent(ValueError):
    """advice.agent must be `persona.<slug>`."""


def validate(advice: AdviceV1, *, spec: PersonaSpec) -> None:
    expected_agent = f"persona.{spec.slug}"
    if advice.agent != expected_agent:
        raise WrongAgent(f"advice.agent={advice.agent!r}, expected {expected_agent!r}")
    if (advice.disclaimer or "").strip() != spec.disclaimer.strip():
        raise DisclaimerMismatch(f"persona {spec.slug}: disclaimer must match YAML verbatim")
