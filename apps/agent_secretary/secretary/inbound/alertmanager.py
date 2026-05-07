"""Alertmanager → secretary.notify.v1 bridge (workflow 30 §6.5).

Alertmanager POSTs a JSON envelope with one or more alerts. We translate
each into a `SecretaryNotifyV1` event and publish to the bus. The
notifier package owns fanout. Severity in the alert label is honored;
unknown severities collapse to `warn`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

from schema import SecretaryNotifyV1

Severity = Literal["info", "warn", "alert", "critical"]
ChannelHint = Literal["briefs", "alerts", "fills", "chat"]
KNOWN_SEVERITIES: tuple[Severity, ...] = ("info", "warn", "alert", "critical")


@dataclass(slots=True)
class ParsedAlert:
    code: str
    severity: Severity
    summary: str
    runbook: str | None
    status: Literal["firing", "resolved"]
    labels: dict[str, str]


class BadAlertmanagerPayload(ValueError):
    """The webhook envelope is missing required fields."""


def parse_payload(payload: dict[str, Any]) -> list[ParsedAlert]:
    """Validate the Alertmanager envelope and return a list of ParsedAlert."""
    if "alerts" not in payload or not isinstance(payload["alerts"], list):
        raise BadAlertmanagerPayload("envelope missing 'alerts' list")
    out: list[ParsedAlert] = []
    for raw in payload["alerts"]:
        out.append(_parse_one(raw))
    return out


def _parse_one(raw: dict[str, Any]) -> ParsedAlert:
    labels = dict(raw.get("labels") or {})
    annotations = dict(raw.get("annotations") or {})
    code = labels.get("code") or labels.get("alertname") or "UNKNOWN"
    severity_raw = labels.get("severity", "warn").lower()
    severity: Severity = severity_raw if severity_raw in KNOWN_SEVERITIES else "warn"
    status_raw = raw.get("status", "firing")
    status: Literal["firing", "resolved"] = "resolved" if status_raw == "resolved" else "firing"
    return ParsedAlert(
        code=code,
        severity=severity,
        summary=annotations.get("summary", code),
        runbook=annotations.get("runbook"),
        status=status,
        labels=labels,
    )


def render(alert: ParsedAlert) -> SecretaryNotifyV1:
    """Build a `secretary.notify.v1` event from one ParsedAlert."""
    prefix = "[FIRING]" if alert.status == "firing" else "[RESOLVED]"
    bullets = [f"- code: `{alert.code}`", f"- severity: `{alert.severity}`"]
    if alert.runbook:
        bullets.append(f"- runbook: {alert.runbook}")
    extra_labels = {
        k: v for k, v in alert.labels.items() if k not in ("severity", "code", "alertname")
    }
    if extra_labels:
        labels_md = ", ".join(f"`{k}={v}`" for k, v in sorted(extra_labels.items()))
        bullets.append(f"- labels: {labels_md}")
    body = f"**{prefix} {alert.summary}**\n\n" + "\n".join(bullets)
    channel_hint: ChannelHint = "alerts"
    return SecretaryNotifyV1(
        severity=alert.severity,
        channel_hint=channel_hint,
        markdown=body,
        language="en",
    )


def render_all(alerts: Iterable[ParsedAlert]) -> list[SecretaryNotifyV1]:
    return [render(a) for a in alerts]
