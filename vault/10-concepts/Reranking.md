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

## Latency intuition — MEASURED, and it killed my first estimate
Rerank cost = candidates × per-pair cost, and per-pair cost is **quadratic in sequence length**: measured on CPU ONNX, 12 ms/pair at ~10 tokens vs **398 ms/pair at ~250 tokens — 33×**. My first estimate ("warm 15 ms per 2 short pairs → 0.4 s per 50") was extrapolated from short pairs and was ~40× off: reranking 50 full chunks took **16.7 s**. Consequences:
- Rerankers are **snippet scorers**: truncate candidates to a snippet window (`TRACKA_RERANK_SNIPPET_TOKENS`); the payload still carries the full chunk downstream — truncation affects scoring, not data.
- Model size matters ~linearly-to-squared: `bge-reranker-base` (278M) at 20×64-token config = 4.1 s; `ms-marco-MiniLM-L-6-v2` (22M) at the same config = **208–257 ms warm** — the fitted, budget-meeting config (p95 426 ms < 500 ms budget; $0.014/1k queries).
- First query carries model load (~5 s) — warm the model at service startup, and quote WARM numbers.

## Where it breaks
- Truncation: rerankers have their own token limit — giant atomic tables arrive amputated and the reranker can only score what it sees.
- Candidate starvation: if fusion's top-50 misses the truth, no reranker can recover it (garbage in, reordered garbage out).

## Related
[[ADR-002 Hybrid Search]] · [[Chunking]] · [[Measurement Harness]]
