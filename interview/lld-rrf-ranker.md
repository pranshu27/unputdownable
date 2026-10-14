# LLD Drill — In-Memory RRF Ranker with Configurable Weights (Week 2 Thu)

**Prompt:** *"Design an in-memory rank-fusion component that merges N ranked lists into one ordering. Callers can weight lists differently (e.g. dense 0.7, sparse 0.3) and tune the damping constant. It must fuse in microseconds and be safe under concurrent queries."*

## 6 beats (speak first, then compare)
1. **Interface:** `fuse(result_lists: list[list[Hashable]], weights: list[float] | None, k: int = 60) -> list[tuple[Hashable, float]]` — weights optional (None = uniform).
2. **Algorithm:** weighted RRF — `score(d) = Σ w_i / (k + rank_i(d))`. Extension of the shipped `reciprocal_rank_fusion` (add per-list weight multiplication; tie-break by first-seen order; de-dupe within a list).
3. **Complexity:** O(total items) time, O(distinct items) space. No sorting of inputs needed.
4. **Concurrency:** the fuser is a pure function — no shared mutable state, so concurrent queries are safe by construction; the only shared thing is the (immutable) weights config.
5. **Validation:** weights length must match lists length; k > 0; empty lists contribute nothing.
6. **Trade-offs:** weighted RRF vs score normalization (weighted RRF keeps rank-only invariance); where this component would live in prod (behind the SearchService seam, cacheable per query-shape).

## Reference implementation (compare after speaking)
The shipped `rrf.py` is the k-only version; the weighted variant is a two-line change: `scores[item] += weight / (k + rank)` with `weight = 1.0 if weights is None else weights[i]`.

## Rubric
- [ ] Interface takes N lists (not exactly 2)
- [ ] Optional weights with uniform default
- [ ] De-duplication within a single list
- [ ] Deterministic tie-breaking
- [ ] Pure-function concurrency argument
- [ ] Stated complexity O(total items)

## MODEL ANSWER — memorize this

**The 60-second frame.** "I'd build weighted RRF as a pure function: for every item, sum `w_i / (k + rank_i)` over every list it appears in, then sort by fused score. Rank-only — no score normalization, ever — because dense cosine and BM25 live on incomparable scales, while *ranks* are universal. That's the whole trick."

**The six beats, expanded:**

1. **Interface.** `fuse(result_lists: list[list[Hashable]], weights: list[float] | None, k: int = 60) -> list[tuple[Hashable, float]]`. Weights optional — `None` means uniform, which must be exactly equal to the unweighted RRF. Validation: weights length must match lists length, all non-negative (a negative weight would create negative scores — meaningless for ranking).
2. **Algorithm.** One pass per list: skip duplicates *within* a list (a retriever that lists an item twice must not double-vote), accumulate `scores[item] += w_i / (k + rank)`, remember first-seen order. Final sort: descending score, ties broken by first-seen order — deterministic output for identical input, no dict-iteration-order accidents.
3. **Complexity.** O(total items across lists) time — one pass, one final sort of *distinct* items. O(distinct items) space. Not "O(n log n)" by reflex — the log n is only over distinct items, and the per-list pass is linear.
4. **Concurrency.** "It's a **pure function** — no shared mutable state, so concurrent queries are safe *by construction*; nothing to lock. The only shared object is the weights config, which I'd treat as immutable and swap atomically (config reload replaces the object, never mutates it)."
5. **Validation beyond unit tests.** Property: with equal weights it must equal plain RRF; heavier weight on list i must move that list's top items up vs uniform — my test: `lists=[[x],[y]]`, weights `[2,1]` → x beats y. And the rank-gap lesson: with k=60, moving from rank 1 to rank 2 costs 61/62 ≈ 0.984 of an item's vote — so a weight bump must beat a **61× gap** to flip a rank-1-vs-rank-2 pair. Say that number; it shows you understand the damping.
6. **Trade-offs.** Weighted RRF vs score normalization (min-max/z-score then weighted sum): normalization is *score-aware* (can be better when scores are well-calibrated) but breaks when scales drift between systems or models get swapped; weighted RRF is robust to any score distribution because it only ever sees ranks. Where it lives in prod: behind the SearchService's fusion seam, trivially cacheable per query-shape, and the same function fuses query-variant lists later (ADR-003).

**If pressed — "why k=60?"** "Cormack et al. 2009's empirical default; k dampens head ranks — large k flattens differences (a rank-2 item nearly equals rank-1), small k makes top ranks dominate. I'd treat 60 as a prior and re-tune on my own golden set, not cargo-cult it."

**Beat sheet (8 beats, in order):** 1 interface + optional weights · 2 rank-only formula + de-dup · 3 O(total items) + deterministic tie-break · 4 pure-function concurrency · 5 property tests + the 61/62 rank-gap number · 6 weighted-RRF vs normalized-scores trade-off · 7 k=60 provenance + re-tune stance · 8 lives behind the fusion seam, reused by query variants.

