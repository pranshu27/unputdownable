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
