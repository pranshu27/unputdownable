"""Embedding backends: dense (BGE-M3 family via fastembed) + sparse (BM25-style).

The backend is selected via ``TRACKA_EMBEDDING_BACKEND``:
- ``fastembed`` (default): ONNX BGE-M3 dense embeddings (1024 dims, per plan.md).
- ``hashing``: deterministic hash-projection used by unit tests — hermetic,
  no model download, clearly marked as dev-only (not for quality claims).

Sparse vectors are computed locally as hashed term-frequency bags; Qdrant's
IDF modifier (see ``core/qdrant.py``) turns them into BM25-style lexical
scores (ADR 002, sparse retriever contract).
"""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod

from ..config import Settings, get_settings

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class EmbeddingBackend(ABC):
    """Dense + sparse embedding interface consumed by ingest and search."""

    @abstractmethod
    def embed_dense(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    def embed_sparse(self, texts: list[str]) -> list[dict]:
        """Return ``{"indices": [...], "values": [...]}`` per text."""


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def sparse_from_tokens(tokens: list[str], buckets: int) -> dict:
    """Hashed bag-of-words with sublinear term-frequency weighting.

    Qdrant applies IDF on top of these raw weights (Modifier.IDF).
    """
    if not tokens:
        return {"indices": [], "values": []}
    counts: dict[int, int] = {}
    for tok in tokens:
        idx = int.from_bytes(hashlib.md5(tok.encode()).digest()[:4], "big") % buckets
        counts[idx] = counts.get(idx, 0) + 1
    # sort by index for determinism
    indices = sorted(counts)
    values = [1.0 + math.log(counts[i]) for i in indices]
    return {"indices": indices, "values": values}


class SparseEmbedMixin:
    """Shared sparse logic: hashing buckets + term-frequency values."""

    buckets: int

    def embed_sparse(self, texts: list[str]) -> list[dict]:
        return [sparse_from_tokens(_tokenize(t), self.buckets) for t in texts]


class FastembedBackend(SparseEmbedMixin, EmbeddingBackend):
    """Dense embeddings via fastembed (ONNX, CPU). Default production backend."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.buckets = self.settings.sparse_hash_buckets
        from fastembed import TextEmbedding  # imported lazily; heavy dependency

        self._model = TextEmbedding(model_name=self.settings.embedding_model)

    def embed_dense(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = [list(map(float, v)) for v in self._model.embed(texts)]
        expected = self.settings.dense_vector_size
        for v in vectors:
            if len(v) != expected:
                raise ValueError(
                    f"Embedding model produced {len(v)} dims; settings expect {expected}. "
                    "Set TRACKA_DENSE_VECTOR_SIZE to match the model."
                )
        return vectors


class HashingBackend(SparseEmbedMixin, EmbeddingBackend):
    """Deterministic hash-projection embeddings. DEV/TEST ONLY — no semantic
    quality; exists so the unit suite runs hermetically without downloads."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.buckets = self.settings.sparse_hash_buckets

    def embed_dense(self, texts: list[str]) -> list[list[float]]:
        size = self.settings.dense_vector_size
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * size
            tokens = _tokenize(text)
            for tok in tokens:
                digest = hashlib.md5(tok.encode()).digest()
                idx = int.from_bytes(digest[:4], "big") % size
                sign = 1.0 if digest[4] % 2 else -1.0
                vec[idx] += sign
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            out.append([x / norm for x in vec])
        return out


_backend: EmbeddingBackend | None = None


def get_embedding_backend(settings: Settings | None = None) -> EmbeddingBackend:
    """Process-wide cached embedding backend (selected by settings)."""
    global _backend
    settings = settings or get_settings()
    if _backend is not None and getattr(_backend, "settings", None) is settings:
        return _backend
    if settings.embedding_backend == "fastembed":
        _backend = FastembedBackend(settings)
    else:
        _backend = HashingBackend(settings)
    return _backend


def reset_embedding_backend() -> None:
    """Drop the cached backend (used by tests to switch backends)."""
    global _backend
    _backend = None
