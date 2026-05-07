"""ops.* event schemas (workflow 05 §4.7)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Severity = Literal["warn", "alert", "critical"]


class OpsHeartbeatV1(BaseModel):
    """Per-service heartbeat — every 60s. Keep payload minimal so the OPS
    stream doesn't balloon (workflow 05 §11 risk #4)."""

    schema_version: Literal["ops.heartbeat.v1"] = Field(default="ops.heartbeat.v1", alias="schema")
    service: str
    ts: datetime
    uptime_s: int = Field(ge=0)
    queue_depth: int = Field(ge=0, default=0)
    errors_last_5m: int = Field(ge=0, default=0)

    model_config = {"populate_by_name": True}


class OpsAlertV1(BaseModel):
    """Anomaly raised by any service. The secretary subscribes and forwards
    to the WeCom alerts bot (workflow 20)."""

    schema_version: Literal["ops.alert.v1"] = Field(default="ops.alert.v1", alias="schema")
    severity: Severity = "warn"
    service: str
    code: str
    message: str = Field(max_length=2000)
    context: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}
