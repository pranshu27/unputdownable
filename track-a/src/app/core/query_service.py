"""Query service: transformation + multi-variant retrieval + reflection - ADR 003.

Flow (all spans timed):
    query -> transform (chain of strategies) -> retrieve original + each variant
          -> fuse all result lists with the existing RRF -> rerank the fused top-50
          -> reflect (rule-based sufficiency: keyword coverage of the top results)
          -> at most ONE bounded rewrite-loop retry with sub-queries

The reflection is a rule-based Self-RAG proxy (coverage + threshold) so the control
flow exists before the LLM lands in Week 7; the critic swaps into the seam later.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from ..config import Settings, get_settings
from ..schemas.search import SearchResult
from .query_transformers import SubQueryDecomposer, apply_pipeline, build_pipeline
from .reranker import NullReranker
from .rrf import reciprocal_rank_fusion

_KEYWORD_RE = re.compile(r"[a-z0-9]{3,}")


@dataclass(slots=True)
class QuerySpans:
    transform_ms: float = 0.0
    retrieval_ms: float = 0.0
    fusion_ms: float = 0.0
    reflection_ms: float = 0.0
    rerank_ms: float = 0.0
    total_ms: float = 0.0
    retries: int = 0


@dataclass(slots=True)
class QueryOutcome:
    results: list[SearchResult]
    spans: QuerySpans
    variants: list[str] = field(default_factory=list)
    reflections: list[dict] = field(default_factory=list)

class QueryService:
    """Orchestrates ADR-003: transform -> multi-variant retrieval -> fuse -> rerank
    -> reflect -> bounded retry."""

    def __init__(self, search: SearchService, settings: Settings | None = None, reranker=None) -> None:
        self.search_svc = search
        self.settings = settings or get_settings()
        if reranker is None:
            from .reranker import get_reranker

            reranker = get_reranker(self.settings)
        self.reranker = reranker
        self.rerank_enabled = self.settings.rerank_enabled and not isinstance(reranker, NullReranker)
        self._chain = build_pipeline(self.settings)

    def _retrieve_variants(self, queries: list[str], top_k: int):
        """Hybrid-retrieve each query; return (id lists, payload map, elapsed ms)."""
        started = time.perf_counter()
        id_lists: list[list[str]] = []
        payload: dict[str, SearchResult] = {}
        for q in queries:
            outcome = self.search_svc.search(q, top_k=top_k, mode="hybrid")
            id_lists.append([r.chunk_id for r in outcome.results])
            for r in outcome.results:
                payload.setdefault(r.chunk_id, r)
        return id_lists, payload, (time.perf_counter() - started) * 1000

    def _fuse(self, id_lists: list[list[str]]):
        started = time.perf_counter()
        fused = reciprocal_rank_fusion(id_lists, k=self.settings.rrf_k)
        return [i for i, _ in fused], (time.perf_counter() - started) * 1000

    def _rerank(self, query: str, ids, payload, top_k: int):
        if not self.rerank_enabled:
            return ids[:top_k], 0.0
        started = time.perf_counter()
        candidates = ids[: self.settings.rerank_candidates]
        scores = self.reranker.rerank(query, [payload[i].text for i in candidates if i in payload])
        candidates = candidates[: len(scores)]
        ranked = sorted(zip(candidates, scores), key=lambda ps: -ps[1])
        return [i for i, _ in ranked[:top_k]], (time.perf_counter() - started) * 1000

    def _reflect(self, query: str, ids, payload):
        """Rule-based sufficiency: fraction of query keywords (>=3 chars) covered by
        the top results. Returns (sufficient, ms, detail)."""
        started = time.perf_counter()
        keywords = set(_KEYWORD_RE.findall(query.lower()))
        top_text = " ".join(payload[i].text.lower() for i in ids[:5] if i in payload)
        covered = {kw for kw in keywords if kw in top_text}
        coverage = len(covered) / len(keywords) if keywords else 1.0
        sufficient = coverage >= self.settings.reflection_min_coverage
        return sufficient, (time.perf_counter() - started) * 1000, {
            "coverage": round(coverage, 3), "missing": sorted(keywords - covered)}

    def search(self, query: str, top_k: int = 5) -> QueryOutcome:
        settings = self.settings
        spans = QuerySpans()
        started = time.perf_counter()

        t0 = time.perf_counter()
        variants = apply_pipeline(query, self._chain)
        spans.transform_ms = (time.perf_counter() - t0) * 1000

        fetch_k = top_k * 2 if self.rerank_enabled else top_k
        id_lists, payload, spans.retrieval_ms = self._retrieve_variants([query, *variants], fetch_k)
        fused_ids, spans.fusion_ms = self._fuse(id_lists)
        top_ids, spans.rerank_ms = self._rerank(query, fused_ids, payload, top_k)

        sufficient, spans.reflection_ms, detail = self._reflect(query, top_ids, payload)
        spans.retries = 0

        # Self-RAG-style bounded rewrite loop: at most ONE retry with sub-queries
        if settings.reflection_enabled and not sufficient:
            sub = SubQueryDecomposer().transform(query)
            retry_queries = sub or variants
            if retry_queries:
                spans.retries = 1
                sub_lists, sub_payload, extra_ms = self._retrieve_variants(retry_queries, fetch_k)
                sub_payload.update(payload)
                payload = sub_payload
                spans.retrieval_ms += extra_ms
                fused2, extra_fuse = self._fuse([*id_lists, *sub_lists])
                spans.fusion_ms += extra_fuse
                top_ids, extra_rerank = self._rerank(query, fused2, payload, top_k)
                spans.rerank_ms += extra_rerank
                sufficient2, extra_reflect, detail2 = self._reflect(query, top_ids, payload)
                spans.reflection_ms += extra_reflect
                detail = {"first": detail, "after_retry": detail2,
                          "sufficient_after_retry": sufficient2}

        spans.total_ms = (time.perf_counter() - started) * 1000
        results = [payload[i] for i in top_ids if i in payload]
        return QueryOutcome(results=results, spans=spans, variants=variants,
                            reflections=[{"sufficient": sufficient, **detail}])


