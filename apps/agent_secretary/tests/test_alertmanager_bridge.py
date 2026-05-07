"""Workflow 30 §6.5 — Alertmanager → SecretaryNotifyV1 bridge."""

from __future__ import annotations

import pytest
from secretary.inbound.alertmanager import (
    BadAlertmanagerPayload,
    parse_payload,
    render,
    render_all,
)


def _alert(
    *,
    code: str,
    severity: str,
    summary: str,
    runbook: str | None = None,
    status: str = "firing",
) -> dict:
    labels = {"alertname": code, "code": code, "severity": severity}
    annotations = {"summary": summary}
    if runbook:
        annotations["runbook"] = runbook
    return {"labels": labels, "annotations": annotations, "status": status}


def test_parse_payload_returns_one_per_alert() -> None:
    payload = {
        "alerts": [
            _alert(code="HOST_DOWN", severity="critical", summary="node down"),
            _alert(code="DISK_FREE_LOW", severity="warn", summary="<15% free"),
        ]
    }
    parsed = parse_payload(payload)
    assert len(parsed) == 2
    assert parsed[0].code == "HOST_DOWN"
    assert parsed[0].severity == "critical"
    assert parsed[1].severity == "warn"


def test_unknown_severity_collapses_to_warn() -> None:
    payload = {"alerts": [_alert(code="X", severity="banana", summary="??")]}
    parsed = parse_payload(payload)
    assert parsed[0].severity == "warn"


def test_resolved_status_preserved() -> None:
    payload = {"alerts": [_alert(code="X", severity="warn", summary="ok", status="resolved")]}
    assert parse_payload(payload)[0].status == "resolved"


def test_bad_payload_rejected() -> None:
    with pytest.raises(BadAlertmanagerPayload):
        parse_payload({"not": "alerts"})


def test_render_emits_secretary_notify_with_runbook_link() -> None:
    parsed = parse_payload(
        {
            "alerts": [
                _alert(
                    code="ADVICE_LEDGER_BROKEN",
                    severity="critical",
                    summary="chain integrity broken",
                    runbook="docs/runbooks/runbook-advice-ledger-broken.md",
                )
            ]
        }
    )[0]
    notify = render(parsed)
    assert notify.severity == "critical"
    assert notify.channel_hint == "alerts"
    assert "ADVICE_LEDGER_BROKEN" in notify.markdown
    assert "runbook-advice-ledger-broken.md" in notify.markdown


def test_render_all_handles_empty_list() -> None:
    assert render_all([]) == []
