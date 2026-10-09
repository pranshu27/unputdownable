---
tags: [design, hld, track-a]
created: 2026-10-08
updated: 2026-10-08
up: "[[Home]]"
related: "[[LLD - Ingestion and Retrieval]]"
---
# HLD - Track A: Agentic RAG Platform

> [!info] Legend
> **OK** built & measured · **WIP** built, needs hardening · **TODO** planned (week noted)
> Source of truth is the repo; this doc is stamped at commit `fc3314e`.

## 1. Purpose & scope

A service that ingests heterogeneous enterprise documents and answers questions over them with cited
passages - hybrid retrieval now, agentic orchestration later.

- **In scope:** ingestion -> hybrid retrieval -> caching/serving -> evals/observability
- **Out of scope:** Track B (AWS governance) and Track C (resilient gateway) own their own HLDs

## 2. Goals / non-goals

**Goals:** defensible retrieval quality with measured deltas; explicit latency budgets; cost per 1k
queries; parsers extensible without pipeline edits; production-shaped (async, containerised, observed).

**Non-goals (now):** multi-tenant RBAC, cross-region HA, GPU serving (lands Week 7).

## 3. Actors

| Actor | Wants | Path |
| :--- | :--- | :--- |
| Analyst | answers with citations from financial statements | `POST /api/v1/search` |
| Ingest engineer | documents indexed, with visibility | `POST /api/v1/documents` |
| Ops | health, traces, alerts | `GET /health` (TODO Phoenix) |
| Agent (W5) | plan/act/verify over tools | LangGraph graph |

## 4. System context

```text
 client --HTTP--> FastAPI (async)
                   |-- /health
                   |-- /api/v1/documents --> IngestService --> parse -> chunk -> embed -> upsert
                   |-- /api/v1/search    --> SearchService --> dense + sparse --> RRF(k=60) --> top-k
                                                 |                                 |
                                                 v                                 v
                                        EmbeddingBackend                    Qdrant `documents`
                                   (fastembed ONNX 384-d + hashed)   (dense HNSW m=16 + sparse IDF)

 TODO: Redis semantic cache (W4) | Postgres audit+tenancy (W9+) | vLLM (W7) | Phoenix/OTel (W14) | reranker (W2)
```

## 5. Components

| Component | Responsibility | Code | Status |
| :--- | :--- | :--- | :--- |
| API layer | validation, routing, OpenAPI | `app/main.py` | OK |
| Parsers (Strategy) | source format -> typed blocks | `core/parsers.py` | OK |
| Chunker | blocks -> chunks, atomic tables | `core/chunker.py` | OK |
| Embedding backend | dense + hashed sparse | `core/embeddings.py` | WIP (CPU, sync) |
| Ingest service | orchestration + spans | `core/ingest_service.py` | OK |
| Vector store | dense+sparse index + payload | `core/qdrant.py` | OK |
| Search + RRF | hybrid retrieval + fusion | `core/search_service.py` | OK |
| Reranker | top-50 -> top-5 | TODO W2 | TODO |
| Agent | plan/act/verify loop | TODO W5 LangGraph | TODO |
| Semantic cache | reuse query embeddings | TODO W4 Redis | TODO |
| Eval harness | Ragas/DeepEval CI gate | TODO W13 | TODO |

## 6. Data flow (measured)

**Ingest:** route by format -> parse (`Block[]`) -> chunk (`Chunk[]` + contextual headers) -> embed
dense+sparse -> upsert.

- parse ~96 ms for the 1.5 MB 10-K (parsing is not the bottleneck)
- embed **60-95 s p95** - the bottleneck
- upsert ~1 s

**Query:** embed (~3-9 ms) -> dense (~4-8 ms) and sparse (~2-8 ms) -> RRF fuse (~0.03-0.08 ms) -> top-k.
Rerank will sit between fuse and top-k from W2.

## 7. Storage & data model

**Qdrant `documents` (OK)** - 290 points, one per chunk:

- vectors: `dense` 384-d cosine (HNSW m=16, ef_construct=100) + `sparse` with IDF modifier
- payload per point:

```text
chunk_id - document_id - document_title - text - contextual_header
token_count - is_table - table_rows - metadata{section_path, source_format}
```

**Qdrant `documents-tests` (OK)** - scratch collection for live tests, dropped on teardown.

**Redis (W4)** - semantic cache: query-embedding key, similarity threshold, TTL, invalidation.

**Postgres (W9+)** - audit trail, tenancy, structured table mirrors (watch the two-sources-of-truth risk).

**Object store (TODO)** - raw source blobs.

## 8. Non-functional budgets (target vs measured)

| Metric | Target | Measured | Verdict |
| :--- | :--- | :--- | :--- |
| ingest p95 / doc | < 2 s | 75-95 s (10-K) | FAIL - embed-bound (W2) |
| ingest throughput | >= 0.5 docs/s | 0.05 docs/s | FAIL - same cause |
| parse time (10-K) | - | ~96 ms | OK |
| search TTFT-equivalent | < 50 ms | p50 11-18 ms / p95 59 ms | OK |
| RRF fuse p95 | < 50 ms | 0.03-0.08 ms | OK (~600x margin) |
| table corruption | < 5% | 0/75 tables | OK |
| parse failure rate | < 5% | 0/8 docs | OK |
| Delta Recall@5 (hybrid-dense) | >= +15% | 0.0 (0.92 = 0.92) | RE-TARGETED to W2 reranker |
| $/1k pages (embed / storage) | - | $0.0025 / $0.088 | OK (reference) |
| $/1k queries | - | not yet measured | TODO |

## 9. Scaling plan (toward 10M docs)

1. Shard by tenant/collection; separate write and read paths.
2. Tune `ef_search` against a measured Recall@k-vs-p95 curve.
3. Quantise (int8/PQ + rescoring) only after measuring the recall loss.
4. Put the semantic cache in front of retrieval.
5. Move embeddings to GPU or batched ONNX sessions.
6. Keep payload on disk; compress the index.

## 10. Failure domains & degradation

| Failure | Behaviour today | Next |
| :--- | :--- | :--- |
| Qdrant down at startup | app boots; `/health` reports error | circuit breaker + retries |
| Malformed document | `parse_failed` stat; batch continues | dead-letter queue + retry |
| Embedding model unavailable | failure at startup/download | pre-baked image, warm pool |
| OCR vendor swapped | not built | adapter behind ScannedPdf strategy |
| Slow embeddings | blocks the ingest worker | async batched workers (W2) |

## 11. Observability

**OK:** per-stage spans on every ingest and search call (parse/chunk/embed/upsert; embed/dense/sparse/fuse),
surfaced in API responses and benchmark output.

**TODO:** OTel traces + Arize Phoenix (W14), counters/histograms, structured logs, alerts on
parse-failure rate and ingest p95, cost dashboard per 1k queries.

## 12. Security & tenancy (TODO)

Tenant isolation via payload filters; PII redaction at ingest; prompt-injection guardrails; audit log.
Track B owns the enterprise RBAC story; Track A keeps a minimal, honest version.

## 13. Roadmap alignment

- **W2** reranker + BGE-M3 + batched embeddings
- **W3** query rewriting / Self-RAG
- **W4** semantic cache, SSE streaming, docker compose
- **W5** LangGraph state machine - **W6** tools + HITL
- **W7** vLLM / PagedAttention
- **W13** Ragas/DeepEval CI gate - **W14** OTel + Phoenix

## 14. Risks & open questions

- Small-corpus saturation hides retrieval gains: 290 points < `full_scan_threshold` (10k) means brute
  force, so Delta = 0. Gains must be shown at scale or via reranking.
- The CPU embedding path is the biggest ingest risk and the top Week-2 fix.
- Mirrored structured tables (Postgres) would create two sources of truth - decide explicitly.
- Scanned / multi-column handling is unvalidated on real PDFs (synthetic stand-ins so far).

## 15. Links

- **ADRs:** `adr/001-parsing-chunking-pipeline.md`, `adr/002-hybrid-search-strategy.md`
- **Design:** [[LLD - Ingestion and Retrieval]]
- **Concepts:** [[Chunking]] · [[Embeddings]] · [[HNSW]] · [[RRF]] · [[Measurement Harness]]
- **Numbers:** `measurements.md` · **LLD drill:** `interview/lld-extensible-document-parser.md`
