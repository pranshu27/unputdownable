---
tags: [moc, vault-home]
created: 2026-09-29
updated: 2026-09-29
---
# 🏠 Home — Track A Agentic RAG Vault

Map of Content for everything understood & built so far. Each note ends with an **Interview soundbite** — the line to say out loud.

**Operating agreement:** [[Working Agreement]] — my role, the session loop, accountability rules, and the 3-month trajectory.

## 🗺️ The Journey (read in this order)
1. [[RAG Overview]] — why any of this exists
2. [[Chunking]] — ADR-001: parsers → blocks → semantic chunks (atomic tables)
3. [[Embeddings]] — dense vs sparse, and why you need both
4. [[HNSW]] — how "find nearest" is fast, and its tuning knobs
5. [[RRF]] — fusing two ranked lists without score normalization
6. [[Measurement Harness]] — quality / latency / cost, every Day 3

## 📐 Decisions (ADR summaries)
- [[ADR-001 Parsing and Chunking]]
- [[ADR-002 Hybrid Search]]
- Full records: `adr/001-…md`, `adr/002-…md` in repo

## 📖 The Book (chapterwise mental map)
- [[Book]] - the complete Track A flow in 17 short chapters; **3-minute recall = Ch1 + Ch6 + Ch7**

## 🏗️ Design docs (maintained)
- [[HLD - Track A Agentic RAG]] - components, data flow, budgets, scaling, failure domains
- [[LLD - Ingestion and Retrieval]] - modules, interfaces, data models, algorithms, tests, debt
- LLD interview drill (trace in progress): `interview/lld-extensible-document-parser.md`

## 📓 Build Log
- [[Build Log]] — one entry per work day (update ritual below)

## 🔁 Daily Update Ritual (do this after EVERY work session)
1. Open [[Build Log]], add an entry at the TOP using `90-templates/tpl-daily-log`.
2. Any NEW concept learned → new note in `10-concepts/` from `tpl-concept`, link it here.
3. Any decision made → new note in `20-decisions/`, cross-link the ADR file.
4. Numbers captured → check they also landed in repo `measurements.md`.
5. Update `updated:` frontmatter on touched notes. Links keep the graph alive — wiki-link aggressively (`[[Chunking]]`, not plain text).

## 🔗 Repo pointers
- Repo root: `/Users/pranshu/Desktop/unputdownable`
- Code: `track-a/src/app/core/` (parsers, chunker, embeddings, rrf, search, ingest)
- Benchmarks: `track-a/scripts/day3_benchmark.py`, `track-a/scripts/complex_batch.py`
- Results: `track-a/scripts/day3_results.json`, `scripts/complex_results.json`, `measurements.md`
- Interview prep leftovers: `interview/` (LLD drill · whiteboard drills · STAR stories + company track · question bank)
- Pattern ledger (revise from here): `dsa/patterns.md` · DSA notebooks: `dsa/*.ipynb`

## 🧭 Current position (Week 2 of 16 · Mon Oct 5)
- ✅ **Week 1 complete:** Day 1 Read & Design · Day 2 Build · Day 3 Integrate & Measure · complex-doc stress batch
- ✅ **DSA drill (Week 1 Thu catch-up):** LC 560 ✅ · LC 974 ✅ · LC 3 ✅ — revise from `dsa/patterns.md` (2 families + 7 traps)
- ⏭️ **Next:** Week 2 Day 1 READ & DESIGN — RRF paper + BGE-M3 paper + cross-encoder explainer → extend ADR-002 with the rerank stage (top-50 → top-5 + latency budget)

## 🚧 Open items
- [ ] **Week 1 leftovers (Thu/Fri)** — LLD drill · whiteboard-from-memory · STAR 1 · company track · bank +10 → `interview/README.md`
- [ ] Point live tests (test_services.py, test_qdrant_integration.py) at a scratch collection — they pollute `documents`
- [ ] Commit `dsa/` (3 notebooks + `patterns.md`) + decide on `.vscode/`
- [ ] Async batched embedding workers (ingest p95 75→95s bottleneck)
- [ ] Week 2: BGE-M3 (1024-d) swap + BGE-Reranker-Large, benchmarked on the lexical-hard goldens
