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

**Anchor candidate found:** the Informatica-to-PySpark agentic migration
(`imports/freedom_portable_nocache/project1/e2e_infa_to_pyspark/TRACKER.md`) — a migration whose
*bottleneck* story is exactly this. Full draft: see `company-projects.md` P1 + STAR 2 below.
Fill the `[YOU]` slots (scale, volumes, hours saved) before rehearsing.

---

## STAR 2 (draft) — Agentic migration of Informatica logic to PySpark/Iceberg

- **S:** `[company]` ran a Teradata EDW whose transformation logic lived in hundreds of Informatica
  PowerCenter mappings, exported as XML nobody could safely read by hand; the move to a PySpark +
  Iceberg lakehouse was manually intractable. `[YOU: N mappings, team size, deadline]`
- **T:** I designed and built the agentic migration system end-to-end.
- **A (3 decisions, each with a rejected alternative):**
  1. **Six specialised agents behind an orchestrator/worker with a pub-sub barrier** — extractor,
     collector, data modeller, PySpark generator, Iceberg writer, parity reviewer — instead of one
     monolithic LLM call. Rejected: single-shot generation (no verification surface).
  2. **RAG as a tool for the modeller** — the mappings were chunked (1,189 chunks in the live run) and
     indexed so the DataModellerAgent could ground field-level STTMs in actual lineage.
  3. **Adversarial critic + human review gate** with input/output guardrails (PII/secret redaction)
     and per-step artifacts + Langfuse tracing — so every step was replayable and nothing shipped
     without a human approval. Rejected: fully autonomous merging.
- **R (artifact-derived numbers):** live E2E run validated — **1,189 chunks indexed**, field-level STTM
  produced, **critic flagged issues, human gate held**, **20/20 tests passing**. `[YOU: hours saved,
  % automated, data volume, defects the gate caught]`
- **Soundbite:** "Six agents, a barrier, RAG-as-tool over 1,189 indexed chunks, an adversarial critic
  and a human gate that actually held — 20/20 tests on the validated run."

## STAR 3 (draft) — Golden-set evaluation that changed the RAG design

- **S:** a RAG service `[YOU: domain, corpus size]` where nobody could say whether answers were right.
- **T:** build an evaluation gate, not a vibe check.
- **A:** 22-query golden set with ground truth and expected entities; hybrid retrieval at k=6; an audit
  pipeline scoring **non-empty / refusal / no-evidence / shortness** per answer, plus **strategy
  attribution** for every response.
- **R:** **22/22 answered non-empty — 0 refused, 0 empty, 0 no-evidence**; avg 1,226 chars; p95 22.6 s.
  And the insight that mattered: the **LLM-primary path fired only 1 of 22 times** — extractive,
  evidence-first fallbacks carried 21/22 answers. The audit revealed the real strategy distribution
  and drove the evidence-first answer contract. `[YOU: what the 3 problem rows were]`
- **Soundbite:** "My eval didn't just score the system — it told me the LLM was carrying one answer in
  twenty-two, so I made evidence-first extraction the contract."

---

## STAR 1 — Production Ingestion Bottleneck  ⬜ (Week 1 Fri · anchor to real company work)

Fill these prompts from your own experience — do **not** invent; if a number is unknown, write "unknown" and dig it up later:

- **S — scale & stakes:** what was being ingested/processed, at what volume (docs/day, records, QPS), and what broke for whom when it was slow?
- **T — my ownership:** what exactly were you accountable for (design? on-call? the fix?)
- **A — decisions (2–3):** e.g. batching vs parallelism, backpressure vs dropping, sync vs queue. For each: what alternative did you reject and why?
- **R — numbers:** latency/cost/throughput before → after, and the business consequence.
- **Rejected alternative you can articulate:** the option you *didn't* take and the reason.

**Why this story is high-value:** it mirrors your own Week 1 finding — parse is ~96 ms while CPU embedding dominates ingest p95 (~60–95 s for a 239-chunk 10-K). If your company story is "the bottleneck was not where everyone assumed", you can reference this project as corroboration.

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
