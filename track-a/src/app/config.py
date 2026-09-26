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

    # Dense embedding model: BGE-M3 -> 1024 dims (per plan.md).
    dense_vector_size: int = 1024
    dense_distance: str = "Cosine"

    # Sparse vector (BM25/IDF) index parameters.
    sparse_index_on_disk: bool = False
    sparse_modifier: str = "IDF"


@lru_cache
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""
    return Settings()
