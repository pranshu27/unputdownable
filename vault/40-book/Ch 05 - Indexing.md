---
tags: [book, track-a]
chapter: 05
prev: "[[Ch 04 - Embeddings]]"
next: "[[Ch 06 - Retrieval & RRF]]"
---
# Ch 5 — Indexing: Qdrant, HNSW and the brute-force cliff

Everything converges into one Qdrant collection, `documents` - 290 points, one per chunk:

- `dense`: 384-d cosine under **HNSW** (m=16, ef_construct=100) - the graph that makes "nearest
  neighbours" cost ~O(log N) instead of O(N)
- `sparse`: the hashed representation with IDF weighting
- payload: `chunk_id`, `document_id`, `document_title`, `text`, `contextual_header`, `token_count`,
  `is_table`, `table_rows`, `metadata{section_path, source_format}`

**The knob that explains a surprising result:** `full_scan_threshold = 10000`. Below it, Qdrant
brute-forces every query - which is why, on 290 points, dense retrieval was already near-ceiling
and hybrid could not beat it (both scored 0.92). At 10M points the graph takes over and the ANN
approximation losses are what hybrid fusion recovers.

**The HNSW knobs, in one breath:** `m` = edges per node (recall vs RAM), `ef_construct` = build
effort, `ef_search` = the runtime recall-vs-latency dial - always tuned against a measured curve.

> **Interview line:** "HNSW trades memory for latency via hierarchical graphs; at small corpora it
> brute-forces anyway, so I benchmark retrieval quality - not ANN behaviour - at this scale."