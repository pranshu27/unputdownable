---
tags: [book, track-a, mind-map]
created: 2026-10-08
---
# 📖 The Track A Book — one flow, chapter by chapter

> [!info] How to read
> **Full pass:** Ch1 → Ch9 in order (30 min). **3-minute recall before an interview:** Ch1 + Ch6 + Ch7.
> Chapters 10+ are stubs — they get written the week that component lands, so the book always
> matches reality. Deep dives live in the [[HLD - Track A Agentic RAG]], [[LLD - Ingestion and Retrieval]]
> and the concept notes; this book is the connective tissue.

## The one-diagram mind map

```text
                         THE FLOW
 docs ─▶ parse ─▶ chunk ─▶ embed (dense+sparse) ─▶ index (Qdrant)
                                                        │
 question ─▶ embed ─▶ dense ∥ sparse ─▶ RRF fuse ─▶ [rerank] ─▶ top-k ─▶ answer

 quality / latency / cost measured at every arrow
```

| Ch | Chapter | One line |
| :-- | :--- | :--- |
| 1 | [[Ch 01 - The Problem]] | why this pipeline exists at all |
| 2 | [[Ch 02 - Parsing]] | messy formats → one uniform shape |
| 3 | [[Ch 03 - Chunking]] | semantic units, self-describing, tables atomic |
| 4 | [[Ch 04 - Embeddings]] | two representations: meaning + exact match |
| 5 | [[Ch 05 - Indexing]] | Qdrant: HNSW, payloads, the brute-force cliff |
| 6 | [[Ch 06 - Retrieval & RRF]] | run both retrievers, fuse by rank |
| 7 | [[Ch 07 - Measurement]] | quality / latency / cost, every week |
| 8 | [[Ch 08 - Serving]] | async API that degrades gracefully |
| 9 | [[Ch 09 - Guardrails]] | tests, fuzz, fidelity checks |
| 10 | [[Ch 10 - Reranking (W2)]] | stub — precision on top of recall |
| 11 | [[Ch 11 - Query Rewriting & Self-RAG (W3)]] | stub — fix the question first |
| 12 | [[Ch 12 - Caching & Streaming (W4)]] | stub — don't pay twice, stream tokens |
| 13 | [[Ch 13 - Agents (W5-6)]] | stub — LangGraph state machine + HITL |
| 14 | [[Ch 14 - vLLM Serving (W7)]] | stub — PagedAttention, TTFT/TPOT |
| 15 | [[Ch 15 - Track B Enterprise (W9-12)]] | stub — Bedrock, OpenSearch, Step Functions |
| 16 | [[Ch 16 - Evals & Observability (W13-14)]] | stub — CI eval gate + Phoenix |
| 17 | [[Ch 17 - Appendix - Prior Evidence]] | completed projects (imports/) — separate from Track A |
