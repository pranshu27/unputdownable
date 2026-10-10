---
tags: [book, track-a]
chapter: 05
prev: "[[Ch 04 - Embeddings]]"
next: "[[Ch 06 - Retrieval & RRF]]"
---
# Ch 5 — Indexing: the tie that taught me something

The benchmark day felt like a victory lap. Hybrid retrieval, fused and tuned, versus dense-only. Golden queries. The results came back: **0.92 versus 0.92.** A perfect tie. Delta: zero.

My first reaction was disappointment - weeks of hybrid machinery, and no delta? My second reaction, after reading the config, was the actual lesson: **`full_scan_threshold = 10000`.** My collection had 290 points. Below ten thousand, Qdrant does not touch the HNSW graph at all - it brute-forces every query, exactly, every time. I had benchmarked the wrong regime. The graph - the thing hybrid fusion is supposed to *repair* when its approximation drops an exact match - had not even been switched on.

That is the honest story of the tie: not "hybrid does not help", but "at this scale nothing can help, because nothing is approximate yet." The delta will have to come from scale, or from the reranker.

The index itself, in one breath:

- **dense**: 384-d cosine under HNSW - m=16 edges per node, ef_construct=100 build effort. Think of HNSW as a city map: sparse motorways on the upper layers, every street on the bottom one, and a greedy descent from motorway to street that reaches the neighbourhood in ~O(log N) steps.
- **ef_search** - the runtime dial trading recall against latency. Always tuned against a measured curve, never a vibes-based constant.
- **payload per point**: `chunk_id`, `document_id`, `document_title`, `text`, `contextual_header`, `token_count`, `is_table`, `table_rows`, `metadata{section_path, source_format}`

> **Walk off stage with:** "The tie taught me to name the regime before celebrating or mourning a benchmark - at 290 points the index brute-forces, so the ANN story has not even started."
