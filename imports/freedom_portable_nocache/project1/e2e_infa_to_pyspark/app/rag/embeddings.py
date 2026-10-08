"""Embedding providers for the RAG vector store.

An embedding turns a chunk of text into a fixed-length numeric vector so that semantic
similarity becomes geometric distance (cosine). The vector store indexes these vectors and
answers nearest-neighbour queries.

Two providers, one interface
-----------------------------
- ``AzureOpenAIEmbedding`` — production path. Uses an Azure OpenAI *embedding* deployment
  (e.g. ``text-embedding-3-small``, 1536 dims). Highest semantic quality.
- ``HashingEmbedding`` — offline/deterministic fallback. A feature-hashing (a.k.a. the
  "hashing trick") + sublinear-TF projection into a fixed dimension. No network, fully
  reproducible, so unit tests and air-gapped runs still get real vectors and a real
  nearest-neighbour search. Lower semantic quality than a trained model, but the geometry
  and the whole pipeline (chunk -> embed -> upsert -> search) are exercised identically.

``get_embedding_provider()`` picks Azure when ``AZURE_EMBEDDING_DEPLOYMENT`` is configured,
otherwise the hashing provider. The two are interchangeable behind ``embed()`` / ``dim``.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from abc import ABC, abstractmethod
from typing import List

from dotenv import load_dotenv

from app.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]+")


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


class EmbeddingProvider(ABC):
    """Common interface: turn texts into L2-normalized vectors of fixed ``dim``."""

    dim: int

    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        ...

    def embed_one(self, text: str) -> List[float]:
        return self.embed([text])[0]


def _l2_normalize(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class HashingEmbedding(EmbeddingProvider):
    """Deterministic feature-hashing embedding (no external service).

    Each token is hashed into one of ``dim`` buckets with a signed contribution and a
    sublinear term-frequency weight. Token *bigrams* are also hashed so word order carries
    a little signal. The result is L2-normalized so cosine == dot product.
    """

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def _hash(self, token: str) -> tuple[int, float]:
        h = hashlib.md5(token.encode("utf-8")).digest()
        bucket = int.from_bytes(h[:4], "big") % self.dim
        sign = 1.0 if h[4] & 1 else -1.0
        return bucket, sign

    def embed(self, texts: List[str]) -> List[List[float]]:
        vectors: List[List[float]] = []
        for text in texts:
            tokens = _tokenize(text)
            counts: dict[str, int] = {}
            for t in tokens:
                counts[t] = counts.get(t, 0) + 1
            # add bigrams for a little word-order signal
            for a, b in zip(tokens, tokens[1:]):
                bg = f"{a}_{b}"
                counts[bg] = counts.get(bg, 0) + 1

            vec = [0.0] * self.dim
            for token, c in counts.items():
                bucket, sign = self._hash(token)
                vec[bucket] += sign * (1.0 + math.log(c))  # sublinear TF
            vectors.append(_l2_normalize(vec))
        return vectors


class AzureOpenAIEmbedding(EmbeddingProvider):
    """Azure OpenAI embedding deployment (production path)."""

    def __init__(self, deployment: str, dim: int = 1536) -> None:
        from openai import AzureOpenAI  # lazy import

        self.deployment = deployment
        self.dim = dim
        self._client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY", ""),
            azure_endpoint=os.getenv("AZURE_OPENAI_API_BASE", ""),
            api_version=os.getenv("AZURE_API_VERSION", "2024-08-01-preview"),
        )

    def embed(self, texts: List[str]) -> List[List[float]]:
        resp = self._client.embeddings.create(model=self.deployment, input=texts)
        return [_l2_normalize(list(d.embedding)) for d in resp.data]


def get_embedding_provider() -> EmbeddingProvider:
    """Pick Azure embeddings when configured, else the deterministic hashing fallback."""
    deployment = os.getenv("AZURE_EMBEDDING_DEPLOYMENT", "").strip()
    if deployment and os.getenv("AZURE_OPENAI_API_KEY"):
        try:
            provider = AzureOpenAIEmbedding(deployment)
            logger.info("RAG embeddings: Azure OpenAI deployment '%s'", deployment)
            return provider
        except Exception as exc:  # pragma: no cover - falls back if openai missing
            logger.warning("Azure embeddings unavailable (%s); using hashing fallback", exc)
    logger.info("RAG embeddings: deterministic hashing provider (offline)")
    return HashingEmbedding()
