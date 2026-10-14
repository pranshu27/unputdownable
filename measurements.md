# Measurements

Log of the 3 fixed measurement categories (quality / latency / cost) captured every Week 1–16 Day 3. These are the empirical numbers cited in interviews (see Operational Guardrails §1 in `daily-goals.md`).

| Week | Quality (Δ Recall@5 / eval delta) | Latency (TTFT + TPOT by span) | Cost ($/1k queries or VRAM/user) | Notes |
| :--- | :--- | :--- | :--- | :--- |
| 1 | Parse failure 0.0% · table corruption 0.0% (0/68) · Δ Recall@5 (hybrid−dense) = 0.0 (both 0.90, ceiling) | Ingest p95 75.2 s (10-K CPU embed bottleneck); search TTFT p50 18.2 ms / p95 59.4 ms; RRF fuse p95 0.084 ms | $0 marginal (local ONNX); ref $0.0025/1k pages embed + $0.088/1k pages storage | Week 1 Day 3 — see below |
| 2 | Recall@5 all four modes **0.92** (lexical-hard 0.90) — rerank Δ = 0 on the 290-pt ceiling · corruption 0/75 | Rerank warm ~15 ms/2 pairs → **~0.4 s per 50 pairs** (clean-box est); benchmark p50 35 s / p95 72 s CONTAMINATED (load-44 swap storm, re-measure quiet) | Rerank ≈ **$0.02/1k queries** clean est (vs $1.77 in the contaminated run); CPU-second method @ $4.7e-5/s | Week 2 — rerank stage measured; deltas still 0 at small-corpus scale |

| 3 | Δ pipeline−baseline = **0.0** (0.821 both, 28 goldens) — **no regression is the deliverable at ~zero cost**; compound goldens 0.0 in BOTH modes (metric-definition bug: all-keywords-in-one-chunk can't hold for span-chunk answers) | transform p95 **0.01 ms** · reflect p95 **0.08 ms** · pipeline overhead p50 **+0.4 ms** | added LLM tokens **0** (rule-based strategies; HyDE deferred to W7) | Week 3 — see below |

## Week 2 Day 3 — 1024-d upgrade attempt + cross-encoder rerank (Track A)

Run: `track-a/scripts/week2_benchmark.py` (full ingest run + `--skip-ingest` eval re-run) · corpus = 8 stress docs, 25 goldens · modes = dense / sparse / hybrid / hybrid+rerank (`BAAI/bge-reranker-base`, top-50 → top-5, off by default).

- **Quality:** 0.92 Recall@5 in all four modes (lexical-hard 0.90) — fusion already saturates; the reranker moved nothing ON THIS CORPUS (ceiling effect, small-corpus brute-force regime). Honest conclusion: rerank's Δ Recall needs a corpus where fusion fails — scale or harder negatives.
- **The memory lesson:** the BGE-large 1024-d upgrade (1.2 GB) was attempted first and died of swap-thrash (7.5 GB used / 165 MB free / load 44) — "the model must fit the box or you benchmark the swap file." Config-only swap stays ready (`TRACKA_EMBEDDING_MODEL`); re-run when quiet.
- **Contamination lesson:** rerank p50 35 s / p95 72 s were measured under the same system storm; the clean warm measurement is ~15 ms per 2 pairs. Quote the clean number with the caveat; re-measure on a quiet box before citing p95.
- **Cost:** rerank ≈ $0.02/1k queries (clean est); dense index 445 KB, sparse est 64 KB (sparse ≈ 14% of dense → ✅ < 20% budget).

## Week 3 Day 3 — Query transformation + reflection (Track A)

Run: `track-a/scripts/week3_benchmark.py` (reuse the 290-pt collection) · baseline = hybrid · pipeline = transform → multi-variant retrieve → fuse → reflect (rerank off in both).

- **Quality:** Δ pipeline−baseline = 0.0 (0.821 both). Compound goldens: 0.0 in BOTH — **the metric was mis-defined** (all keywords must appear in ONE chunk; compound answers span chunks). Fix queued: per-keyword hit-rate across top-k for compound queries. Honest framing: the pipeline did not help YET (rule-based decomposition is shallow, and the goldens it could win are scored by a broken metric), and it provably did not hurt.
- **Latency (the real deliverable):** transform p95 0.01 ms · reflect p95 0.08 ms · total overhead p50 **+0.4 ms** — ADR-003's control flow costs nothing until the LLM lands.
- **Cost:** added LLM tokens = 0.
- **Retries:** 0 (reflection never triggered — coverage ≥ 0.6 everywhere; the bounded retry is tested in unit tests, untested on real insufficient queries — say so honestly).

## Week 1 Day 3 — Ingestion pipeline + hybrid retrieval (Track A)

Run: `track-a/scripts/day3_benchmark.py --reset` · batch = Apple FY2023 10-K (HTML, 1.56 MB) + 2 Markdown notes + 1 plain-text transcript · dense = BGE-large-en-v1.5 (1024-d, ONNX/fastembed, CPU) · sparse = hashed bag-of-words + Qdrant IDF · fusion = RRF k=60 (from scratch) · collection rebuilt fresh.

**Quality**
- Parse failure rate: **0.0%** (0/4 docs incl. the 10-K)
- Table corruption rate: **0.0%** (0/68 tables, 737 rows preserved atomically; ADR-001 target < 5% ✅)
- Recall@5 dense-only: **0.90** (9/10 golden queries)
- Recall@5 hybrid (RRF): **0.90**
- **Δ Recall@5 (hybrid − dense): 0.0** — dense was already at 90% ceiling on this small corpus with keyword-containment ground truth; hybrid tied at ceiling rather than beating it. (ADR-002's ≥ +15% delta is re-targeted for Week 2's reranker benchmark on hard/lexical queries where dense fails — e.g. exact identifiers.)

**Latency**
- Ingest p95 per doc: **75.2 s** — dominated by the 10-K's 239-chunk CPU embedding (bge-small, ~3.3 chunks/s single-thread ONNX); the 3 lighter docs were 42–412 ms each (ADR-001 < 2 s/doc target ✅ for them; async batched embed workers = Week 2 fix)
- Ingest throughput: **0.053 docs/s** single worker (target ≥ 0.5 missed on the 10-K; parse itself is 99 ms — the bottleneck is embedding, not parsing/chunking)
- Search retrieval TTFT-equivalent: **p50 18.2 ms / p95 59.4 ms**
- Span decomposition (per-query): embed ~4–6 ms · dense retrieve ~5–11 ms · sparse retrieve ~4–9 ms (one 38.5 ms outlier) · **RRF fuse p95 0.084 ms** (ADR-002 < 50 ms target ✅ by ~600×)
- TPOT: n/a this week (no generation span yet; LLM lands Week 7)

**Cost** (local ONNX embedding ⇒ $0 marginal compute; reference prices for interview math)
- Index storage: dense 385.5 KB (251 pts × 384-d fp32) + sparse est. 55.2 KB ⇒ ~0.44 MB total ⇒ **$4.4e-5/GB-month** at $0.10/GB-mo
- Embedding tokens: **63,316** total (63k tokens for a 239-chunk 10-K + 3 docs)
- Reference $/1k pages (hosted embedding at $0.02/1M tokens, 500 tok/page): **$0.0025**
- Reference storage $/1k pages: **$0.088**
- Sparse index ≈ 14% of dense index bytes (ADR-002 < 20% target ✅)

**Run notes:** collection rebuilt fresh (384-d dense Cosine + sparse IDF); 251 points. Model note: fastembed's `TextEmbedding` doesn't ship BGE-M3; Day 3 used BAAI/bge-small-en-v1.5 (384-d) for CPU-friendly iteration — upgrade path to BGE-M3/large (1024-d) is config-only (`TRACKA_EMBEDDING_MODEL`, `TRACKA_DENSE_VECTOR_SIZE`).


