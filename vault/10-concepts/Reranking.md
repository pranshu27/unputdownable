# Reranking

**Stage:** retrieval, after fusion · **Status:** built + measured W2

## The one idea
A **bi-encoder** compresses the query and the document into one vector *each*, before they ever meet — all their interaction is a dot product. A **cross-encoder** feeds the *pair* (query, candidate) through one transformer, so every token of the query attends to every token of the candidate. It never needs to be searchable (no index, no embeddings) — it only needs to be right. So: bi-encoder retrieves (recall stage, fast), cross-encoder reorders (precision stage, slow but only on ~50 candidates).

## Shape of the stage

```text
dense hits + sparse hits -> RRF fuse -> take top-50 -> cross-encoder scores each
(query, candidate) pair -> reorder -> keep top-5
```

- Implemented as an optional seam: `core/reranker.py` (fastembed `TextCrossEncoder`, ONNX on CPU), off by default (`TRACKA_RERANK_ENABLED=false`) so the baseline stays reproducible.
- Model: `BAAI/bge-reranker-base` — the plan said *Large*; fastembed ships only base (recorded deviation).
- Raw outputs are logits (relevant ≫ 0, irrelevant ≪ 0): sanity direction-check before trusting: relevant doc scored +3.07, irrelevant −10.19.

## Latency intuition
Rerank cost = candidates × pairs-time. Warm CPU call on 2 pairs ≈ 15 ms ⇒ 50 pairs ≈ hundreds of ms on CPU — the single biggest span in the query path. At scale: batch on GPU, or a smaller reranker, or rerank fewer candidates.

## Where it breaks
- Truncation: rerankers have their own token limit — giant atomic tables arrive amputated and the reranker can only score what it sees.
- Candidate starvation: if fusion's top-50 misses the truth, no reranker can recover it (garbage in, reordered garbage out).

## Related
[[ADR-002 Hybrid Search]] · [[Chunking]] · [[Measurement Harness]]
