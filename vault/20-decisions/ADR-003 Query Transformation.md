# ADR-003 Query Transformation

## Decision (Oct 2026)
Query transformation is a **pluggable, config-driven chain** before retrieval:
sub-query decomposition + rule-based rewrite (LLM-free), HyDE as a generator seam
(no-op until W7); variants + original fuse through the existing RRF; Self-RAG-style
**rule-based reflection** (keyword coverage ≥ 0.6) triggers ONE bounded retry.

## Why
- Retrieval failures split: corpus-side (fixed by hybrid+rerank in ADR-002) vs question-side.
- Compound questions retrieve poorly as one query; decomposed sub-queries + fusion fix it.
- The original query always keeps its vote — variants can only add candidates.

## Rejected
- Transform every query blindly (latency + regression risk on short queries).
- Full Self-RAG with LLM critic now (no generator until W7; seam-first instead).
- Concatenating variant results without fusion (duplicates distort ranking).

## Expected measurements (Week 3) — MEASURED
- Δ Recall@5 pipeline−baseline = **0.0** (0.821 both) — no regression is the deliverable at ~zero cost.
- Compound goldens: 0.0 in BOTH modes — **metric-definition bug** (all-in-one-chunk can't hold for
  span-chunk answers); fix: per-keyword hit-rate across top-k.
- Latency: transform p95 0.01 ms · reflect p95 0.08 ms · overhead p50 +0.4 ms ✅ (< 1 ms).
- Cost: 0 LLM tokens ✅ (rule-based; HyDE lands W7).

## Interview soundbite
> "I built the query-transformation control flow LLM-free — decomposition and rewrite as
> config-driven chain stages, reflection as a coverage proxy with one bounded retry — so the
> Week-7 LLM swaps into a seam that already has spans, budgets and tests."
