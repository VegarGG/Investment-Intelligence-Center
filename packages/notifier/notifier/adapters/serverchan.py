"""Server酱 Turbo adapter (workflow 20 §7.3).

POST application/x-www-form-urlencoded to sctapi.ftqq.com. Markdown body
limit ≈32 KB.
"""

from __future__ import annotations

import os

import httpx

from ..types import Notification
from .base import AdapterDown, AdapterRejected

ENDPOINT_TPL = "https://sctapi.ftqq.com/{key}.send"
BODY_LIMIT = 32_000


class ServerChanAdapter:
    name = "serverchan"

    def __init__(
        self,
        *,
        sendkey: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._sendkey = sendkey or os.environ.get("SERVERCHAN_SENDKEY", "")
        self._client = client

    async def send(self, notification: Notification) -> None:
        if not self._sendkey:
            raise AdapterRejected("serverchan: SERVERCHAN_SENDKEY not configured")
        title = self._title(notification)
        body = notification.markdown[:BODY_LIMIT]
        url = ENDPOINT_TPL.format(key=self._sendkey)
        client = self._client or httpx.AsyncClient(timeout=10.0)
        owns = self._client is None
        try:
            try:
                resp = await client.post(
                    url,
                    data={"title": title, "desp": body},
                    headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
                )
            except httpx.HTTPError as exc:
                raise AdapterDown(f"serverchan transport: {exc}") from exc
            if resp.status_code >= 500:
                raise AdapterDown(f"serverchan {resp.status_code}")
            if resp.status_code >= 400:
                raise AdapterRejected(f"serverchan {resp.status_code}: {resp.text[:200]}")
        finally:
            if owns:
                await client.aclose()

    def _title(self, n: Notification) -> str:
        prefix_zh = "【提醒】" if n.severity.value in ("alert", "critical") else "【简报】"
        prefix_en = "[ALERT] " if n.severity.value in ("alert", "critical") else "[BRIEF] "
        prefix = prefix_zh if n.language == "zh" else prefix_en
        first_line = n.markdown.strip().splitlines()[0] if n.markdown.strip() else "IIC"
        # Server酱 title cap is 32 chars in practice.
        body = first_line.lstrip("# ").strip()[:30]
        return f"{prefix}{body}"
