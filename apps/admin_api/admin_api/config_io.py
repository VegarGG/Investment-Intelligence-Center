"""Read/write the YAML configuration files behind the admin UI (P3.1).

Files allowed to be edited via the API are whitelisted by path so a typo
on the wire can't write to an unrelated file. Every write goes through a
two-step ``propose -> apply`` flow:

  1. ``propose(path, body)`` validates the body is YAML and returns the
     ``before_hash`` + ``after_hash`` so the UI can show a diff and the
     user can confirm.
  2. ``apply(path, body, actor, reason)`` writes the file atomically and
     appends a row to ``lake.config_audit``.

Writes happen via temp-file-then-rename so a half-written YAML never
becomes the source of truth for any agent reading the file mid-flight.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from featureflags.paths import repo_root

# Whitelist of (rel-path-prefix, semantic-name) pairs the UI can edit.
EDITABLE_PATHS: tuple[tuple[str, str], ...] = (
    ("docs/prompts/persona/", "personas"),
    ("packages/featureflags/flags.yaml", "featureflags"),
    ("infra/intel/", "intel-config"),
    ("infra/cron/schedules.yaml", "schedules"),
    ("infra/quant/watchlist.yaml", "watchlist"),
    ("infra/notifier/preferences.yaml", "notifier"),
    ("infra/futu/brokers.yaml", "brokers"),
)


@dataclass(frozen=True, slots=True)
class FileSnapshot:
    path: Path
    content: str
    sha256: str


def _hash(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _is_editable(rel_path: str) -> bool:
    rel_path = rel_path.lstrip("/")
    for prefix, _ in EDITABLE_PATHS:
        if prefix.endswith("/") and rel_path.startswith(prefix):
            return True
        if rel_path == prefix:
            return True
    return False


def _abs_path(rel_path: str) -> Path:
    if not _is_editable(rel_path):
        raise PermissionError(f"path not editable via admin API: {rel_path}")
    p = (repo_root() / rel_path.lstrip("/")).resolve()
    if not p.is_relative_to(repo_root()):
        raise PermissionError(f"path escapes repo root: {rel_path}")
    return p


def read(rel_path: str) -> FileSnapshot:
    """Return the current snapshot of a YAML file."""
    p = _abs_path(rel_path)
    content = p.read_text() if p.is_file() else ""
    return FileSnapshot(path=p, content=content, sha256=_hash(content.encode("utf-8")))


def propose(rel_path: str, new_content: str) -> dict[str, Any]:
    """Validate the proposed YAML and report before/after hashes."""
    try:
        yaml.safe_load(new_content)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML: {exc}") from exc
    current = read(rel_path)
    return {
        "path": str(current.path.relative_to(repo_root())),
        "before_sha256": current.sha256,
        "after_sha256": _hash(new_content.encode("utf-8")),
        "size_bytes": len(new_content.encode("utf-8")),
    }


def apply(rel_path: str, new_content: str) -> FileSnapshot:
    """Write the new YAML atomically. Returns the after-snapshot.

    Callers are responsible for emitting the ``lake.config_audit`` row
    (see ``audit.append``) — this function only owns the file write.
    """
    try:
        yaml.safe_load(new_content)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML: {exc}") from exc
    target = _abs_path(rel_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        delete=False,
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    ) as tmp:
        tmp.write(new_content)
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, target)
    return FileSnapshot(
        path=target,
        content=new_content,
        sha256=_hash(new_content.encode("utf-8")),
    )


def editable_paths() -> Iterable[tuple[str, str]]:
    """Return the editable-file whitelist for the UI."""
    return EDITABLE_PATHS
