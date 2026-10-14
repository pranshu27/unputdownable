# MBB Case 1 — Legal Document Review Platform (Week 2 Fri · 30 min, spoken)

**Prompt:** *"A law firm wants an AI platform to review contracts: upload, extract obligations, flag risky clauses, and let associates query the corpus with citations. Design it, estimate the unit economics, and tell me how you would roll it out."*

## The 6-step MECE framework (speak through, in this order)
1. **Clarify + scope** (2 min): users (associates, partners, compliance?), document types (NDAs, MSAs, leases?), volume (docs/day, corpus size), success metric (review-hours per contract? flag precision?).
2. **Requirements → architecture** (8 min): ingestion (parsers: PDF/DOCX/scanned), clause extraction (LLM + validation), retrieval (hybrid + rerank + citations), review UX (queue, flag review, HITL), storage (tenancy isolation!).
3. **Deep-dive one pillar** (5 min): pick extraction OR retrieval and go deep — accuracy regime, guardrails, failure modes.
4. **Unit economics** (5 min): per-contract math: pages × (parse $ + embed $ + LLM-extraction $ + retrieval $) vs human-hours saved × rate. State assumptions out loud.
5. **Risks & guardrails** (5 min): hallucinated citations (mitigation: evidence-first contract), confidentiality (tenancy, redaction), audit trail (regulation).
6. **Rollout** (5 min): pilot on one practice group, shadow-mode (AI flags vs associate flags) for N weeks, then assisted review; kill criteria.

## Rubric
- [ ] Clarifying questions before structure
- [ ] MECE top-level structure stated explicitly
- [ ] At least one deep-dive with numbers
- [ ] Unit-economics arithmetic performed aloud with stated assumptions
- [ ] Risk section includes a guardrail mechanism (not just "we will be careful")
- [ ] Rollout with measurable gates

## MODEL ANSWER — memorize this (the full spoken run)

**0. Opening (30 s).** "Let me make sure I solve the right problem before structuring — three quick questions: users (associates only, or partners/compliance?), document mix (NDAs and MSAs? leases? volume per week?), and the success metric — is it review-hours per contract, flag precision, or revenue per seat?"

**1. Structure (MECE, say it as a tree).** "I'll structure the platform along the document lifecycle: **Ingest → Understand → Retrieve → Review → Roll out** — five MECE pillars; economics and risks cut across."

**2. Ingest (90 s).** "Contract intake: PDF/DOCX/scanned. Parsers behind a strategy interface; scanned goes to OCR asynchronously. The design constraint that matters: tables and party/term structure must survive parsing intact — a mis-parsed indemnity clause is worse than a missing one. Ingestion metric: parse-failure rate + clause-extraction coverage, not throughput alone."

**3. Understand — extraction (2 min, THE deep-dive).** "Obligation extraction is the core: parties, effective dates, renewal, indemnity, termination-for-cause, caps. LLM-extracted fields need *verifiable evidence*: every extracted field cites the source clause span — no citation, no field. Then validation: cross-field consistency (renewal date < termination date), and a critic pass scoring each extraction. My measured reference point from my own RAG eval: an evidence-first contract with a golden set turned 'the answers look fine' into 22/22 with zero no-evidence answers — extraction without evidence is not a product."

**4. Retrieve (90 s).** "Associates ask questions across the corpus; answers must carry citations. Hybrid retrieval (dense + lexical, RRF fusion) with a cross-encoder rerank stage — measured on my own build: fusion sub-millisecond, rerank is the latency budget item. Permissioning is a first-class failure mode: a corporate-doc leak to the wrong client is the one error this product can never make — so filtering is a pre-filter at query time, with a permission-leak eval as a hard gate."

**5. Review UX (90 s).** "Flag queue: risk flags ranked by severity × exposure, each with clause evidence; associate accepts/rejects — the rejections become eval data. Human-in-the-loop by design: the model triages, the human owns the call. That division is what makes accuracy *improvable*: every rejection is a labeled example."

**6. Unit economics (5 min, arithmetic ALOUD).** "Assumptions stated first: MSA ~80 pages; LLM extraction ≈ $0.50 per MSA (assumed token pricing), parse+embed ≈ $0.02, retrieval ≈ $0.001 per query. Human first-pass review: 80 pages × ~3 min/page ≈ 4 hours ≈ $400 at $100/h loaded. Platform cost ≈ $0.55 per contract → even at 10× the token price, one order of magnitude cheaper; value case stands on hours, not tokens. Break-even seat math: platform fixed cost vs hours saved — the sensitivity is *extraction accuracy* (bad flags cost reviewer trust, not just rework), so I'd spend margin on eval, not on cheaper models."

**7. Risks & guardrails (2 min).** "Hallucinated citations → evidence-first contract (no span, no field). Confidentiality → tenancy isolation + redaction at ingest + pre-filter retrieval. Regulatory audit → immutable per-document audit trail. Model drift → weekly golden-set regression, any recall drop blocks the model update."

**8. Rollout (90 s).** "Pilot one practice group, **shadow mode** for 4–6 weeks: AI flags logged, not shown; measure flag precision/recall vs associate decisions. Gate to assisted review: precision ≥ agreed bar on the pilot corpus. Then expand practice groups one at a time. Kill criteria: if precision can't clear the bar with prompt/model iteration, the product narrows to extraction-assist only — a smaller win, still a win."

**Beat sheet (12 beats):** 1 clarify ×3 · 2 five-pillar MECE stated · 3 ingest with parse-failure metric · 4 extraction deep-dive with evidence-first + golden-set number · 5 hybrid+rerank retrieval + permission-leak hard gate · 6 review queue = labeled-eval flywheel · 7 economics arithmetic aloud with stated assumptions · 8 sensitivity = extraction accuracy · 9 risks each WITH a mechanism · 10 shadow-mode rollout · 11 measurable gate · 12 kill criteria.


## Your notes after the run
- (structure, assumptions, final recommendation)
