---
tags: [build-log, log]
created: 2026-09-29
updated: 2026-10-05
---
# 📓 Build Log

One entry per work day. **Newest first.** Use `90-templates/tpl-daily-log`.
Rule of thumb: 5 bullets max per day — what was built, what was measured, what was learned, what's next.

---

## 2026-10-05 · DSA drill — prefix sums & sliding window (Week 1 Thu catch-up)
- **Built:** 3 drill notebooks in `dsa/` — LC 560 ✅ (fuzz 200/200), LC 974 ✅ (fuzz 300/300, hand-derived 7), LC 3 ✅ (fuzz 500/500, `max(left, last[c] + 1)` trap) — plus `dsa/patterns.md` (2 pattern families, skeletons, 7 cross-cutting traps) and `.vscode/settings.json` with AI completions off.
- **Built (leftover scaffolds):** `interview/` — `lld-extensible-document-parser.md` (25-min spoken drill: 6-beat structure, 10-point rubric, reference mapped to `parsers.py`), `whiteboard-drills.md` (ingestion-from-memory + answer key, plus the 10M-doc drill for Week 2 Fri), `star-stories.md` (STAR template with metric slots, STAR 1 + company-track prompts), `question-bank.md` (seeded with 10).
- **Measured:** LC 560 optimal **2.6 ms** at n=20,000 vs brute 5,532 ms; LC 974 optimal **2.2 ms** at n=20,000 vs brute 89.5 ms at only n=2,000; LC 3 fixed version fuzz 400/400 over letters+digits+symbols+**spaces**.
- **Learned:** (1) the **pair lens** — a window is a pair of moments, equal state closes it, n moments at a state ⇒ 1+2+…+(n−1) windows; (2) the **family switch** — monotone validity (no-duplicates) ⇒ sliding window, non-monotone (sum = k with negatives) ⇒ count pairs; (3) **input opacity** — never `split()`/normalize, spaces are characters and `[0]*26` can't index one.
- **Open drill items:** spoken LLD — Extensible Document Parser (narrate `track-a/src/app/core/parsers.py`).
- **Next:** Week 2 Day 1 · Mon Oct 5 READ & DESIGN — RRF paper + BGE-M3 paper + cross-encoder reranking explainer → extend ADR-002 with the rerank stage (top-50 → top-5 + latency budget).

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
