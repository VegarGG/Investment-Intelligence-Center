"""plan.v1 — team-level trade plan envelope (v2.5 T2.2 / B3.2).

The Investment Board (T2.4) reads `plan.v1` envelopes from analysis teams
(quant, fundamental, persona, intel). Each team aggregates 1+ `advice.v1`
records into one `plan.v1` per trigger event per ticker.

This is **additive** to `advice.v1` — agents continue emitting AdviceV1
for backward compat; teams emit PlanV1 on top. Backtest grades both.

Hard validators (per plan §T2.2):
- entry_window_close > entry_window_open.
- For action=buy: target_price > entry_price > stop_loss.
- For action=sell: stop_loss > entry_price > target_price.
- For action=hold: evidence may be empty; price ordering is relaxed.
- max_drawdown_pct in [0, 100].
- horizon_days in [1, 365].
- evidence non-empty unless action=hold.
- disclaimer mandatory when team='persona'.
- expires_at > issued_at and ≤ 365d after.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Literal

import ulid
from pydantic import BaseModel, Field, field_validator, model_validator

from .advice import Asset, Evidence

Team = Literal["quant", "fundamental", "persona", "intel"]
Action = Literal["buy", "sell", "hold"]

_ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
_MAX_HORIZON_DAYS = 365


class PortfolioContextV1(BaseModel):
    """Minimal portfolio slice attached to a plan (FUTU-derived per T2.7).

    The full PortfolioSnapshotV1 ships in T2.7; this is the subset a Plan
    needs at the moment its team writes it.
    """

    current_position_pct_nav: float = Field(ge=-100.0, le=100.0, default=0.0)
    open_orders_count: int = Field(ge=0, default=0)
    cost_basis_per_share: float | None = Field(default=None, ge=0.0)
    base_currency: str = "USD"


class PlanV1(BaseModel):
    """Team-level trade plan envelope (per plan §T2.2)."""

    schema_version: Literal["plan.v1"] = Field(default="plan.v1", alias="schema")
    id: str
    team: Team
    persona_slug: str | None = None
    issued_at: datetime
    asset: Asset
    action: Action
    entry_price: float = Field(ge=0.0)
    entry_window_open: datetime
    entry_window_close: datetime
    target_price: float = Field(ge=0.0)
    stop_loss: float = Field(ge=0.0)
    max_drawdown_pct: float = Field(ge=0.0, le=100.0)
    horizon_days: int = Field(ge=1, le=_MAX_HORIZON_DAYS)
    sizing_pct_nav: float = Field(ge=0.0, le=100.0)
    confidence: float = Field(ge=0.0, le=1.0)
    thesis: str = Field(max_length=4000)
    evidence: list[Evidence] = Field(default_factory=list)
    portfolio_context: PortfolioContextV1 | None = None
    expires_at: datetime
    disclaimer: str | None = None

    model_config = {"populate_by_name": True}

    @field_validator("id")
    @classmethod
    def _id_is_ulid(cls, v: str) -> str:
        if not _ULID_RE.match(v):
            raise ValueError(f"id must be a ULID; got {v!r}")
        try:
            ulid.ULID.from_str(v)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"id={v!r} fails ulid.ULID.from_str: {exc}") from exc
        return v

    @model_validator(mode="after")
    def _entry_window_monotone(self) -> "PlanV1":
        if self.entry_window_close <= self.entry_window_open:
            raise ValueError(
                "entry_window_close must be strictly after entry_window_open"
            )
        return self

    @model_validator(mode="after")
    def _action_price_ordering(self) -> "PlanV1":
        if self.action == "buy":
            if not (self.target_price > self.entry_price > self.stop_loss):
                raise ValueError(
                    f"buy requires target_price > entry_price > stop_loss; "
                    f"got target={self.target_price}, entry={self.entry_price}, stop={self.stop_loss}"
                )
        elif self.action == "sell":
            if not (self.stop_loss > self.entry_price > self.target_price):
                raise ValueError(
                    f"sell requires stop_loss > entry_price > target_price; "
                    f"got target={self.target_price}, entry={self.entry_price}, stop={self.stop_loss}"
                )
        # action=hold relaxes the ordering — the plan is "stay flat"; the
        # team may still cite a target / stop for reference.
        return self

    @model_validator(mode="after")
    def _evidence_required_unless_hold(self) -> "PlanV1":
        if self.action != "hold" and not self.evidence:
            raise ValueError("evidence is required when action != 'hold'")
        return self

    @model_validator(mode="after")
    def _persona_team_requires_persona_slug(self) -> "PlanV1":
        if self.team == "persona" and not (self.persona_slug or "").strip():
            raise ValueError("team='persona' requires persona_slug")
        if self.team != "persona" and self.persona_slug:
            raise ValueError(
                f"team={self.team!r} must not set persona_slug (got {self.persona_slug!r})"
            )
        return self

    @model_validator(mode="after")
    def _persona_team_requires_disclaimer(self) -> "PlanV1":
        if self.team == "persona" and not (self.disclaimer or "").strip():
            raise ValueError(
                "team='persona' must include a non-empty disclaimer (workflow 13 §6 ethics rule)"
            )
        return self

    @model_validator(mode="after")
    def _expiry_within_one_year(self) -> "PlanV1":
        delta = self.expires_at - self.issued_at
        if delta <= timedelta(0):
            raise ValueError(f"expires_at must be after issued_at (got delta={delta})")
        if delta > timedelta(days=_MAX_HORIZON_DAYS):
            raise ValueError(
                f"expires_at - issued_at must be <= {_MAX_HORIZON_DAYS}d "
                f"(got {delta.days}d)"
            )
        return self
