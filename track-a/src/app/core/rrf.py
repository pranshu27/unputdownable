"""Reciprocal Rank Fusion (RRF) — implemented from scratch per ADR 002.

RRF(d) = sum over result lists R of 1 / (k + rank_i(d))

``k`` dampens the effect of top ranks (Cormack et al. 2009 use k=60).
This is a whiteboard-flex algorithm: no library call, no external dep.
"""

from __future__ import annotations

from typing import Hashable


def reciprocal_rank_fusion(
    result_lists: list[list[Hashable]],
    k: int = 60,
) -> list[tuple[Hashable, float]]:
    """Fuse ranked ID lists into a single ranking with RRF scores.

    Args:
        result_lists: ordered lists of item IDs (best first) from each retriever.
        k: RRF constant (default 60).

    Returns:
        Items sorted by fused score descending; ties keep first-seen order.
        Duplicate IDs within a single list are de-duplicated (keep best rank).
    """
    scores: dict[Hashable, float] = {}
    order: dict[Hashable, int] = {}
    for result_list in result_lists:
        seen: set[Hashable] = set()
        for rank, item in enumerate(result_list, start=1):
            if item in seen:
                continue  # de-duplicate within one retriever's list
            seen.add(item)
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
            if item not in order:
                order[item] = len(order)
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], order[kv[0]]))
    return ranked


def weighted_rank_fusion(
    result_lists: list[list[Hashable]],
    k: int = 60,
    weights: list[float] | None = None,
) -> list[tuple[Hashable, float]]:
    """Weighted RRF (Week 2 Thu LLD drill): score(d) = sum_i w_i / (k + rank_i(d)).

    ``weights`` optional; None = uniform (identical to :func:`reciprocal_rank_fusion`).
    Raises ValueError when weights length != result_lists length or any w < 0.
    """
    if weights is None:
        weights = [1.0] * len(result_lists)
    if len(weights) != len(result_lists):
        raise ValueError(f"weights ({len(weights)}) must match result_lists ({len(result_lists)})")
    if any(w < 0 for w in weights):
        raise ValueError("weights must be non-negative")
    scores: dict[Hashable, float] = {}
    order: dict[Hashable, int] = {}
    for w, result_list in zip(weights, result_lists):
        seen: set[Hashable] = set()
        for rank, item in enumerate(result_list, start=1):
            if item in seen:
                continue
            seen.add(item)
            scores[item] = scores.get(item, 0.0) + w / (k + rank)
            if item not in order:
                order[item] = len(order)
    return sorted(scores.items(), key=lambda kv: (-kv[1], order[kv[0]]))
