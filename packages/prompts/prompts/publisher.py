"""Append-only publisher (workflow 04 §6.7, §4 footer).

On import the package walks `packages/prompts/registry/` and writes each
`(caller_id, version)` to `/srv/iic/prompts_versioned/<caller_id>/
<version>__<sha>.md`. If a previously-published `(caller_id, version)`
now resolves to a different SHA, publish() raises ImmutablePromptError —
that's how §2.4 ("a change with no version bump fails CI") is enforced
beyond the CI job in `prompt-eval.yml`.

In dev environments where /srv/iic isn't writable, the publisher logs a
warning and is a no-op — agents can still import normally.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from .exceptions import ImmutablePromptError

log = logging.getLogger(__name__)

PUBLISHED_ROOT = Path(os.environ.get("PROMPTS_PUBLISHED_ROOT", "/srv/iic/prompts_versioned"))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _published_path(root: Path, caller_id: str, version: str, sha: str) -> Path:
    return root / caller_id / f"{version}__{sha}.md"


def _existing_versions(root: Path, caller_id: str, version: str) -> list[Path]:
    """Files matching <version>__*.md for this caller. Empty if not yet published."""
    parent = root / caller_id
    if not parent.exists():
        return []
    return sorted(parent.glob(f"{version}__*.md"))


def persist(
    caller_id: str, version: str, source_text: str, *, root: Path | None = None
) -> Path | None:
    """Persist source_text under (caller_id, version). Idempotent.

    Returns the path written (or the existing path on no-op), or None if the
    publish root isn't writable (dev mode).

    Raises ImmutablePromptError if (caller_id, version) was previously
    published with a different SHA — i.e. someone changed the file without
    bumping the version.
    """
    target_root = root or PUBLISHED_ROOT
    if not _root_is_writable(target_root):
        log.debug("publish skipped — %s is not writable (dev mode)", target_root)
        return None

    sha = _sha256(source_text)
    existing = _existing_versions(target_root, caller_id, version)

    if existing:
        prior_path = existing[0]
        prior_sha = prior_path.stem.split("__", 1)[1]
        if prior_sha != sha:
            raise ImmutablePromptError(
                f"prompt {caller_id} v{version} was previously published as "
                f"{prior_path.name} (sha={prior_sha}) but the source now hashes "
                f"to {sha}. Bump the version (per workflow 04 §2.4) instead "
                f"of mutating an existing version."
            )
        return prior_path

    target = _published_path(target_root, caller_id, version, sha)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source_text, encoding="utf-8")
    return target


def _root_is_writable(root: Path) -> bool:
    try:
        root.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError):
        return False
    return os.access(root, os.W_OK)
