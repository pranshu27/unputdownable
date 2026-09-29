---
tags: [build-log, log]
created: 2026-09-29
updated: 2026-09-29
---
# 📓 Build Log

One entry per work day. **Newest first.** Use `90-templates/tpl-daily-log`.
Rule of thumb: 5 bullets max per day — what was built, what was measured, what was learned, what's next.

---

## 2026-09-29 · Week 1 Day 3 (evening) — Complex-doc stress batch
- **Built:** 4 stress docs in `track-a/data/`: ACME 10-K (colspan/rowspan, XBRL, negatives),
  incident postmortem (deep hierarchy, exact IDs), scanned-OCR lease, two-column paper.
- **Built:** `scripts/complex_batch.py` — 8-doc batch, 25 goldens incl. lexical-hard;
  results → `scripts/complex_results.json`. Qdrant now 290 pts, strays gone.
- **Measured:** 0/8 parse failures · 0/75 table corruption · Recall@5 dense 0.92 = hybrid 0.92
  (lexical-hard 0.9/0.9) · ingest p95 95.2 s (embed-bound).
- **Learned:** small corpus (< 10k pts ⇒ brute force) saturates both retrievers →
  Δ Recall@5 belongs to the Week-2 reranker benchmark; documented in [[ADR-002 Hybrid Search]].
- **Next:** DSA drill Thu; Week 2: BGE-M3, batched embed workers, reranker.

## 2026-09-29 · Week 1 Day 3 — Integrate & Measure
- **Built:** ADR-001 pipeline end-to-end: `parsers.py` (Strategy Pattern) → `chunker.py`
  (semantic + contextual headers + atomic tables) → `embeddings.py` → `ingest_service.py`.
- **Built:** ADR-002 hybrid search: dense + hashed-sparse(BM25/IDF) + `rrf.py` from scratch.
- **Measured (Day-3 run, `day3_benchmark.py --reset`):** parse failure 0% · table
  corruption 0/68 · Recall@5 0.90/0.90 · ingest p95 75.2 s (embed-bound) · search TTFT
  p50 18.2 ms · RRF fuse p95 0.084 ms · $ math baseline logged in `measurements.md`.
- **Learned:** parse is 99 ms; the 10-K's CPU embedding dominates ingest → async batched
  embed workers queued for Week 2.

## 2026-09-28 · Week 1 Day 2 — Build
- FastAPI async skeleton + Pydantic v2 schemas (`main.py`, `api/routes/`, `schemas/`).
- Qdrant v1.19.1 via docker-compose, dense+sparse collection config (`core/qdrant.py`);
  aligned server/client versions; live integration tests (auto-skip when down).
- Learned: graceful lifespan — app boots even when Qdrant is down; `/health` reports it.

## 2026-09-28 · Week 1 Day 1 — Read & Design
- HNSW paper skim → mental model: hierarchical graph, O(log N), M / ef_construct /
  ef_search knobs, HNSW-vs-IVF-PQ memory/recall trade. See [[HNSW]].
- Wrote ADR-001 (parsing/chunking) + renumbered hybrid search to ADR-002.
