---
tags: [concept, embeddings]
created: 2026-09-29
up: "[[Home]]"
related: "[[HNSW]], [[RRF]]"
---
# Embeddings — dense vs sparse

> [!abstract] Soundbite "Dense understands meaning but fails on exact identifiers; BM25 does exact match but zero paraphrase. They fail in complementary ways — that's the whole argument for hybrid."

## Dense vectors
Text → a vector (ours: **BGE-small-en-v1.5, 384-d**, via fastembed/ONNX on CPU) where *similar meaning ⇒ nearby points*. Cosine similarity is the metric.
- Strength: paraphrase, synonyms, "how does X relate to Y".
- Weakness: exact strings are noise to it — `ERR-4021`, CIK `0001874410`, `$4,535.35` mean nothing special semantically.

## Sparse vectors (BM25-style)
A vector with one dimension per term; nonzero only at observed terms. Ours: **hashed bag-of-words** (no vocab to maintain) + Qdrant's `modifier: "idf"` so rare terms weigh more. Strength: exact match. Weakness: no semantics ("car" ≠ "automobile").

## In this repo
- `core/embeddings.py` — `get_embedding_backend(settings)`, `embed_dense(texts)`, `embed_sparse(texts)` returning `{indices, values}` for Qdrant's `SparseVector`.
- Config knobs: `TRACKA_EMBEDDING_MODEL`, `TRACKA_DENSE_VECTOR_SIZE` (384 small → 1024 BGE-M3/large is a **config-only** upgrade in Week 2).
- The embedding text = `f"{contextual_header}\n\n{chunk_text}"` — the header steers the embedding, not just the reader.

## The numbers so far
| Corpus | Recall@5 dense | hybrid | Δ |
|---|---|---|---|
| Day-3 batch (251 pts) | 0.90 | 0.90 | 0.0 |
| Complex batch (290 pts) | 0.92 | 0.92 | 0.0 |

Why tied: 290 points < Qdrant `full_scan_threshold` (10k) ⇒ brute force, and bge-small matches exact numbers fine at this scale. Hybrid's win needs scale or the reranker (Week 2 benchmark on the lexical-hard queries).

## Interview soundbite
> "I embed the chunk *with its contextual header*, use hashed sparse vectors with IDF in Qdrant, and keep the model swap config-only because the encoder is an implementation detail behind the EmbeddingBackend interface."
