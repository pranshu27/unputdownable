---
tags: [book, track-a]
chapter: 06
prev: "[[Ch 05 - Indexing]]"
next: "[[Ch 07 - Measurement]]"
---
# Ch 6 — Retrieval: run both, fuse by rank

At query time the question is embedded twice and both stores are queried:

1. dense query -> ranked list by cosine
2. sparse query -> ranked list by BM25/IDF
3. **RRF fuse: `score(d) = sum 1 / (60 + rank_L(d))`** - implemented from scratch (`core/rrf.py`)

**Why rank-based:** cosine lives in [0,1], BM25 is unbounded - adding raw scores mixes incompatible
units. Ranks need no normalisation. k=60 dampens the head so consensus across lists dominates one
list's confidence.

**Measured:** fuse p95 = **0.03-0.084 ms** against a 50 ms budget (~600x headroom). Fusion is free.

**The honest lesson:** on the 290-point corpus dense = hybrid = 0.92 Recall@5, Delta = 0. Not a
failure - a diagnosis: small corpora saturate, and hybrid's win shows at ANN scale or through the
reranker (Ch 10). The lexical-hard golden queries (exact identifiers) are the instrument.

> **Interview line:** "RRF, from scratch: rank-only fusion with k=60 - no score normalisation, and
> it costs 0.08 ms p95."