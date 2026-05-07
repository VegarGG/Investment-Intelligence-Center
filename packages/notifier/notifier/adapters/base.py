"""Adapter ABC + shared exceptions (workflow 20 §4)."""

from __future__ import annotations

from typing import Protocol

from ..types import Notification


class AdapterDown(Exception):
    """The adapter's transport is unreachable — router should cascade."""


class AdapterRateLimit(Exception):
    """The adapter hit a per-second / per-minute cap. Router cascades."""


class AdapterRejected(Exception):
    """Provider returned a 4xx that won't succeed on retry — surface up."""


class Adapter(Protocol):
    name: str

    async def send(self, notification: Notification) -> None: ...
