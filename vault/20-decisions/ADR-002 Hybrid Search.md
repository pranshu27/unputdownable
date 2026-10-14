---
tags: [decision, adr, summary]
created: 2026-09-29
up: "[[Home]]"
source: "adr/002-hybrid-search-strategy.md"
related: "[[RRF]], [[Embeddings]]"
---
# ADR-002 — Hybrid Search Strategy (summary)

> [!info] Full record lives in the repo: `adr/002-hybrid-search-strategy.md`.

## Context
Dense-only retrieval fails on exact identifiers, codes, and numbers; sparse-only fails on paraphrase. Track A needs one retrieval path that degrades gracefully on both.

## Decision
Hybrid pipeline on Qdrant:
1. **Dense retriever** — HNSW vector index ([[HNSW]]), BGE embeddings ([[Embeddings]]).
2. **Sparse retriever** — BM25-style lexical index with IDF modifier.
3. **Fusion via RRF k=60, implemented from scratch** ([[RRF]]) — not a library call.
4. Week 2 adds a **cross-encoder reranker**: top-50 → top-5 within a latency budget.

## Trade-offs admitted
- Two indexes ≈ 2× write amplification at ingest (sparse ≈ 14% of dense bytes — fine).
- RRF adds a fuse step (measured: 0.084 ms p95 — negligible).
- Hashed sparse vocab = collisions possible; acceptable vs maintaining a vocab.

## Success metrics
- Δ Recall@5 (hybrid − dense) ≥ +15% target — **re-targeted to Week 2**: on the small corpus both legs saturate (0.92/0.92); the lexical-hard golden queries (`ERR-4021`, `0001874410`, `4,535.35`) are where the delta should finally appear.
- Fuse latency < 50 ms → ✅ by ~600×.
- Sparse index < 20% of dense bytes → ✅.

## Week-2 addendum (Oct 2026): the rerank stage
- **Decision:** fuse top-50 → **cross-encoder rerank** → top-5; optional seam
  (`core/reranker.py`, fastembed `TextCrossEncoder`), off by default.
- **Why a cross-encoder:** it reads query and candidate *together*; a bi-encoder never
  lets them meet. Precision stage on top of the recall stage.
- **Deviation:** plan said BGE-Reranker-Large; fastembed ships only **base** → recorded.
- **Measured:** Recall@5 0.92 in ALL modes incl. rerank (Δ = 0 — ceiling at 290 pts);
  warm rerank ~15 ms/2 pairs ≈ 0.4 s per 50 pairs (clean est; benchmark p50/p95
  machine-contaminated, re-measure quiet); ≈ $0.02/1k queries.

## Key methodology insight (Sep 29)
Qdrant brute-forces below `full_scan_threshold` (10k). With 290 points, dense matches exact numbers fine ⇒ Δ = 0. **Hybrid's win condition is scale (HNSW approximation loss) or reranking quality, not small-corpus fusion.** This reframe is interview gold.

## Interview soundbite
> "I fused dense and sparse with RRF I wrote myself — rank-only, k=60, no score normalization. My own harness showed Δ Recall@5 = 0 on a 290-point corpus, which taught me the honest lesson: hybrid pays off at ANN scale, so I re-targeted that metric to the Week-2 reranker benchmark on exact-identifier queries."
