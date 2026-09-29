---
tags: [moc, vault-home]
created: 2026-09-29
updated: 2026-09-29
---
# 🏠 Home — Track A Agentic RAG Vault

Map of Content for everything understood & built so far. Each note ends with an
**Interview soundbite** — the line to say out loud.

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

## 🧭 Current position (Week 1 of 16)
- ✅ Day 1 Read & Design · ✅ Day 2 Build · ✅ Day 3 Integrate & Measure · ✅ complex-doc stress batch
- ⏭️ Next: Thu Oct 1 DRILL (DSA two-pointer/sliding-window + spoken LLD) → Week 2 (BGE-M3, batched embed workers, reranker top-50→top-5 on lexical-hard queries)

## 🚧 Open items
- [ ] Point live tests (test_services.py, test_qdrant_integration.py) at a scratch collection — they pollute `documents`
- [ ] Commit complex docs + complex_batch.py
- [ ] Async batched embedding workers (ingest p95 75→95s bottleneck)
