"""Workflow 05 §3 + workflow 13 §6 — persona disclaimer rule.

Defense-in-depth: the persona prompt template embeds the disclaimer
instruction (workflow 04 §9 gotcha 6); this validator catches anything
that slips through.
"""

from __future__ import annotations

from typing import Any

import pytest
from schema.advice import AdviceV1


class TestPersonaDisclaimerRequired:
    def test_persona_rogers_without_disclaimer_rejected(self, good_long: dict[str, Any]) -> None:
        good_long["agent"] = "persona.rogers"
        with pytest.raises(ValueError, match="disclaimer"):
            AdviceV1.model_validate(good_long)

    def test_persona_with_empty_string_disclaimer_rejected(self, good_long: dict[str, Any]) -> None:
        good_long["agent"] = "persona.buffett"
        good_long["disclaimer"] = "   "
        with pytest.raises(ValueError, match="disclaimer"):
            AdviceV1.model_validate(good_long)

    def test_persona_with_disclaimer_ok(self, good_long: dict[str, Any]) -> None:
        good_long["agent"] = "persona.soros"
        good_long["disclaimer"] = "Stylized agent inspired by public writings; not Mr. Soros."
        adv = AdviceV1.model_validate(good_long)
        assert adv.agent == "persona.soros"

    def test_non_persona_agent_disclaimer_optional(self, good_long: dict[str, Any]) -> None:
        # fundamental, quant, etc. don't need a disclaimer.
        good_long["agent"] = "fundamental"
        good_long.pop("disclaimer", None)
        adv = AdviceV1.model_validate(good_long)
        assert adv.disclaimer is None

    @pytest.mark.parametrize(
        "slug",
        ["rogers", "buffett", "soros", "druckenmiller", "wood", "dalio", "burry", "degen"],
    )
    def test_every_persona_slug_enforced(self, good_long: dict[str, Any], slug: str) -> None:
        good_long["agent"] = f"persona.{slug}"
        good_long.pop("disclaimer", None)
        with pytest.raises(ValueError, match="disclaimer"):
            AdviceV1.model_validate(good_long)
