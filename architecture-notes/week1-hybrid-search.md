# Mental Model: Hybrid Search (HNSW + BM25 + RRF)

## HNSW (Hierarchical Navigable Small World)
- **Core Mechanism:** A multi-layered graph structure. Top layers have few nodes (fast search), bottom layers have more nodes (high precision).
- **Complexity:** $O(\log N)$ search complexity.
- **Key Parameters:**
    - `M`: Maximum number of neighbors per node.
    - `ef_construction`: Size of the dynamic list for the nearest neighbors during index creation (higher = better index quality, slower build).
    - `ef_search`: Size of the dynamic list for the nearest neighbors during search (higher = higher recall, higher latency).

## Qdrant Hybrid Search (Dense + Sparse)
- **Dense:** Semantic representation (vectors) using HNSW.
- **Sparse:** Lexical representation (BM25) using inverted index.
- **Fusion:** Reciprocal Rank Fusion (RRF).
    - **Formula:** $RRF(d) = \sum_{r \in R} \frac{1}{k + rank(d, r)}$
    - Handles ranking from different retriever sources.

## Trade-offs
| Component | Metric | Trade-off |
| :--- | :--- | :--- |
| **HNSW** | `ef_search` ↑ | Recall ↑, Latency ↑ |
| **HNSW** | `M` ↑ | Recall ↑, Memory ↑ |
| **Hybrid** | RRF | Quality (Recall@5) ↑, Latency (RRF merge) ↑ |
