"""Workflow 20 §6 — severity → channel routing."""

from __future__ import annotations

from notifier.router import severity_to_channels
from notifier.types import Severity


class _Stub:
    def __init__(self, name: str) -> None:
        self.name = name

    async def send(self, _notification) -> None:
        return None


def _adapters(*names: str) -> dict[str, _Stub]:
    return {n: _Stub(n) for n in names}


def test_info_starts_with_wecom_then_cascade() -> None:
    plan = severity_to_channels(
        Severity.INFO,
        by_name=_adapters("wecom_bot", "serverchan", "ntfy", "smtp"),
    )
    assert [a.name for a in plan.primary] == ["wecom_bot"]
    assert [a.name for a in plan.fallbacks] == ["serverchan", "ntfy", "smtp"]
    assert plan.parallel is False


def test_warn_uses_same_chain_as_info() -> None:
    plan = severity_to_channels(
        Severity.WARN, by_name=_adapters("wecom_bot", "serverchan", "ntfy", "smtp")
    )
    assert plan.primary[0].name == "wecom_bot"


def test_alert_fans_wecom_plus_serverchan_first() -> None:
    plan = severity_to_channels(
        Severity.ALERT,
        by_name=_adapters("wecom_bot", "serverchan", "ntfy", "smtp"),
    )
    assert {a.name for a in plan.primary} == {"wecom_bot", "serverchan"}
    assert [a.name for a in plan.fallbacks] == ["ntfy", "smtp"]


def test_critical_runs_all_four_in_parallel() -> None:
    plan = severity_to_channels(
        Severity.CRITICAL,
        by_name=_adapters("wecom_bot", "serverchan", "ntfy", "smtp"),
    )
    assert plan.parallel is True
    assert {a.name for a in plan.primary} == {"wecom_bot", "serverchan", "ntfy", "smtp"}


def test_missing_wecom_falls_back_gracefully() -> None:
    plan = severity_to_channels(Severity.INFO, by_name=_adapters("serverchan", "smtp"))
    assert [a.name for a in plan.primary] == ["serverchan"]
    assert [a.name for a in plan.fallbacks] == ["smtp"]
