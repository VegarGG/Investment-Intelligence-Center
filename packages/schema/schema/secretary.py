"""secretary.* event schemas (workflow 05 §4.6)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["info", "warn", "alert", "critical"]
ChannelHint = Literal["briefs", "alerts", "fills", "chat"]


class SecretaryNotifyV1(BaseModel):
    """Outbound notification request the secretary fans to packages/notifier."""

    schema_version: Literal["secretary.notify.v1"] = Field(
        default="secretary.notify.v1", alias="schema"
    )
    severity: Severity = "info"
    channel_hint: ChannelHint = "alerts"
    language: Literal["en", "zh"] = "en"
    markdown: str = Field(max_length=4096)
    mentioned_list: list[str] | None = None

    model_config = {"populate_by_name": True}
