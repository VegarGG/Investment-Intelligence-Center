"""WeCom user-id whitelist (workflow 15 §2.6)."""

from __future__ import annotations

import os


def allowed_users() -> set[str]:
    raw = os.environ.get("SECRETARY_ALLOWED_USERS", "")
    return {u.strip() for u in raw.split(",") if u.strip()}


def is_allowed(user_id: str, *, allowed: set[str] | None = None) -> bool:
    allowed = allowed or allowed_users()
    return user_id in allowed
