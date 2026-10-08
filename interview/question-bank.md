# Question Bank

Format: **question → answer skeleton → where the detail lives.** Rehearse the skeleton out loud (30–60 s), then check the link.
Bank size target: +10 per MOCK & BANK day. Current: **10 seeded** (Week 1 Fri ✅ pending your pass over them).

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
