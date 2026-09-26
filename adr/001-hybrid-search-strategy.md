# ADR 001: Hybrid Search Strategy

## Status
Proposed (Sep 28, 2026)

## Context
Goal: Implement high-performance document retrieval for Track A (Agentic RAG).
Requirement: Capture both semantic context (vectors) and exact keyword matches (lexical).

## Decision
Implement a Hybrid Search pipeline using Qdrant:
1.  **Dense Retriever:** HNSW vector index.
2.  **Sparse Retriever:** BM25 lexical index.
3.  **Fusion:** Reciprocal Rank Fusion (RRF) for merging results.

## Alternatives Considered
1.  **Dense-only search:** High recall on semantic queries; fails on specific technical identifiers or acronyms.
2.  **Sparse-only search (BM25):** High precision on keywords; fails on semantic synonyms.
3.  **Late Reranking:** (Deferred) - Might be used in later weeks if RRF is insufficient.

## Trade-offs
- **Latency:** RRF introduces a minor latency overhead per request.
- **Complexity:** Managing two indices (vector and sparse).
- **Cost:** Higher memory footprint for storing both vector and sparse indices.

## Expected Measurements (Validation on Day 3)
- **Quality (Measure):** Δ Recall@5 (Target: Hybrid Search > Dense-only by >= 15%).
- **Latency (Measure):** TTFT + TPOT (Target: RRF overhead < 50ms).
- **Cost (Measure):** VRAM/Storage (Target: Sparse index size < 20% of total index size).
