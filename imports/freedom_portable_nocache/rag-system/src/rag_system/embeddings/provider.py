"""Embedding providers — standalone version.

Three providers, one interface (EmbeddingProvider.embed):
- HashingEmbedding           — offline, deterministic, no network. Tests / air-gapped.
- SentenceTransformerEmbedding — local semantic embeddings via sentence-transformers.
                                 Default model: all-MiniLM-L6-v2 (dim=384, ~80 MB).
                                 No API key needed; first call downloads the model.
- AzureOpenAIEmbedding       — Azure OpenAI embedding deployment (production).

Priority in get_embedding_provider():
    Azure (if keys + deployment set) > SentenceTransformer (default) > Hashing
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from abc import ABC, abstractmethod
from typing import List

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]+")


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def _l2_normalize(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class EmbeddingProvider(ABC):
    """Abstract embedding interface used by ingestion and retrieval components."""

    dim: int

    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of texts into L2-normalized vector representations."""
        ...

    def embed_one(self, text: str) -> List[float]:
        """Embed a single text by delegating to the batch embed API."""
        return self.embed([text])[0]


class HashingEmbedding(EmbeddingProvider):
    """Deterministic feature-hashing embedding (no external service).

    Token + bigram feature hashing with sublinear TF weighting, L2-normalized.
    """

    def __init__(self, dim: int = 256) -> None:
        """Initialize deterministic hashing embedding dimensionality."""
        self.dim = dim

    def _hash(self, token: str) -> tuple[int, float]:
        """Map a token to a signed feature-hash bucket."""
        h = hashlib.md5(token.encode("utf-8")).digest()
        bucket = int.from_bytes(h[:4], "big") % self.dim
        sign = 1.0 if h[4] & 1 else -1.0
        return bucket, sign

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed texts using token and bigram feature hashing with log-TF weighting."""
        vectors: List[List[float]] = []
        for text in texts:
            tokens = _tokenize(text)
            counts: dict[str, int] = {}
            for t in tokens:
                counts[t] = counts.get(t, 0) + 1
            for a, b in zip(tokens, tokens[1:]):
                bg = f"{a}_{b}"
                counts[bg] = counts.get(bg, 0) + 1
            vec = [0.0] * self.dim
            for token, c in counts.items():
                bucket, sign = self._hash(token)
                vec[bucket] += sign * (1.0 + math.log(c))
            vectors.append(_l2_normalize(vec))
        return vectors


class SentenceTransformerEmbedding(EmbeddingProvider):
    """Local semantic embeddings via sentence-transformers (no API key needed).

    Default model: all-MiniLM-L6-v2
        - dim=384, ~80 MB download on first use
        - Good semantic quality for technical/code content
        - Fully offline after first download

    Override with LOCAL_EMBEDDING_MODEL env var, e.g.:
        LOCAL_EMBEDDING_MODEL=BAAI/bge-small-en-v1.5   # better retrieval, dim=384
        LOCAL_EMBEDDING_MODEL=all-mpnet-base-v2         # higher quality, dim=768
    """

    DEFAULT_MODEL = "all-MiniLM-L6-v2"

    def __init__(self, model_name: str | None = None) -> None:
        """Load a sentence-transformer model and capture output vector dimension."""
        from sentence_transformers import SentenceTransformer  # lazy import

        self._model_name = model_name or os.getenv("LOCAL_EMBEDDING_MODEL", self.DEFAULT_MODEL)
        self._model = SentenceTransformer(self._model_name)
        self.dim = self._model.get_sentence_embedding_dimension()

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate normalized semantic embeddings using the loaded local model."""
        vecs = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [list(map(float, v)) for v in vecs]


class AzureOpenAIEmbedding(EmbeddingProvider):
    """Azure OpenAI embedding deployment (production path)."""

    def __init__(self, deployment: str, dim: int = 1536) -> None:
        """Initialize Azure OpenAI embedding client for the configured deployment."""
        from openai import AzureOpenAI  # lazy import

        self.deployment = deployment
        self.dim = dim
        self._client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY", ""),
            azure_endpoint=os.getenv("AZURE_OPENAI_API_BASE", ""),
            api_version=os.getenv("AZURE_API_VERSION", "2024-08-01-preview"),
        )

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Call Azure OpenAI embeddings API and normalize returned vectors."""
        resp = self._client.embeddings.create(model=self.deployment, input=texts)
        return [_l2_normalize(list(d.embedding)) for d in resp.data]


def get_embedding_provider() -> EmbeddingProvider:
    # 1. Azure OpenAI (production — if key + deployment are both set)
    deployment = os.getenv("AZURE_EMBEDDING_DEPLOYMENT", "").strip()
    if deployment and os.getenv("AZURE_OPENAI_API_KEY"):
        try:
            return AzureOpenAIEmbedding(deployment)
        except Exception:
            pass

    # 2. SentenceTransformer (local semantic — default open-source path)
    if os.getenv("USE_HASHING_EMBEDDING", "").lower() not in ("1", "true", "yes"):
        try:
            return SentenceTransformerEmbedding()
        except Exception:
            pass

    # 3. HashingEmbedding (offline deterministic fallback — tests / no torch)
    # Keep dim configurable so fallback remains compatible with existing pgvector schema.
    try:
        hashing_dim = int(os.getenv("HASHING_EMBEDDING_DIM", "256"))
    except ValueError:
        hashing_dim = 256
    return HashingEmbedding(dim=hashing_dim)
