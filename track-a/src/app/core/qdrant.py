"""Qdrant client wiring: dense (HNSW) + sparse (BM25/IDF) collection config."""

from qdrant_client import QdrantClient, models

from ..config import Settings, get_settings


def build_collection_config(settings: Settings | None = None) -> dict:
    """Return the Qdrant collection config for dense + sparse vectors.

    Dense vectors use the HNSW index (BGE-M3, 1024 dims, cosine). Sparse vectors use
    an inverted index with IDF weighting for lexical/BM25 retrieval (see ADR 002).
    """
    settings = settings or get_settings()
    return {
        "vectors_config": {
            "dense": models.VectorParams(
                size=settings.dense_vector_size,
                distance=models.Distance.COSINE,
            ),
        },
        "sparse_vectors_config": {
            "sparse": models.SparseVectorParams(
                index=models.SparseIndexParams(on_disk=settings.sparse_index_on_disk),
                modifier=models.Modifier.IDF,
            ),
        },
    }


def get_qdrant_client(settings: Settings | None = None) -> QdrantClient:
    """Return a Qdrant client bound to the configured URL."""
    settings = settings or get_settings()
    return QdrantClient(url=settings.qdrant_url)


def ensure_collection(client: QdrantClient, settings: Settings | None = None) -> bool:
    """Create the dense+sparse collection if needed (recreates on dim mismatch).

    Returns ``True`` when the collection was (re)created, ``False`` when a
    compatible collection already existed.
    """
    settings = settings or get_settings()
    if client.collection_exists(settings.qdrant_collection):
        try:
            info = client.get_collection(settings.qdrant_collection)
            dims = info.config.params.vectors["dense"].size
            if dims == settings.dense_vector_size:
                return False
            client.delete_collection(settings.qdrant_collection)  # stale dims; rebuild
        except Exception:
            return False
    client.create_collection(
        collection_name=settings.qdrant_collection,
        **build_collection_config(settings),
    )
    return True
