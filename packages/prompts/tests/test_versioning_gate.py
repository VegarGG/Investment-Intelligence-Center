"""Workflow 04 §6.7 + acceptance criterion 3 — publisher immutability + version selection."""

from __future__ import annotations

from pathlib import Path

import pytest
from prompts.exceptions import (
    ImmutablePromptError,
    NoStableVersionError,
    UnknownCallerError,
)
from prompts.publisher import _published_path, _sha256, persist


class TestPublisherIdempotency:
    def test_first_publish_writes(self, tmp_path: Path) -> None:
        path = persist("intel.synth", "1.0.0", "hello", root=tmp_path)
        assert path is not None
        assert path.exists()
        assert path.read_text() == "hello"

    def test_repeat_publish_is_noop(self, tmp_path: Path) -> None:
        first = persist("intel.synth", "1.0.0", "hello", root=tmp_path)
        second = persist("intel.synth", "1.0.0", "hello", root=tmp_path)
        assert first == second

    def test_mutation_without_bump_raises(self, tmp_path: Path) -> None:
        persist("intel.synth", "1.0.0", "version A", root=tmp_path)
        with pytest.raises(ImmutablePromptError, match="(?i)bump the version"):
            persist("intel.synth", "1.0.0", "version A modified", root=tmp_path)

    def test_new_version_lands_alongside(self, tmp_path: Path) -> None:
        a = persist("intel.synth", "1.0.0", "alpha", root=tmp_path)
        b = persist("intel.synth", "1.1.0", "beta", root=tmp_path)
        assert a is not None and b is not None
        assert a.parent == b.parent
        assert a.name != b.name
        assert {f.name for f in tmp_path.glob("intel.synth/*.md")} == {a.name, b.name}

    def test_path_includes_first_16_of_sha(self, tmp_path: Path) -> None:
        path = persist("c", "1.0.0", "x", root=tmp_path)
        assert path is not None
        assert _sha256("x") in path.name
        assert path == _published_path(tmp_path, "c", "1.0.0", _sha256("x"))


class TestRegistryLookup:
    """Black-box: drive registry.get() against the seeded registry."""

    def test_known_caller_returns_stable(self) -> None:
        from prompts.registry import get

        rendered = get("intel.synth", events_json="[]")
        assert rendered.caller_id == "intel.synth"
        assert rendered.tier == "pro"
        assert rendered.version == "1.0.0"

    def test_unknown_caller_raises(self) -> None:
        from prompts.registry import clear_cache, get

        clear_cache()
        with pytest.raises(UnknownCallerError):
            get("does.not.exist", x=1)

    def test_explicit_version_resolution(self) -> None:
        from prompts.registry import get

        rendered = get("intel.synth", version="1.0.0", events_json="[]")
        assert rendered.version == "1.0.0"

    def test_explicit_unknown_version_raises(self) -> None:
        from prompts.registry import get

        with pytest.raises(UnknownCallerError, match="no version"):
            get("intel.synth", version="9.9.9", events_json="[]")

    def test_caller_with_no_stable_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Build a synthetic caller dir with only beta versions.
        from prompts import registry as registry_mod

        synth_root = tmp_path / "registry"
        caller_dir = synth_root / "fake.caller"
        caller_dir.mkdir(parents=True)
        (caller_dir / "1.0.0.md").write_text(
            "---\ncaller_id: fake.caller\nversion: 1.0.0\ntier: pro\nstatus: beta\n---\nbody"
        )
        monkeypatch.setattr(registry_mod, "REGISTRY_ROOT", synth_root)
        registry_mod.clear_cache()
        with pytest.raises(NoStableVersionError):
            registry_mod.get("fake.caller")


class TestPublisherDevMode:
    def test_unwritable_root_returns_none(self, tmp_path: Path) -> None:
        # /proc/1/this-cannot-exist is reliably non-writable in CI sandboxes.
        # Use a non-existent path under /dev/null/ so the parent isn't a dir.
        bad = Path("/dev/null/iic-published")
        result = persist("c", "1.0.0", "x", root=bad)
        assert result is None
