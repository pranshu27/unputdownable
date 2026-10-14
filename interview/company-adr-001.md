# Company ADR #1 — The Human Review Gate in an Agentic Pipeline (draft)

**Topic picked (Fri deliverable):** where the human gate should sit in the agentic Informatica-to-PySpark migration pipeline, what it blocks, and what evidence the critic owes the human. Evidence base: `imports/freedom/project1/e2e_infa_to_pyspark/TRACKER.md`.

## Draft ADR skeleton (fill [YOU] slots from real project facts)

**Context:** 6 AutoGen agents (extractor → collector → modeller → generator → writer → reviewer)
+ adversarial critic produce PySpark + Iceberg migrations for [YOU: N] PowerCenter mappings.
Bad generated SQL shipped to the lakehouse corrupts curated data silently — detection lag is days.

**Decision:** the human gate sits **after the critic and before the Iceberg write** (merge step); it blocks on: critic score below threshold [YOU: threshold?], static-parity review failures, and any schema-change (new columns/drops). The gate consumes the critic's evidence bundle (diff, parity report, flagged risks), not raw code.

**Alternatives rejected:** (1) gate after every agent — humans become the bottleneck; (2) fully autonomous merge — silent-corruption risk; (3) gate only on critic failure — misses parity blind spots the critic did not score.

**Trade-offs:** throughput (each gate costs human minutes [YOU: measured?]) vs blast radius (a bad merge touches downstream for days). Bounded by batching: one approval can cover a batch of [YOU: N] similar mappings.

**Success metrics:** gate catch-rate (defects caught / defects that would have shipped), human-latency per gate, % mappings auto-approved.

## Interview defense — memorize this (the 3-minute ADR walk)

**Setup (30 s).** "The decision I'd defend: where the human gate sits in our agentic Informatica-to-PySpark migration pipeline. Six AutoGen agents — extractor, collector, modeller, generator, writer, reviewer — plus an adversarial critic, migrating PowerCenter mappings to PySpark + Iceberg. The stakes: a bad generated transform doesn't fail loudly — it corrupts curated lakehouse data silently, and detection lag is days downstream."

**Decision (30 s).** "The gate sits **after the critic and before the Iceberg write**. It blocks on three triggers: critic score below threshold, static-parity review failures, and any schema change — new columns or drops. And critically, the gate consumes the **critic's evidence bundle** — the diff, the parity report, flagged risks — not raw generated code."

**Why there (and not elsewhere) (60 s — the alternatives).** "Gate after every agent: humans become the bottleneck at [YOU: N] mappings — you've rebuilt manual review with extra steps. Fully autonomous merge: that's the silent-corruption scenario. Gate only on critic failure: misses the parity blind spots the critic didn't score. After-critic-before-write is the narrowest choke point where everything upstream has already been machine-verified — human attention goes to the residual risk, not the noise."

**Evidence bundle rationale (30 s).** "Consuming the evidence bundle, not raw code, is a design decision with a lesson behind it: reviewers approve faster and more accurately on diffs+parity than on SQL reading. And it makes the gate auditable — the bundle IS the record of why each merge was approved."

**Trade-off stated honestly (30 s).** "Cost: each gate costs human minutes — bounded by batching: one approval can cover a batch of similar mappings [YOU: batch size]. The risk you accept: similarity-based batching means one bad pattern in a batch survives N approvals — which is exactly why schema changes always break the batch and gate individually."

**Metrics (30 s).** "Gate catch-rate — defects caught / defects that would have shipped; human-latency per gate; auto-approval share. From my run: critic flagged issues pre-merge, the gate held, 20/20 tests passed on the validated E2E run, 1,189 chunks indexed for the mapping RAG. [YOU: catch-rate + hours saved once measured.]"

**Beat sheet (9):** 1 six agents + stakes (silent corruption, days lag) · 2 gate position after-critic-before-write · 3 three block triggers · 4 evidence-bundle-not-raw-code · 5 rejected: gate-everywhere (bottleneck) · 6 rejected: autonomous (blast radius) · 7 rejected: critic-only (blind spots) · 8 batching trade-off + the schema-change exception · 9 three metrics + 20/20 + 1,189 chunks.

