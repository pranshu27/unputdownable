# Self-RAG

**Stage:** retrieval control flow · **Status:** rule-based proxy built W3 (ADR-003); LLM critic W7

## The one idea
Don't trust retrieval silently — **reflect on it**. Self-RAG's paper does this with reflection tokens (an LLM that grades its own context: *Is this sufficient? Support? Useful?*). Before an LLM exists, the CONTROL FLOW can still exist:

```text
retrieve -> reflect: does coverage of query keywords >= threshold in the top results?
  sufficient -> done
  not        -> ONE bounded retry: retrieve with decomposed sub-queries,
                fuse everything, re-check (then stop, sufficient or not)
```

## Why rule-based first is honest, not a hack
The critic is a seam (`_reflect`). The retry loop, the budget, the spans and the outcome shape are identical regardless of who sits in the seat — a rule proxy today, an LLM in Week 7. What the proxy CANNOT judge: semantic sufficiency (paraphrase coverage) — that is exactly what the LLM adds.

## The cost side
Each retry doubles retrieval cost for insufficient queries. Bounded to ONE retry — unbounded loops are how rewrite systems eat their own latency budget.

## Related
[[Query Transformation]] · [[ADR-002 Hybrid Search]] · [[Measurement Harness]]
