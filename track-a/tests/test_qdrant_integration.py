"""Live Qdrant integration tests.

Auto-skip when Qdrant is not reachable (e.g. Docker down), so the unit suite still
passes in CI without infrastructure.

Writes NEVER touch the real collection: they go to the ``scratch_client`` fixture
(collection ``documents-tests``), which is dropped on teardown. Previously the
round-trip test left a ``"hello world"`` point inside ``documents``.
"""

import pytest
from qdrant_client import models

from app.config import get_settings
from app.core.qdrant import ensure_collection, get_qdrant_client


def _live_client(settings):
    """Client bound to ``settings``; skips the test when Qdrant is unreachable."""
    c = get_qdrant_client(settings)
    try:
        c.get_collections()  # force a round-trip; raises if the server is down
    except Exception as exc:  # pragma: no cover - depends on local Docker
        pytest.skip(f"Qdrant unavailable: {exc}")
    return c


def test_production_collection_config_is_read_only():
    """Read-only assertion that the real collection exists with the expected config."""
    settings = get_settings()
    c = _live_client(settings)
    try:
        info = c.get_collection(settings.qdrant_collection)
    except Exception:  # pragma: no cover - collection not created yet
        pytest.skip(f"collection {settings.qdrant_collection!r} does not exist yet")
    assert str(info.status).lower() == "green"
    assert "dense" in info.config.params.vectors
    assert "sparse" in info.config.params.sparse_vectors
    assert info.config.params.vectors["dense"].size == settings.dense_vector_size


def test_roundtrip_upsert_and_query(scratch_client):
    """Upsert + query round-trip, isolated in the scratch collection."""
    c, settings = scratch_client
    assert settings.qdrant_collection != get_settings().qdrant_collection, (
        "integration tests must not write into the production collection"
    )
    ensure_collection(c, settings)
    c.upsert(
        collection_name=settings.qdrant_collection,
        points=[
            models.PointStruct(
                id=1,
                vector={"dense": [0.01] * settings.dense_vector_size},
                payload={"text": "hello world"},
            )
        ],
    )
    res = c.query_points(
        collection_name=settings.qdrant_collection,
        query=[0.01] * settings.dense_vector_size,
        using="dense",
        limit=1,
    )
    assert len(res.points) == 1
    assert res.points[0].payload["text"] == "hello world"
