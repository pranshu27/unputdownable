---
tags: [design, hld, track-a]
created: 2026-10-08
updated: 2026-10-08
up: "[[Home]]"
related: "[[LLD - Ingestion and Retrieval]]"
---
# HLD - Track A: Agentic RAG Platform

**Living document.** Source of truth is the repo, stamped at commit `3da2b67`.
**Legend:** OK = built & measured / WIP = built, needs hardening / TODO = planned (week noted).

## 1. Purpose & scope
A service that ingests heterogeneous enterprise documents and answers questions over them with
cited passages - hybrid retrieval now, agentic orchestration later. In scope: ingestion -> hybrid
retrieval -> caching/serving -> evals/observability. Out of scope: Track B (AWS governance) and
Track C (resilient gateway) own their own HLDs.

## 2. Goals / non-goals
**Goals:** defensible retrieval quality with measured deltas; explicit latency budgets; cost per
1k queries; parsers extensible without pipeline edits; production-shaped (async, containerised, observed).
**Non-goals (now):** multi-tenant RBAC, cross-region HA, GPU serving (Week 7).

## 3. Actors
| Actor | Wants | Path |
| :--- | :--- | :--- |
| Analyst | answer with citations from financial statements | POST /api/v1/search |
| Ingest engineer | submit documents, know they indexed | POST /api/v1/documents |
| Ops | health, traces, alerts | GET /health, TODO Phoenix |
| Agent (W5) | plan/act/verify loop over tools | LangGraph graph |

## 4. System context
```
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
| API layer | validation, routing, OpenAPI | `app/main.py`, `api/routes/*` | OK |
| Parsers (Strategy) | source format -> typed blocks | `core/parsers.py` | OK (SEC-HTML path; DOCX is a placeholder) |
| Chunker | blocks -> self-describing chunks, atomic tables | `core/chunker.py` | OK |
| Embedding backend | dense + hashed sparse | `core/embeddings.py` | WIP (CPU ONNX, sync) |
| Ingest service | orchestration + per-stage spans | `core/ingest_service.py` | OK |
| Vector store | dense+sparse index + payload | `core/qdrant.py` | OK |
| Search service + RRF | hybrid retrieval + fusion | `core/search_service.py`, `core/rrf.py` | OK |
| Reranker (cross-encoder) | top-50 -> top-5 | TODO W2 | TODO |
| Agent orchestration | plan/act/verify | TODO W5 LangGraph | TODO |
| Semantic cache | reuse query embeddings | TODO W4 Redis | TODO |
| Eval harness | Ragas/DeepEval CI gate | TODO W13 | TODO |

## 6. Data flow (measured)
**Ingest:** route by format -> parse (`Block[]`) -> chunk (`Chunk[]` + contextual headers) -> embed
dense+sparse -> upsert. Spans: parse ~96 ms (10-K, 1.5 MB) - embed **60-95 s p95** (bottleneck) -
upsert ~1 s.
**Query:** embed (~3-9 ms) -> dense (~4-8 ms) and sparse (~2-8 ms) -> RRF fuse (~0.03-0.08 ms) -> top-k.
TODO: rerank sits between fuse and top-k from W2.

## 7. Storage & data model
| Store | Holds | Status |
| :--- | :--- | :--- |
| Qdrant `documents` | 290 points; dense 384-d cosine + sparse IDF; payload {chunk_id, document_id, document_title, text, contextual_header, token_count, is_table, table_rows, metadata} | OK |
| Qdrant `documents-tests` | scratch collection for live tests (dropped on teardown) | OK |
| Redis | semantic cache: query-embedding key, similarity threshold, TTL, invalidation | TODO W4 |
| Postgres | audit trail, tenancy, structured table mirrors | TODO W9+ |
| Object store | raw source blobs | TODO |

## 8. Non-functional budgets (target vs measured)
| Metric | Target | Measured | Verdict |
| :--- | :--- | :--- | :--- |
| ingest p95 / doc | < 2 s | 75-95 s (the 10-K) | FAIL - embed-bound, W2 batching |
| ingest throughput | >= 0.5 docs/s | 0.05 docs/s | FAIL - same cause |
| parse time (10-K) | - | ~96 ms | OK (parsing is not the problem) |
| search TTFT-equivalent | < 50 ms | p50 11-18 ms, p95 59 ms | OK |
| RRF fuse p95 | < 50 ms | 0.03-0.08 ms | OK (~600x headroom) |
| table corruption | < 5% | 0/75 tables | OK |
| parse failure rate | < 5% | 0/8 docs | OK |
| Delta Recall@5 (hybrid-dense) | >= +15% | 0.0 (0.92 = 0.92) | RE-TARGETED to W2 reranker on lexical-hard goldens |
| $/1k pages (embed / storage) | - | $0.0025 / $0.088 (reference prices) | OK, documented |
| $/1k queries | - | not yet (needs reranker + LLM spans) | TODO |

## 9. Scaling plan (toward 10M docs)
Shard by tenant/collection; tune `ef_search` against a measured Recall@k-vs-p95 curve; quantise
(int8/PQ + rescoring) only after measuring the recall loss; separate write and read paths; put the
semantic cache in front of retrieval; move embeddings to GPU or batched ONNX sessions; keep payload
on disk and compress the index.

## 10. Failure domains & degradation
| Failure | Behaviour today | Next |
| :--- | :--- | :--- |
| Qdrant down at startup | app still boots; `/health` reports the error (best-effort lifespan) | circuit breaker + retry budget |
| Malformed document | exception caught -> `parse_failed` stat; batch continues | dead-letter queue + per-doc retry |
| Embedding model unavailable | failure at startup/download | pre-baked image, warm pool |
| OCR vendor swapped | not built | adapter behind a ScannedPdf strategy |
| Slow embeddings | blocks the ingest worker | async batched workers (W2) |

## 11. Observability
OK: per-stage spans on every ingest and search call (parse/chunk/embed/upsert; embed/dense/sparse/fuse)
surfaced in API responses and benchmark output.
TODO: OTel traces + Arize Phoenix (W14), counters/histograms, structured logs, alerts on parse-failure
rate and ingest p95, cost dashboard per 1k queries.

## 12. Security & tenancy (TODO)
Tenant isolation via payload filters; PII redaction at ingest; prompt-injection guardrails; audit log.
Track B owns the enterprise RBAC story; Track A keeps a minimal, honest version.

## 13. Roadmap alignment
W2 reranker + BGE-M3 + batched embeddings - W3 query rewriting/Self-RAG - W4 semantic cache, SSE
streaming, docker compose - W5 LangGraph state machine - W6 tools + HITL - W7 vLLM/PagedAttention -
W13 Ragas/DeepEval gate - W14 OTel + Phoenix.

## 14. Risks & open questions
- Small-corpus saturation hides retrieval gains: 290 points < `full_scan_threshold` (10k) means brute
  force and Delta=0. Gains must be shown at scale or through reranking.
- The CPU embedding path is the single biggest ingest risk and the top Week-2 fix.
- Mirrored structured tables (Postgres) would create two sources of truth - decide explicitly.
- Scanned/multi-column handling is unvalidated on real PDFs (only synthetic stand-ins so far).

## 15. Links
ADRs: `adr/001-parsing-chunking-pipeline.md`, `adr/002-hybrid-search-strategy.md` |
Design: [[LLD - Ingestion and Retrieval]] | Concepts: [[Chunking]] [[Embeddings]] [[HNSW]] [[RRF]] [[Measurement Harness]] |
Numbers: `measurements.md` | LLD drill: `interview/lld-extensible-document-parser.md`
