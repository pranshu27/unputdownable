"""Shared pytest fixtures for the Track A suite.

Live-Qdrant tests must never write into the production collection
(``settings.qdrant_collection``, default ``documents``). They are handed a scratch
collection instead, created on demand and dropped at module teardown.
"""

from __future__ import annotations

import pytest

from app.config import get_settings

SCRATCH_COLLECTION = "documents-tests"


@pytest.fixture(scope="module")
def settings():
    """Cached application settings."""
    return get_settings()


@pytest.fixture(scope="module")
def scratch_settings():
    """Settings pointed at a throwaway collection so tests never pollute ``documents``."""
    return get_settings().model_copy(update={"qdrant_collection": SCRATCH_COLLECTION})


@pytest.fixture(scope="module")
def scratch_client(scratch_settings):
    """Live Qdrant client bound to the scratch collection; skips when Qdrant is down.

    Yields ``(client, scratch_settings)``; deletes the scratch collection at teardown.
    """
    from app.core.qdrant import ensure_collection, get_qdrant_client

    client = get_qdrant_client(scratch_settings)
    try:
        client.get_collections()  # round-trip; raises when the server is down
    except Exception as exc:  # pragma: no cover - depends on local Docker
        pytest.skip(f"Qdrant unavailable: {exc}")

    ensure_collection(client, scratch_settings)
    yield client, scratch_settings

    try:  # best-effort cleanup
        client.delete_collection(SCRATCH_COLLECTION)
    except Exception:  # pragma: no cover
        pass
