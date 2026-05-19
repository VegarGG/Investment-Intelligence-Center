"""Connector test / status helpers for the Settings → Connectors page (P3.4).

Each connector has:
  - name           — DeepSeek / Anthropic / Groq / OpenAI / FRED / NewsAPI /
                     GDELT / Tushare / FUTU OpenD / WeCom
  - status         — derived from sealed-secret presence + last test
  - test()         — async live handshake; returns ConnectorStatus

Most of these are 1-shot test pings. They are intentionally cheap (a
single GET with a 5 s timeout) so the UI's "Test" button feels snappy.
We never store the secret in this module — fetch it on demand from the
sealed-secret store and let the OS GC the plaintext.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Literal

import httpx
import yaml

from . import secrets

ConnectorState = Literal["ok", "error", "unconfigured"]


@dataclass(frozen=True, slots=True)
class ConnectorStatus:
    name: str
    state: ConnectorState
    detail: str | None = None


def _read_plaintext(name: str) -> str | None:
    p = secrets._enc_path(name)  # noqa: SLF001 — intentional
    if not p.is_file():
        return None
    try:
        raw = subprocess.check_output(["sops", "-d", str(p)], timeout=10)
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    try:
        doc = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        return None
    val = doc.get("value")
    return str(val) if val else None


async def test_deepseek() -> ConnectorStatus:
    key = _read_plaintext("deepseek_api_key") or os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        return ConnectorStatus(name="deepseek", state="unconfigured")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://api.deepseek.com/v1/models",
                headers={"Authorization": f"Bearer {key}"},
            )
            if resp.status_code == 200:
                return ConnectorStatus(name="deepseek", state="ok", detail="models endpoint 200")
            return ConnectorStatus(name="deepseek", state="error", detail=f"http {resp.status_code}")
    except httpx.HTTPError as exc:
        return ConnectorStatus(name="deepseek", state="error", detail=str(exc))


async def test_anthropic() -> ConnectorStatus:
    key = _read_plaintext("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return ConnectorStatus(name="anthropic", state="unconfigured")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                },
            )
            # The 400 from a GET still proves auth is working — 401 fails it.
            if resp.status_code in (200, 400, 405):
                return ConnectorStatus(name="anthropic", state="ok", detail="auth accepted")
            return ConnectorStatus(name="anthropic", state="error", detail=f"http {resp.status_code}")
    except httpx.HTTPError as exc:
        return ConnectorStatus(name="anthropic", state="error", detail=str(exc))


async def test_fred() -> ConnectorStatus:
    key = _read_plaintext("fred_api_key") or os.environ.get("FRED_API_KEY")
    if not key:
        return ConnectorStatus(name="fred", state="unconfigured")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"https://api.stlouisfed.org/fred/series?series_id=GS10&api_key={key}&file_type=json"
            )
            if resp.status_code == 200:
                return ConnectorStatus(name="fred", state="ok", detail="GS10 lookup 200")
            return ConnectorStatus(name="fred", state="error", detail=f"http {resp.status_code}")
    except httpx.HTTPError as exc:
        return ConnectorStatus(name="fred", state="error", detail=str(exc))


async def test_gdelt() -> ConnectorStatus:
    # No auth needed; ping lastupdate.txt.
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("http://data.gdeltproject.org/gdeltv2/lastupdate.txt")
            if resp.status_code == 200:
                return ConnectorStatus(name="gdelt", state="ok", detail="lastupdate 200")
            return ConnectorStatus(name="gdelt", state="error", detail=f"http {resp.status_code}")
    except httpx.HTTPError as exc:
        return ConnectorStatus(name="gdelt", state="error", detail=str(exc))


async def test_connector(name: str) -> ConnectorStatus:
    handlers = {
        "deepseek": test_deepseek,
        "anthropic": test_anthropic,
        "fred": test_fred,
        "gdelt": test_gdelt,
    }
    handler = handlers.get(name)
    if handler is None:
        return ConnectorStatus(name=name, state="unconfigured", detail="no test handler")
    return await handler()


def known_connectors() -> tuple[str, ...]:
    return ("deepseek", "anthropic", "groq", "openai", "fred", "newsapi", "gdelt", "wecom", "futu")
