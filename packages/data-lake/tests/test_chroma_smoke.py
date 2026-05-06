"""Workflow 02 §5.6 — ChromaDB smoke tests.

Unit-level: bootstrap_collections returns the canonical names. The actual
heartbeat / round-trip is in the integration suite.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from data_lake.chroma import CANONICAL_COLLECTIONS, bootstrap_collections


class TestCanonicalCollections:
    def test_canonical_set_includes_news_filings_me(self) -> None:
        assert "news" in CANONICAL_COLLECTIONS
        assert "filings" in CANONICAL_COLLECTIONS
        assert "me" in CANONICAL_COLLECTIONS

    def test_bootstrap_creates_canonical_then_persona(self) -> None:
        with patch("data_lake.chroma.client") as mock_client:
            mock_client.return_value.get_or_create_collection = MagicMock(
                side_effect=lambda name, metadata: type("Coll", (), {"name": name})()
            )
            names = bootstrap_collections(("rogers", "buffett"))
        assert names[: len(CANONICAL_COLLECTIONS)] == list(CANONICAL_COLLECTIONS)
        assert "persona_memory_rogers" in names
        assert "persona_memory_buffett" in names


@pytest.mark.integration
class TestChromaIntegration:
    def test_heartbeat_and_canonical_collections_exist(self) -> None:
        from data_lake.chroma import client

        c = client()
        c.heartbeat()
        bootstrap_collections()
        names = {coll.name for coll in c.list_collections()}
        for canonical in CANONICAL_COLLECTIONS:
            assert canonical in names
