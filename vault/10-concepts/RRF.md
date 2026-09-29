---
tags: [concept, fusion, adr-002]
created: 2026-09-29
up: "[[Home]]"
related: "[[Embeddings]], [[ADR-002 Hybrid Search]]"
---
# RRF — Reciprocal Rank Fusion (implemented from scratch)

> [!abstract] Soundbite
> "RRF fuses ranked lists using only ranks — 1/(k+rank) — so dense cosine and BM25's
> unbounded scores never need normalization. k=60 dampens a single list's top result."

## The formula
$$\text{score}(d) = \sum_{\text{lists } L} \frac{1}{k + \text{rank}_L(d)}, \quad k=60$$

A doc ranked r in a list contributes `1/(60+r)`. Sum over both lists (dense, sparse).

## Why rank-based, not score-based
- Cosine ∈ [0,1]; BM25 is unbounded (can be 20+). Adding raw scores mixes incompatible units.
- Min-max normalizing per query works but is unstable (outliers, all-same scores).
- RRF needs only ordinal information → scale-free, dead simple, hard to beat.

## Why k=60
Dampens the head: with k=0, rank #1 contributes 30× rank #30; with k=60, rank #1
contributes 1.0 and rank #30 contributes 0.33 — consensus across lists dominates
over a single list's confidence. (Cormack et al. 2009; k tuned empirically, 60 robust.)

## In this repo
- `core/rrf.py` — from scratch on purpose (whiteboard-flex). Be able to write it cold:
  build rank maps from both result lists, accumulate `1/(k+rank)` into a dict, sort.
- `core/search_service.py` — dense query → sparse query → fuse → top-k; spans timed
  per stage (embed / dense / sparse / fuse).
- Measured fuse p95 = **0.084 ms** vs 50 ms budget (~600× headroom).

## When it's NOT enough
RRF fuses lists; it can't fix structurally corrupted chunks (two-column interleaving),
and it can't re-order within semantic quality — that's the **cross-encoder reranker**
(Week 2: top-50 → top-5). RRF is cheap recall ensembling; reranking is precision.

## Interview soundbite
> "I implemented RRF from scratch, not as a library call: score = Σ 1/(k+rank), k=60.
> Rank-only fusion means no score normalization across retrievers — and fusion costs
> me 0.08 ms p95 against a 50 ms budget."
