"""CLI wrapper around walk_forward.WalkForwardHarness (v2.5 T1.12).

Used by `.github/workflows/walk-forward.yml`. Reads a JSONL fixture file
of historical advice (kept under `apps/agent_backtest/fixtures/`) and
produces a delta report at the path given to `--out`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from backtest.walk_forward import (
    WalkForwardHarness,
    compare,
    replay_from_jsonl,
    write_report,
)


def _default_fixture() -> Path:
    # parent.parent = apps/agent_backtest (this file is at
    # apps/agent_backtest/backtest/walk_forward_cli.py). Intra-package
    # sibling resolution — not a repo-root walk, so no repo_root() call.
    return Path(__file__).resolve().parent.parent / "fixtures" / "historical_advice.jsonl"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Walk-forward delta runner.")
    parser.add_argument("--baseline", default="HEAD~1")
    parser.add_argument("--candidate", default="HEAD")
    parser.add_argument("--fixture", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=Path("walk_forward.json"))
    args = parser.parse_args(argv)

    fixture = args.fixture or _default_fixture()
    if not fixture.exists():
        # CI runs without a fixture should pass the gate (no advice → no delta).
        print(f"no fixture at {fixture} — trivially passing", file=sys.stderr)
        args.out.write_text(
            json.dumps({"materially_negative": False, "reason": "no fixture"}, indent=2)
        )
        return 0

    history = replay_from_jsonl(fixture)
    harness = WalkForwardHarness(history=history)

    baseline = harness.run(prompt_version=args.baseline)
    candidate = harness.run(prompt_version=args.candidate)
    delta = compare(baseline, candidate)

    write_report(delta, out_dir=args.out.parent)
    args.out.write_text(json.dumps(delta.summary(), indent=2, default=str))

    print(json.dumps(delta.summary(), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# Re-exposed so `python -m backtest.walk_forward_cli` works under poetry.
if os.environ.get("WALK_FORWARD_CLI_AS_MODULE") == "1":
    raise SystemExit(main())
