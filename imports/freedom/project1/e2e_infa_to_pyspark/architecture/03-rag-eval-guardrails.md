# 03 — RAG, Evaluation, Guardrails, Critic & Human-in-the-Loop

This document describes the advanced, production-style components added on top of the
core extractor → orchestrator → generator pipeline. Together they turn a "demo" agentic
script into a **resume-grade, e2e agentic system** with retrieval grounding, quality
measurement, safety, and human oversight.

The full flow now reads:

```
PowerCenter XML dump
   │
   ▼  (Phase 1: pub/sub + barrier)
PCExtractorAgent ──▶ PCResultCollectorAgent  ── normalized nodes
   │
   ▼  Input Guardrails  (PII / secrets / injection redaction)
   ▼  RAG  (cross-file TF-IDF retrieval → retrieved_context)
   │
   ▼  (Phase 2: orchestrator/worker)
OrchestratorAgent
   ├─ 1. DataModellerAgent     (RAG-grounded logical model: entities, SCD strategy)
   ├─ 2. PySparkGenerationAgent (per node) ─▶ Output Guardrails (schema / destructive SQL)
   ├─ 3. IcebergWriterAgent     (MERGE / write strategy)
   ├─ 4. ReviewAgent            (static review)
   ├─ 5. CriticAgent            (adversarial scoring → verdict + requires_human_review)
   └─ 6. human_review_gate      (auto in CI / interactive console approval)
   │
   ▼
FinalResult { data_model, pyspark_nodes, iceberg_write, review, guardrails, critic, human_decision }
```

---

## 1. RAG — Retrieval-Augmented Generation for the Data Modeller

**Why:** A single mapping rarely contains enough context to design a good model. The data
modeller needs to see *related* sources, targets, shared transformations, and naming
conventions that live across **all** Informatica files in the dump.

**What we built** (`app/rag/knowledge_base.py`):

- `InformaticaKnowledgeBase` indexes every `<SOURCE>`, `<TARGET>`, `<MAPPING>`,
  `<TRANSFORMATION>`, and `<CONNECTOR>` node across all XML files into `Document`s.
- Dependency-light **TF-IDF + cosine similarity** (no external vector store) — deterministic
  and runnable offline for evals/CI.
- `retrieve(query, k)` returns the top-k nodes; `build_context(query, k, max_chars)` packs
  them into a token-budgeted context block injected as `meta_data["retrieved_context"]`.

This runs **after extraction, before PySpark generation** — exactly where the modeller
needs grounding.

**Production swap-in:** Replace the TF-IDF index with pgvector / Azure AI Search / FAISS +
an embedding model. The `retrieve()` / `build_context()` interface stays identical, so only
the index internals change.

---

## 2. Evaluation — ROUGE + structural metrics

**Why:** "Is the model working fine?" needs a number, not a vibe. We measure generated
PySpark against a golden reference.

**What we built** (`app/evaluation/metrics.py`):

| Metric | What it captures |
| --- | --- |
| `rouge_n` (n=1,2) | n-gram overlap (precision/recall/F1) |
| `rouge_l` | longest common subsequence — order-aware similarity |
| `token_f1` | bag-of-tokens overlap |
| `exact_match` | strict equality |
| `is_parseable_python` | `ast.parse` — does it even compile? |
| `references_expected` | does the code use required symbols (e.g. `withColumn`, merge keys)? |

`evaluate(generated, reference, expected_symbols)` returns an `EvaluationResult`
(`.to_dict()`, `.overall_f1`); `evaluate_batch(pairs)` aggregates across a test set —
ready to wire into a **CI eval gate** that fails a PR if `overall_f1` drops below a
threshold.

**Production additions noted in code:** BLEU, CodeBLEU, embedding cosine similarity,
**execution-based parity** (run both pipelines on sample data and diff DataFrames), and
LLM-as-judge.

---

## 3. Guardrails — input and output safety

**Why:** Informatica exports can contain real connection strings, credentials, and PII.
LLM output can hallucinate destructive SQL or drop required schema fields. Both directions
need protection.

**What we built** (`app/guardrails/engine.py`) — each guardrail has `.name` and
`.check(text) → GuardrailResult` with an action of `ALLOW / REDACT / WARN / BLOCK`:

**Input guardrails** (`default_input_engine()`):
- `PIIGuardrail` — redacts SSN, email, phone, credit-card, IP.
- `SecretsGuardrail` — redacts `password=`, API keys, JDBC creds, Azure keys.
- `PromptInjectionGuardrail` — flags "ignore previous instructions"-style phrases.

**Output guardrails** (`default_output_engine()`):
- `DestructiveSQLGuardrail` — **blocks** `DROP` / `TRUNCATE` / `WHERE`-less `DELETE`.
- `SchemaGuardrail` — enforces required keys (`node_name`, `pyspark_code`).
- `SQLOverrideFidelityGuardrail` — ensures a hand-written SQL override survives translation.

The `GuardrailEngine` threads redactions through all guardrails and produces a
`GuardrailReport` (`.blocked`, `.findings`, `.to_dict()`) that is attached to the
`FinalResult` for auditability.

**Other guardrail types worth adding in production** (documented in the module): toxicity /
content moderation, topical (off-domain) filtering, token-budget caps, rate limiting,
output-length / infinite-loop breakers, and **groundedness** checks (does the answer cite
the retrieved context?).

---

## 4. Critic Agent — adversarial validation

**Why:** A second model that *tries to break* the output catches far more than a single
generator pass.

**What we built** (`app/agents/critic_agent.py`, `prompts/critic_prompt.py`):

- Scores the artifact 0–1 on **correctness, completeness, sql_fidelity, safety,
  determinism**.
- Emits JSON: `{ verdict: approve|revise|reject, confidence, scores, blocking_issues,
  suggestions, requires_human_review }`.
- Sets `requires_human_review = true` whenever `confidence < 0.85` **or** there are blocking
  issues — i.e. the machine escalates the hard cases to a human.
- Soft-fails closed: on any error it returns `verdict=revise` + `requires_human_review=true`
  (fail-safe, never fail-open).

---

## 5. Human-in-the-Loop gate

**Why:** "final PySpark output is validated by [a machine] first before being validated by a
human." The critic is the machine validator; the gate is the human one.

**What we built** (`app/agents/human_gate.py`):

- `human_review_gate(request, mode)` with `CONFIDENCE_THRESHOLD = 0.85`.
- **`auto` mode (CI/default):** auto-approves only when the critic did not flag
  `requires_human_review` *and* confidence ≥ 0.85; otherwise it **holds** for a human.
- **`interactive` mode:** prints the critic verdict + blocking issues and prompts the
  reviewer (`Approve? [y/N]`) at the console (`python -m app.run --human interactive`).
- Returns a `HumanReviewDecision { approved, reviewer, comments }` recorded in the
  `FinalResult`.

In production this callable wraps a queue / web-approval / Slack action instead of `input()`
— the agent contract is unchanged.

---

## 6. What else an e2e Agentic project should add

Beyond what's implemented, these are the components that take this from "great demo" to
"production platform" (call-outs map to patterns in the `des_` reference repos —
`helm/`, `buildspec.yml`, `docker-compose.yaml`):

**Observability & cost**
- Distributed tracing of every agent hop (OpenTelemetry; LangFuse / Phoenix for LLM spans).
- Per-run **token & cost accounting**, with budget alerts.
- Structured run logs + a run-id correlating extraction → model → codegen → critic.

**Reliability**
- Retries with backoff + **rate limiting** around the model client (already `max_retries=5`).
- **Dead-letter queue** for nodes that repeatedly fail extraction/generation.
- Idempotency keys so re-runs don't duplicate work.

**Data & retrieval**
- Real **vector DB** for RAG (pgvector / Azure AI Search) with periodic re-indexing.
- **Schema registry** + **lineage tracking** (OpenLineage / Marquez) for source→target maps.

**Quality & governance**
- **CI eval gate** using `evaluation/` — block merges when ROUGE/F1 regresses.
- **Prompt versioning** (prompts as versioned artifacts) + A/B prompt experiments.
- **Agent memory** / feedback loop: store human decisions and critic verdicts to fine-tune
  prompts and few-shot examples over time.
- Golden-dataset regression suite (execution-based parity on sample data).

**Delivery**
- Containerization + **Helm chart** for AKS deployment (mirrors `des_` repos).
- CI/CD (`buildspec.yml` / GitHub Actions): lint → unit tests → eval gate → image build.
- Secrets via Key Vault / managed identity (never in the XML or `.env` in prod).

**UX**
- A review UI surfacing the critic report, guardrail findings, and a diff of generated vs
  reference PySpark for the human approver.
