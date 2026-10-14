# LLD Drill — Query Rewriter Pipeline (Chain of Responsibility) (Week 3 Thu)

**Prompt:** *"Design a query-rewriting stage that passes each query through a configurable chain of transformations. Some strategies need an LLM, some are pure rules; adding a strategy must not touch the chain driver; every stage can veto (produce no variant)."*

## 6 beats
1. **Pattern:** Chain of Responsibility — each `QueryTransformer` handles or passes; the driver (`apply_pipeline`) composes the chain from config (already built: `core/query_transformers.py` + `build_pipeline`).
2. **Contract per stage:** `transform(query) -> list[str]` (0..n variants; empty = veto). Stages must be side-effect-free and idempotent.
3. **Config-driven assembly:** the chain is a string setting ("subquery,rewrite,hyde") — adding a strategy = new class + config token, driver untouched.
4. **LLM stages:** HyDE holds a `Generator` hook; without it the stage vetoes (graceful no-op until Week 7).
5. **Failure semantics:** a raising stage is caught by the driver, logged, and skipped — the chain continues with the next stage (degrade, don't fail the query).
6. **Trade-offs:** chain order matters (decompose before rewrite? rewrite before decompose?) — argue your order; variants deduplicate across stages; the original query always retrieves too.

## Rubric
- [ ] Named Chain of Responsibility (not "a loop")
- [ ] Veto semantics via empty list
- [ ] Config-driven assembly, Open/Closed
- [ ] LLM-stage seam with graceful degradation
- [ ] Failure isolation per stage
- [ ] Order-of-stages argument

## MODEL ANSWER — memorize this

**The 60-second frame.** "Chain of Responsibility: each stage gets the query, returns zero or more transformed variants — empty list means *veto* — and the driver composes the chain from config, so adding a strategy is a class plus a config token, never a driver edit. My shipped version: `SubQueryDecomposer`, `RewriteTransformer`, and `HydeTransformer`, which holds a generator hook and degrades to a veto until the LLM lands in Week 7."

**The six beats, expanded:**

1. **Pattern name + why.** Chain of Responsibility, because stages are independent handlers and the *driver* doesn't know which apply — the config decides. Not "a loop over functions": the pattern buys you per-stage contracts, per-stage tests, and per-stage failure isolation.
2. **Stage contract.** `transform(query) -> list[str]` — 0..n variants; empty = veto (the strategy decided it doesn't apply: e.g. the decomposer on a simple query returns `[]`, never the query itself — "a query is not its own variant"). Stages are side-effect-free and idempotent; they never see each other's internals.
3. **Config-driven assembly (Open/Closed).** `TRACKA_QUERY_TRANSFORM_PIPELINE="subquery,rewrite,hyde"` — `build_pipeline()` maps tokens to classes. New strategy = new class + new token. Driver untouched: that's the Open/Closed principle made concrete.
4. **The LLM stage.** HyDE needs a hypothetical-document *generator* — an LLM. The stage holds a `Generator` callable; when it's `None`, `transform` vetoes. The seam is the point: the control flow, tests, and spans exist today; Week 7 swaps the callable, not the pipeline.
5. **Failure semantics.** A raising stage is caught by the driver, logged with the stage name, and skipped — the chain continues with the next stage. *Degrade, don't fail the query.* A transformation bug must never take down retrieval; the worst case is the original query retrieving untransformed.
6. **Order argument + the safety net.** I decompose *before* rewriting (split compound queries first, then clean fragments — rewriting first would clean the whole compound sentence once, and splitting a rewritten sentence can re-introduce filler). But the real safety net is downstream: the **original query always retrieves too**, and every variant list fuses with it via RRF — a bad variant can only *add* candidates, never steer the ranking away. Variants deduplicate across stages (case-insensitive).

**If pressed — "why not mutate the query in place through the chain?"** "Mutation loses information — the original is the one artifact that's known-good. Variants are *additive* candidates; the fusion step is what keeps a bad rewrite from steering retrieval. That design choice is why my benchmark can compare pipeline-vs-baseline at all."

**Beat sheet (8 beats):** 1 Chain of Responsibility named · 2 contract: 0..n variants, empty = veto, idempotent · 3 config-token assembly, Open/Closed · 4 HyDE generator seam, graceful no-op · 5 per-stage failure isolation (log + skip) · 6 order argument (decompose→rewrite) · 7 original-keeps-its-vote fusion safety net · 8 dedupe across stages.

