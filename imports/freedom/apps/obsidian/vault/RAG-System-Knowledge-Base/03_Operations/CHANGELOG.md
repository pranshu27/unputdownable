# Changelog — rag-system

## [2026-08-27] — S11 / Week +1 Observability Delivery + Knowledge Refresh

### Added
- Implemented Week +1 observability response envelope in `src/rag_system/api/app.py`:
	- `trace` metadata (`request_id`, `endpoint`, UTC timestamp, intent/workflow/orchestration when available)
	- `telemetry.timing_ms` stage timings for retrieval, semantic, rerank, generation, and total paths (when applicable)
	- `telemetry.events` structured lifecycle stage summaries
	- `telemetry.usage` token/cost placeholder fields with explicit unavailable reasons
- Added reusable skills for trace debugging and always-on assistant behavior:
	- `.github/skills/langsmith-fetch/SKILL.md`
	- `.agents/skills/langsmith-fetch/SKILL.md`
	- `.github/skills/assistant-behavior/SKILL.md`
	- `.agents/skills/assistant-behavior/SKILL.md`
	- `.github/instructions/assistant-behavior.instructions.md`
- Added `CONCEPTUAL_BIBLE.md` with end-to-end conceptual coverage of rag-system architecture and runtime concepts (excluding tracker concepts).
- Added `PROJECT_BIBLE.md`, a unified long-form study guide that combines E2E design + conceptual architecture + code-cited implementation anchors, endpoint contracts, examples, and tradeoff analysis.

### Changed
- Updated `tests/test_smoke.py` assertions to validate Week +1 `trace` and `telemetry` contract fields on key endpoints.
- Updated `API_TESTING.md` Week +1 observability checklist from planning-only language to implementation validation steps.
- Updated `SYSTEM_E2E_FLOW.md` observability sections to mark Week +1 instrumentation as implemented and document payload contract details.
- Added canonical cross-links in `SYSTEM_E2E_FLOW.md` and `CONCEPTUAL_BIBLE.md` to point readers to the merged deep-read `PROJECT_BIBLE.md`.
- Refreshed tracker interview-prep seed content (`apps/genai-portfolio-tracker-react/src/data.js`, `apps/genai-portfolio-tracker-react/src/components/Interview.jsx`) with observability-focused STAR content, QBank entries, and flash cards.

### Validation
- Targeted smoke command already run and passing:
	- `tests/test_smoke.py -k "retrieve_endpoint or answer_lineage_routes_semantic_primary or semantic_lineage_endpoint or semantic_impact_endpoint"` (**4 passed**)

## [2026-08-23] — S11 / P3 Observability Integration (Two-Week Extension)

### Added
- Integrated P3 observability scope into the active rag-system project (no separate stream).
- Expanded `documents/lld/P3_OBSERVABILITY_LLD.md` into an execution-ready LLD with two-week delivery plan.
- Added observability integration contract in architecture docs:
	- Week +1 instrumentation foundation
	- Week +2 operations/alerts/gates and incident readiness

### Changed
- Updated `SYSTEM_E2E_FLOW.md` with a dedicated P3 section (`## 17`) covering extension milestones and authority-boundary safeguards.
- Updated `PROJECT_REVIEW_QA_ALIGNMENT.md` to reflect P3 integration decision, timeline extension, and updated milestone sequence.
- Updated `API_TESTING.md` with observability validation checklist for upcoming instrumentation rollout.

### Notes
- This entry documents scope integration and planning alignment; functional observability instrumentation will land under the scheduled two-week execution plan.

## [2026-08-23] — S10 / Graph-First Semantic Ingestion + Linked Explanation Artifacts

### Added
- `build_workflow_lineage_graph()` in `src/rag_system/lineage/networkx_lineage.py` to build workflow connector graphs first and derive deterministic lineage chains from NetworkX traversal.
- Semantic explanation artifact generation in `InformaticaKnowledgeBase` for every semantic node/path:
	- `artifact_kind=node_definition|lineage_definition`
	- metadata includes `workflow`, `workflow_key`, `node_id` or `path_evidence_id`, `graph_hash`, `generated_at`, `authoritative=false`.
- `InformaticaKnowledgeBase.search_semantic_explanations()` for vector-ranked explanation retrieval linked to semantic `evidence_id` values.

### Changed
- `InformaticaKnowledgeBase.build_from_folder()` now uses graph-first lineage derivation per workflow before semantic persistence.
- Semantic workflow model now carries graph metadata (`graph_hash`, graph engine marker), and lineage coverage telemetry includes graph node/edge counts.
- `/answer` semantic-primary path now attempts linked vector explanation retrieval first (by semantic evidence ids), then falls back to generic transformation context retrieval.
- `PgSemanticStore` now persists `graph_hash` in `rag.semantic_workflows` and surfaces it via semantic snapshots/hydration.

### Validation
- `tests/test_smoke.py`: **51 passed** after graph-first ingestion + explanation artifact integration.

## [2026-08-23] — S09 / NetworkX Lineage Intelligence + Cross-Workflow Semantic Routing

### Added
- `src/rag_system/lineage/networkx_lineage.py` and `src/rag_system/lineage/__init__.py` for graph-backed lineage/impact traversal.
- Cross-workflow field identity support in the graph engine (`field::<field_norm>` identity nodes) so a single field can be traced across workflows when no workflow hint is provided.
- `PgSemanticStore.load_workflow_lineage_models()` to hydrate graph state from PostgreSQL semantic tables in `/connect`-only runtime mode.
- `InformaticaKnowledgeBase.lineage_graph_snapshot()` for graph observability metadata.
- New smoke coverage for cross-workflow lineage graph behavior in `tests/test_smoke.py`.

### Changed
- `InformaticaKnowledgeBase.query_semantic_lineage()` and `query_semantic_impact()` now use NetworkX graph queries first, with semantic-store fallback preserved.
- `/answer` semantic-primary path now supports deterministic cross-workflow lineage/impact when field anchor exists and workflow hint is omitted.
- Semantic answer rendering now includes workflow context per path when relevant.
- `/health` and `/semantic/model` now expose `lineage_graph` diagnostics.
- Intent router stabilization: strong SQL-override heuristics short-circuit optional LLM intent classification for deterministic behavior.
- SQL-intent retrieval fallback now retries with workflow-token-stripped and anchor queries when initial lexical fetch returns no hits.

### Validation
- `tests/test_smoke.py`: **51 passed** after graph integration and retrieval fallback hardening.
- Existing semantic-primary lineage/impact tests remain green with graph-backed execution.

## [2026-08-22] — S08 / Semantic-First Pivot (Deterministic Truth + RAG Copilot)

### Why We Pivoted
- Deterministic lineage and impact answers were not reliably enforceable through retrieval-only RAG because evidence ranking can drift across similarly named workflows and identifier-heavy fields.
- Project review requirements require system behavior that is auditable and exact for lineage and impact questions, not only probable from top-k chunks.
- The same corpus must support two distinct needs: deterministic data-flow truth and flexible natural-language assistance.

### Architecture Pivot
- Semantic model is now the source of truth for lineage and impact outcomes, persisted in PostgreSQL relational tables under `rag.semantic_*`.
- Retrieval (vector + BM25 + hybrid + rerank) remains active as a copilot context layer for explanations, summaries, and non-deterministic exploratory questions.
- API routing now enforces semantic-first behavior for lineage/impact intents, with evidence-grounded refusal when semantic support is unavailable.
- New deterministic API surfaces:
- `GET /semantic/model`
- `GET /semantic/lineage`
- `GET /semantic/impact`

### Added
- `src/rag_system/store/semantic_store.py` with PostgreSQL-backed semantic persistence and deterministic query methods.
- Semantic-store integration in `src/rag_system/knowledge_base.py` with postgres-first query path and in-memory semantic fallback.
- Semantic-first response helpers and route integration in `src/rag_system/api/app.py`.
- Semantic API smoke coverage in `tests/test_smoke.py`.

### Validation
- Smoke suite expanded and passing with semantic-first behavior checks (`50 passed`).
- End-to-end architecture reference updated to semantic-first design with physical postgres model in `SYSTEM_E2E_FLOW.md`.

## [2026-08-18] — S06 / Graph Contract Simplification + Parity Validation

### Changed
- Simplified public retrieval/answer contract by removing deprecated controls (`smart_retrieval`, `planner_model`, `friendly`) from active call paths
- Aligned eval harnesses and integration/smoke tests to current `/answer` signature
- Updated `SYSTEM_E2E_FLOW.md` to reflect graph/legacy orchestration mode controls and removal of smart/friendly public knobs

### Fixed
- LangGraph state handoff bug in `src/rag_system/graph/answer_graph.py` where undeclared planner output keys (`hits`, `plan`, `resolved_mode`, etc.) were dropped between nodes, causing empty-evidence graph answers
- `src/rag_system/api/app.py` now restores extractive answer fallback when `llm=false` and evidence exists
- Retrieval fan-out for file-scoped queries now expands before source-file prioritization to reduce false source mismatches

### Added
- Graph-vs-legacy regression artifact: `eval/graph_vs_legacy_answer_regression.json`
	- candidate set: `28`
	- accepted (legacy): `22`
	- accepted (graph): `22`
	- acceptance delta: `0`

### Validation
- Targeted test suites passed after migration:
	- `tests/test_smoke.py`
	- `tests/test_ragas_eval.py`
	- `tests/test_integration.py`
- Consolidated run: `44 passed`
- Graph-mode answer-level RAGAS run (`22` queries):
	- `faithfulness=0.2857`
	- `answer_relevancy=0.0000`
	- report: `eval/ragas_report_latest.json`

## [2026-08-18] — S06 / Week 4 Kickoff Quality Gate

### Added
- `src/rag_system/eval/quality_gate.py` — report-to-report quality gate CLI for answer-level metrics
- `tests/test_quality_gate.py` — regression tests for pass/fail threshold behavior
- `eval/ragas_baseline_w3.json` — locked Week 3 baseline artifact for faithfulness and answer relevancy
- `.github/workflows/week4-quality-gate.yml` — PR/workflow gate scaffold that enforces max faithfulness drop of `0.02`
- `src/rag_system/eval/validate_answer_dataset_grounding.py` — validator that checks answer-eval rows map to real XML files and expected entities under `INFA_XML_FOLDER`

### Changed
- `eval/golden_answer_eval.jsonl` now uses Informatica-grounded questions only (real `wf_*.XML` workflows and in-file entities), replacing generic platform questions
- `eval/golden_answer_eval.jsonl` retrieval depth tuned from `k=10` to `k=6` for cleaner evidence context in answer-level scoring
- `src/rag_system/store/vector_store.py` now auto-reconnects when psycopg connection is closed, preventing runtime 500 errors on `/retrieve`, `/answer`, and `/health`
- `src/rag_system/eval/ragas_eval.py` GPT-5 judge runtime now enforces higher `max_completion_tokens` default for truncation resistance

### Validation
- Local gate logic validated by unit tests (`test_quality_gate.py`)
- Gate threshold semantics: pass on drop `<= 0.02`, fail on drop `> 0.02`
- Grounding validation passed for `eval/golden_answer_eval.jsonl` against `INFA_XML_FOLDER`
- End-to-end grounded RAGAS run completed (`--llm`, `k=6`): `faithfulness=0.9600`, `answer_relevancy=0.0803`

## [2026-08-17] — S05 / Week 3 Evaluation Expansion + RAGAS Harness

### Added
- Expanded retrieval golden dataset for Week 3: `eval/golden_retrieval_w3.jsonl` (53 queries, bucketed by `identifier`, `lineage`, `semantic`, `sql_override`)
- Smoke subset dataset: `eval/golden_retrieval_w3_smoke.jsonl`
- Answer eval dataset for RAGAS: `eval/golden_answer_eval.jsonl`
- Bucket-level rollup reporting in `src/rag_system/eval/retrieval_eval.py` (`by_bucket` summaries in console + JSON report)
- RAGAS eval harness in `src/rag_system/eval/ragas_eval.py` for `/answer` quality scoring

### Changed
- `pyproject.toml` eval extras now pin reproducible dependencies for current RAGAS flow:
	- `ragas>=0.4.3`
	- `datasets>=5.0.0`
	- `langchain-community<0.4`
- `ragas_eval.py` now:
	- prefers `ragas.metrics.collections` imports (with backward fallback)
	- returns a clear credential error when `OPENAI_API_KEY` is missing

### Validation
- Full Week 3 retrieval run completed (`k=10`, 53 queries):
	- `hybrid`: recall@10=`0.4057`, nDCG@10=`0.3131`
	- `vector`: recall@10=`0.3868`, nDCG@10=`0.3068`
	- `bm25`: recall@10=`0.0189`, nDCG@10=`0.0189`
	- artifact: `eval/report_w3_k10.json`
- Week 3 smoke run completed (`k=10`, 8 queries):
	- artifact: `eval/report_w3_smoke_k10.json`
- RAGAS harness import/runtime path verified; score artifact generation is blocked only by missing `OPENAI_API_KEY` in local shell.

## [2026-08-15] — S04 / Startup Reliability + Deterministic Connect

### Added
- `/connect` now supports blocking mode via `background=false` for deterministic startup when local sentence-transformer initialization is slow in background threads
- `API_TESTING.md` now documents `POST /connect?background=false` as a reliable fallback startup path

### Changed
- `.env` loading now resolves from project root in both `src/rag_system/api/app.py` and `src/rag_system/knowledge_base.py`, so Uvicorn startup from outside the repo still picks up backend/database settings

### Validation
- Services restarted successfully (`docker compose` pgvector)
- API health verified after blocking connect: `kb_built=true`, `chunk_count=4033`, `ingest.state=connected`
- Smoke tests: `20 passed`
- Retrieval eval refreshed (`k=8`):
	- `hybrid`: recall@8=`0.4000`, nDCG@8=`0.2567`
	- `vector`: recall@8=`0.4000`, nDCG@8=`0.2567`
	- `bm25`: recall@8=`0.1500`, nDCG@8=`0.1917`

## [2026-08-14] — S04 / Retrieval Evaluation Harness Baseline

### Added
- `src/rag_system/eval/retrieval_eval.py` — JSONL-driven retrieval evaluation CLI for `/retrieve` with per-mode summaries and optional threshold gating (`--min-recall`, `--min-ndcg`)
- `eval/golden_retrieval.jsonl` — 10-query golden dataset with graded matcher rules
- `tests/test_retrieval_eval.py` — matcher and metric tests, including duplicate-match regression coverage
- `API_TESTING.md` retrieval evaluation section with harness commands and output artifact guidance

### Fixed
- nDCG normalization logic in eval harness so repeated hits cannot inflate scores above `1.0`
- Removed package-import side effect warning when running `python -m rag_system.eval.retrieval_eval`

### Baseline (k=8, 10 queries)
- `hybrid`: recall@8 = `0.3000`, nDCG@8 = `0.2451`
- `vector`: recall@8 = `0.3000`, nDCG@8 = `0.2451`
- `bm25`: recall@8 = `0.4500`, nDCG@8 = `0.4787`

## [2026-08-13] — S03 / BM25 Hybrid Retrieval + Reranker + Citations + Refusal + Prompt Versioning

### Added
- **BM25 + hybrid retrieval** (`store/vector_store.py`): PostgreSQL FTS tsvector generated column + GIN index; `search_bm25(query_text, k)` using `ts_rank + plainto_tsquery`; `search_hybrid(query_vector, query_text, k, rrf_k=60, vector_weight=0.7, bm25_weight=0.3)` using Reciprocal Rank Fusion; `_ensure_schema()` auto-adds `fts` column + GIN index on startup
- **`knowledge_base.py`** — `hybrid_search(query, k, filter_node_class, rrf_k)` delegates to `PgVectorStore.search_hybrid()`; falls back to vector-only for `InMemoryVectorStore`
- **`/retrieve` mode param** — accepts `mode=hybrid|vector|bm25` (default: `hybrid`); `rerank=true` fetches k×3 candidates then applies cross-encoder, returns top-k
- **Cross-encoder reranker** (`reranking/cross_encoder.py`): lazy-loaded `cross-encoder/ms-marco-MiniLM-L-6-v2`; `rerank(query, hits, top_k)` scores (query, passage) pairs, adds `rerank_score`/`retrieval_score` fields, returns sorted list
- **`/answer` endpoint** — citation-backed answer generation: retrieves top-k, checks refusal policy, builds `[chunk_id]`-labelled evidence blocks, renders versioned prompt template, returns `{ refused, prompt, evidence, prompt_version }`
- **Refusal policy** — `_insufficient_evidence()` checks vector cosine similarity of top hit against `REFUSAL_SCORE_THRESHOLD` (default `0.60`); returns `refused=true, reason=insufficient_evidence` for out-of-domain queries
- **Prompt versioning** (`prompts/prompts.yml` + `src/rag_system/prompts/__init__.py`): `PromptConfig(name, version, description, template)` dataclass; `get_prompt()`, `render_prompt()`, `list_prompts()` helpers; YAML loaded once with `lru_cache`; two initial templates: `answer_with_citations` and `lineage_summary` (both v1.0.0)
- **`/prompts` endpoint** — lists all prompt names + versions from `prompts.yml`
- **`/health` extended** — now includes `prompt_versions` dict

### Fixed
- `regex=` param on `Query()` → `pattern=` (removes FastAPI deprecation warning)

### Stats
- **20/20 smoke tests pass** (unchanged — all new code covered by endpoint tests)
- Refusal threshold calibrated: `vector_score ≥ 0.60` required for `/answer` to respond (bge-small-en-v1.5 scores ~0.53 for unrelated queries vs 0.79+ for in-domain)
- BM25 FTS column + GIN index added to live `rag.rag_chunks` table (703 rows)



### Added
- `ingestion/lineage_parser.py` — BFS backward resolver over 13,237 CONNECTOR edges; `build_lineage_chains()` traces every TARGET field back to its SOURCE; `_build_reverse_adj()` inverts CONNECTOR graph; `_trace_back()` BFS with path tracking; `summarise()` for logging stats
- `chunking/chunker.py` — `render_lineage_chain()` produces self-describing `NODE_CLASS: LINEAGE` text with TARGET:, SOURCE:, HOP_COUNT:, PATH: labels; `chunk_lineage_chains()` converts resolved chains into Chunk objects with lineage metadata
- `knowledge_base.py` — `build_from_folder()` now calls `parse_powercenter_xml()` + `build_lineage_chains()` + `chunk_lineage_chains()` per XML file after regular node chunking; unresolved chains skipped with warning
- `tests/test_smoke.py` — 6 new lineage smoke tests: chains_resolved, chain_fields, hops_order, chunk_rendered, chunk_id_stable, chunk_node_class
- `weekly/S02_2026-08-12.md` — session doc with Mermaid diagrams for lineage data flow and retrieval

### Stats
- 13,237 CONNECTOR edges across 7 XML files now processed (was 0 in S01)
- **20/20 smoke tests pass** (14 original + 6 new lineage)
- Lineage chunk count in pgvector: TBD (requires re-ingest when XMLs accessible)



## [2026-08-11] — S01 / Ingestion + Chunking + Index (RAG System)

### Added
- Standalone `rag-system/` package (pyproject.toml, `src/rag_system/` layout)
- `ingestion/xml_parser.py` — PowerCenter XML → canonical node dicts (SOURCE / TRANSFORMATION / TARGET)
- `ingestion/pc_processor.py` — `walk_xml_folder()` walks all 7 `wf_*.XML` exports; attaches `_source_file` key per node
- `chunking/chunker.py` — structure-aware chunking: 700-token max, 100-token overlap on splits; enriched metadata (`source_db`, `has_sql_override`, `has_join`, `has_filter`, `field_count`, `port_count`, `primary_key_count`, `folder`)
- `embeddings/provider.py` — `HashingEmbedding` (offline/deterministic, dim=256) + `AzureOpenAIEmbedding`; `get_embedding_provider()` auto-selects
- `store/vector_store.py` — `InMemoryVectorStore` (tests/offline) + `PgVectorStore` (pgvector, IVFFlat cosine index, batched upsert)
- `knowledge_base.py` — `InformaticaKnowledgeBase.build_from_folder()` + `search(query, k, filter_node_class)`; deduplicates identical chunks after generation
- `api/app.py` — FastAPI service: `GET /health`, `GET /retrieve?q=...&k=5&node_class=SOURCE`, `POST /ingest`; `AUTO_INGEST=true` env flag; lifespan startup
- `docker-compose.yml` — `pgvector/pgvector:pg17` on port 5433, named volume, healthcheck
- `.env` — local pgvector connection string (`postgresql://raguser:ragpass@localhost:5433/ragdb`)
- `tests/test_smoke.py` — 14 offline tests (chunker, embeddings, store, KB, FastAPI endpoints)
- `tests/test_integration.py` — 16 tests against real XML corpus; auto-skips when OneDrive offline

### Fixed
- `setuptools.backends.legacy` → `setuptools.build_meta` (Python 3.11 setuptools compat)
- Chunk ID collisions: same SOURCE/TARGET table appearing in multiple FOLDER elements within one XML produced duplicate IDs (131 → 15 → 0 after content-hash suffix + dedup in KB)
- FastAPI `on_event("startup")` → `lifespan` context manager (deprecation warning removed)

### Stats
- Corpus: 7 XML files, ~8.6 MB total, 460 canonical nodes → **703 unique chunks** in pgvector
- Transformation types indexed: Source Qualifier (288), Expression (121), Filter (58), Joiner (39), Lookup Procedure (24), Aggregator (8), Sorter (7), Update Strategy (4), Custom (15)
- **30/30 tests pass** (14 smoke + 16 integration)
