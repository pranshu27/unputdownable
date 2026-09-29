---
tags:
  - concept
  - ann
  - index
created: 2026-09-29
up: "[[Home]]"
related: "[[Embeddings]], [[Measurement Harness]]"
---
# HNSW — Hierarchical Navigable Small World

> [!abstract] Soundbite
> "HNSW buys you O(log N) search by paying memory: M edges per node and ef_search at
> query time is your recall-vs-latency dial. IVF-PQ buys the memory back with recall."

## The mental model (draw this)
- **Brute force**: compare query to every vector. Perfect recall, O(N). Fine ≤ ~10k
  points (Qdrant's `full_scan_threshold`), hopeless at 100M.
- **HNSW**: multi-layer graph. Top layers are sparse (long-range "expressway" jumps),
  bottom layer holds every node ("local streets"). Search = greedy descent: start at
  the top, walk to the closest neighbor, drop a layer when stuck. ~O(log N) distance
  computations instead of N.

## The knobs (yours: m=16, ef_construct=100, on_disk=false)
| Knob | Effect | Trade |
|---|---|---|
| `M` (edges/node) | graph connectivity | ↑ recall, ↑ RAM |
| `ef_construct` | effort building graph | ↑ recall, ↑ build time |
| `ef_search` | candidate list at query time | ↑ recall, ↑ query latency — **the runtime dial** |
| Quantization (int8/PQ) | compress vectors 4–16× | ↓ RAM, some recall loss (PQ needs rescoring) |

HNSW vs IVF-PQ in one line: **HNSW = graphs, great recall, RAM-hungry; IVF-PQ = cluster
then quantize, cheap RAM, more recall risk.**

## In this repo
- Collection config in `core/qdrant.py`: dense 384-d Cosine HNSW + sparse with IDF.
- Verify live: `curl -s localhost:6333/collections/documents | python3 -m json.tool`
- Your corpus (290 pts) never touches the graph — brute force. Don't benchmark ANN
  behavior on it; benchmark *retrieval quality* instead.

## Interview soundbite
> "HNSW trades memory for latency: upper layers let you skip most of the corpus in
> O(log N). I'd tune ef_search against a Recall@5-vs-p95 curve, not a fixed value."
