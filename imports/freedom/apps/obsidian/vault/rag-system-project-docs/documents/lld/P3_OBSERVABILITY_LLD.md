# P3 - Observability and Monitoring LLD (Integrated into rag-system)

## 1) Purpose

Integrate observability directly into the existing rag-system so semantic-first correctness, latency, reliability, and cost can be measured per request and enforced through quality gates.

## 2) Integration Decision

P3 is no longer treated as a separate stream. It is merged into the current rag-system execution plan.

Decision:
1. Keep one project track (semantic-first graph architecture + observability in same repo).
2. Extend current project by two weeks to implement and validate P3 scope end-to-end.

## 3) Scope

### 3.1 In Scope

1. Trace context propagation across ingest, retrieve, and answer paths.
2. Structured telemetry/event schema for semantic-first + vector-secondary flows.
3. Request-level latency/cost/reliability metrics for `/answer`, `/retrieve`, `/semantic/*`.
4. Dashboard and alert definitions.
5. Regression gates and incident runbook updates.

### 3.2 Out of Scope

1. Multi-region observability infra.
2. Full APM vendor migration.
3. Cross-service distributed tracing beyond current repo boundaries.

## 4) Two-Week Extension Plan

### Week +1 (Observability Foundation)

1. Add request trace context model:
	- `request_id`, `session_id` (if present), `answer_id` (if present), `workflow_hint`, `intent`, `orchestration_mode`.
2. Add request timing envelope:
	- total latency, semantic query latency, retrieval latency, rerank latency, LLM latency.
3. Add LLM usage/cost fields:
	- model, prompt/completion tokens (when available), estimated cost, retry count.
4. Add structured event schema (JSON log shape) for key stages:
	- ingest start/end
	- semantic query start/end
	- secondary retrieval strategy used
	- refusal reason emitted
5. Surface telemetry in API response payload (non-breaking additive fields).

### Week +2 (Operations and Gates)

1. Build observability summary endpoints/reports:
	- p50/p95/p99 latency snapshots
	- refusal rate by reason
	- LLM error/retry rate
	- semantic-vs-retrieval routing ratio
2. Define alert thresholds:
	- latency regression threshold
	- semantic guardrail refusal spike
	- LLM error rate spike
3. Extend quality gate checks:
	- enforce max latency/cost regression budget
	- enforce no semantic guardrail bypass
4. Publish incident runbook:
	- triage flow for semantic layer outages
	- triage flow for vector/LLM degradation
	- rollback and fallback playbook

## 5) Technical Design

### 5.1 Telemetry Envelope (API Payload)

Additive `telemetry` section (example):

```json
{
  "telemetry": {
	 "request_id": "req_...",
	 "intent": "lineage",
	 "orchestration_mode": "semantic_primary",
	 "timings_ms": {
		"total": 842,
		"semantic": 41,
		"secondary_retrieval": 19,
		"llm": 731
	 },
	 "llm": {
		"model": "...",
		"used": true,
		"retries": 1,
		"prompt_tokens": 1320,
		"completion_tokens": 280,
		"estimated_cost_usd": 0.0123
	 },
	 "routing": {
		"semantic_status": "ok",
		"secondary_strategy": "semantic_explanation_vectors"
	 }
  }
}
```

### 5.2 Structured Event Schema (Log)

Common fields:
1. `timestamp`
2. `event_name`
3. `request_id`
4. `workflow_hint`
5. `intent`
6. `status`
7. `duration_ms`
8. `error_code` (if any)

Event families:
1. `ingest.*`
2. `semantic_query.*`
3. `secondary_retrieval.*`
4. `llm_generation.*`
5. `answer_finalized`

### 5.3 Metrics Contract

Core metrics:
1. `answer_latency_ms` (p50/p95/p99)
2. `semantic_query_latency_ms`
3. `secondary_retrieval_latency_ms`
4. `llm_latency_ms`
5. `llm_error_rate`
6. `refusal_rate_by_reason`
7. `semantic_primary_ratio`

## 6) Acceptance Criteria

1. Every `/answer` response includes trace context and timing envelope.
2. Semantic-first flows expose whether secondary strategy was linked explanation vectors or generic fallback.
3. Latency and error metrics are reportable with p50/p95 and reason breakdowns.
4. Quality gates fail on configured latency/cost regressions.
5. Runbook includes deterministic triage steps for semantic/vector/LLM failures.

## 7) Risks and Mitigations

1. Risk: telemetry overhead degrades hot-path latency.
	- Mitigation: monotonic timers, lightweight logging, sampling for verbose logs.
2. Risk: payload bloat for clients.
	- Mitigation: compact telemetry schema and opt-in verbosity where needed.
3. Risk: token/cost unavailable from provider in some paths.
	- Mitigation: include `null` with explicit `estimation_method` fallback.

## 8) Deliverables

1. Code updates in rag-system API and orchestration paths.
2. Updated docs:
	- `rag-system/SYSTEM_E2E_FLOW.md`
	- `rag-system/API_TESTING.md`
	- `rag-system/PROJECT_REVIEW_QA_ALIGNMENT.md`
3. Test coverage and benchmark artifacts for observability acceptance.

## 9) Status

P3 is now integrated into the current project scope with a two-week extension and execution tracking under rag-system.
