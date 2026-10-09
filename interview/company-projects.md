# Company Projects Inventory — evidence-first

**Purpose:** the Fri deliverable "list own GenAI projects, pick ADR topic #1" — built from your
**imports/ archives** (artifact-derived facts you can defend) plus `[YOU]` slots only you can fill.
**Project separation (do not mix):** P1-P4 are **completed prior projects**. Track A
(`track-a/`) is the **current, separate build** with its own HLD/LLD (`vault/30-design/`) - none of
these artifacts are part of Track A, and Track A borrows no code from them.

**Confidentiality rule:** the artifacts contain client names (e.g. an auto-insurance client) —
in interviews say "a large insurance client", never the name, and describe patterns, not internals.

---

## P1 — Agentic Informatica-to-PySpark migration  ⭐ strongest story

**What it is (from `imports/freedom/project1/e2e_infa_to_pyspark/TRACKER.md`):**
an agent pipeline that migrates Teradata EDW / Informatica PowerCenter logic (from XML exports) to
**PySpark + Apache Iceberg**, with RAG grounding, guardrails, adversarial critique and a human gate.

**Artifact-derived evidence (defensible as-is):**
- **6 specialised AutoGen agents** in an orchestrator/worker design: PCExtractorAgent ->
  PCResultCollectorAgent (pub/sub + barrier) -> DataModellerAgent (field-level STTM, **RAG as a tool**)
  -> PySparkGenerationAgent -> IcebergWriterAgent -> ReviewAgent (static parity) -> CriticAgent
  (adversarial score) -> **human_review_gate** (approve/hold)
- **Input guardrails: PII/secret redaction** before anything flows; **output guardrails** on generation
- **Live E2E run validated (2026-06-25): 1,189 chunks indexed for RAG grounding, field-level STTM
  produced, critic flagged issues, human gate held, 20/20 tests passing**
- Observability: per-step artifact recorder (every step persisted to `runs/`) + **Langfuse tracing**
- 2 test files / 20 tests; docs incl. `CODEBASE_TEXTBOOK.md` and `architecture/03-rag-eval-guardrails.md`

**Metrics you must supply `[YOU]`:** number of PowerCenter mappings/workflows in scope · % migrated
automated vs manual · analyst-hours saved · data volume (GB/TB) processed · what the critic/review
agents caught that humans missed · runtime per mapping.

**ADR-worthiness: HIGH** — contested decisions everywhere: agent topology, RAG-as-tool vs fine-tune,
Iceberg MERGE strategy, how much the human gate should block.

## P2 — RAG system with a golden-set eval gate

**What it is (`imports/freedom/rag-system/`):** a RAG service with Streamlit UI,
prompt registry (`prompts.yml`), design docs (CONCEPTUAL_BIBLE, SYSTEM_E2E_FLOW: "semantic-first",
"graph-augmented", "evidence-first answer contract", guardrail routing) and — the gem — **an eval
folder with real audit results**.

**Artifact-derived evidence (computed from the files today):**
- **22 golden queries** (hybrid retrieval, k=6) with ground-truth + expected entities
- **22/22 answered non-empty · 0 refused · 0 empty · 0 no-evidence · 0 under-120-chars**
- avg answer length **1,225.9 chars** · **p95 latency 22.56 s**
- **strategy attribution per answer:** fallback_extractive **15** · grounded_relevance_fallback **6** ·
  llm_primary **1**
- separate non-empty/LLM-error check: 22/22, `llm_used_count: 22`; 295 full responses archived

**The story inside the numbers:** the LLM-primary path fired only **1 of 22** times — extractive,
evidence-first fallbacks carried 21/22 answers *without a single empty or no-evidence response*.
That is the strongest possible "evaluation changed my design" story: the audit did not just score the
system, it revealed the real answer-strategy distribution and drove the evidence-first contract.

**Metrics `[YOU]`:** production corpus size · who used it · was p95 22.5 s acceptable and why ·
what the 3 problem_rows were · how the golden set was chosen.

**ADR-worthiness: HIGH** — evidence-first vs free-generation is a genuine, contested trade-off.

## P3 — BI modernization program (QlikView -> Tableau/Power BI)

**What it is (`imports/bi-modernization/` (renamed 2026-10-08: `react-modernization/`, `qlikview-converter/`, `jira-copilot-service/`)):** a conversion program with LLM-assisted tooling.

**Artifact-derived evidence:**
- **84 Power BI tabular models** (`.tmdl`) across the program
- **8+ dashboard workspaces** by name in `pbib_input_files/` (auto-insurance dashboards, claims,
  sentiment analysis, data-analyst projects...)
- converter tooling with **prompts/ and tests/** directories; largest workstream alone is 865 files
- plus a containerised **Jira-to-Copilot integration service** (Docker, AWS Secrets Manager)

**Metrics `[YOU]`:** dashboards migrated vs total portfolio · timeline · parity/acceptance rate ·
users downstream · licensing or compute savings · manual-effort reduction per dashboard.

## P4 — Legacy React modernization ("genai" app)

**Artifact-derived:** 175 `.tsx` + 32 `.ts` files across structured modules (core, layouts, Hooks,
Lib, data, types), 56 runtime dependencies, test/build scripts wired.

**Metrics `[YOU]`:** what legacy UI it replaced · bundle/perf before-after · users.

---

## How to phrase metrics honestly
1. **Artifact-derived numbers** (above) are yours to quote — they exist in files you own.
2. **`[YOU]` numbers** must be true: dig them up from trackers/tickets/memory before the interview.
   If unknown: "on the order of" + the number you *can* defend (e.g. "roughly 40 mappings").
3. Never quote client names or internal repo names. Patterns, not internals.

## ADR topic #1 recommendation (Fri deliverable)
**Pick P1's human_review_gate:** where should the gate sit in an agentic migration pipeline, what does
it block, and what evidence does the critic owe the human? Contested, measurable (gate catches per
run), internal, and directly relevant to your Week 3 Self-RAG and Track B HITL work.
