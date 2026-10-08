# RAG System Conceptual Bible (Tracker Excluded)

> For the merged deep-read walkthrough that combines conceptual architecture + E2E + code examples, see [PROJECT_BIBLE.md](./PROJECT_BIBLE.md).

This document captures the core concepts, authority boundaries, and runtime patterns used by the `rag-system` application.

## 1. System Posture

The system runs a **semantic-first truth layer** plus a **RAG copilot layer**:

1. Semantic layer is authoritative for lineage/impact truth.
2. Retrieval/LLM layers are advisory for explanation and conversational UX.
3. If semantic evidence is missing for lineage/impact, the system must refuse rather than synthesize.

## 2. Authority Boundaries

### 2.1 Authoritative

- Structured semantic entities (`workflow`, `mapping`, `node`, `port`, `connector`, `lineage_path`)
- Deterministic lineage/impact query results
- Semantic status codes (`ok`, `workflow_not_indexed`, `field_not_found`)

### 2.2 Non-Authoritative

- Vector/BM25 chunks
- LLM-generated text
- Explanation artifacts derived from semantic facts
- Telemetry and observability payloads

## 3. Core Data Layers

### 3.1 Ingestion Layer

Transforms Informatica PowerCenter XML into normalized runtime artifacts:

1. Parse XML to canonical nodes and connectors.
2. Build deterministic semantic model tables.
3. Build retrieval chunks for copilot workflows.
4. Generate embeddings and upsert into vector store.

### 3.2 Semantic Layer

Persistent deterministic model under `rag.semantic_*` tables:

- `semantic_workflows`
- `semantic_mappings`
- `semantic_nodes`
- `semantic_ports`
- `semantic_connectors`
- `semantic_lineage_paths`
- `semantic_lineage_hops`

This layer exists to answer lineage/impact with exact workflow/field constraints.

### 3.3 Retrieval Layer

Context system for natural language and explanation:

- Vector similarity retrieval (pgvector)
- Lexical retrieval (PostgreSQL FTS)
- Hybrid fusion (RRF)
- Optional cross-encoder reranking

## 4. Graph Intelligence

NetworkX lineage graph is used as deterministic accelerator:

1. Build workflow connector graphs.
2. Resolve lineage/impact through graph traversal.
3. Keep graph hash/version metadata for traceability.

Key rule: graph and SQL semantic queries are both deterministic paths; vector retrieval is never the truth source for lineage/impact claims.

## 5. Query Intent Model

The router classifies user intent and chooses execution path:

- `lineage` or `impact` -> semantic-primary path
- `usage`, `sql_override`, `logic`, generic exploration -> retrieval path

For semantic-first intents:

1. Workflow hint and field anchor are required.
2. Missing anchors produce explicit refusal reason.
3. Secondary vector context may be attached only after semantic proof exists.

## 6. Retrieval Concepts

### 6.1 Chunking

Chunking is object-boundary and workflow-aware:

- Chunk IDs are stable and deduplicated.
- Metadata captures node class, source file, mapping context, and feature flags.
- Chunks represent retrievable context, not deterministic truth.

### 6.2 Embedding Provider Chain

Runtime provider fallback model:

1. Azure embedding provider (when configured/available)
2. Local sentence-transformer provider
3. Hashing fallback provider

This keeps development and production resilient to provider outages.

### 6.3 Hybrid Ranking

Hybrid mode fuses lexical and vector lists to improve precision/recall balance.

- RRF helps merge rank sources.
- Reranker improves top-k ordering quality.
- Refusal thresholds rely on similarity-quality signals, not fused-rank values alone.

## 7. Answer Orchestration

Two orchestration modes may exist (`legacy` and `graph`) but must preserve answer contract compatibility.

Graph-mode principle:

1. State handoff fields must be declared in graph state schema.
2. Missing schema keys can silently drop planner outputs.
3. Parity tests must validate graph vs legacy acceptance behavior.

## 8. Evidence-First Answer Contract

Answer responses carry:

- Strategy/orchestration markers
- Refusal flags and reasons
- Ordered evidence list (semantic first when applicable)
- Optional citations and explanation text

Evidence ordering rule:

1. `semantic_layer` evidence first for semantic-primary answers.
2. `vector_secondary` evidence next (optional).

## 9. Conversational Runtime Concepts

The API supports chat sessions and memory behavior to improve continuity:

1. Session lifecycle and persisted transcript.
2. Memory summaries for long-running interactions.
3. Capability/context responses for onboarding prompts.

This improves UX without changing semantic truth boundaries.

## 10. Observability Concepts

Week +1 introduces additive response telemetry:

- `trace`: request identity and route context
- `telemetry.timing_ms`: stage-level latencies
- `telemetry.events`: lifecycle stage summaries
- `telemetry.usage`: provider usage/cost placeholders

Observability contract:

1. Diagnostics must not influence truth decisions.
2. Telemetry can explain behavior, not change behavior.
3. Semantic-first refusal policy remains authoritative.

## 11. Quality, Evaluation, and Gates

Quality control is layered:

1. Smoke/integration tests for contract and regression safety.
2. Golden/candidate datasets for deterministic acceptance checks.
3. Graph-vs-legacy parity reports.
4. Answer-level RAGAS artifacts for generation quality tracking.

Metric governance pattern:

- Keep baseline artifacts locked.
- Compare each run as delta from baseline.
- Treat faithfulness/relevancy trends as optimization inputs, not one-time scores.

## 12. Operational Concepts

### 12.1 Ingest/Connect Lifecycle

- `POST /ingest`: full parse -> semantic build -> embedding -> upsert
- `POST /connect`: attach to existing indexed state without full rebuild

### 12.2 Concurrency and Safety

- Ingest/connect operations are lock-protected.
- API readiness is explicit (`/health` and semantic/model snapshots).
- Deterministic refusals are preferred over speculative answers.

## 13. Failure Philosophy

System behavior under uncertainty:

1. Fail explicitly with deterministic reason codes.
2. Preserve authority boundaries under partial degradation.
3. Keep fallback behavior visible and diagnosable.
4. Never silently convert missing semantic proof into generated truth claims.

## 14. What This Bible Excludes

This document intentionally excludes tracker-specific product concepts (portfolio UX, flashcards, STAR rendering workflows), and focuses only on the `rag-system` runtime and architecture.
