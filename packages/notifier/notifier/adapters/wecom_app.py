"""WeCom self-built app adapter (workflow 20 §7.2).

Used for direct messages to a specific user (Secretary chat replies).
Token caching is keyed by `(corp_id, agent_id)` and refreshed lazily on
401/expiry.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import httpx

from .. import markdown_normalizer
from ..types import Notification
from .base import AdapterDown, AdapterRejected

TOKEN_URL = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"  # noqa: S105 — public endpoint
SEND_URL = "https://qyapi.weixin.qq.com/cgi-bin/message/send"
TOKEN_TTL_S = 7000  # WeCom returns 7200 — keep slack


class WeComAppAdapter:
    name = "wecom_app"

    def __init__(
        self,
        *,
        corp_id: str | None = None,
        agent_id: str | None = None,
        secret: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._corp_id = corp_id or os.environ.get("WECOM_CORP_ID", "")
        self._agent_id = agent_id or os.environ.get("WECOM_AGENT_ID", "")
        self._secret = secret or os.environ.get("WECOM_APP_SECRET", "")
        self._client = client
        self._token: str | None = None
        self._token_fetched_at: float = 0.0
        self._token_lock = asyncio.Lock()

    async def send(self, notification: Notification) -> None:
        if not notification.target_user:
            raise AdapterRejected("wecom_app requires Notification.target_user")
        if notification.channel_hint.value != "chat":
            raise AdapterRejected("wecom_app only handles channel_hint='chat'")
        if not (self._corp_id and self._agent_id and self._secret):
            raise AdapterRejected("wecom_app missing corp_id/agent_id/app_secret")

        token = await self._access_token()
        body: dict[str, Any] = {
            "touser": notification.target_user,
            "msgtype": "markdown",
            "agentid": self._agent_id,
            "markdown": {
                "content": markdown_normalizer.clean(
                    notification.markdown, language=notification.language
                )
            },
        }
        client = self._client or httpx.AsyncClient(timeout=10.0)
        owns = self._client is None
        try:
            try:
                resp = await client.post(SEND_URL, params={"access_token": token}, json=body)
            except httpx.HTTPError as exc:
                raise AdapterDown(f"wecom_app transport: {exc}") from exc
            if resp.status_code >= 500:
                raise AdapterDown(f"wecom_app {resp.status_code}")
            if resp.status_code >= 400:
                raise AdapterRejected(f"wecom_app {resp.status_code}: {resp.text[:200]}")
        finally:
            if owns:
                await client.aclose()

    async def _access_token(self) -> str:
        if self._token and (time.monotonic() - self._token_fetched_at) < TOKEN_TTL_S:
            return self._token
        async with self._token_lock:
            if self._token and (time.monotonic() - self._token_fetched_at) < TOKEN_TTL_S:
                return self._token
            client = self._client or httpx.AsyncClient(timeout=10.0)
            owns = self._client is None
            try:
                resp = await client.get(
                    TOKEN_URL,
                    params={"corpid": self._corp_id, "corpsecret": self._secret},
                )
                if resp.status_code != 200:
                    raise AdapterDown(f"wecom_app token http {resp.status_code}")
                payload = resp.json()
                token = payload.get("access_token")
                if not isinstance(token, str) or not token:
                    raise AdapterDown(f"wecom_app token: {payload}")
                self._token = token
                self._token_fetched_at = time.monotonic()
                return token
            finally:
                if owns:
                    await client.aclose()
