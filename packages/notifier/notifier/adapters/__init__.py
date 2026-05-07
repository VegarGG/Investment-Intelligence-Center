"""Adapter implementations (workflow 20 §7)."""

from .base import Adapter, AdapterDown, AdapterRateLimit, AdapterRejected
from .ntfy import NtfyAdapter
from .serverchan import ServerChanAdapter
from .smtp import SmtpAdapter
from .wecom_app import WeComAppAdapter
from .wecom_bot import WeComBotAdapter

__all__ = [
    "Adapter",
    "AdapterDown",
    "AdapterRateLimit",
    "AdapterRejected",
    "WeComBotAdapter",
    "WeComAppAdapter",
    "ServerChanAdapter",
    "NtfyAdapter",
    "SmtpAdapter",
]
