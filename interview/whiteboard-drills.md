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

## Drill 2 — Hybrid search at 10M docs (Week 2 Fri · 30 min, after the reranker lands)

**Task:** whiteboard how the same system survives 10M docs: sharding, ANN tuning (`m`/`ef_search`), quantization choice, cache tiers, and what changes in the latency budget once a cross-encoder reranker is in the path. Placeholder — do it after Week 2's reranker benchmark so you can quote real numbers.
