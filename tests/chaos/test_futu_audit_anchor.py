"""v2.5 N3.0c — futu-audit-anchor.sh produces a verifiable .ots artifact.

This is a synthetic-environment drill: we stub `psql` and `ots` so the
script exercises its own control flow without needing a live Postgres
or the real `commits.opentimestamps.org` server. The B3.3b real
integration (with live OTS) lives in `tests/penetration/` and is gated
on `IIC_RUN_FUTU_LIVE=1`.

What this test guards:
  - Script exits 0 on the happy path.
  - A `.head` file with a hex chain head lands under the anchor dir.
  - A `.ots` artifact lands next to it (we fake `ots stamp` to write one).
  - Missing PG_DSN → exit 2; missing `ots` binary → exit 3.
"""

from __future__ import annotations

import os
import re
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ANCHOR_SH = REPO_ROOT / "infra/linux/scripts/futu-audit-anchor.sh"


@pytest.fixture
def fake_bin_dir(tmp_path: Path) -> Path:
    """Make a directory of fake `psql` and `ots` shell executables."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    psql = bin_dir / "psql"
    psql.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            # Fake psql: returns a fixed sha256 hex (64 chars).
            echo "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
            """
        )
    )
    psql.chmod(0o755)

    ots = bin_dir / "ots"
    ots.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            # Fake ots: when called as `ots stamp <file>` write <file>.ots.
            if [ "$1" = "stamp" ] && [ -n "$2" ]; then
              printf "fake-ots-proof-for-%s\\n" "$2" > "$2.ots"
              exit 0
            fi
            exit 0
            """
        )
    )
    ots.chmod(0o755)
    return bin_dir


def _run_anchor(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(ANCHOR_SH)],
        env=env,
        capture_output=True,
        text=True,
    )


def test_anchor_writes_head_and_ots_on_happy_path(
    tmp_path: Path,
    fake_bin_dir: Path,
) -> None:
    anchor_dir = tmp_path / "anchors"
    env = {
        **os.environ,
        "PATH": f"{fake_bin_dir}:{os.environ.get('PATH', '')}",
        "IIC_FUTU_AUDIT_ANCHOR_DIR": str(anchor_dir),
        "IIC_PG_DSN_RO": "postgres://fake/dsn",
    }
    result = _run_anchor(env)
    assert result.returncode == 0, result.stderr

    heads = list(anchor_dir.glob("*.head"))
    assert len(heads) == 1, f"expected one .head file, got {heads}"
    head_text = heads[0].read_text().strip()
    assert re.fullmatch(r"[0-9a-f]{64}", head_text), head_text

    ots_files = list(anchor_dir.glob("*.head.ots"))
    assert len(ots_files) == 1, f"expected one .ots artifact, got {ots_files}"


def test_anchor_exits_2_when_dsn_missing(
    tmp_path: Path,
    fake_bin_dir: Path,
) -> None:
    env = {
        # Wipe inherited DSN env so the script fails closed.
        "PATH": f"{fake_bin_dir}:/usr/bin:/bin",
        "IIC_FUTU_AUDIT_ANCHOR_DIR": str(tmp_path / "anchors"),
    }
    result = _run_anchor(env)
    assert result.returncode == 2, (result.returncode, result.stderr)


def test_anchor_exits_3_when_ots_missing(tmp_path: Path) -> None:
    # Provide psql but not ots.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    psql = bin_dir / "psql"
    psql.write_text("#!/usr/bin/env bash\necho deadbeef\n")
    psql.chmod(0o755)

    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "IIC_FUTU_AUDIT_ANCHOR_DIR": str(tmp_path / "anchors"),
        "IIC_PG_DSN_RO": "postgres://fake/dsn",
    }
    result = _run_anchor(env)
    assert result.returncode == 3, (result.returncode, result.stderr)
