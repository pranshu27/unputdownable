---
tags: [book, track-a, qdrant, first-timer]
chapter: 05b
prev: "[[Ch 05 - Indexing]]"
next: "[[Ch 06 - Retrieval & RRF]]"
---
# Ch 5b — Qdrant for first-timers (the database under the pipeline)

**What Qdrant actually is:** a database whose rows are *vectors*. A **collection** is the table, a **point** is the row: an id, one or more vectors, and a JSON **payload** you can filter on. That is 90% of the mental model.

## Our real deployment (2 minutes to stand up)

`track-a/docker-compose.yml` runs `qdrant/qdrant:v1.19.1` with port **6333** (REST) and **6334** (gRPC), storage on a named volume `qdrant_storage`. Version is pinned - and earlier we aligned the python client to the same version, which is the first gotcha: client/server version mismatches are the #1 Qdrant support question.

## Look at the real collection (live commands)

```bash
curl -s http://localhost:6333/collections | jq
# -> {"result":{"collections":[{"name":"documents"}]}}

curl -s http://localhost:6333/collections/documents | jq
```

The real response tells you everything about the design:

- `vectors.dense`: 384 dims, Cosine (BGE-small)
- `sparse_vectors.sparse`: modifier **IDF** (rare terms weighted up)
- `hnsw_config`: m=16, ef_construct=100
- `full_scan_threshold`: 10000 - below this, brute force (the reason Delta=0 on 290 points)
- `points_count`: 290 (one point per chunk)
- `payload_schema`: {} - we filter nothing yet; indexes for payload fields are a TODO

## Writing: a point is id + vectors + payload

```python
from qdrant_client import models
client.upsert("documents", points=[models.PointStruct(
    id=str(chunk.chunk_id),                 # ids must be UUIDs or unsigned ints
    vector={"dense": dense_vec,             # named vector 1
            "sparse": models.SparseVector(indices=[...], values=[...])},  # named vector 2
    payload={"chunk_id": ..., "text": ..., "is_table": ..., "table_rows": ...},
)])
```

**Named vectors are the key idea:** one point carries BOTH the dense and the sparse vector, and at query time you choose which to use with `using="dense"` or `using="sparse"`. That single feature is what makes hybrid search possible in one store.

## Reading: query, scroll, count

```python
res = client.query_points("documents", query=question_vec, using="dense", limit=5)
pts, offset = client.scroll("documents", limit=250, with_payload=True, with_vectors=False)
client.count("documents", exact=True)
```

- `query_points` = ANN search over the chosen named vector; `using` picks the space
- `scroll` = browse everything (that is how we audited the 290 points and found the 9 test leftovers)
- `count(exact=True)` = honest number for the scoreboard
- filtering on payload (e.g. `is_table=true`) needs **payload indexes** at scale - our `payload_schema` is empty, so that is a TODO, not a mystery

## First-timer gotchas (all ones we hit or dodged)

1. **Dims must match the collection** - 384-d vectors into a 1024-d collection fail. Our `ensure_collection` deletes and recreates on a dims mismatch on purpose.
2. **Sparse vectors are `{indices, values}` pairs**, not dicts of terms - the hashing happens in our embedder, IDF in Qdrant.
3. **`full_scan_threshold`** - below 10k points there is no ANN at all; benchmarks at small corpora say nothing about ANN behaviour.
4. **Point ids are constrained** - UUIDs or unsigned ints; we use chunk UUIDs.
5. **REST for humans (6333), gRPC for speed (6334)** - the python client speaks both.

> **Interview line:** "Qdrant stores one point per chunk with two named vectors - dense cosine and sparse IDF - plus the payload that carries the structured table rows, so exact queries and semantic queries hit the same store."
