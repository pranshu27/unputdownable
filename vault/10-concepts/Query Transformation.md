# Query Transformation

**Stage:** retrieval, before it · **Status:** built W3 (ADR-003)

## The one idea
Retrieval failures have two sources: the corpus lacks the answer, or the *question* is malformed — compound ("fee schedule **and also** latency budget"), padded with filler ("what is", "tell me about"), or vocabulary-mismatched ("revenue" vs "net sales"). Fix the question before blaming the retriever.

## The pipeline (config-driven chain)

```text
query -> [SubQueryDecomposer] -> [RewriteTransformer] -> [HyDE] -> variants
original query + variants  ->  each retrieves (hybrid)  ->  fuse ALL lists with RRF
```

- **SubQueryDecomposer:** split on conjunctions/separators, strip filler + leading articles; fires ONLY on genuinely compound queries (a simple query is not its own variant).
- **RewriteTransformer:** deterministic cleanup + small synonym map (<0.1 ms).
- **HyDE:** needs a generator (LLM) — ships as a seam that degrades to a no-op until W7.
- **The safety trick:** the ORIGINAL always retrieves too and keeps its vote in fusion — a bad variant can only *add* candidates, never steer away.

## Landed lessons from building it
- A regex chain needs article-stripping (`"what is the fee schedule"` → "the fee schedule" ≠ "fee schedule") and trailing-punctuation stripping — three test failures before the rules were honest.
- Fusing variant lists costs n+1 retrievals — bounded by enabling only strategies that fire.

## Related
[[ADR-002 Hybrid Search]] · [[RRF]] · [[Self-RAG]]
