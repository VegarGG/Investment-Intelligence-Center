"""v2.5 T2.2 / B3.2 — plan.v1 schema acceptance.

≥ 30 unit tests covering every validator's positive + negative path,
plus the goldens-set sanity check at the end.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError
from schema import Asset, Evidence, PlanV1, PortfolioContextV1


def _base_kwargs(**over):
    when = datetime(2026, 5, 8, 13, 0, tzinfo=UTC)
    out: dict = {
        "id": "01HX8E5G7M0000000000000001",
        "team": "quant",
        "issued_at": when,
        "asset": Asset(kind="equity", ticker="AAPL", venue="NASDAQ"),
        "action": "buy",
        "entry_price": 200.0,
        "entry_window_open": when + timedelta(minutes=30),
        "entry_window_close": when + timedelta(hours=8),
        "target_price": 220.0,
        "stop_loss": 190.0,
        "max_drawdown_pct": 8.0,
        "horizon_days": 30,
        "sizing_pct_nav": 2.5,
        "confidence": 0.65,
        "thesis": "Momentum + earnings beat",
        "evidence": [Evidence(kind="factor", ref="momentum")],
        "expires_at": when + timedelta(days=30),
    }
    out.update(over)
    return out


# --------------------------------------------------------------- positive paths
def test_buy_plan_validates():
    p = PlanV1(**_base_kwargs())
    assert p.team == "quant"
    assert p.action == "buy"


def test_sell_plan_validates():
    when = datetime(2026, 5, 8, 13, 0, tzinfo=UTC)
    p = PlanV1(**_base_kwargs(
        action="sell",
        entry_price=200.0,
        target_price=180.0,
        stop_loss=210.0,
    ))
    assert p.action == "sell"


def test_hold_plan_with_empty_evidence():
    p = PlanV1(**_base_kwargs(
        action="hold",
        entry_price=200.0,
        target_price=200.0,
        stop_loss=200.0,
        evidence=[],
        sizing_pct_nav=0.0,
        max_drawdown_pct=0.0,
    ))
    assert p.action == "hold"
    assert p.evidence == []


def test_persona_team_with_disclaimer():
    p = PlanV1(**_base_kwargs(
        team="persona",
        persona_slug="rogers",
        disclaimer="Stylized agent; not Mr. Rogers.",
    ))
    assert p.team == "persona"
    assert p.persona_slug == "rogers"


def test_intel_team_validates():
    p = PlanV1(**_base_kwargs(team="intel"))
    assert p.team == "intel"


def test_fundamental_team_validates():
    p = PlanV1(**_base_kwargs(team="fundamental"))
    assert p.team == "fundamental"


def test_portfolio_context_attaches():
    p = PlanV1(**_base_kwargs(
        portfolio_context=PortfolioContextV1(
            current_position_pct_nav=3.5, open_orders_count=1,
            cost_basis_per_share=180.0, base_currency="USD",
        )
    ))
    assert p.portfolio_context.current_position_pct_nav == 3.5


def test_max_horizon_365_passes():
    p = PlanV1(**_base_kwargs(horizon_days=365))
    assert p.horizon_days == 365


def test_evidence_with_url_passes():
    p = PlanV1(**_base_kwargs(
        evidence=[Evidence(kind="filing", ref="10-Q", url="https://sec.gov/x")]
    ))
    assert p.evidence[0].url == "https://sec.gov/x"


def test_schema_alias_round_trip():
    p = PlanV1(**_base_kwargs())
    j = p.model_dump(by_alias=True)
    assert j["schema"] == "plan.v1"
    PlanV1.model_validate(j)


# --------------------------------------------------------------- negative paths
def test_buy_with_target_below_entry_fails():
    with pytest.raises(ValidationError) as exc:
        PlanV1(**_base_kwargs(target_price=190.0))
    assert "target_price > entry_price > stop_loss" in str(exc.value)


def test_buy_with_stop_above_entry_fails():
    with pytest.raises(ValidationError):
        PlanV1(**_base_kwargs(stop_loss=210.0))


def test_sell_with_target_above_entry_fails():
    with pytest.raises(ValidationError) as exc:
        PlanV1(**_base_kwargs(
            action="sell", target_price=210.0, stop_loss=220.0
        ))
    assert "stop_loss > entry_price > target_price" in str(exc.value)


def test_sell_with_stop_below_entry_fails():
    with pytest.raises(ValidationError):
        PlanV1(**_base_kwargs(action="sell", target_price=180.0, stop_loss=190.0))


def test_buy_evidence_empty_fails():
    with pytest.raises(ValidationError) as exc:
        PlanV1(**_base_kwargs(evidence=[]))
    assert "evidence is required" in str(exc.value)


def test_persona_without_slug_fails():
    with pytest.raises(ValidationError) as exc:
        PlanV1(**_base_kwargs(team="persona", disclaimer="x"))
    assert "persona_slug" in str(exc.value)


def test_persona_without_disclaimer_fails():
    with pytest.raises(ValidationError) as exc:
        PlanV1(**_base_kwargs(team="persona", persona_slug="rogers"))
    assert "disclaimer" in str(exc.value)


def test_non_persona_with_persona_slug_fails():
    with pytest.raises(ValidationError) as exc:
        PlanV1(**_base_kwargs(team="quant", persona_slug="rogers"))
    assert "must not set persona_slug" in str(exc.value)


def test_entry_window_inverted_fails():
    when = datetime(2026, 5, 8, 13, 0, tzinfo=UTC)
    with pytest.raises(ValidationError) as exc:
        PlanV1(**_base_kwargs(
            entry_window_open=when + timedelta(hours=2),
            entry_window_close=when,
        ))
    assert "entry_window_close" in str(exc.value)


def test_entry_window_equal_fails():
    when = datetime(2026, 5, 8, 13, 0, tzinfo=UTC)
    with pytest.raises(ValidationError):
        PlanV1(**_base_kwargs(
            entry_window_open=when, entry_window_close=when,
        ))


def test_max_drawdown_above_100_fails():
    with pytest.raises(ValidationError):
        PlanV1(**_base_kwargs(max_drawdown_pct=120.0))


def test_max_drawdown_negative_fails():
    with pytest.raises(ValidationError):
        PlanV1(**_base_kwargs(max_drawdown_pct=-5.0))


def test_horizon_zero_fails():
    with pytest.raises(ValidationError):
        PlanV1(**_base_kwargs(horizon_days=0))


def test_horizon_above_365_fails():
    with pytest.raises(ValidationError):
        PlanV1(**_base_kwargs(horizon_days=400))


def test_confidence_above_one_fails():
    with pytest.raises(ValidationError):
        PlanV1(**_base_kwargs(confidence=1.5))


def test_confidence_negative_fails():
    with pytest.raises(ValidationError):
        PlanV1(**_base_kwargs(confidence=-0.1))


def test_sizing_above_100_fails():
    with pytest.raises(ValidationError):
        PlanV1(**_base_kwargs(sizing_pct_nav=150.0))


def test_id_not_ulid_fails():
    with pytest.raises(ValidationError) as exc:
        PlanV1(**_base_kwargs(id="not-a-ulid"))
    assert "id must be a ULID" in str(exc.value)


def test_expires_before_issued_fails():
    when = datetime(2026, 5, 8, 13, 0, tzinfo=UTC)
    with pytest.raises(ValidationError) as exc:
        PlanV1(**_base_kwargs(expires_at=when - timedelta(days=1)))
    assert "expires_at must be after issued_at" in str(exc.value)


def test_expires_more_than_365_after_fails():
    when = datetime(2026, 5, 8, 13, 0, tzinfo=UTC)
    with pytest.raises(ValidationError):
        PlanV1(**_base_kwargs(expires_at=when + timedelta(days=400)))


def test_team_invalid_fails():
    with pytest.raises(ValidationError):
        PlanV1(**_base_kwargs(team="bogus"))


def test_action_invalid_fails():
    with pytest.raises(ValidationError):
        PlanV1(**_base_kwargs(action="long"))  # plan.v1 uses buy/sell/hold


def test_entry_price_negative_fails():
    with pytest.raises(ValidationError):
        PlanV1(**_base_kwargs(entry_price=-1.0))


# --------------------------------------------------------------- goldens
from featureflags.paths import repo_root as _repo_root  # noqa: E402

GOLDENS_PATH = _repo_root() / "tests" / "fixtures" / "plan_v1_examples.json"


def test_goldens_set_loads_and_validates():
    raw = json.loads(GOLDENS_PATH.read_text())
    examples = raw["examples"]
    assert len(examples) >= 4
    seen_teams = set()
    for ex in examples:
        plan = PlanV1.model_validate(ex)
        seen_teams.add(plan.team)
    # Expect at least one (team, action) per major team.
    assert {"quant", "fundamental", "persona", "intel"}.issubset(seen_teams)
