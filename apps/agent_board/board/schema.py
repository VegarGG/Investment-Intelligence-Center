"""BoardDecisionV1 — output of the Investment Board (v2.5 N3.3 / T2.4)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


_ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


class BoardDecisionV1(BaseModel):
    """One decision per high-impact event.

    Persisted to ``lake.advice`` under ``agent='board'`` so the same hash
    chain that protects every other agent's advice protects the Board's
    decision too.
    """

    schema_version: Literal["board.decision.v1"] = Field(
        default="board.decision.v1", alias="schema"
    )
    id: str
    trigger_event_id: str
    considered_plan_ids: list[str]
    chosen_plan_id: str
    chair_rationale: str = Field(max_length=4000)
    dissent_record: str = Field(max_length=8000)
    risk_view: str = Field(max_length=4000)
    confidence: float = Field(ge=0.0, le=1.0)
    issued_at: datetime

    model_config = {"populate_by_name": True}

    @field_validator("id")
    @classmethod
    def _id_is_ulid(cls, v: str) -> str:
        if not _ULID_RE.match(v):
            raise ValueError(f"id must be a ULID; got {v!r}")
        return v

    @model_validator(mode="after")
    def _chosen_in_considered(self) -> "BoardDecisionV1":
        if self.chosen_plan_id not in self.considered_plan_ids:
            raise ValueError(
                f"chosen_plan_id={self.chosen_plan_id!r} not in considered_plan_ids"
            )
        return self

    @model_validator(mode="after")
    def _dissent_when_multiple(self) -> "BoardDecisionV1":
        if len(self.considered_plan_ids) > 1 and not self.dissent_record.strip():
            raise ValueError("dissent_record must be non-empty when >1 plans considered")
        return self
