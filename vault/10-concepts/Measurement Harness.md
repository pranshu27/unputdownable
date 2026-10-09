---
tags: [concept, measurement, quality-latency-cost]
created: 2026-09-29
up: "[[Home]]"
related: "[[RAG Overview]]"
---
# Measurement Harness — quality / latency / cost, every Day 3

> [!abstract] Soundbite "Every claim I make has a number attached. I run the same three-category harness every week: quality, latency, cost. It's how I caught that my bottleneck is CPU embedding, not parsing — parse is 99 ms, embed is 60 s."

## The fixed ritual (daily-goals.md, Operational Guardrails #1)
Every Week 1–16 Day 3 captures **exactly these three categories**, logged to repo `measurements.md`. The numbers become interview STAR stories.

## Category 1 — Quality
| Metric | How | Day-3 / complex-batch result |
|---|---|---|
| Parse failure rate | docs that errored in the pipeline / total | 0.0% (0/4) · 0.0% (0/8) |
| Table corruption rate | every source cell must survive into exactly one chunk | 0/68 · **0/75** |
| Recall@5 dense vs hybrid | golden queries, keyword-containment ground truth | 0.90=0.90 · 0.92=0.92 |
| Δ Recall@5 (lexical-hard) | exact-identifier queries (`ERR-4021`, CIK, `$4,535.35`) | 0.9 = 0.9 — small-corpus ceiling |

⚠️ Methodology honesty: keyword-containment ground truth is *easy* — a corpus under 10k points brute-forces and both retrievers saturate. The null Δ is a finding, not a failure: hybrid's advantage needs scale or reranking (Week 2).

## Category 2 — Latency
| Metric | Day 3 | Complex batch | Diagnosis |
|---|---|---|---|
| Ingest p95 | 75.2 s | 95.2 s | the 10-K's 239 chunks on CPU (~3.3 chunks/s) — **embed-bound** |
| Parse time (10-K) | ~99 ms | 96 ms | parsing is NOT the problem |
| Search TTFT p50 / p95 | 18.2 / 59.4 ms | ~11 ms / — | spans: embed 3–9, dense 4–8, sparse 2–8 |
| RRF fuse p95 | 0.084 ms | 0.03 ms | fusion ~free (budget 50 ms) |
| TPOT | n/a | n/a | no generation span until the LLM lands (Week 7) |

Fix queued for Week 2: async batched embedding workers.

## Category 3 — Cost
Local ONNX ⇒ $0 marginal compute; capture *reference* prices for interview math:
- Embedding: 63k tokens (Day 3) → $0.0025/1k pages @ $0.02/1M tokens, 500 tok/page
- Storage: ~0.44 MB index → $0.088/1k pages @ $0.10/GB-mo
- Sparse index ≈ 14% of dense bytes (target < 20% ✅)

## Where the harness lives
- `track-a/scripts/day3_benchmark.py` — Day-3 record (frozen, don't rewrite history)
- `track-a/scripts/complex_batch.py` — 8-doc batch, lexical-hard goldens, per-query breakdown
- Results JSON → `measurements.md` table (Week column)

## Interview soundbite
> "I measure three fixed categories every week — quality (parse/corruption/recall), latency (p95 by span), cost ($/1k pages) — and my harness told me something uncomfortable: hybrid didn't beat dense on a tiny corpus. That's a measurement methodology insight, and it's why Week 2 benchmarks on lexical-hard queries."
