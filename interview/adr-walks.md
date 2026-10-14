# ADR Walks — memorize (the 2-minute spoken defense of each decision)

## ADR-002 walk — Hybrid Search + the rerank stage

**The 30-second version.** "Dense retrieval catches paraphrase, sparse catches exact identifiers — neither survives alone, so I fuse both with RRF I wrote from scratch: score = Σ 1/(k+rank), k=60, rank-only, no score normalization. Then a cross-encoder reranks the fused top-50 down to top-5 — it reads query and candidate together, which a bi-encoder can never do. Both stages sit behind config seams, and the reranker ships OFF by default because I measure before I enable."

**The numbers, in speaking order.**
1. "My harness showed Recall@5 = 0.92 across ALL four modes — dense, sparse, hybrid, hybrid+rerank — and Δ = 0."
2. "The honest reason: 290 points is below Qdrant's `full_scan_threshold` of 10k — everything brute-forces exactly, so both retrievers saturate. Hybrid's win condition is ANN scale or reranker quality — NOT small-corpus fusion."
3. "Rerank latency taught me the sharpest lesson of the build: cross-encoder cost is QUADRATIC in pair length — measured, 12 ms per pair at ~10 tokens versus 398 ms at ~250 tokens, 33×. Reranking 50 full chunks took 16.7 seconds; my first 'estimate' from short pairs was 100× off."
4. "So I fitted the config to the budget: fastembed's small cross-encoder — ms-marco-MiniLM, 22M params — reranking 20 candidates truncated to 64-token snippets: p50 257 ms, p95 426 ms, inside my 500 ms budget, at $0.014 per 1k queries. The big bge-reranker-base at the same config is 4.1 seconds — that one needs a GPU."
5. "Table integrity through all of it: 0/75 corrupted, including a 42-row balance sheet."

**If pushed — 'doesn't truncating to 64 tokens hide answers?'** "I tested that hypothesis — it's false on this corpus: the one golden that misses does so in EVERY configuration, including the no-rerank no-truncation baseline. The miss is a corpus-coverage fact, not a snippet artifact. And structurally: the snippet decides the ORDER, the payload still carries the full chunk downstream — truncation costs scoring fidelity on tail content, not data."

**If pushed — 'so the reranker is useless?'** "On this corpus, at this size, yes — and that's a measurement, not an excuse. The reranker earns its 0.4 s when fusion's top-50 ordering is wrong at the top: overlapping-doc corpora, semantic-vs-exact vocabulary gaps, or at ANN scale where approximation loss makes rank-1≠best. That's a Week-4+ re-benchmark at scale, and the seam means I flip one env var."

**If pushed — 'why RRF over normalized weighted sum?'** "Scores across systems don't share a scale — cosine ∈ [−1,1]-ish, BM25 unbounded, and a model swap silently changes both. Ranks are universal. Weighted RRF exists when I need to bias a leg — I built `weighted_rank_fusion` — but with k=60 a weight must beat a 61/62 rank-gap to flip a top pair; the damping is strong."

**Beat sheet (10):** 1 dense+sparse one-liner · 2 RRF formula + k=60 + rank-only · 3 cross-encoder reads pairs together · 4 top-50→top-5 · 5 0.92 all modes + Δ=0 · 6 brute-force-below-10k honesty beat · 7 quadratic-in-pair-length: 12 ms@10 tok → 398 ms@250 tok · 8 fitted config: MiniLM 20×64 → p50 257 / p95 426 ✅ (bge-base 4.1 s = GPU) · 9 $0.014/1k · 10 truncation-hypothesis disproof (baseline also misses) + ordering-insurance stance.

## ADR-003 walk — Query Transformation + Self-RAG reflection

**The 30-second version.** "Retrieval failures split in two: the corpus lacks the answer, or the question is malformed — compound, filler-padded, vocabulary-mismatched. ADR-002 fixed the corpus side; ADR-003 fixes the question side with a config-driven transformation chain: sub-query decomposition and rule-based rewrite — both LLM-free — plus HyDE as a seam that vetoes until the Week-7 LLM lands. Variants and the original all retrieve, everything fuses through the same RRF. After retrieval, a Self-RAG-style reflection — rule-based coverage proxy — can trigger exactly ONE bounded retry with decomposed sub-queries."

**The numbers.**
1. "Transform p95 = 0.01 ms, reflection p95 = 0.08 ms, total pipeline overhead p50 = +0.4 ms — the control flow is free until the LLM arrives."
2. "Δ Recall pipeline−baseline = 0.0 on 28 goldens (0.821 both) — and that IS the deliverable: no regression at zero cost, with the seam ready for the LLM."
3. "The honest bug: my compound goldens scored 0.0 in BOTH modes because the metric required every keyword in ONE chunk — compound answers span chunks by nature. Fix: per-keyword hit-rate across top-k. Measure the metric before trusting the delta — that's the meta-lesson."
4. "Zero LLM tokens added; retries fired 0 times in the run — the bounded retry is unit-tested, not yet exercised on real insufficient queries."

**If pushed — 'why not full Self-RAG now?'** "Full Self-RAG's critic is an LLM — I don't have a generator until Week 7. What I built today is the CONTROL FLOW: sufficiency check, bounded retry, spans and outcome shape — the LLM critic later swaps into the `_reflect` seam without touching the pipeline. What the rule proxy can't judge — paraphrase-level sufficiency — is exactly what the LLM adds."

**If pushed — 'when does transformation hurt?'** "A bad rewrite steers retrieval. My safety net: the original always retrieves and keeps its RRF vote — variants only ADD candidates. And decomposition only fires on genuinely compound queries — a simple query gets zero variants."

**Beat sheet (10):** 1 two-sources-of-failure split · 2 chain: subquery/rewrite/hyde, config-driven · 3 HyDE veto seam (W7) · 4 variants+original fused via RRF · 5 reflection = coverage proxy, ONE bounded retry · 6 +0.4 ms / 0.01 / 0.08 spans · 7 Δ=0.0 as deliverable · 8 compound-metric bug honesty beat · 9 zero tokens, retries 0 · 10 LLM-swaps-into-seam stance.
