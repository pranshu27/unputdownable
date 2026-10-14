"""Cross-encoder reranker - ADR 002, Week-2 addendum.

A cross-encoder reads (query, candidate) TOGETHER and scores relevance - something a
bi-encoder can never do, because it compresses query and document into one vector each
before they ever meet. That is why it is precise and slow, and why it only gets shown the
top candidates (fuse top-50 -> rerank -> top-5).

Implementation: fastembed's TextCrossEncoder (ONNX on CPU, same story as the embedder).
`BAAI/bge-reranker-large` is not in fastembed's catalogue; the plan's intent (BGE-family
cross-encoder) is met with `BAAI/bge-reranker-base` - deviation recorded in the ADR.
"""

from __future__ import annotations

from ..config import Settings, get_settings


class CrossEncoderReranker:
    """Thin wrapper over fastembed's TextCrossEncoder; model loads lazily."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._model = None  # lazy: first rerank() triggers the (multi-GB) download

    def _ensure_model(self):
        if self._model is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            self._model = TextCrossEncoder(model_name=self.settings.reranker_model)
        return self._model

    def rerank(self, query: str, texts: list[str]) -> list[float]:
        """Score every (query, text) pair; higher = more relevant, order preserved."""
        if not texts:
            return []
        model = self._ensure_model()
        return [float(s) for s in model.rerank(query, texts)]


class NullReranker:
    """Disabled reranker (rerank_enabled=False): scores pass through unchanged."""

    def rerank(self, query: str, texts: list[str]) -> list[float]:
        return [0.0] * len(texts)


def get_reranker(settings: Settings | None = None) -> CrossEncoderReranker | NullReranker:
    settings = settings or get_settings()
    return CrossEncoderReranker(settings) if settings.rerank_enabled else NullReranker()
