"""Workflow 13 §5.1 — loader is strict; bad YAML fails boot."""

from __future__ import annotations

from pathlib import Path

import pytest
from persona.loader import load, load_dir


def test_load_real_persona() -> None:
    spec = load(Path("docs/prompts/persona/rogers.yaml"))
    assert spec.slug == "rogers"
    assert spec.disclaimer.startswith("Stylized agent")
    assert "commodities" in spec.universe_weights


def test_loader_rejects_missing_disclaimer(tmp_path: Path) -> None:
    f = tmp_path / "x.yaml"
    f.write_text("slug: x\ndisplay_name: X\n")
    with pytest.raises(ValueError, match="disclaimer"):
        load(f)


def test_loader_rejects_non_mapping(tmp_path: Path) -> None:
    f = tmp_path / "y.yaml"
    f.write_text("- a\n- b\n")
    with pytest.raises(ValueError, match="must be a mapping"):
        load(f)


def test_load_dir_requires_unique_slugs(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text("slug: x\ndisplay_name: X\ndisclaimer: 'd'\n")
    (tmp_path / "b.yaml").write_text("slug: x\ndisplay_name: X2\ndisclaimer: 'd2'\n")
    with pytest.raises(ValueError, match="duplicate persona slug"):
        load_dir(tmp_path)
