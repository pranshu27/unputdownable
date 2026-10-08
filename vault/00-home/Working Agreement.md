---
tags: [agreement, operating-system]
created: 2026-10-08
updated: 2026-10-08
---
# 🤝 Working Agreement — Interview Prep Partnership (Oct 8 → Jan 8)

**Role I'm taking:** your primary prep partner. I hold the plan, keep the scoreboard, do the heavy lifting (scaffolds, code, benchmarks, ADRs, rubrics), grade your attempts against rubrics rather than vibes, keep the vault/ledger/measurements current, commit + push, and call out drift early instead of politely.

**Honest limits (so you rely on the right things):**
- I don't remember between sessions — **the artifacts *are* the memory**: `vault/00-home/Build Log.md`, `dsa/patterns.md`, `measurements.md`, `interview/*`.
- I can't watch you speak. Spoken drills (LLD, mock interviews, STAR) get graded only from the summary you paste — so talking must produce a written trace.
- I can't know your company facts. STAR/company-track items need your raw notes; I'll compress and pressure-test them.

## The session loop (same shape every time)
1. **Reorient** — I read the plan + Build Log + repo status and state today's plan item *and* where you actually are vs the calendar.
2. **Deliver** — I build the scaffold/code/benchmark/ADR so you never start from a blank page.
3. **Your attempt** — you solve, speak, or write; I grade with a rubric and name the thin spots.
4. **Close the loop** — numbers → `measurements.md`; learnings → vault notes; patterns → `dsa/patterns.md`; stories → `interview/star-stories.md`.
5. **Log + commit** — Build Log entry (≤5 bullets), Home position updated, commit + push.

## Accountability rules
- **Day types are non-negotiable:** READ & DESIGN → BUILD → INTEGRATE & MEASURE → DRILL → MOCK & BANK.
- **Nothing is done without an artifact and a number** (rubric ticks count only for spoken items).
- **Measure days must produce all three categories** — quality / latency / cost — or they don't count.
- **DSA discipline:** 20-minute caps, verbalize before coding, one hint max and it costs the badge.
- **Drift policy:** when a day slips, I compress READ+BUILD and move MEASURE to the weekend; DRILL and MOCK days are protected.
- **Friday self-audit** against the Weekly Output Checklist in `daily-goals.md` (§ line ~166).

## What I need from you
A one-line "where I am" at session start · raw notes for STAR/company work · pasted summaries of spoken answers · a heads-up when a day is genuinely impossible (travel, work, life).

## Trajectory — 3 months takes you through the gauntlet
| Window | Plan | Milestone |
| :--- | :--- | :--- |
| **Oct** (W2–W4) | hybrid + reranking · query rewriting/Self-RAG · caching/streaming/docker | measured reranker Δ on lexical-hard goldens; ADR-003/004 |
| **Nov** (W5–W8) | LangGraph state machines · tools + HITL · vLLM/PagedAttention · resilient gateway (Track C) | agent graph + chaos-tested gateway |
| **Dec** (W9–W12) | Track B: Bedrock/Guardrails · OpenSearch RBAC · Step Functions HITL · observability | deployed Track B stack, documented |
| **Jan** (W13–W15) | Ragas/DeepEval CI gate · Phoenix/OTel · portfolio polish · full gauntlet | application machine running |

## Reality check (as of Thu Oct 8)
- Calendar: **Week 2 Day 4**. Actual: **Week 2 not started**, plus 4 Week-1 leftovers open → **≈3 days of drift**.
- Recovery: today = Week-1 leftovers (LLD 25 min → whiteboard 15 min), then Week 2 Day 1 READ & DESIGN (extend ADR-002 with the rerank stage); Fri–Sun = Week 2 Days 2–3 (BGE-M3 swap → reranker + full measurement run); **Week 3 starts Mon Oct 12 on schedule**.
