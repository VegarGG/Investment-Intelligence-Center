"""ntfy adapter (workflow 20 §7.4). Self-hosted on the LAN; no auth."""

from __future__ import annotations

import os

import httpx

from ..types import Notification
from .base import AdapterDown


class NtfyAdapter:
    name = "ntfy"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        topic_prefix: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        resolved_url = base_url or os.environ.get("NTFY_BASE_URL") or "http://ntfy:80"
        self._base_url = resolved_url.rstrip("/")
        self._prefix = topic_prefix or os.environ.get("NTFY_TOPIC_PREFIX", "iic")
        self._client = client

    async def send(self, notification: Notification) -> None:
        topic = f"{self._prefix}-{notification.channel_hint.value}"
        url = f"{self._base_url}/{topic}"
        priority = self._priority_header(notification.severity.value)
        client = self._client or httpx.AsyncClient(timeout=5.0)
        owns = self._client is None
        try:
            try:
                resp = await client.post(
                    url,
                    content=notification.markdown.encode("utf-8"),
                    headers={
                        "Content-Type": "text/markdown; charset=utf-8",
                        "Title": "IIC",
                        "Priority": priority,
                    },
                )
            except httpx.HTTPError as exc:
                raise AdapterDown(f"ntfy transport: {exc}") from exc
            if resp.status_code >= 500:
                raise AdapterDown(f"ntfy {resp.status_code}")
        finally:
            if owns:
                await client.aclose()

    @staticmethod
    def _priority_header(severity: str) -> str:
        return {
            "info": "default",
            "warn": "high",
            "alert": "high",
            "critical": "urgent",
        }.get(severity, "default")
