"""SMTP email adapter (workflow 20 §7.5).

Last-resort outbound. Subject mirrors severity + channel_hint. The HTML
body is the markdown rendered via a tiny converter — avoids pulling a
markdown→HTML dependency for what amounts to a fallback channel.
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Protocol

from ..types import Notification
from .base import AdapterDown, AdapterRejected


class SmtpClient(Protocol):
    def send_message(self, msg: EmailMessage) -> dict[str, tuple[int, bytes]]: ...


class SmtpAdapter:
    name = "smtp"

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        sender: str | None = None,
        recipient: str | None = None,
        client_factory: object | None = None,
    ) -> None:
        self._host: str = host or os.environ.get("SMTP_HOST", "") or ""
        self._port = port or int(os.environ.get("SMTP_PORT", "587"))
        self._user = user or os.environ.get("SMTP_USER", "")
        self._password = password or os.environ.get("SMTP_PASSWORD", "")
        self._sender = sender or os.environ.get("SMTP_FROM", "")
        self._recipient = recipient or os.environ.get("SMTP_TO", "")
        self._client_factory = client_factory  # tests inject

    async def send(self, notification: Notification) -> None:
        if not (self._host and self._sender and self._recipient):
            raise AdapterRejected("smtp: missing host/from/to")
        msg = self._build_message(notification)
        try:
            client = self._open_client()
            try:
                client.send_message(msg)
            finally:
                close = getattr(client, "quit", None) or getattr(client, "close", None)
                if close:
                    close()
        except (OSError, smtplib.SMTPException) as exc:
            raise AdapterDown(f"smtp transport: {exc}") from exc

    def _build_message(self, n: Notification) -> EmailMessage:
        msg = EmailMessage()
        msg["Subject"] = f"[IIC {n.severity.value}/{n.channel_hint.value}]"
        msg["From"] = self._sender
        msg["To"] = self._recipient
        msg.set_content(n.markdown)  # plain-text fallback
        msg.add_alternative(_markdown_to_html(n.markdown), subtype="html")
        return msg

    def _open_client(self) -> SmtpClient:
        if self._client_factory is not None:
            stub: SmtpClient = self._client_factory()  # type: ignore[operator]
            return stub
        smtp = smtplib.SMTP(self._host, self._port, timeout=10)
        smtp.starttls()
        if self._user and self._password:
            smtp.login(self._user, self._password)
        return smtp


def _markdown_to_html(text: str) -> str:
    """Tiny inline converter — preserves `**bold**`, headings, line breaks.

    Good enough for an SMTP fallback; richer rendering belongs in a real
    markdown library if/when SMTP becomes a primary channel.
    """
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("# "):
            out.append(f"<h1>{_escape(s[2:])}</h1>")
        elif s.startswith("## "):
            out.append(f"<h2>{_escape(s[3:])}</h2>")
        elif s.startswith("- "):
            out.append(f"<li>{_escape(s[2:])}</li>")
        else:
            out.append(f"<p>{_escape(s)}</p>")
    return "<html><body>" + "\n".join(out) + "</body></html>"


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
