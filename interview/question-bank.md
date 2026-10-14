# Question Bank

Format: **question → answer skeleton → where the detail lives.** Rehearse the skeleton out loud (30–60 s), then check the link. Bank size target: +10 per MOCK & BANK day. Current: **10 seeded** (Week 1 Fri ✅ pending your pass over them).

## RAG / system design
1. **Walk me through your ingestion pipeline end-to-end.** → route by format → Strategy parser → typed blocks → semantic chunking + contextual headers + atomic tables → dense + sparse embed → upsert. | `vault/10-concepts/Chunking.md`
2. **How do you know your chunking is correct?** → I don't assert it, I measure it: every source table cell must survive into exactly one chunk → 0/75 tables corrupted. | `vault/10-concepts/Measurement Harness.md`
3. **Why hybrid search instead of dense-only?** → dense loses exact identifiers (codes, CIKs, part numbers); sparse/BM25 loses paraphrase; they fail complementarily → fuse. | `vault/10-concepts/Embeddings.md`
4. **Explain RRF and why it's rank-based.** → `score = Σ 1/(k+rank)`, k=60; cosine vs unbounded BM25 have incompatible scales, ranks don't need normalization; measured fuse p95 ≈ 0.03–0.08 ms. | `vault/10-concepts/RRF.md`
5. **What's your ingest bottleneck, and how would you fix it?** → not parsing (~96 ms); CPU embedding dominates (60–95 s p95 for a 239-chunk 10-K) → batched async embed workers, then GPU/ONNX session tuning. | Build Log 2026-10-05
6. **How would this survive 10M documents?** → sharding by collection/tenant, ANN tuning (`m`, `ef_search`) against a recall-vs-p95 curve, quantization (int8/PQ + rescoring), semantic cache tier. | `vault/10-concepts/HNSW.md` (extend in Week 2 Fri)

## DSA patterns
7. **Count subarrays summing to k.** → hash the prefix sum; look up `pre − k`; seed `{0:1}`; lookup before insert. | `dsa/subarray-sum-equals-k.ipynb`
8. **Count subarrays whose sum is divisible by k.** → same skeleton, new unit: hash `pre mod k`; equal remainders bracket a multiple-of-k stretch; n moments at a remainder ⇒ 1+2+…+(n−1) windows. | `dsa/subarray-sums-divisible-by-k.ipynb`
9. **Longest substring without repeating characters.** → sliding window + last-seen index map; `left = max(left, last[c]+1)` (never let `left` move backwards — the `"abba"` trap). | `dsa/longest-substring-without-repeating-characters.ipynb`
10. **When is a sliding window invalid?** → when validity isn't monotone in window size (e.g. "sum = k" with negatives can be broken *and* fixed by new elements) → switch to the pair-counting family. | `dsa/patterns.md` (traps §4)

## Behavioral
- STAR 1 (Production Ingestion Bottleneck): see `interview/star-stories.md` — rehearse to 90 s with ≥3 numbers.

## Company / experience (evidence: `interview/company-projects.md`)
11. **Design an agentic migration pipeline with human oversight.** -> orchestrator/worker + barrier, extractor -> modeller (RAG-as-tool) -> generator -> writer -> parity reviewer -> adversarial critic -> human gate; guardrails in and out; per-step artifacts + tracing. | P1, imports tracker mermaid
12. **How do you evaluate a RAG system when you have no user labels?** -> golden set with ground truth + expected entities; audit dimensions (empty / refusal / no-evidence / shortness); strategy attribution per answer; the eval revealed the LLM carried 1/22 answers. | P2, rag-system/eval
13. **How would you approach a legacy BI modernization?** -> inventory the estate (84 tabular models, 8+ workspaces), build converter tooling with prompts + tests, parity review as the acceptance gate. | P3, bi-modernization

## Week 2 Fri / Week 3 Fri additions
14. **Why a cross-encoder can beat a bi-encoder on relevance.** -> bi-encoders compress query and doc into one vector each before they meet; a cross-encoder reads them together (full attention across the pair) -> more precise, much slower -> two-stage shape. | `core/reranker.py`, ADR-002 W2
15. **Your rerank latency budget at scale?** -> fitted config measured: MiniLM + 20 cand x 64-token snippets -> p50 257 ms / p95 426 ms (budget 500 ms MET); bge-base = 4.1 s same config (GPU only); cost is quadratic in pair length (12 -> 398 ms/pair, 10 -> 250 tok). | week2_results_fitted.json
16. **How do you fuse more than two ranked lists?** -> same RRF: sum 1/(k+rank) over n lists; optional per-list weights (w_i/(k+rank)); variants from query transformation fuse exactly this way. | `core/query_service.py`
17. **When does query transformation hurt retrieval?** -> a bad rewrite steers the query; mitigated by fusing the ORIGINAL with every variant (variants only add votes). | ADR-003
18. **What is HyDE and when would you not use it?** -> embed a hypothetical answer document instead of the question; needs generation (latency + cost); skip for keyword-exact queries where sparse wins. | ADR-003 (deferred to W7)
19. **Design Self-RAG-style reflection without an LLM.** -> rule-based sufficiency proxy: keyword coverage of top results vs threshold; one bounded retry with decomposed sub-queries; the LLM critic later swaps into the seam. | `core/query_service.py`
20. **How do you bound a rewrite loop?** -> max 1 retry, only when sufficiency fails AND sub-queries exist; every loop adds spans, so retries are counted in the outcome. | ADR-003
21. **Pre-filter vs post-filter for permissioned search?** -> pre-filter with payload indexes (avoids retrieving leaked docs), post-filter wastes candidates; needs payload_schema indexes (our TODO). | Drill 3
22. **What would a permission-leak eval look like?** -> golden queries run as user A asserting NO results from user B's docs; the one failure class that must be impossible. | Drill 3
23. **Unit economics of a document-review platform.** -> per-contract: pages x (parse+embed+extract+retrieval $) vs human-hours saved x rate; state assumptions aloud. | mbb-case-1.md
