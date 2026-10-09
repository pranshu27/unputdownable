---
tags: [book, track-a]
chapter: 04
prev: "[[Ch 03 - Chunking]]"
next: "[[Ch 05 - Indexing]]"
---
# Ch 4 — Embeddings: two representations

One representation is never enough. The pipeline embeds every chunk **twice**:

- **Dense** - BGE-family ONNX vectors (384-d today, 1024-d BGE-M3/large is a config swap). Captures
  *meaning*: paraphrase, synonyms. Fails at exact strings - `ERR-4021`, CIK `0001874410`, `$4,535.35`
  are just noise to it.
- **Sparse** - hashed bag-of-words with IDF weighting. Captures *exact terms*. Fails at paraphrase.

They fail in complementary directions - which is the entire argument for hybrid retrieval (Ch 6).

**Details that matter:** the contextual header is embedded *with* the chunk text; the sparse index
hashes into 65,536 buckets (collisions accepted by design) and Qdrant applies IDF so rare terms win.

> **Interview line:** "Dense understands meaning but drops exact identifiers; BM25 does exact match
> but zero paraphrase. Complementary failure modes - so I run both and fuse."