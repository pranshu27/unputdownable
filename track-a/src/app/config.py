"""Runtime configuration loaded from environment variables (prefix ``TRACKA_``)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings.

    All values can be overridden via environment variables prefixed with ``TRACKA_``
    (e.g. ``TRACKA_QDRANT_URL``) or via a ``.env`` file in the working directory.
    """

    model_config = SettingsConfigDict(
        env_prefix="TRACKA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Track A Agentic RAG"
    api_v1_prefix: str = "/api/v1"

    # --- Qdrant ------------------------------------------------------------------
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "documents"

    # Dense embedding model: BGE-small-en-v1.5 -> 384 dims (fast CPU ONNX; upgrade
    # path to BGE-M3/large 1024-d documented in README — set via TRACKA_DENSE_VECTOR_SIZE).
    dense_vector_size: int = 384
    dense_distance: str = "Cosine"

    # Sparse vector (BM25/IDF) index parameters.
    sparse_index_on_disk: bool = False
    sparse_modifier: str = "IDF"
    sparse_hash_buckets: int = 65536

    # --- Embeddings ----------------------------------------------------------------
    # fastembed = ONNX BGE family (default, 1024 dims); hashing = hermetic test backend.
    # Note: fastembed's TextEmbedding does not ship BGE-M3; BGE-large-en-v1.5 provides
    # the same 1024-dim vector as plan.md's BGE-M3 dense config.
    embedding_backend: str = "fastembed"
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    # --- Chunking (ADR 001) --------------------------------------------------------
    chunk_target_tokens: int = 250
    chunk_overlap_tokens: int = 50

    # --- Hybrid search (ADR 002) ---------------------------------------------------
    rrf_k: int = 60

    # --- Reranking (ADR 002 Week-2 addendum) -----------------------------------------
    # Cross-encoder reranks fused candidates: fuse top-50 -> rerank -> top-5.
    # Disabled by default so the hermetic test suite and the Day-3 baseline stay unchanged.
    rerank_enabled: bool = False
    reranker_model: str = "BAAI/bge-reranker-base"  # fastembed ships base, not large
    rerank_candidates: int = 50

    # --- Query transformation (ADR 003, Week 3) ---------------------------------------
    # Chain selected by membership, e.g. "subquery,rewrite,hyde". Rule-based strategies
    # are LLM-free; hyde degrades to a no-op until the generator lands (Week 7).
    query_transform_pipeline: str = "subquery"
    reflection_enabled: bool = True   # Self-RAG-style sufficiency check + 1 bounded retry
    reflection_min_coverage: float = 0.6  # fraction of query keywords covered by top results

    # --- Data ----------------------------------------------------------------------
    data_dir: str = "data"


@lru_cache
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""
    return Settings()
