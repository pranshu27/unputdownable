---
tags: [design, lld, track-a]
created: 2026-10-08
updated: 2026-10-08
up: "[[Home]]"
related: "[[HLD - Track A Agentic RAG]]"
---
# LLD - Ingestion & Retrieval (Track A)

**Living document** for the low-level design: modules, interfaces, data models, algorithms,
sequences, error handling, tests and debt. Stamped at commit `3da2b67`.

## 1. Module map
| File | Responsibility |
| :--- | :--- |
| `app/main.py` | app factory, lifespan (best-effort Qdrant init), router mount |
| `app/config.py` | pydantic-settings, `TRACKA_*` env prefix |
| `app/api/routes/{health,documents,search}.py` | HTTP surface |
| `app/schemas/{common,documents,search}.py` | Pydantic v2 models |
| `core/parsers.py` | Strategy parsers -> `Block[]` |
| `core/chunker.py` | `Block[]` -> `Chunk[]` (atomic tables, contextual headers) |
| `core/embeddings.py` | `EmbeddingBackend`: fastembed dense + hashed sparse; `HashingBackend` for tests |
| `core/ingest_service.py` | orchestration, `IngestStats` spans, `load_source` |
| `core/qdrant.py` | client factory, collection config, dims-aware `ensure_collection` |
| `core/search_service.py` | dense + sparse queries, fusion, span timings |
| `core/rrf.py` | rank-based fusion, written from scratch |

## 2. Interfaces
```python
DocumentParser(Protocol).parse(source: str, title: str) -> ParsedDocument
get_parser(fmt: DocumentFormat) -> DocumentParser              # registry dispatch
EmbeddingBackend.embed_dense(texts) -> list[list[float]]
EmbeddingBackend.embed_sparse(texts) -> list[dict]             # {indices, values}
IngestService.ingest(payload: DocumentUpload, source_text: str | None) -> IngestResult
SearchService.search(query, top_k=5, mode="hybrid"|"dense"|"sparse") -> SearchOutcome
rrf_fuse(ranked_lists: list[list[str]], k: int = 60) -> list[tuple[str, float]]
ensure_collection(client, settings) -> bool                    # True when (re)created
```

## 3. Data models
| Type | Fields | Invariants |
| :--- | :--- | :--- |
| `Block` | `kind` (HEADING/PARAGRAPH/TABLE), `text`, `level`, `section_path[]`, `table_rows[][] or None` | tables are atomic; `section_path` copied per block |
| `ParsedDocument` | `title`, `blocks[]` | `table_count` / `total_table_rows` derived per access (no `cached_property` under `slots`) |
| `Chunk` | `chunk_id`, `document_id`, `text`, `contextual_header`, `start_index`, `end_index`, `token_count`, `is_table`, `table_rows`, `metadata` | header = `title > section > subsection`; table chunk never merged with prose |
| `DocumentUpload` | `document_id`, `title`, `source_format`, `source_uri` | Pydantic-validated at the boundary |
| `IngestResponse` | `document_id`, `status`, `chunks_created` | 202-style accepted response |
| `IngestStats` | parse/chunk/embed/upsert/total ms, counters, `parse_failed`, `error` | feeds the measurement harness |
| `SearchQuery` | `query`, `top_k`, `use_hybrid` | `use_hybrid=False` -> dense only |
| `SearchResult` | `rank`, `score`, `text`, `payload` | ranks contiguous from 1 (tests assert this) |

## 4. Algorithms
- **Chunk packing:** paragraphs packed to `chunk_target_tokens=250`; oversized paragraphs split on
  sentence boundaries; `chunk_overlap_tokens=50` carried between chunks; each heading is a hard
  boundary; tables emitted as their own single chunk regardless of size.
- **Contextual headers:** `title > section_path...` computed per chunk and prepended to the embedding
  text, not just stored.
- **Sparse encoding:** hashed bag-of-words into `sparse_hash_buckets=65536` (collisions accepted by
  design); IDF weighting applied by Qdrant (`modifier=IDF`).
- **RRF:** `score(d) = sum over lists L of 1 / (k + rank_L(d))` with `k = 60`; rank-only so cosine and
  BM25 scales never need normalisation.
- **ANN:** HNSW `m=16`, `ef_construct=100`; `full_scan_threshold=10000` means exact brute force below
  10k points - the reason dense and hybrid tie on the 290-point corpus.

## 5. Sequences
```
INGEST  source -> load_source -> chunk_source(parse + chunk) -> embed dense + sparse
               -> ensure_collection -> upsert
        spans: parse_ms, embed_ms, upsert_ms, total_ms (+ chunks/table_chunks/source_tokens)

QUERY   query -> embed_dense  -> query_points(using="dense")  -
              -> embed_sparse -> query_points(using="sparse") -+-> rrf_fuse -> top-k
        spans: embed_ms, retrieve_dense_ms, retrieve_sparse_ms, fuse_ms, total_ms
```

## 6. Error handling & states
| Case | Behaviour |
| :--- | :--- |
| Parse or embed raises | caught in `ingest` -> `status=FAILED`, `parse_failed=True`, error string; batch continues |
| Empty chunk list | `FAILED` with 0 chunks; nothing upserted |
| Qdrant unreachable at startup | app still boots; `/health` surfaces `qdrant_error` |
| Collection dims mismatch | `ensure_collection` deletes and recreates |
| Legacy/malformed points | search skips payloads lacking `chunk_id` / `document_id` |
| TODO | dead-letter queue, retries with backoff, per-doc timeouts, circuit breaker |

## 7. Config knobs
| Env var | Default | Effect |
| :--- | :--- | :--- |
| `TRACKA_QDRANT_URL` | `http://localhost:6333` | store endpoint |
| `TRACKA_QDRANT_COLLECTION` | `documents` | collection (live tests use `documents-tests`) |
| `TRACKA_DENSE_VECTOR_SIZE` | `384` | dims - must match the model (1024 for BGE-M3/large) |
| `TRACKA_EMBEDDING_BACKEND` | `fastembed` | `fastembed` or `hashing` (hermetic tests) |
| `TRACKA_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | encoder |
| `TRACKA_CHUNK_TARGET_TOKENS` / `_OVERLAP_TOKENS` | `250` / `50` | chunking shape |
| `TRACKA_RRF_K` | `60` | fusion damping |
| `TRACKA_SPARSE_HASH_BUCKETS` | `65536` | sparse dimensionality |

## 8. Extension points
| Want | Do |
| :--- | :--- |
| New source format | new class implementing `DocumentParser` + one `_PARSERS` registry line + tests |
| Third-party parser with a different API | wrap it in an adapter that returns `ParsedDocument` |
| OCR / scanned path | `ScannedPdfParser` behind the same protocol; engine swappable |
| Different encoder | swap the `EmbeddingBackend` implementation; set `DENSE_VECTOR_SIZE` |
| Reranking (W2) | cross-encoder between fuse and top-k |
| Different fusion | replace `rrf_fuse` behind the same signature (e.g. weighted RRF) |

## 9. Test map
| File | Covers |
| :--- | :--- |
| `test_parsers.py` | per-strategy block extraction (markdown tables, HTML headings/tables, plain text) |
| `test_chunker.py` | packing, overlap, contextual headers, table atomicity |
| `test_rrf.py` | fusion maths, k damping, rank ordering |
| `test_schemas.py` | validation boundaries (empty title, bad format) |
| `test_qdrant_config.py` | collection config (dense dims, sparse IDF) |
| `test_qdrant_integration.py` | live: read-only prod config check + round-trip in `documents-tests` |
| `test_services.py` | end-to-end ingest + hybrid search on the scratch collection |
| `test_health.py` | app boot and health payload |
**Guardrail:** quality claims come from the benchmark/fuzz harnesses (`scripts/*.py`) with reference
implementations - never from assertions alone.
**TODO:** golden-file fixtures for scanned/multi-column docs, property-based chunk invariants, CI eval gate (W13).

## 10. Known limitations & debt
| Debt | Impact | Fix |
| :--- | :--- | :--- |
| DOCX routed to the plain-text parser | flat paragraphs, no tables | real DOCX strategy |
| PDF routed to the SEC-HTML parser | no true PDF text-layer extraction | pypdf / pdfplumber strategy |
| CPU embeddings, one document at a time | ingest p95 75-95 s | batched async workers (W2) |
| No streaming parse | a 400-page filing is fully in memory | incremental parse |
| Derived counts under `slots=True` | recomputed per access; no `cached_property` | precompute in `__post_init__` |
| Tables with < 2 rows dropped | possible layout-table content loss | layout heuristic |
| `rowspan` ignored in HTML | ragged rows (cells still atomic) | rowspan-aware builder |
| Live tests used to write into `documents` | polluted the production collection | FIXED: scratch-collection fixture |

## 11. Drill status
Spoken LLD drill: `interview/lld-extensible-document-parser.md` - traces 1-2 logged; open:
follow-up A (extensibility diff) and B1-B3 (blast radius, fidelity proof, testing strategy).

## 12. Links
[[HLD - Track A Agentic RAG]] | [[Chunking]] [[RRF]] [[HNSW]] | ADR 001 / 002 |
code: `track-a/src/app/core` | numbers: `measurements.md` | tests: `track-a/tests`
