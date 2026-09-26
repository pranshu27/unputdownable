"""Live Qdrant integration tests.

These tests auto-skip when Qdrant is not reachable (e.g. Docker not running), so the
unit suite still passes in CI without infrastructure.
"""

import pytest
from qdrant_client import models

from app.config import get_settings
from app.core.qdrant import ensure_collection, get_qdrant_client


@pytest.fixture(scope="module")
def client():
    settings = get_settings()
    c = get_qdrant_client(settings)
    try:
        c.get_collections()  # force a round-trip; raises if the server is down
    except Exception as exc:  # pragma: no cover - depends on local Docker
        pytest.skip(f"Qdrant unavailable: {exc}")
    return c, settings


def test_collection_has_dense_and_sparse_vectors(client):
    c, settings = client
    ensure_collection(c, settings)
    info = c.get_collection(settings.qdrant_collection)
    assert str(info.status).lower() == "green"
    assert "dense" in info.config.params.vectors
    assert "sparse" in info.config.params.sparse_vectors
    assert info.config.params.vectors["dense"].size == settings.dense_vector_size


def test_roundtrip_upsert_and_query(client):
    c, settings = client
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
