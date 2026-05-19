"""sops-sealed secrets for the admin UI (P3.3).

Layout on disk:

    secrets/sealed/
      deepseek_api_key.yaml.enc
      anthropic_api_key.yaml.enc
      groq_api_key.yaml.enc
      fred_api_key.yaml.enc
      openai_api_key.yaml.enc
      wecom_bot_url.yaml.enc

The plaintext is a tiny YAML doc:
    name: deepseek
    value: sk-...

Reads decrypt via the local sops + age binary chain (the host's age key
must be present; CI uses a per-environment age key). Writes accept
plaintext from the UI, encrypt, then store. The dashboard never sees
the plaintext after the initial paste — subsequent reads return a
``masked`` view (`••••` + last 4 chars) plus a ``rotate`` action.

If sops/age aren't installed (e.g. unit-test environments) the API
returns 503 from the rotate endpoint. Decryption is opt-in via the
``IIC_ADMIN_DECRYPT_SECRETS=1`` env knob.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path

import yaml

from featureflags.paths import repo_root

SEALED_DIR_REL = "secrets/sealed"
KNOWN_SECRETS: tuple[str, ...] = (
    "deepseek_api_key",
    "anthropic_api_key",
    "groq_api_key",
    "openai_api_key",
    "fred_api_key",
    "newsapi_key",
    "wecom_bot_url",
    "futu_opend_password",
)


def _sealed_dir() -> Path:
    return repo_root() / SEALED_DIR_REL


def _enc_path(name: str) -> Path:
    return _sealed_dir() / f"{name}.yaml.enc"


def list_secrets() -> list[dict[str, object]]:
    """Return one row per known secret, with `present=True/False`."""
    out: list[dict[str, object]] = []
    for name in KNOWN_SECRETS:
        p = _enc_path(name)
        out.append(
            {
                "name": name,
                "present": p.is_file(),
                "path": str(p.relative_to(repo_root())) if p.exists() else None,
            }
        )
    return out


def _have_sops() -> bool:
    return shutil.which("sops") is not None


def masked_value(name: str) -> str | None:
    """Decrypt and return ``••••<last4>``. Returns None when sops is
    unavailable or the secret is absent."""
    p = _enc_path(name)
    if not p.is_file() or not _have_sops():
        return None
    if os.environ.get("IIC_ADMIN_DECRYPT_SECRETS", "0") != "1":
        return None
    try:
        raw = subprocess.check_output(["sops", "-d", str(p)], timeout=10)
        doc = yaml.safe_load(raw) or {}
        value = str(doc.get("value", ""))
        if not value:
            return None
        return f"••••{value[-4:]}" if len(value) >= 4 else "••••"
    except subprocess.SubprocessError:
        return None


def rotate(name: str, plaintext: str) -> Path:
    """Write a new sops-encrypted secret. Replaces the existing file."""
    if name not in KNOWN_SECRETS:
        raise ValueError(f"unknown secret {name!r}")
    if not _have_sops():
        raise RuntimeError("sops not installed on this host")
    sealed = _sealed_dir()
    sealed.mkdir(parents=True, exist_ok=True)
    target = _enc_path(name)
    doc = yaml.safe_dump({"name": name, "value": plaintext}, sort_keys=True)
    tmp = sealed / f".{name}.yaml.plain"
    tmp.write_text(doc)
    try:
        # sops -e --output <target> <tmp>
        subprocess.check_call(
            ["sops", "-e", "--output", str(target), str(tmp)],
            timeout=15,
        )
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    return target


def known_secret_names() -> Iterable[str]:
    return KNOWN_SECRETS
