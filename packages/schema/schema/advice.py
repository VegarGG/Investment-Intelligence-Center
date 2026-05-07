"""advice.v1 — the central contract emitted by every advisory agent.

GROUND TRUTH from PLAN_v2.1 §3 / workflow 05 §3. Append-only: adding an
optional field is allowed; renaming, removing, or adding a required field
requires bumping to advice.v2 with a parallel-publish window
(workflow 05 §11).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Literal

import ulid
from pydantic import BaseModel, Field, field_validator, model_validator

AssetKind = Literal["equity", "etf", "future", "option", "fx", "crypto", "bond"]
Direction = Literal["long", "short", "flat"]
EvidenceKind = Literal["news", "filing", "factor", "macro", "social", "filing_url"]

_ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
_MAX_HORIZON_DAYS = 365


class Asset(BaseModel):
    kind: AssetKind
    ticker: str
    venue: str
    name: str | None = None


class Evidence(BaseModel):
    kind: EvidenceKind
    ref: str | None = None
    url: str | None = None


class AdviceV1(BaseModel):
    """The contract every advisory agent emits and the backtester consumes.

    Hard validators (workflow 05 §3):
      - id is a ULID.
      - confidence in [0, 1].
      - entry_band[0] <= entry_band[1].
      - For direction=long:  entry_band[1] < target_band[0] AND stop_loss < entry_band[0].
      - For direction=short: target_band[1] < entry_band[0] AND stop_loss > entry_band[1].
      - For direction=flat:  target_band == entry_band == [px, px], stop_loss ignored.
      - evidence non-empty for direction != flat.
      - expires_at - issued_at <= 365 days.
      - agent.startswith('persona.') => disclaimer non-empty.
    """

    schema_version: Literal["advice.v1"] = Field(default="advice.v1", alias="schema")
    id: str
    agent: str
    issued_at: datetime
    asset: Asset
    thesis: str = Field(max_length=4000)
    direction: Direction
    confidence: float = Field(ge=0.0, le=1.0)
    entry_band: tuple[float, float]
    target_band: tuple[float, float]
    stop_loss: float
    horizon_days: int = Field(ge=1, le=365 * 5)
    max_drawdown_pct: float = Field(ge=0.0, le=100.0)
    sizing_hint_pct_nav: float = Field(ge=0.0, le=100.0)
    expires_at: datetime
    evidence: list[Evidence] = Field(default_factory=list)
    disclaimer: str | None = None

    model_config = {"populate_by_name": True}

    @field_validator("id")
    @classmethod
    def _id_is_ulid(cls, v: str) -> str:
        if not _ULID_RE.match(v):
            raise ValueError(f"id must be a ULID (26 chars, Crockford base32); got {v!r}")
        # Sanity: it parses through python-ulid too (catches valid-looking but
        # out-of-range ULIDs).
        try:
            ulid.ULID.from_str(v)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"id={v!r} fails ulid.ULID.from_str: {exc}") from exc
        return v

    @field_validator("entry_band", "target_band")
    @classmethod
    def _band_ascending(cls, v: tuple[float, float]) -> tuple[float, float]:
        lo, hi = v
        if lo > hi:
            raise ValueError(f"band must be ascending: got ({lo}, {hi})")
        return v

    @model_validator(mode="after")
    def _direction_consistency(self) -> AdviceV1:
        entry_lo, entry_hi = self.entry_band
        target_lo, target_hi = self.target_band

        if self.direction == "long":
            if entry_hi >= target_lo:
                raise ValueError(
                    f"long: entry_band[1]={entry_hi} must be < target_band[0]={target_lo}"
                )
            if self.stop_loss >= entry_lo:
                raise ValueError(
                    f"long: stop_loss={self.stop_loss} must be < entry_band[0]={entry_lo}"
                )
        elif self.direction == "short":
            if target_hi >= entry_lo:
                raise ValueError(
                    f"short: target_band[1]={target_hi} must be < entry_band[0]={entry_lo}"
                )
            if self.stop_loss <= entry_hi:
                raise ValueError(
                    f"short: stop_loss={self.stop_loss} must be > entry_band[1]={entry_hi}"
                )
        else:  # flat
            if not (entry_lo == entry_hi == target_lo == target_hi):
                raise ValueError(
                    "flat: target_band and entry_band must each collapse to a single price"
                )

        return self

    @model_validator(mode="after")
    def _evidence_required_when_directional(self) -> AdviceV1:
        if self.direction != "flat" and not self.evidence:
            raise ValueError(
                "evidence is required for direction != flat — uncited advice is rejected"
            )
        return self

    @model_validator(mode="after")
    def _expiry_within_one_year(self) -> AdviceV1:
        delta = self.expires_at - self.issued_at
        if delta <= timedelta(0):
            raise ValueError(f"expires_at must be after issued_at (got delta={delta})")
        if delta > timedelta(days=_MAX_HORIZON_DAYS):
            raise ValueError(
                f"expires_at - issued_at must be <= {_MAX_HORIZON_DAYS}d " f"(got {delta.days}d)"
            )
        return self

    @model_validator(mode="after")
    def _persona_requires_disclaimer(self) -> AdviceV1:
        if self.agent.startswith("persona.") and not (self.disclaimer or "").strip():
            raise ValueError(
                f"persona agent {self.agent!r} must include a non-empty disclaimer "
                "(workflow 13 §6 ethics rule)"
            )
        return self
