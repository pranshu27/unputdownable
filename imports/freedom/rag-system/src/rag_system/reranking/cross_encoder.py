"""Cross-encoder reranker for W2.

Uses ``cross-encoder/ms-marco-MiniLM-L-6-v2`` to rescore retrieved hits
in order of true relevance, replacing the retrieval-only rank.

The model is loaded lazily on first call so startup is not slowed down.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

logger = logging.getLogger("rag_system.reranking")

_DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_model = None


def _get_model(model_name: str | None = None):
    global _model
    if _model is None:
        from sentence_transformers import CrossEncoder  # lazy import

        name = model_name or os.getenv("CROSS_ENCODER_MODEL", _DEFAULT_MODEL)
        logger.info("Loading cross-encoder: %s", name)
        _model = CrossEncoder(name)
        logger.info("Cross-encoder ready: %s", name)
    return _model


def rerank(
    query: str,
    hits: List[Dict[str, Any]],
    top_k: int | None = None,
    model_name: str | None = None,
) -> List[Dict[str, Any]]:
    """Rerank *hits* (list of /retrieve hit dicts) for *query*.

    Each hit must have a ``text`` field.  Returns a new list sorted by
    cross-encoder score (descending), with ``rerank_score`` added to each
    hit and the original ``score`` preserved as ``retrieval_score``.

    Parameters
    ----------
    query:      The user query string.
    hits:       Retrieved hit dicts (each with at least ``text`` key).
    top_k:      If set, return only the top_k after reranking.
    model_name: Override the model (default: cross-encoder/ms-marco-MiniLM-L-6-v2).
    """
    if not hits:
        return hits

    model = _get_model(model_name)
    pairs = [(query, h["text"]) for h in hits]
    scores = model.predict(pairs).tolist()

    reranked = []
    for hit, rs in zip(hits, scores):
        new_hit = dict(hit)
        new_hit["retrieval_score"] = new_hit.pop("score", None)
        new_hit["score"] = rs
        new_hit["rerank_score"] = rs
        reranked.append(new_hit)

    reranked.sort(key=lambda h: h["score"], reverse=True)

    if top_k is not None:
        reranked = reranked[:top_k]

    return reranked
