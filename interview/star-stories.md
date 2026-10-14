# STAR Stories + Company Track

## The template (keep every story to 90 seconds spoken)

| Part | Must contain | Common failure |
| :--- | :--- | :--- |
| **S**ituation | scale + stakes in one sentence | rambling context |
| **T**ask | your specific ownership ("I owned X") | "we" everywhere |
| **A**ction | 2–3 decisions, each with the alternative you rejected | listing activities, no decisions |
| **R**esult | **≥2 numbers** (before/after, cost, latency, blast radius) | "it worked well" |

Rule: **three numbers minimum per story** (scale, delta, business impact). Rehearse out loud, not in your head.

---

## STAR 1 — Production Ingestion / Migration Bottleneck  🟡 (evidence found in imports/)

**Anchor candidate found:** the Informatica-to-PySpark agentic migration (`imports/freedom/project1/e2e_infa_to_pyspark/TRACKER.md`) — a migration whose *bottleneck* story is exactly this. Full draft: see `company-projects.md` P1 + STAR 2 below. Fill the `[YOU]` slots (scale, volumes, hours saved) before rehearsing.

---

## STAR 2 (draft) — Agentic migration of Informatica logic to PySpark/Iceberg

- **S:** `[company]` ran a Teradata EDW whose transformation logic lived in hundreds of Informatica PowerCenter mappings, exported as XML nobody could safely read by hand; the move to a PySpark + Iceberg lakehouse was manually intractable. `[YOU: N mappings, team size, deadline]`
- **T:** I designed and built the agentic migration system end-to-end.
- **A (3 decisions, each with a rejected alternative):**
  1. **Six specialised agents behind an orchestrator/worker with a pub-sub barrier** — extractor, collector, data modeller, PySpark generator, Iceberg writer, parity reviewer — instead of one monolithic LLM call. Rejected: single-shot generation (no verification surface).
  2. **RAG as a tool for the modeller** — the mappings were chunked (1,189 chunks in the live run) and indexed so the DataModellerAgent could ground field-level STTMs in actual lineage.
  3. **Adversarial critic + human review gate** with input/output guardrails (PII/secret redaction) and per-step artifacts + Langfuse tracing — so every step was replayable and nothing shipped without a human approval. Rejected: fully autonomous merging.
- **R (artifact-derived numbers):** live E2E run validated — **1,189 chunks indexed**, field-level STTM produced, **critic flagged issues, human gate held**, **20/20 tests passing**. `[YOU: hours saved, % automated, data volume, defects the gate caught]`
- **Soundbite:** "Six agents, a barrier, RAG-as-tool over 1,189 indexed chunks, an adversarial critic and a human gate that actually held — 20/20 tests on the validated run."

### STAR 2 — 90-SECOND CUT (memorize this)
"[S] Our Teradata EDW's logic lived in hundreds of Informatica PowerCenter mappings — XML nobody could safely hand-migrate to the new PySpark+Iceberg lakehouse. [T] I built the agentic migration system end-to-end. [A] Three decisions: six specialised agents behind an orchestrator with a barrier instead of one monolithic LLM call — a monolith has no verification surface; RAG-as-tool so the modeller grounded field mappings in actual lineage — 1,189 chunks indexed in the live run; and an adversarial critic plus a human review gate instead of autonomous merging — every step artifacted and traced. [R] The validated end-to-end run: 20/20 tests passing, critic flagged issues pre-merge, the gate held. [YOU: hours saved / % automated]."

## STAR 3 (draft) — Golden-set evaluation that changed the RAG design

- **S:** a RAG service `[YOU: domain, corpus size]` where nobody could say whether answers were right.
- **T:** build an evaluation gate, not a vibe check.
- **A:** 22-query golden set with ground truth and expected entities; hybrid retrieval at k=6; an audit pipeline scoring **non-empty / refusal / no-evidence / shortness** per answer, plus **strategy attribution** for every response.
- **R:** **22/22 answered non-empty — 0 refused, 0 empty, 0 no-evidence**; avg 1,226 chars; p95 22.6 s. And the insight that mattered: the **LLM-primary path fired only 1 of 22 times** — extractive, evidence-first fallbacks carried 21/22 answers. The audit revealed the real strategy distribution and drove the evidence-first answer contract. `[YOU: what the 3 problem rows were]`
- **Soundbite:** "My eval didn't just score the system — it told me the LLM was carrying one answer in twenty-two, so I made evidence-first extraction the contract."

### STAR 3 — 90-SECOND CUT (memorize this)
"[S] A RAG service where nobody could say whether answers were right. [T] I built an evaluation gate, not a vibe check. [A] A 22-query golden set with ground truth; an audit pipeline scoring every answer — non-empty, refusal, no-evidence, shortness — plus strategy attribution per response. [R] 22/22 answered non-empty, zero no-evidence, avg 1,226 chars, p95 22.6 s. The finding that mattered: the LLM-primary path fired 1 time in 22 — evidence-first extraction carried 21. So I made evidence-first the answer contract. [YOU: the 3 problem rows]."

---

## STAR 1 — Production Ingestion Bottleneck  ⬜ → MODEL ANSWER (memorize; [YOU] slots = personal numbers)

**The story in one line:** *the bottleneck was never where everyone assumed — measurement moved the fix.*

**S (30 s).** "[YOU: company/system] ingested [YOU: volume] and throughput looked 'slow'. The standing assumption: parsing is the bottleneck — it's the heavy-looking step — and the team was about to buy a bigger parser fleet."

**T (20 s).** "I owned finding it: instrument the pipeline end-to-end and attribute latency per stage — parse, transform, embed/load — before anyone spent money."

**A (60 s — three decisions, each with a rejected alternative).**
1. **Instrument per stage before optimizing anything.** Rejected: parallelize-first — you can't speed up what you haven't attributed.
2. **Attack the real bottleneck: batch + async the slow stage.** I rebuilt this exact shape at home and got the same answer: parsing ~96 ms per document while CPU embedding dominated ingest p95 (~60–95 s for one 239-chunk filing) — the fix is batching embed calls, not touching the parser. `[YOU: company numbers — before/after]`
3. **Make the measurement a standing harness, not a one-off.** Rejected: one profiling session — drift re-introduces bottlenecks silently.

**R (30 s).** "[YOU: before/after]. Reference build: parse p95 < 100 ms; embedding identified as >99% of ingest latency; p95 dropped `[YOU: x]` after batching. Consequence: [YOU: hours saved / SLA met / fleet NOT purchased]."

**Delivery note:** name the discipline out loud — *"I don't optimize un-instrumented paths."*

**Beat sheet (8):** 1 standing assumption named · 2 ownership: instrument first · 3 rejected: parallelize-first · 4 attribution numbers (96 ms vs 60–95 s) · 5 fix = batch/async slow stage · 6 rejected: one-off profiling · 7 two before/after numbers · 8 discipline one-liner.

---

## Company track — own GenAI projects & ADR topic #1  ⬜ (Week 1 Fri)

**Step 1 — inventory (aim for 3–5 rows):**

| Project | How it's actually built (models, infra) | What's interesting / risky | Would I defend it publicly? |
| :--- | :--- | :--- | :--- |
| | | | |

**Step 2 — pick ADR topic #1** using these filters:
- **Internal & real** — you have first-hand context (interviews reward specificity)
- **Contested** — there was a genuine trade-off, not an obvious call
- **Measurable** — you can cite at least one number
- **Not confidential** — describe the pattern, not the customer's data or internals

Write the chosen topic here: `______________________________________`

## STAR 3 — Solving Hallucinations in Production (Week 3 Fri · anchor: company validation loops)

**S — Situation.** [YOU: company] shipped [YOU: LLM feature — e.g. the RAG golden-set eval / agent-generated migration SQL] where a wrong answer did not fail loudly — it passed review and landed in production.

**T — Task.** Make "wrong" *detectable*: every generated answer needed verifiable evidence, and validation had to run inside the loop, not after it.

**A — Action.**
- Built an evidence contract: no answer ships without chunk-level attribution.
- Built a golden-set eval harness: [YOU: N=22?] queries with expected non-empty evidence; measured LLM-carried vs evidence-carried answers (**[YOU: 1/22 LLM-carried — quote this]**).
- Added the validation loop: [YOU: describe — e.g. critic agent scores generator output before the human gate; gate consumes the evidence bundle].
- Failure taxonomy: [YOU: no-evidence / wrong-evidence / right-evidence-wrong-summary] and the guardrail for each.

**R — Result.**
- [YOU: 22/22 non-empty, 0 no-evidence] golden-set pass rate.
- Attribution distribution [YOU: 15/6/1 — retrieval-heavy / mixed / LLM-carried] — the punchline: *the system is mostly a retrieval system with a writing layer, and that is a feature, not an embarrassment*.
- Latency/quality budget kept by [YOU: the bounded retry / the rerank stage].

**Delivery notes:**
- Numbers first, adjectives never: the 1/22 line lands harder than "we improved reliability".
- If asked "so LLMs were unnecessary?" — counter: the LLM layer is the *interface*, the evidence layer is the *product*; separate their failure modes.
- Two-minute cut; stretch to five only with the failure-taxonomy digression.

