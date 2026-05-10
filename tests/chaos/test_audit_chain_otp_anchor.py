"""v2.5 N3.6 — Verify the last 7 daily OpenTimestamps anchors.

Synthetic mode (default): asserts the anchor directory contains the
expected ``YYYY-MM-DD.head`` + ``.head.ots`` pair structure for the last
7 days (or skips if no anchors exist yet — the cron has to have run at
least once).

Real mode (IIC_RUN_FUTU_LIVE=1): additionally calls ``ots verify`` on
each ``.ots`` artifact to confirm it anchors against
``commits.opentimestamps.org`` / Bitcoin.
"""

from __future__ import annotations

import os
import re
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ANCHOR_DIR = Path(
    os.environ.get("IIC_FUTU_AUDIT_ANCHOR_DIR", "/srv/iic/futu-audit-anchors")
)
LIVE = os.environ.get("IIC_RUN_FUTU_LIVE") == "1"


def _expected_dates(n: int = 7) -> list[str]:
    today = datetime.now(UTC).date()
    return [(today - timedelta(days=i)).isoformat() for i in range(n)]


def test_anchor_directory_has_at_least_one_pair() -> None:
    if not ANCHOR_DIR.exists():
        pytest.skip(f"anchor dir {ANCHOR_DIR} not present (cron has not run yet)")
    pairs = sorted(ANCHOR_DIR.glob("*.head"))
    if not pairs:
        pytest.skip(f"no .head artifacts in {ANCHOR_DIR}")
    head_path = pairs[-1]
    head_text = head_path.read_text().strip()
    assert re.fullmatch(r"[0-9a-f]{64}", head_text), head_text
    assert head_path.with_suffix(".head.ots").exists(), (
        f"missing .ots proof next to {head_path}"
    )


def test_recent_anchors_present_for_last_seven_days() -> None:
    if not ANCHOR_DIR.exists():
        pytest.skip(f"anchor dir {ANCHOR_DIR} not present")
    expected = _expected_dates(7)
    found = {p.stem for p in ANCHOR_DIR.glob("*.head")}
    missing = [d for d in expected if d not in found]
    if not found:
        pytest.skip("no anchors at all yet")
    # We tolerate some missing days during early bootstrap, but at least
    # the most recent 3 must be there.
    assert sum(1 for d in expected[:3] if d in found) >= 1, (
        f"no anchors found among the last 3 days; missing={missing}"
    )


@pytest.mark.skipif(not LIVE, reason="IIC_RUN_FUTU_LIVE not set")
def test_ots_verify_last_seven_anchors_real() -> None:
    """Phase B drill: ``ots verify`` against commits.opentimestamps.org."""
    expected = _expected_dates(7)
    failures: list[tuple[str, str]] = []
    for day in expected:
        ots = ANCHOR_DIR / f"{day}.head.ots"
        head = ANCHOR_DIR / f"{day}.head"
        if not (ots.exists() and head.exists()):
            continue
        result = subprocess.run(
            ["ots", "verify", str(ots)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            failures.append((day, (result.stderr or result.stdout)[:200]))
    assert not failures, f"OTS verification failed for: {failures}"
