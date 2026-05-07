"""WeCom group-bot adapter (workflow 20 §7.1).

POST to webhook URL; retry once on 5xx; raise AdapterDown on hard failure
so the router can cascade.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

from .. import markdown_normalizer
from ..types import Notification
from .base import AdapterDown, AdapterRateLimit, AdapterRejected

WEBHOOK_BASE = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"


class WeComBotAdapter:
    """Sends to the bot whose webhook key matches `notification.channel_hint`."""

    name = "wecom_bot"

    def __init__(
        self,
        *,
        keys: dict[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
        max_retries: int = 1,
    ) -> None:
        self._keys = keys or _keys_from_env()
        self._client = client
        self._max_retries = max_retries

    async def send(self, notification: Notification) -> None:
        channel = notification.channel_hint.value
        if channel == "chat":
            raise AdapterRejected("wecom_bot does not handle 'chat' channel")
        key = self._keys.get(channel)
        if not key:
            raise AdapterRejected(f"no webhook key for channel={channel}")

        body: dict[str, Any] = {
            "msgtype": "markdown",
            "markdown": {
                "content": markdown_normalizer.clean(
                    notification.markdown, language=notification.language
                )
            },
        }
        if notification.mentioned_list:
            body["mentioned_list"] = notification.mentioned_list

        url = f"{WEBHOOK_BASE}?key={key}"
        await self._post_with_retry(url, body)

    async def _post_with_retry(self, url: str, body: dict[str, Any]) -> None:
        client = self._client or httpx.AsyncClient(timeout=10.0)
        owns = self._client is None
        try:
            for attempt in range(self._max_retries + 1):
                try:
                    resp = await client.post(url, json=body)
                except httpx.HTTPError as exc:
                    if attempt == self._max_retries:
                        raise AdapterDown(f"wecom_bot transport: {exc}") from exc
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                if resp.status_code == 429:
                    raise AdapterRateLimit("wecom_bot 429")
                if resp.status_code >= 500:
                    if attempt == self._max_retries:
                        raise AdapterDown(f"wecom_bot {resp.status_code}")
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                if resp.status_code >= 400:
                    raise AdapterRejected(f"wecom_bot {resp.status_code}: {resp.text[:200]}")
                return  # 2xx
        finally:
            if owns:
                await client.aclose()


def _keys_from_env() -> dict[str, str]:
    out = {}
    for channel in ("briefs", "alerts", "fills"):
        key = os.environ.get(f"WECOM_BOT_{channel.upper()}_KEY")
        if key:
            out[channel] = key
    return out
