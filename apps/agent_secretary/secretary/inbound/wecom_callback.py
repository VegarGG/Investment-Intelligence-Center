"""WeCom inbound callback verification (workflow 15 §5.5).

Production decrypts the WeCom AES-encrypted XML; we focus on the
HMAC-SHA1 signature check which is the first defense and is independent
of the AES key. Real wiring uses `wechatpy` for the full decrypt step.
"""

from __future__ import annotations

import hashlib


def signature(token: str, *, timestamp: str, nonce: str, encrypt: str | None = None) -> str:
    """WeCom signature spec: SHA1 of sorted [token, timestamp, nonce, encrypt]."""
    parts = [token, timestamp, nonce]
    if encrypt is not None:
        parts.append(encrypt)
    parts.sort()
    return hashlib.sha1("".join(parts).encode("utf-8")).hexdigest()  # noqa: S324


def verify(
    *, token: str, timestamp: str, nonce: str, msg_signature: str, encrypt: str | None = None
) -> bool:
    return signature(token, timestamp=timestamp, nonce=nonce, encrypt=encrypt) == msg_signature
