---
tags: [concept, moc, foundation]
created: 2026-09-29
up: "[[Home]]"
---
# RAG Overview

> [!abstract] The one-paragraph version RAG = give an LLM the right document chunks at answer time. To find "the right chunks" you index text as vectors, retrieve nearest neighbors, and fuse multiple retrievers. Everything in Week 1 exists to make the *index* trustworthy and the *retrieval* measurable.

## Why it exists
An LLM doesn't know your documents. At query time you: (1) split docs into chunks, (2) embed chunks into vectors, (3) at query time embed the question and retrieve the closest chunks, (4) stuff them into the prompt. Retrieval quality bounds answer quality — garbage chunks in, hallucinations out.

## The pipeline we built (Track A, Week 1)
```
raw doc ──parse──▶ Block[] ──chunk──▶ Chunk[] ──embed──▶ dense+sparse vectors
                                                        │
                                              upsert to Qdrant ("documents")
                                                        │
query ──embed──▶ dense + sparse search ──RRF fuse──▶ top-k chunks ──▶ (LLM: Week 7)
```

## Where each piece lives
| Stage | File | ADR |
|---|---|---|
| parse → blocks | `track-a/src/app/core/parsers.py` | [[ADR-001 Parsing and Chunking]] |
| blocks → chunks | `core/chunker.py` | [[ADR-001 Parsing and Chunking]] |
| embed dense+sparse | `core/embeddings.py` | [[Embeddings]] |
| upsert | `core/ingest_service.py` | — |
| search + fuse | `core/search_service.py`, `core/rrf.py` | [[ADR-002 Hybrid Search]] |
| prove it works | `scripts/complex_batch.py`, `measurements.md` | [[Measurement Harness]] |

## Interview soundbite
> "RAG quality is bounded by retrieval quality, and retrieval quality is bounded by chunk quality — so I instrument the whole chain: parse failure rate, table corruption rate, Δ Recall@5, p95 latency, and $/1k pages. Every claim has a number."
