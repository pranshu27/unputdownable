# ADR 003: Query Transformation Pipeline

## Status
Proposed (Oct 14, 2026) - Week 3 Day 1

## Context
Retrieval failures split in two: the corpus failed to contain the answer, or the *question* was
malformed for the corpus (compound questions, filler words, vocabulary mismatch). Week 2 fixed the
corpus side (hybrid + rerank). This ADR fixes the question side - with an honest constraint: the
generation LLM does not land until Week 7, so anything requiring generation needs a pluggable
seam that degrades to a no-op today.

## Decision
1. **Query transformation is a pluggable, config-driven pipeline** (`core/query_transformers.py`):
   a chain of `QueryTransformer` strategies applied before retrieval; each strategy is a class,
   selected/enabled via settings - no pipeline code changes to add one.
2. **Sub-query decomposition (LLM-free):** split compound questions on conjunctions/filler
   patterns into focused sub-queries. Each sub-query retrieves independently; all variants are
   fused with the original via the existing RRF (one fusion, n+1 lists).
3. **Rule-based rewrite (LLM-free):** deterministic cleanup - strip interrogative filler
   ("what is", "tell me about"), collapse synonyms from a small domain map.
4. **HyDE (deferred generation):** the interface ships with a `Generator` hook; without a
   generator it degrades to a no-op. Wired to the real LLM in Week 7.
5. **Self-RAG-style reflection (rule-based proxy):** after retrieval, a sufficiency check
   (query-keyword coverage of the top results + minimum score) decides whether to run one rewrite
   loop (retrieve with decomposed sub-queries, fuse, re-check). Bounded: at most ONE retry.

## Alternatives Considered
1. **Always transform every query** - rejected: transformations cost latency and can hurt
   short, well-formed queries; enable per-query only when a strategy applies.
2. **Full Self-RAG with an LLM critic now** - rejected: needs the generator (Week 7); the
   rule-based proxy captures the control flow, so the LLM later swaps into a defined seam.
3. **Multi-retrieval without fusion (concatenate results)** - rejected: duplicates across
   variants distort ranking; RRF over variant lists is already built and measured.

## Trade-offs
- **Latency:** each enabled strategy adds a transform span (~0.1 ms rule-based); the reflection
  retry can double retrieval cost on insufficient queries (bounded to one retry).
- **Quality risk:** a bad rewrite can steer retrieval wrong; mitigated by fusing the ORIGINAL
  query with every variant (variants can only add, the original keeps its vote).
- **Complexity:** a second service layer (`QueryService`) between API and SearchService.

## Expected Measurements (Week 3 Day 3)
- **Quality:** Delta Recall@5 (transformed pipeline vs baseline hybrid+rerank) - target: >= 0 on
  simple goldens (no regressions), positive on compound queries.
- **Latency:** transform span p95 (< 1 ms rule-based) + reflection-loop overhead on insufficient
  queries (target < 2x single retrieval).
- **Cost:** added LLM tokens = 0 until Week 7 (rule-based strategies are free).