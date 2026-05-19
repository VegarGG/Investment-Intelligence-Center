"""v2.5 T0.2 acceptance — single source of truth for personas.

Fails if any code in the repo references a persona slug that does not
have a `docs/prompts/persona/<slug>.yaml`. The check is a regex sweep
of the codebase + a positive load of the YAML directory; the goal is
to make persona-list drift impossible to merge.
"""

from __future__ import annotations

import re

import pytest

from featureflags.paths import persona_dir, repo_root
from orchestrator.plan.personas import list_persona_slugs

REPO_ROOT = repo_root()
PERSONA_DIR = persona_dir()

# Pattern: things that *look like* persona slug references in code or
# string literals. We intentionally only flag the orchestrator + agent
# packages so this test stays fast and false-positive-free.
SCAN_PATHS = (
    REPO_ROOT / "apps" / "orchestrator",
    REPO_ROOT / "apps" / "agent_persona",
    REPO_ROOT / "apps" / "agent_secretary",
)

# Forbidden hard-codes. Keep this list aligned with the historical drift
# the v2.5 architecture review surfaced.
HARDCODED_TUPLE_RE = re.compile(
    r'"(?P<slug>rogers|buffett|soros|druckenmiller|burry|wood|dalio|retail_degen)"',
    re.MULTILINE,
)


def test_yaml_directory_loads():
    """The source of truth itself must be parseable + non-empty."""
    slugs = list_persona_slugs(force_reload=True)
    assert len(slugs) >= 4, f"expected at least 4 personas, got {slugs}"
    assert len(set(slugs)) == len(slugs), f"duplicate slug: {slugs}"


def test_every_slug_has_a_yaml():
    """Every slug emitted by list_persona_slugs() must correspond to a YAML."""
    yaml_files = {p.stem for p in PERSONA_DIR.glob("*.yaml")}
    for slug in list_persona_slugs(force_reload=True):
        assert slug in yaml_files, f"slug {slug!r} has no docs/prompts/persona/{slug}.yaml"


def test_no_hardcoded_persona_tuple_outside_yaml_dir():
    """No source file may declare a hard-coded persona slug list.

    `morning_brief.py` had one in v2.1; T0.2 forbids it. We detect by
    looking for two or more known slugs as quoted string literals on
    adjacent lines (which is what the offending tuples look like).
    """

    yaml_slugs = {p.stem for p in PERSONA_DIR.glob("*.yaml")}
    offenders: list[str] = []
    for root in SCAN_PATHS:
        for py in root.rglob("*.py"):
            if "tests" in py.parts:
                continue
            text = py.read_text()
            hits = HARDCODED_TUPLE_RE.findall(text)
            if len(hits) >= 2:
                # Two distinct slugs in the same file → quoted-tuple smell.
                if len(set(hits)) >= 2:
                    offenders.append(str(py.relative_to(REPO_ROOT)))

    assert not offenders, (
        "hard-coded persona tuple detected in: "
        + ", ".join(offenders)
        + f" — expected slugs to be sourced from {PERSONA_DIR.relative_to(REPO_ROOT)}"
    )

    # Sanity: every yaml file is registered (catches stem-mismatch slug bugs).
    declared = set(list_persona_slugs(force_reload=True))
    assert yaml_slugs == declared, (
        f"yaml stems {yaml_slugs} do not match declared slugs {declared}"
    )


@pytest.mark.parametrize(
    "minimum_slug",
    ["rogers", "buffett", "soros", "druckenmiller", "burry"],
)
def test_v25_minimum_persona_set(minimum_slug):
    """v2.5 §T1.2 requires at least these 5 to ship before T2 begins."""
    slugs = list_persona_slugs(force_reload=True)
    assert minimum_slug in slugs, f"missing required persona {minimum_slug}: have {slugs}"
