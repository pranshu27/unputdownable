# Project Review Alignment (As of 2026-08-23)

## Update Log (2026-08-23) — P3 Observability Integrated In-Project

Scope decision:
1. P3 (observability and monitoring) is integrated into this same rag-system project.
2. Current project timeline is extended by two weeks to deliver observability end-to-end.

Committed two-week outcomes:
1. Request-level trace and timing telemetry across `/answer`, `/retrieve`, and semantic APIs.
2. Structured event schema for semantic-first routing lifecycle and refusal paths.
3. Latency/cost/reliability metrics surfaced for review and quality gates.
4. Dashboards, alert thresholds, and incident runbook aligned to semantic-first production posture.

Why this matters for review:
1. Converts observability from a "next step" into an implementation commitment inside the active project.
2. Improves audit confidence for latency, failure handling, and cost discussions in review rounds.
3. Preserves deterministic authority boundaries while adding measurable operational signals.

## Update Log (2026-08-23) — Graph-First Ingestion + Linked Explanation Artifacts

What changed since the previous update:
1. Ingestion now builds a workflow-directed NetworkX graph first from connector and port relationships.
2. Lineage paths are derived from graph traversal, then persisted as semantic truth in PostgreSQL (`rag.semantic_*`).
3. Each workflow now carries deterministic graph metadata (`graph_hash`) persisted in `rag.semantic_workflows`.
4. Explanation artifacts are generated from deterministic semantic facts for nodes and lineage paths:
- `artifact_kind=node_definition`
- `artifact_kind=lineage_definition`
5. `/answer` semantic-primary flow now retrieves linked explanation artifacts by semantic `evidence_id` before falling back to generic transformation context retrieval.

Why this matters for review questions:
1. Determinism remains intact: graph-derived outputs are persisted and queried as semantic truth.
2. Auditability improves: every workflow snapshot has a graph version hash for traceability.
3. Controlled AI usage: LLM can explain deterministic facts, but cannot invent lineage truth when semantic evidence is missing.
4. Explainability quality improves without relaxing safety: narrative artifacts are now evidence-linked and explicitly non-authoritative.

Graph-first + semantic-store tradeoff (final posture):
1. NetworkX is the derivation/runtime accelerator for traversal and impact exploration.
2. PostgreSQL semantic tables remain system-of-record for persistence, governance, and recovery.
3. Vector explanation artifacts are retrieval-only context and are never used as truth for lineage/impact decisions.
4. If graph state is unavailable in memory, semantic-store query path remains authoritative fallback.

## Update Log (2026-08-23) — NetworkX Lineage Intelligence

What changed since yesterday:
1. Added a NetworkX lineage engine in the semantic layer path for deterministic traversal.
2. Added cross-workflow field identity tracing for lineage/impact questions when workflow hint is not supplied.
3. Preserved PostgreSQL semantic tables as durable truth and retained semantic-store fallback when in-memory graph is unavailable.
4. Stabilized SQL-intent routing with deterministic heuristic short-circuit and retrieval fallback in low-hit scenarios.

Why this matters for review questions:
1. Determinism: lineage/impact answers are no longer dependent on retrieval ranking when semantic graph evidence exists.
2. Reproducibility: graph is rebuilt from the same semantic records (in-memory on ingest, PostgreSQL hydration on connect).
3. Explainability: each deterministic answer path is tied to structured workflow/mapping/field hops.
4. Coverage: we can now answer cross-workflow field-trace questions without speculative retrieval synthesis.

NetworkX vs semantic-store tradeoff (final posture):
1. PostgreSQL semantic tables remain system-of-record for persistence, governance, and recovery.
2. NetworkX adds in-memory traversal, reachability, and graph analytics speed for runtime lineage questions.
3. If graph state is unavailable, semantic-store query path remains authoritative fallback.
4. This is additive, not a replacement of semantic persistence.

## Architecture Pivot Log (2026-08-22)

Why pivot was mandatory (hard review questions we could not pass with retrieval-first RAG):
1. Can we guarantee the same lineage answer for the same `(workflow, field)` across reranker/model/version changes?
- Retrieval-first answer: no guaranteed determinism; ranking shifts can change top-k evidence.

2. Can we prove every lineage hop as a stable, queryable record instead of an inferred narrative from retrieved text?
- Retrieval-first answer: only partially; lineage chunks improve recall but are still selected by probabilistic ranking.

3. Can we enforce strict workflow scope and fail closed when the field is not resolved in that workflow?
- Retrieval-first answer: not reliably for all intents (especially usage-style questions) without deterministic entity resolution.

4. Can impact analysis be reproduced and audited by data teams without depending on LLM phrasing or retrieval order?
- Retrieval-first answer: not fully; it can be evidence-grounded but remains ranking-dependent.

5. Can reviewers trace an answer to normalized entities (workflow/node/port/connector/path) with stable IDs?
- Retrieval-first answer: limited; chunk IDs exist, but they are retrieval artifacts, not a relational semantic contract.

Pivot decision:
- For lineage/impact, probabilistic retrieval is insufficient as a system-of-record.
- Deterministic semantic queries must be the primary decision path; retrieval remains secondary for explanation.

What we are pivoting to:
- A semantic-first architecture where lineage and impact are answered from a normalized semantic model persisted in PostgreSQL (`rag.semantic_*`).
- RAG remains in the platform, but only as a copilot layer for natural-language explanation, supporting context, and exploratory queries.
- Runtime behavior is now intent-aware:
- lineage/impact intents -> deterministic semantic query path first
- semantic/summary/copilot intents -> retrieval + synthesis path

Target architecture contract:
- Truth plane: relational semantic entities (workflow, node, port, connector, lineage path).
- Copilot plane: vector/BM25/hybrid retrieval over chunk corpus for narrative support.
- API contract: `GET /semantic/model`, `GET /semantic/lineage`, `GET /semantic/impact` for deterministic access.
- Safety contract: if semantic truth cannot support a deterministic answer, return explicit refusal instead of speculative generation.

Examples of what was wrong with the previous retrieval-first strategy:
1. Cross-workflow drift on identifier-heavy fields:
- Query pattern: "Where is BeginInteractionGroup_Id used?"
- Failure mode: top-k retrieval can include chunks from similarly named workflows where the token appears, but not the exact lineage chain needed for the asked workflow.
- Risk: answer looks plausible yet references the wrong mapping context.

2. Hop truncation in multi-step lineage:
- Query pattern: "Trace INTERACTION_ID from target back to source."
- Failure mode: retrieval may return only intermediate transformation chunks and miss one connector hop in the path.
- Risk: incomplete or incorrect source attribution.

3. Impact ambiguity:
- Query pattern: "If field X changes, what breaks downstream?"
- Failure mode: retrieval returns descriptive mentions of X but not a deterministic downstream path set.
- Risk: impact analysis becomes suggestive rather than auditable.

4. Rank-instability under tuning changes:
- Query pattern: same query run across rerank/model/version updates.
- Failure mode: small scoring shifts change top-k evidence and therefore final answer.
- Risk: non-repeatable answers for governance-sensitive lineage questions.

What exactly is chunked in the semantic-first approach:
1. Deterministic semantic layer (truth plane):
- Not answered from chunks.
- Parsed workflow structure is persisted as normalized relational entities in `rag.semantic_*` and queried directly for lineage/impact.

2. Copilot retrieval layer (still chunked):
- Canonical node chunks: one SOURCE/TRANSFORMATION/TARGET node per chunk, with split+overlap only when content exceeds token budget.
- Lineage narrative chunks: one resolved lineage chain per chunk (`NODE_CLASS: LINEAGE`) for explanation support.
- Semantic explanation artifact chunks: node/path definitions generated from deterministic facts and stored with metadata (`workflow`, `node_id` or `path_evidence_id`, `graph_hash`, `generated_at`, `authoritative=false`).
- Chunk metadata includes mapping/type/sql-override/join/filter/field and hop information for filtering and evidence rendering.

3. Operational rule:
- Lineage and impact API paths use semantic relational queries as primary truth.
- Chunks are used to explain and contextualize the result, not to decide the deterministic lineage outcome.
- For semantic-primary answers, explanation artifacts are linked to returned semantic evidence IDs before generic vector context is considered.

This note aligns current RAG-system development with the core review questions:

1. What problem are we solving?
2. Why does it need AI?
3. What was the baseline?
4. How were results evaluated?
5. What happens when the system fails?
6. What are latency and cost?
7. Why this architecture?
8. What are the trade-offs?

Primary evidence sources:
- SYSTEM_E2E_FLOW.md
- CHANGELOG.md
- API_TESTING.md
- eval/report_w3_k10.json
- eval/ragas_baseline_w3.json
- eval/ragas_report_latest.json
- eval/graph_vs_legacy_answer_regression.json
- weekly/S01_2026-08-11.md ... weekly/S08_2026-08-22.md

---

## 1) What Problem Are We Solving?

We are reducing time-to-understanding for Informatica PowerCenter workflows (XML exports) during migration, debugging, and impact analysis.

Current pain points addressed:
- Workflow logic is distributed across SOURCE, TRANSFORMATION, TARGET, and connector-level lineage.
- Manual inspection is slow and error-prone for large mappings (thousands of chunks).
- Usage questions (for example: "Where is BeginInteractionGroup_Id used?") can drift to wrong mappings without explicit entity grounding.

What is delivered so far:
- Ingestion and indexing of 25 XML files into 4033 chunks.
- Retrieval over source logic, SQL overrides, transformations, and lineage chains.
- Conversational interface with memory and context inventory.

Concrete example:
- User asks: "Where is BeginInteractionGroup_Id used?"
- System now applies usage-entity guardrails and resolves to grounded evidence from wf_4205_calculate_dm_facts.XML.

---

## 2) Why Does It Need AI?

A keyword-only search is not enough for analyst-style questions that are intent-based, indirect, or phrased conversationally.

Where AI is necessary:
- Semantic retrieval for natural language queries that do not match exact XML tokens.
- Hybrid fusion (vector + lexical) to combine intent understanding with exact technical token matching.
- Citation-grounded answer synthesis across multiple evidence chunks.
- Conversational follow-up handling with compressed session memory.

Why not only rules/search:
- Pure lexical search misses semantic variants.
- Pure vector search can drift on identifier-heavy engineering queries.
- This domain requires both strict token precision (for IDs/workflow names) and semantic understanding (for descriptive questions).

---

## 3) What Was the Baseline?

We track two baselines: retrieval quality and answer quality.

Initial retrieval baseline (S04, 10-query set, k=8):
- hybrid: recall@8 = 0.3000, nDCG@8 = 0.2451
- vector: recall@8 = 0.3000, nDCG@8 = 0.2451
- bm25: recall@8 = 0.4500, nDCG@8 = 0.4787

Week-3 retrieval baseline expansion (53-query set, k=10):
- hybrid: recall@10 = 0.405660, nDCG@10 = 0.313095
- vector: recall@10 = 0.3868, nDCG@10 = 0.3068
- bm25: recall@10 = 0.0189, nDCG@10 = 0.0189

Locked answer-level baseline (eval/ragas_baseline_w3.json):
- query_count = 12
- faithfulness = 0.4
- answer_relevancy = 0.0

---

## 4) How Did We Evaluate Results?

Evaluation is offline, repeatable, and artifact-based.

Retrieval evaluation:
- Harness: src/rag_system/eval/retrieval_eval.py
- Dataset: eval/golden_retrieval_w3.jsonl
- Metrics: recall@k and nDCG@k
- Reporting: per-mode summary + bucket breakdown (identifier, lineage, semantic, sql_override)

Answer evaluation:
- Harness: src/rag_system/eval/ragas_eval.py
- Dataset: eval/golden_answer_eval.jsonl
- Metrics: faithfulness, answer_relevancy
- Output: JSON artifact with aggregate scores and per-query details (including refusal and llm_error)

Current answer artifact snapshot (eval/ragas_report_latest.json):
- query_count = 22
- faithfulness = 0.6071
- answer_relevancy = 0.0206

Regression/quality controls:
- Faithfulness drop gate: max drop 0.02 vs baseline (quality_gate.py)
- Graph vs legacy parity artifact: accepted diff = 0 (22 accepted in both modes)

---

## 5) What Happens When the System Fails?

Failure handling is explicit and layered.

Observed/handled failure classes:
1. Low-confidence retrieval:
- Refusal policy returns refused=true with score/threshold diagnostics.

2. LLM empty or failed generation:
- Retry with larger token budget.
- If still empty, fallback to extractive grounded answer.

3. Reranker unavailable:
- Return retrieval-only results and include rerank_error.

4. Planner rewrite misses:
- Fallback chain retries original query, anchor terms, and mode fallback (bm25 -> hybrid).

5. Usage query drift:
- Entity-first fallback retrieval (bm25/hybrid/vector on extracted entity).
- Rerank guardrail restores pre-rerank entity-containing hits when needed.

6. Startup/connect instability:
- Blocking connect mode available: /connect?background=false.

7. Embedding dimension mismatch:
- Optional auto-recreate table when configured.

Net behavior target:
- Prefer safe refusal or grounded fallback over ungrounded hallucinated answer.

---

## 6) What Are Latency and Cost?

What is currently measured and evidenced:
- Vector index query execution (EXPLAIN ANALYZE sample): about 4.47 ms.
- FTS query execution (EXPLAIN ANALYZE sample): about 2.67 ms.
- These are database-stage timings, not full end-to-end API latency.

What affects latency most:
- Cross-encoder reranking (optional) adds second-stage inference cost.
- LLM generation dominates when llm=true.
- Retry paths (empty LLM response retry, planner fallback) add tail latency.

What affects cost most:
- LLM calls (primary answer generation + optional rewrite pass).
- Larger max token budgets and retries increase token spend.
- Running llm=false enables extractive mode with near-zero external model cost.

Current gap:
- No first-class, persisted per-request token/cost telemetry in API response artifacts yet.
- Next step is to add request-level timing and token accounting fields for p50/p95 latency and cost per answer.

---

## 7) Why This Architecture?

Architecture choice is intentional for this domain.

Current stack rationale:
- PostgreSQL + pgvector + FTS:
  - one store for vectors + metadata + lexical indexing
  - supports hybrid retrieval with manageable ops overhead

- Hybrid retrieval (vector + bm25-style FTS + RRF):
  - balances semantic intent and exact token precision

- Optional cross-encoder reranker:
  - improves ranking quality when precision matters
  - can be disabled for lower latency

- Refusal + grounded fallback strategy:
  - improves trustworthiness under weak evidence

- Graph orchestration option with legacy fallback:
  - allows planner/executor/validator loop while preserving deterministic fallback path

- SQLite chat persistence:
  - simple, local, reliable session memory for conversational workflows

This is a practical, incremental architecture: production-like quality controls without over-engineering infra too early.

---

## 8) Can You Explain the Trade-Offs?

Key trade-offs in current implementation:

1. Hybrid vs single-mode retrieval:
- Pro: better robustness across semantic and identifier-heavy queries.
- Con: more moving parts and score calibration complexity.

2. Reranking on/off:
- Pro: higher precision in top-k results.
- Con: extra inference latency and compute.

3. Strict refusal thresholds:
- Pro: reduces hallucination risk.
- Con: can increase false refusals for borderline but useful evidence.

4. Graph orchestration vs legacy path:
- Pro: policy-driven retries and quality gating.
- Con: control flow complexity and harder debugging.

5. Local sentence embeddings vs managed embedding API:
- Pro: lower variable cost, offline-friendly.
- Con: model management responsibility and hardware sensitivity.

6. SQLite session memory:
- Pro: simple persistence with low overhead.
- Con: limited for multi-tenant/high-concurrency scaling without migration.

---

## Progress Alignment Summary (S01 -> S10 + P3 Integration)

- S01-S02: Foundation (parsing, chunking, vector store, lineage extraction)
- S03-S04: Retrieval quality upgrades (hybrid, rerank, refusal, eval baseline)
- S05-S06: Evaluation rigor + quality gates + graph parity and contract simplification
- S07: Conversational productization and usage-entity grounding guardrails
- S08: Semantic-first pivot for deterministic lineage/impact truth
- S09: NetworkX runtime lineage/impact traversal and cross-workflow field identity tracing
- S10: Graph-first ingestion + linked explanation artifacts with semantic evidence ID binding
- P3 integration: two-week observability extension committed inside current project scope

This means the project is no longer just "RAG retrieval demo"; it is now an evidence-grounded assistant with measurable quality controls and failure-safe behaviors.

---

## Recommended Next Alignment Milestones

1. Execute Week +1 observability foundation:
- request trace context propagation
- per-stage timing telemetry
- LLM token/cost telemetry fields
- structured event schema for semantic-first flows

2. Execute Week +2 observability operations:
- p50/p95/p99 latency snapshots and alerts
- refusal/error spike alerts
- observability-aware quality gates and incident runbook

3. Strengthen answer relevance:
- raise answer_relevancy through prompt/data tuning and targeted eval rows
- keep faithfulness gate active to avoid regressions

4. Expand failure drills:
- synthetic chaos tests for reranker/LLM/DB outages
- verify fallback/refusal behavior remains deterministic

5. Add architecture decision records:
- capture why each major trade-off was chosen and under what assumptions
