# Whiteboard Drills

## Drill 1 — Ingestion pipeline from memory (Week 1 Fri · 15 min)

**Task:** on a blank surface, draw the end-to-end Track A pipeline and narrate it. No notes, no repo, no vault. Then come back here and check.

```
YOUR DIAGRAM (draw it on paper/whiteboard — paste nothing here until after)

raw doc ──▶ ??? ──▶ ??? ──▶ ??? ──▶ ??? ──▶ ???
```

**Narrate through these, in order:** format routing → parse → block stream → chunking rules → embedding → upsert → search → fusion → top-k. Name the contract at each stage (what type crosses the boundary).

**Numbers you should be able to quote without looking (from `measurements.md`):**
- Points in the collection after the complex batch: **290**
- Table corruption: **0 / 75** tables (Day 3: 0/68)
- Parse time for the 10-K: **~96 ms** — and the ingest bottleneck: CPU embedding (~60–95 s p95)
- Search lazy spans: embed ~3–9 ms · dense ~4–8 ms · sparse ~2–8 ms · **RRF fuse p95 0.03–0.084 ms**
- Recall@5 dense vs hybrid on the complex batch: **0.92 = 0.92** (Δ = 0 on a small corpus)

### Answer key — check only after drawing
`app/core/`: `ingest_service` routes by URI → `get_parser(fmt)` (Strategy) → `ParsedDocument(blocks)` → `chunk_document` (semantic packing, contextual headers, atomic tables) → `EmbeddingBackend.embed_dense/embed_sparse` → Qdrant upsert (dense 384-d Cosine + sparse IDF) → `SearchService` runs dense + sparse, `rrf.py` fuses with k=60 → top-k. Boundaries: `Block[]`, `Chunk[]`, vectors, `PointStruct`, ranked results.

## Drill 1 — MODEL ANSWER (memorize the draw order)

**Draw order (say it while drawing, 15 min):** client → API → parsers → chunker → embedder → Qdrant, with a metrics rail underneath.

1. **Client → FastAPI** (async): `/ingest` accepts upload, returns immediately (202) — ingestion is a background task; `/search` is the synchronous path.
2. **Parsers (Strategy Pattern + registry):** PDF/MD/HTML → one uniform stream of typed blocks (heading/paragraph/table); tables atomic; `section_path` on every block. Failure isolation per doc; corruption metric, not vibes.
3. **Chunker:** semantic boundaries (headings/paragraphs), contextual headers prepended ("Title > Section"), target ~250 whitespace tokens; **tables never split** — a giant table is one atomic chunk (embedding truncates, payload doesn't — say this trade-off).
4. **Embedder:** fastembed ONNX on CPU — dense bge-small-en-v1.5 (384-d), sparse = hashed bag-of-words (65,536 buckets); Qdrant's IDF modifier turns it BM25-style.
5. **Qdrant:** ONE collection, named vectors `dense` + `sparse`; HNSW (m/ef knobs) + sparse index; payload = text, section path, document id, tokens.
6. **Search path:** query → embed both → two query_points → RRF (k=60, my own 20-line function) → top-k. Cross-encoder rerank sits after fusion, OFF by default (measure before enabling).
7. **Metrics rail (the differentiator):** parse-failure rate, table-corruption rate, ingest p95 by span, Recall@5 on a golden set — "I don't ship retrieval I can't measure."

**The two honesty beats that score:** (a) "my own benchmark showed hybrid = dense on a 290-point corpus because Qdrant brute-forces below 10k points — hybrid's win is at ANN scale or via the reranker"; (b) "ingest p95 was embed-bound (parse 96 ms vs embed minutes for a 239-chunk 10-K) — measurement found the bottleneck, not intuition."

**Beat sheet (9):** 1 async ingest + sync search · 2 strategy parsers, uniform typed blocks, atomic tables · 3 semantic chunker + contextual headers · 4 tables-never-split + truncation trade-off · 5 fastembed dense+sparse · 6 one collection, named vectors · 7 RRF from scratch, rerank after fusion · 8 metrics rail · 9 the two honesty beats.

## Drill 2 — Hybrid search at 10M docs (Week 2 Fri · 30 min)

**Task:** whiteboard how the same system survives 10M docs.

**Structure the answer:** (1) capacity math first: 10M chunks × 1024-d × 4 B = ~40 GB dense alone → memory sizing decides quantization; (2) sharding: by tenant/collection, or time?; (3) ANN tuning: `m`/`ef_search` against a measured Recall@k-vs-p95 curve; quantization (int8 = 4x, PQ = 16x) only after measuring recall loss; (4) cache tiers: semantic cache (query embedding) → rerank cache → payload cache; (5) rerank in the budget: fused top-50 rerank costs ~O(50) cross-encoder calls — batched ONNX or GPU; (6) write path: async workers, upsert batching.

**Numbers to quote from this repo:** fuse 0.03-0.08 ms · rerank fitted config (MiniLM, 20 × 64-token snippets) **p50 257 ms / p95 426 ms** — inside budget · bge-reranker-base = 4.1 s at the same config (CPU budget breaker) · full-chunk rerank of 50 candidates = 16.7 s, never on CPU · cross-encoder cost quadratic in pair length (12 ms/pair @ 10 tok → 398 ms/pair @ 250 tok, measured) · 290 pts brute-force regime.

### Your diagram (draw after reading the structure)

## Drill 2 — MODEL ANSWER (the 10M-doc math, memorize)

**Open with capacity math (this is what separates senior from junior):**

```text
10M chunks x 1024-d x 4 B (fp32)  = ~40 GB dense vectors alone
+ HNSW graph edges (m=16 -> ~64 B/node) ~= 0.6 GB
+ payload (text ~250 tokens ~= 1 KB)     ~= 10 GB
+ sparse index (hashed, ~220 B)          ~= 2 GB
=> ~53 GB -> does NOT fit in a 32 GB box comfortably -> memory decides the design
```

1. **Quantization:** int8 scalar = 4x reduction (40→10 GB) with usually small recall loss — **measure Recall@k before/after on the golden set; PQ (16x) only if int8's recall drop is unacceptable.** Storage math beats vibes.
2. **Sharding:** by collection/tenant first (blast-radius isolation beats balanced shards); Qdrant clusters per collection, replication for read QPS + failover.
3. **ANN tuning:** sweep (m, ef_search) against Recall@5-vs-p95 ON MY golden set; ef_search is the live latency knob (higher ef = higher recall = higher latency).
4. **Cache tiers (hot path):** L1 semantic cache (query-embedding similarity → cached result set, threshold-tuned, TTL); L2 rerank cache ((query,chunk) pairs); L3 payload/page cache. Cache INVAL must be tied to reindex events, not just TTL.
5. **Rerank at scale:** fused top-50 → cross-encoder: my measured CPU number says ~200-400 ms for 50 pairs — at scale that's a GPU batch job (or smaller reranker, or rerank top-20). Budget it explicitly in p95.
6. **Write path:** async ingest workers, batched upserts, backpressure via queue depth metric; reindex = new collection + atomic alias switch (zero-downtime swaps).

**Beat sheet (8):** 1 capacity math ~53 GB · 2 int8 with measured recall, PQ conditional · 3 tenant-first sharding + replication · 4 (m, ef) sweep on golden set · 5 three cache tiers with invalidation rule · 6 rerank GPU/batch budget · 7 batched async writes + backpressure metric · 8 alias-switch reindex.

## Drill 3 — Enterprise KB search with context-aware filtering (Week 3 Fri · 30 min)

**Task:** design search over a 2M-doc enterprise knowledge base where permissions, freshness and department matter (HR docs visible to HR only; policy docs versioned).

**Structure:** (1) clarify: corpus, users, permission model; (2) ingestion: metadata extraction + ACL propagation at index time; (3) retrieval: pre-filter vs post-filter (pre-filter with payload indexes — our `payload_schema` TODO is exactly this), hybrid + rerank; (4) freshness: versioned docs, reindex SLA; (5) evaluation: golden set + permission-leak test (the one failure you must never have); (6) rollout + audit.
## Drill 3 — MODEL ANSWER (memorize)

**Clarify (30 s):** users/roles, doc classes (HR-restricted, versioned policies, general), freshness SLO, and the one hard rule: permission violations are not tolerable at ANY recall gain.

1. **Ingest:** extract ACL metadata at index time (owner, department, classification, effective dates, supersedes-link) — ACL is part of the document, propagated from the source system on every reindex.
2. **Indexing:** Qdrant payload indexes on the filter fields (`payload_schema` TODO — say it); dense+sparse as in Track A; versioned policies indexed as separate points with `supersedes` links, only `is_latest` filtered by default.
3. **Retrieval:** **pre-filter with payload indexes** (filter → then ANN inside the allowed set). Post-filter wastes candidates and can starve top-k; pre-filter needs the indexes. Hybrid + RRF + rerank unchanged from ADR-002; query transformation for compound questions (ADR-003).
4. **The eval that matters:** permission-leak test — run golden queries as user A, assert ZERO results from user B's docs. This is a hard CI gate, not a dashboard. Plus freshness test: edited doc retrievable within the reindex SLO.
5. **Audit:** every query logs (user, filters, returned doc ids) for compliance review.

**Beat sheet (7):** 1 the hard rule stated FIRST · 2 ACL extracted at index time · 3 payload indexes → pre-filter (say why not post-filter) · 4 versioned docs + is_latest · 5 permission-leak eval as CI gate · 6 freshness SLO test · 7 audit trail.
