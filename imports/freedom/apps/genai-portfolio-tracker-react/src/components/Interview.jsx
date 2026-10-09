import { useEffect, useMemo, useState } from 'react'

// ─── helpers ───────────────────────────────────────────────────────────────
function uid() { return Date.now().toString(36) + Math.random().toString(36).slice(2, 5) }
function todayStr() { return new Date().toISOString().slice(0, 10) }

const TOPICS = [
  'All',
  'Architecture',
  'Retrieval',
  'Evaluation',
  'Governance',
  'API Design',
  'Vector Store',
  'Embeddings',
  'Testing',
  'DevOps',
  'Problem Solving',
  'Debugging',
  'Delivery',
  'Chunking',
  'Operations',
  'LLM',
]
const READINESS = { ready: { label: 'Ready', color: '#22c55e' }, needs_work: { label: 'Needs Work', color: '#f59e0b' }, shaky: { label: 'Shaky', color: '#ef4444' } }
const DIFFICULTIES = ['All', 'Beginner', 'Intermediate', 'Advanced']
const DIFFICULTY_ORDER = ['Beginner', 'Intermediate', 'Advanced']
const CATEGORY_TO_DIFFICULTY = {
  Ingestion: 'Beginner',
  Retrieval: 'Beginner',
  Storage: 'Beginner',
  Indexing: 'Intermediate',
  'Vector Search': 'Intermediate',
  'SQL Retrieval': 'Intermediate',
  Ranking: 'Advanced',
  Lineage: 'Intermediate',
  Evaluation: 'Intermediate',
  Safety: 'Advanced',
  Governance: 'Advanced',
  Operations: 'Beginner',
  LLM: 'Intermediate',
}

const DEFAULT_FLASHCARDS = [
  {
    id: 'fc-rag',
    category: 'Retrieval',
    term: 'RAG (Retrieval-Augmented Generation)',
    one_liner: 'RAG grounds LLM answers with retrieved evidence instead of relying only on model memory.',
    example: 'Ask where InteractionEvent_Id comes from and answer using LINEAGE chunks with citations.',
  },
  {
    id: 'fc-chunking',
    category: 'Ingestion',
    term: 'Chunking',
    one_liner: 'Chunking splits parsed workflow artifacts into retrievable units with enough context.',
    example: 'A transformation with ports plus SQL override is stored as one chunk.',
  },
  {
    id: 'fc-chunk-overlap',
    category: 'Ingestion',
    term: 'Chunk Overlap',
    one_liner: 'Overlap preserves context continuity when a large node is split into adjacent chunks.',
    example: 'A long transformation text is split with overlap so field definitions are not lost at boundaries.',
  },
  {
    id: 'fc-chunk-id-hash',
    category: 'Ingestion',
    term: 'Chunk ID Hash Suffix',
    one_liner: 'A content hash suffix in chunk_id keeps IDs stable and avoids collisions across similar node names.',
    example: 'Two EXPTRANS nodes in different files still produce distinct chunk_ids.',
  },
  {
    id: 'fc-embedding',
    category: 'Vector Search',
    term: 'Embedding',
    one_liner: 'An embedding maps text to a numeric vector for semantic similarity search.',
    example: 'A question about join logic retrieves Joiner-related chunks even without exact wording.',
  },
  {
    id: 'fc-l2-norm',
    category: 'Vector Search',
    term: 'L2 Normalization',
    one_liner: 'L2 normalization scales vectors to unit length so cosine similarity behaves consistently.',
    example: 'Dot-product style comparisons remain meaningful across different query lengths.',
  },
  {
    id: 'fc-cosine',
    category: 'Vector Search',
    term: 'Cosine Similarity Search',
    one_liner: 'Cosine similarity measures vector direction alignment, not absolute magnitude.',
    example: 'The query vector is compared to chunk embeddings using cosine-based ranking.',
  },
  {
    id: 'fc-pgvector',
    category: 'Storage',
    term: 'pgvector',
    one_liner: 'pgvector adds vector columns and nearest-neighbor search to PostgreSQL.',
    example: 'Embeddings are stored as vector(768) in rag.rag_chunks.',
  },
  {
    id: 'fc-ivfflat',
    category: 'Indexing',
    term: 'IVFFlat Index',
    one_liner: 'IVFFlat is an approximate nearest-neighbor index that speeds vector similarity queries.',
    example: 'The chunk embedding column uses an IVFFlat cosine index for faster retrieval at scale.',
  },
  {
    id: 'fc-fts',
    category: 'Indexing',
    term: 'FTS tsvector Column',
    one_liner: 'A tsvector column stores tokenized text for PostgreSQL full-text search.',
    example: 'rag.rag_chunks.fts enables lexical matching over chunk text.',
  },
  {
    id: 'fc-gin',
    category: 'Indexing',
    term: 'GIN Index',
    one_liner: 'GIN accelerates lookups on tsvector columns used by full-text search.',
    example: 'BM25-like queries use fts with a GIN index for fast filtering.',
  },
  {
    id: 'fc-tsquery',
    category: 'SQL Retrieval',
    term: 'plainto_tsquery',
    one_liner: 'plainto_tsquery converts raw text into a tsquery expression for lexical matching.',
    example: 'The bm25 mode builds tsquery from the user question before searching fts.',
  },
  {
    id: 'fc-ts-rank',
    category: 'SQL Retrieval',
    term: 'ts_rank',
    one_liner: 'ts_rank scores how well a document matches the tsquery terms.',
    example: 'BM25-style ranking in the store uses ts_rank to sort candidate chunks.',
  },
  {
    id: 'fc-to-tsvector',
    category: 'SQL Retrieval',
    term: 'to_tsvector Normalization',
    one_liner: 'to_tsvector tokenizes, normalizes, and stems text into lexemes for FTS indexing.',
    example: '"qualify", "qualified", and "qualifying" normalize to related lexemes in the fts column.',
  },
  {
    id: 'fc-ts-match-operator',
    category: 'SQL Retrieval',
    term: '@@ Match Operator',
    one_liner: 'The @@ operator checks whether a tsvector document matches a tsquery expression.',
    example: 'WHERE fts @@ plainto_tsquery(\'english\', query) filters lexical candidates before ranking.',
  },
  {
    id: 'fc-tsvector-generated',
    category: 'Indexing',
    term: 'Generated FTS Column',
    one_liner: 'A GENERATED ALWAYS tsvector column keeps lexical index content in sync with text automatically.',
    example: 'Upserting chunk text refreshes fts without any manual trigger logic.',
  },
  {
    id: 'fc-bitmap-scan',
    category: 'Indexing',
    term: 'Bitmap Index Scan Path',
    one_liner: 'PostgreSQL often uses Bitmap Index Scan + Bitmap Heap Scan for selective FTS filters.',
    example: 'FTS plan first hits rag_rag_chunks_fts_idx, then fetches matching rows for ts_rank sorting.',
  },
  {
    id: 'fc-bm25',
    category: 'Retrieval',
    term: 'BM25 (Lexical Search)',
    one_liner: 'BM25-like retrieval prioritizes exact term overlap between query and indexed text.',
    example: 'An exact workflow token like wf_4202_fnd_rltinteraction.XML tends to rank highly.',
  },
  {
    id: 'fc-hybrid',
    category: 'Retrieval',
    term: 'Hybrid Retrieval',
    one_liner: 'Hybrid retrieval combines lexical and vector results to balance precision and semantic coverage.',
    example: 'The API mode=hybrid merges BM25 and vector candidates before final ranking.',
  },
  {
    id: 'fc-rrf',
    category: 'Ranking',
    term: 'RRF (Reciprocal Rank Fusion)',
    one_liner: 'RRF merges ranked lists by adding reciprocal-rank contributions from each retriever.',
    example: 'A chunk appearing in both BM25 and vector lists gets a stronger combined score.',
  },
  {
    id: 'fc-rrf-k',
    category: 'Ranking',
    term: 'rrf_k Damping',
    one_liner: 'rrf_k controls how strongly top ranks are favored during fusion.',
    example: 'Higher rrf_k reduces the dominance of rank-1 hits in the fused list.',
  },
  {
    id: 'fc-reranker',
    category: 'Ranking',
    term: 'Cross-Encoder Reranker',
    one_liner: 'A cross-encoder rescoring model evaluates query-passage pairs for better final ordering.',
    example: 'Retrieve top 24, rerank with ms-marco-MiniLM-L-6-v2, then keep top 8.',
  },
  {
    id: 'fc-fetch-k',
    category: 'Ranking',
    term: 'fetch_k Oversampling',
    one_liner: 'fetch_k retrieves more candidates than needed so filtering or reranking still returns k good hits.',
    example: 'When rerank=true, the system fetches extra candidates before trimming to top-k.',
  },
  {
    id: 'fc-vector-operator',
    category: 'Vector Search',
    term: '<=> Cosine Distance Operator',
    one_liner: 'In pgvector, <=> computes vector distance for nearest-neighbor ordering queries.',
    example: 'ORDER BY embedding <=> query_vector LIMIT k returns nearest chunks.',
  },
  {
    id: 'fc-ivfflat-lists',
    category: 'Indexing',
    term: 'IVFFlat Lists',
    one_liner: 'IVFFlat partitions vectors into lists so search probes only a subset instead of scanning all rows.',
    example: 'Tuning list count trades memory/build cost for better nearest-neighbor latency.',
  },
  {
    id: 'fc-explain-analyze',
    category: 'Operations',
    term: 'EXPLAIN ANALYZE',
    one_liner: 'EXPLAIN ANALYZE validates the real query plan, timing, and index usage in production-like runs.',
    example: 'Vector plan shows Index Scan on rag_rag_chunks_emb_idx; FTS plan shows Bitmap Index Scan on rag_rag_chunks_fts_idx.',
  },
  {
    id: 'fc-jsonb-metadata-filter',
    category: 'Storage',
    term: 'JSONB Metadata Filtering',
    one_liner: 'JSONB metadata allows structured predicates alongside vector or lexical retrieval.',
    example: 'Filter on metadata fields such as node_class, has_sql_override, or source_file during search.',
  },
  {
    id: 'fc-retrieval-mode-auto',
    category: 'Retrieval',
    term: 'Retrieval Mode Resolution',
    one_liner: 'Mode resolution chooses vector, bm25, hybrid, or auto path based on request intent and available signals.',
    example: 'Identifier-heavy queries can route to lexical/hybrid mode while semantic questions stay vector-first.',
  },
  {
    id: 'fc-smart-fallback',
    category: 'Retrieval',
    term: 'Smart Retrieval Fallback',
    one_liner: 'Fallback logic broadens retrieval when strict filters or sparse matches under-return candidates.',
    example: 'If node_class filter gives too few hits, strategy can widen candidate search to keep answers grounded.',
  },
  {
    id: 'fc-lineage',
    category: 'Lineage',
    term: 'Field-Level Lineage Chain',
    one_liner: 'Lineage chains trace each target field back through hops to its source field.',
    example: 'A lineage chunk includes TARGET, SOURCE, HOP_COUNT, and PATH labels.',
  },
  {
    id: 'fc-node-class',
    category: 'Retrieval',
    term: 'node_class Filter',
    one_liner: 'node_class narrows search scope to SOURCE, TRANSFORMATION, TARGET, or LINEAGE chunks.',
    example: 'Use node_class=LINEAGE when asking source-to-target tracing questions.',
  },
  {
    id: 'fc-recall',
    category: 'Evaluation',
    term: 'Recall@k',
    one_liner: 'Recall@k measures how many expected relevant matches are found in top-k hits.',
    example: 'If 2 of 4 expected matchers are present in top 8, recall@8 is 0.5.',
  },
  {
    id: 'fc-ndcg',
    category: 'Evaluation',
    term: 'nDCG@k',
    one_liner: 'nDCG@k rewards putting higher-importance matches earlier in the ranking.',
    example: 'A score-3 match at rank 1 gives better nDCG than rank 7.',
  },
  {
    id: 'fc-ragas-answer-eval',
    category: 'Evaluation',
    term: 'Answer-Level RAGAS Run',
    one_liner: 'Answer-level RAGAS scores generation quality using model-judged metrics on a fixed query set.',
    example: 'Week 3 executed a 12-query answer dataset and produced ragas_report_latest.json as the baseline artifact.',
  },
  {
    id: 'fc-faithfulness-metric',
    category: 'Evaluation',
    term: 'Faithfulness Metric',
    one_liner: 'Faithfulness measures whether generated claims are supported by retrieved evidence.',
    example: 'Week 3 baseline faithfulness was 0.4000, so future prompt/retrieval changes should improve this score.',
  },
  {
    id: 'fc-answer-relevancy-metric',
    category: 'Evaluation',
    term: 'Answer Relevancy Metric',
    one_liner: 'Answer relevancy measures how directly the final response addresses the user query intent.',
    example: 'Week 3 baseline answer_relevancy was 0.0000, making it the primary Week 4 improvement target.',
  },
  {
    id: 'fc-eval-baseline-governance',
    category: 'Governance',
    term: 'Baseline-to-Delta Governance',
    one_liner: 'Treat baseline metrics as a fixed checkpoint and evaluate every change as a measurable delta.',
    example: 'Compare Week 4 runs against Week 3 faithfulness and answer_relevancy before claiming quality gains.',
  },
  {
    id: 'fc-refusal',
    category: 'Safety',
    term: 'Refusal Policy',
    one_liner: 'Refusal logic blocks generation when evidence quality is below threshold.',
    example: 'When evidence is weak, /answer returns refused=true instead of a guessed response.',
  },
  {
    id: 'fc-prompt-versioning',
    category: 'Governance',
    term: 'Prompt Versioning',
    one_liner: 'Prompt templates are versioned to keep answer behavior reproducible over time.',
    example: 'Responses include prompt_version so regressions can be tied to prompt changes.',
  },
  {
    id: 'fc-auto-connect',
    category: 'Operations',
    term: 'AUTO_CONNECT',
    one_liner: 'AUTO_CONNECT wires the API to an existing vector store on startup without re-ingesting XML.',
    example: 'After restart, service can reconnect to preloaded 4033 chunks quickly.',
  },
  {
    id: 'fc-connect-endpoint',
    category: 'Operations',
    term: '/connect Endpoint',
    one_liner: 'POST /connect binds the running API process to already indexed pgvector data.',
    example: 'If /retrieve returns 503 after restart, call /connect and recheck /health.',
  },
  {
    id: 'fc-connect-sync',
    category: 'Operations',
    term: '/connect background=false',
    one_liner: 'Synchronous connect mode blocks until attach is complete, returning deterministic readiness.',
    example: 'Use /connect?background=false before demos to confirm chunk_count is ready in the response.',
  },
  {
    id: 'fc-ingest-endpoint',
    category: 'Operations',
    term: '/ingest Endpoint',
    one_liner: 'POST /ingest parses workflows, chunks content, creates embeddings, and upserts rows.',
    example: 'Use background=false for a blocking ingest during controlled test runs.',
  },
  {
    id: 'fc-ingest-lock',
    category: 'Operations',
    term: 'Ingest Concurrency Lock',
    one_liner: 'A process-level lock prevents overlapping ingest/connect operations from corrupting runtime state.',
    example: 'Concurrent ingest requests are serialized so only one rebuild mutates KB state at a time.',
  },
  {
    id: 'fc-upsert',
    category: 'Storage',
    term: 'ON CONFLICT DO UPDATE',
    one_liner: 'Idempotent upsert avoids duplicate rows when the same chunk is re-ingested.',
    example: 'Re-running ingestion updates existing chunk_id rows in place.',
  },
  {
    id: 'fc-dimension-mismatch',
    category: 'Storage',
    term: 'Embedding Dimension Mismatch',
    one_liner: 'When embedding dimension changes, vector schema must be recreated and corpus re-indexed.',
    example: 'A migration from vector(384) to vector(768) requires table/index rebuild before fresh ingest.',
  },
  {
    id: 'fc-evidence-blocks',
    category: 'LLM',
    term: 'Evidence Block Prompting',
    one_liner: 'Answer generation uses structured evidence blocks with chunk IDs so outputs remain citeable and auditable.',
    example: 'The final answer includes [chunk_id] references tied to retrieved context passages.',
  },
  {
    id: 'fc-openai-path',
    category: 'LLM',
    term: 'OpenAI Answer Path',
    one_liner: 'The /answer endpoint can optionally generate answer_text using OpenAI after retrieval and gating.',
    example: 'If llm=true and key is missing, response includes llm_used=false and llm_error.',
  },
]

const FLASHCARD_OVERRIDES = {
  'fc-ragas-answer-eval': {
    one_liner: 'Answer-level RAGAS evaluates end-to-end response quality on the current golden subset using the same /answer path used in production.',
    example: 'Latest graph-mode run evaluated 22 questions and wrote eval/ragas_report_latest.json.',
  },
  'fc-faithfulness-metric': {
    one_liner: 'Faithfulness measures whether answer claims are supported by retrieved evidence blocks and citations.',
    example: 'Latest graph-mode snapshot: faithfulness=0.2857 (22-query run). Track deltas per prompt/retrieval change.',
  },
  'fc-answer-relevancy-metric': {
    one_liner: 'Answer relevancy measures whether the response directly addresses query intent, not just whether evidence exists.',
    example: 'Latest graph-mode snapshot remained answer_relevancy=0.0000, so prompt/evidence shaping is the top tuning priority.',
  },
  'fc-eval-baseline-governance': {
    one_liner: 'Governance uses both locked baseline artifacts and latest run snapshots to track regression and recovery clearly.',
    example: 'Keep baseline lock for gates, then compare each release against latest parity + RAGAS artifacts before promotion.',
  },
  'fc-smart-fallback': {
    term: 'Source-Hint Retrieval Fan-Out',
    one_liner: 'For file-scoped wf_*.XML questions, retrieval fans out wider before trimming so source-file hints are not lost in early top-k truncation.',
    example: 'fetch_k is widened for source-hinted queries, then results are filtered/prioritized by matching source file.',
  },
  'fc-openai-path': {
    one_liner: 'The answer path supports llm=true generation and also deterministic extractive fallback when llm=false with evidence present.',
    example: 'Graph/legacy parity checks can run with llm=false to isolate retrieval/orchestration behavior from judge-model variance.',
  },
}

const NEW_FLASHCARDS = [
  {
    id: 'fc-conversational-rag-stack',
    category: 'Architecture',
    term: 'Conversational RAG Stack',
    one_liner: 'A production-like chatbot needs session state, memory, capability routing, and grounded retrieval working together.',
    example: 'Current flow combines chat sessions, summary memory, capability introspection, and citation-grounded answers.',
    difficulty: 'Intermediate',
  },
  {
    id: 'fc-capability-routing',
    category: 'API Design',
    term: 'Capability-Aware Intent Routing',
    one_liner: 'Natural prompts like "what can it do" should route to a context-inventory answer, not generic generation.',
    example: 'Capability prompts now return indexed XML coverage, node class counts, and top mappings/folders.',
    difficulty: 'Intermediate',
  },
  {
    id: 'fc-chat-session-persistence',
    category: 'Operations',
    term: 'Persistent Chat Sessions',
    one_liner: 'Write-through persistence keeps session messages and memory summaries durable across restarts.',
    example: 'SQLite-backed sessions lazy-load from storage when cache is empty, preserving continuity.',
    difficulty: 'Beginner',
  },
  {
    id: 'fc-markdown-chat-rendering',
    category: 'Delivery',
    term: 'Markdown Chat Rendering',
    one_liner: 'Rendering assistant responses as markdown improves readability and user trust for structured outputs.',
    example: 'Headings, bullets, code blocks, and links are rendered directly in assistant bubbles.',
    difficulty: 'Beginner',
  },
  {
    id: 'fc-starter-prompts-ux',
    category: 'Delivery',
    term: 'Starter Prompt UX',
    one_liner: 'Starter prompt chips reduce first-message friction and guide users toward high-signal questions.',
    example: 'Users can click capability, lineage, usage, and workflow logic prompts to prefill chat input.',
    difficulty: 'Beginner',
  },
  {
    id: 'fc-graph-state-schema',
    category: 'Architecture',
    term: 'LangGraph State Schema Completeness',
    one_liner: 'StateGraph with TypedDict keeps only declared keys, so node handoff fields must be explicitly present in the state schema.',
    example: 'Missing hits/plan/resolved_mode keys caused empty-evidence graph answers until AnswerGraphState was expanded.',
    difficulty: 'Advanced',
  },
  {
    id: 'fc-graph-parity-regression',
    category: 'Evaluation',
    term: 'Graph-vs-Legacy Parity Regression',
    one_liner: 'Parity regression compares orchestration modes under the same dataset and acceptance policy before shipping contract changes.',
    example: 'Current parity artifact shows legacy accepted 22 and graph accepted 22 (delta 0) on the 28-case candidate set.',
    difficulty: 'Intermediate',
  },
  {
    id: 'fc-answer-contract-simplification',
    category: 'API Design',
    term: 'Answer Contract Simplification',
    one_liner: 'Deprecated smart/friendly knobs were removed from public request contract to reduce hidden behavior drift.',
    example: 'Public orchestration is now selected with use_graph and optional graph_max_retries, while planner rewrite remains internal.',
    difficulty: 'Intermediate',
  },
  {
    id: 'fc-golden-candidate-flow',
    category: 'Governance',
    term: 'Candidate-to-Golden Dataset Flow',
    one_liner: 'Keep a broad candidates file and maintain golden as a validated subset that passes explicit acceptance checks.',
    example: 'golden_answer_eval_candidates.jsonl feeds golden_answer_eval.jsonl after deterministic acceptance rules and parity checks.',
    difficulty: 'Beginner',
  },
  {
    id: 'fc-observability-trace-envelope',
    category: 'Operations',
    term: 'Trace Envelope Contract',
    one_liner: 'Each key response includes a trace envelope so one request can be followed across route logic and diagnostics.',
    example: 'trace.request_id + endpoint + timestamp let teams correlate response behavior with logs and incident timelines.',
    difficulty: 'Beginner',
  },
  {
    id: 'fc-observability-stage-timing',
    category: 'Operations',
    term: 'Stage Timing Telemetry',
    one_liner: 'Stage-level timing breaks total latency into semantic, retrieval, rerank, and generation components.',
    example: 'telemetry.timing_ms pinpoints whether latency came from retrieval fan-out or answer generation.',
    difficulty: 'Intermediate',
  },
  {
    id: 'fc-telemetry-authority-boundary',
    category: 'Governance',
    term: 'Telemetry Authority Boundary',
    one_liner: 'Observability must remain additive and cannot alter semantic-first truth decisions.',
    example: 'Lineage refusals still depend on semantic evidence status, even if telemetry fields are missing.',
    difficulty: 'Advanced',
  },
  {
    id: 'fc-usage-placeholder-policy',
    category: 'Operations',
    term: 'Usage Placeholder Policy',
    one_liner: 'When providers do not emit token/cost counters, return explicit null placeholders with a reason.',
    example: 'telemetry.usage.unavailable_reason keeps cost visibility honest without inventing token numbers.',
    difficulty: 'Intermediate',
  },
]

const QUESTION_PATCHES = {
  q1: {
    answer:
      'Current architecture is graph-aware and contract-simplified. Ingestion parses PowerCenter XML nodes and lineage paths into structured chunks. Retrieval supports vector, BM25, and hybrid, with source-file hint prioritization for wf_*.XML questions. Answering supports legacy or graph orchestration (planner -> executor -> validator) selected by use_graph / ANSWER_ORCHESTRATION_MODE. Public smart/friendly knobs were removed, and graph state now explicitly carries retrieval handoff fields to avoid silent node-to-node data loss.',
  },
  q4: {
    answer:
      'pgvector remains the primary store because it unifies vector, lexical FTS, and metadata filters in one transactional system. Current operational focus is reliability: reconnect-and-retry behavior for closed connections, source-file coverage parity checks, and explicit schema validation before release. This keeps retrieval and governance artifacts reproducible across restarts and contract migrations.',
  },
  q6: {
    answer:
      'Quality regression control now runs in layers: smoke/integration tests, candidate-to-golden acceptance checks, graph-vs-legacy parity regression, and answer-level RAGAS snapshots. CI quality gate policy uses controlled thresholds, while relevancy tuning remains an active optimization track. This separates reliability regressions from generation-quality regressions.',
  },
  q27: {
    answer:
      'Refusal logic is mode-aware and threshold-driven, but threshold values are runtime-configured and corpus-dependent. The critical design principle is unchanged: use semantic similarity signals from retrieved evidence, not fused-rank scores alone, for refusal decisions. In current runs, orchestration parity and evidence quality checks are validated first, then threshold/prompt tuning is applied to improve relevancy without introducing unsupported answers.',
  },
  q39: {
    answer:
      'The latest answer-level run proved that graph-mode orchestration and evaluation execution are stable after contract simplification and state-handoff fixes. Current snapshot on the 22-query golden set is faithfulness=0.2857 and answer_relevancy=0.0000, which means reliability is no longer the blocker; response relevance tuning is the primary next step.',
  },
  q40: {
    answer:
      'The latest blocker was not runtime config drift but graph state loss: planner outputs were missing from TypedDict state, so executor saw empty evidence. Fixing AnswerGraphState handoff fields restored graph behavior, then parity regression confirmed no acceptance delta vs legacy. This established a repeatable migration checklist: contract update -> state schema check -> parity report -> RAGAS run.',
  },
  q41: {
    answer:
      'Governance should track both locked baselines and latest snapshots. Use baseline artifacts for gate policy, then require each release to publish parity and RAGAS deltas against latest production-intent behavior. This avoids celebrating stale metrics and keeps discussions tied to current evidence.',
  },
}

function followUpDirection(question, topic) {
  const q = String(question || '').toLowerCase()

  if (q.includes('tradeoff') || q.includes('trade-off')) {
    return 'Direction: compare two options with a concrete decision rule (latency, quality, cost), then name the chosen default and fallback.'
  }
  if (q.includes('test') || q.includes('fixture') || q.includes('ci')) {
    return 'Direction: give a test pyramid answer: unit scope, integration scope, and one deterministic assertion you would add immediately.'
  }
  if (q.includes('metric') || q.includes('relevancy') || q.includes('faithfulness')) {
    return 'Direction: answer with metric definition, latest value, and one specific lever you will tune next.'
  }
  if (q.includes('debug') || q.includes('failure') || q.includes('bug')) {
    return 'Direction: walk through signals -> hypothesis -> isolation step -> fix -> verification artifact.'
  }
  if (q.includes('governance') || q.includes('baseline') || q.includes('gate')) {
    return 'Direction: separate policy from execution: what is gated now, what is monitored, and what evidence file proves each.'
  }
  if (topic === 'Architecture' || topic === 'Retrieval') {
    return 'Direction: answer in flow order (ingest, retrieve, answer), then highlight one risk and one safeguard from current implementation.'
  }
  return 'Direction: start with the current state, name one concrete example from this repo, and close with how you would validate it.'
}

function normalizeFollowUps(followUps, topic) {
  return (followUps || []).map(item => {
    if (typeof item === 'string') {
      return { question: item, direction: followUpDirection(item, topic) }
    }
    const question = String(item?.question || item?.q || '').trim()
    const direction = String(item?.direction || '').trim() || followUpDirection(question, topic)
    return { question, direction }
  }).filter(f => f.question)
}

function normalizeQuestionBank(qbank) {
  return (qbank || []).map(raw => {
    const patch = QUESTION_PATCHES[raw.id] || {}
    const merged = { ...raw, ...patch }
    return {
      ...merged,
      follow_ups: normalizeFollowUps(merged.follow_ups, merged.topic),
    }
  })
}

function normalizeFlashcard(card) {
  return {
    ...card,
    difficulty: card.difficulty || CATEGORY_TO_DIFFICULTY[card.category] || 'Intermediate',
  }
}

function mergeDefaultFlashcards(savedFlashcards) {
  const seeded = [...DEFAULT_FLASHCARDS, ...NEW_FLASHCARDS].map(card => {
    const patch = FLASHCARD_OVERRIDES[card.id] || {}
    return normalizeFlashcard({ ...card, ...patch })
  })

  const merged = new Map(seeded.map(card => [card.id, card]))
  ;(savedFlashcards || []).forEach(card => {
    if (!card?.id) return
    if (merged.has(card.id)) return
    merged.set(card.id, normalizeFlashcard(card))
  })
  return [...merged.values()]
}

// ─── Expandable Q&A card ───────────────────────────────────────────────────
function QACard({ qa, onToggleBookmark, bookmarked }) {
  const [open, setOpen] = useState(false)
  const [showCode, setShowCode] = useState(false)

  return (
    <div className={`iv-card${open ? ' open' : ''}`}>
      <div className="iv-card-header" onClick={() => setOpen(!open)}>
        <div className="iv-card-left">
          <span className="iv-q-icon">Q</span>
          <div>
            <div className="iv-card-title">{qa.question}</div>
            <div className="iv-card-meta">
              <span className="iv-topic-tag">{qa.topic}</span>
              {qa.upcoming_weeks?.length > 0 &&
                <span className="iv-future-tag">→ W{qa.upcoming_weeks.join(', W')}</span>}
            </div>
          </div>
        </div>
        <div className="iv-card-right">
          <button className={`iv-bookmark${bookmarked ? ' active' : ''}`}
            onClick={e => { e.stopPropagation(); onToggleBookmark(qa.id) }}
            title={bookmarked ? 'Remove bookmark' : 'Bookmark'}>
            {bookmarked ? '★' : '☆'}
          </button>
          <span className="jrn-chevron">{open ? '▲' : '▼'}</span>
        </div>
      </div>

      {open && (
        <div className="iv-card-body">
          <div className="iv-answer-section">
            <div className="iv-section-label">Answer</div>
            <div className="iv-answer-text">{qa.answer}</div>
          </div>

          {qa.code && (
            <div className="iv-code-section">
              <div className="iv-section-label" style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Code Reference</span>
                <button className="iv-toggle-code" onClick={() => setShowCode(!showCode)}>
                  {showCode ? 'Hide' : 'Show'} code ↕
                </button>
              </div>
              {showCode && <pre className="iv-code-block"><code>{qa.code}</code></pre>}
            </div>
          )}

          {(qa.file_refs?.length > 0 || qa.upcoming_weeks?.length > 0) && (
            <div className="iv-refs-row">
              {qa.file_refs?.length > 0 && (
                <div className="iv-refs-col">
                  <div className="iv-section-label">Source Files</div>
                  {qa.file_refs.map((r, i) => (
                    <div key={i} className="iv-ref-pill file">{r}</div>
                  ))}
                </div>
              )}
              {qa.upcoming_weeks?.length > 0 && (
                <div className="iv-refs-col">
                  <div className="iv-section-label">Connects to Upcoming Work</div>
                  {qa.upcoming_context?.map((c, i) => (
                    <div key={i} className="iv-ref-pill future">{c}</div>
                  ))}
                </div>
              )}
            </div>
          )}

          {qa.follow_ups?.length > 0 && (
            <div className="iv-followup-section">
              <div className="iv-section-label">Likely Follow-up Questions</div>
              <ul className="iv-followup-list">
                {qa.follow_ups.map((f, i) => (
                  <li key={i}>
                    <div>{f.question || f}</div>
                    {f.direction && <div className="iv-followup-direction">{f.direction}</div>}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Practice session card ─────────────────────────────────────────────────
function SessionCard({ session, qbank, actions }) {
  const [open, setOpen] = useState(session._new || false)
  const upd = (field, val) => actions.updateInterviewSession(session.id, field, val)

  return (
    <div className={`iv-card${open ? ' open' : ''}`}>
      <div className="iv-card-header" onClick={() => setOpen(!open)}>
        <div className="iv-card-left">
          <span className="iv-s-icon">📋</span>
          <div>
            <div className="iv-card-title">
              {session.title || <em style={{ opacity: 0.4 }}>Untitled session</em>}
            </div>
            <div className="iv-card-meta">
              <span>{session.date}</span>
              {session.overall && <span className="iv-topic-tag">{session.overall}</span>}
              <span style={{ color: 'var(--text-3)' }}>{(session.qs || []).length} Qs practiced</span>
            </div>
          </div>
        </div>
        <div className="iv-card-right">
          <button className="jrn-del" onClick={e => { e.stopPropagation(); actions.deleteInterviewSession(session.id) }}>✕</button>
          <span className="jrn-chevron">{open ? '▲' : '▼'}</span>
        </div>
      </div>

      {open && (
        <div className="iv-card-body" onClick={e => e.stopPropagation()}>
          <div className="jrn-row">
            <div className="jrn-field">
              <div className="jrn-label">Session Title</div>
              <input className="jrn-input" value={session.title || ''}
                placeholder="e.g. Mock with Recruiter — RAG System"
                onChange={e => upd('title', e.target.value)} />
            </div>
            <div className="jrn-field" style={{ maxWidth: 160 }}>
              <div className="jrn-label">Date</div>
              <input className="jrn-input" type="date" value={session.date}
                onChange={e => upd('date', e.target.value)} />
            </div>
            <div className="jrn-field" style={{ maxWidth: 160 }}>
              <div className="jrn-label">Overall Feel</div>
              <select className="jrn-input jrn-select" value={session.overall || 'needs_work'}
                onChange={e => upd('overall', e.target.value)}>
                {Object.entries(READINESS).map(([k, v]) => (
                  <option key={k} value={k}>{v.label}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Per-question readiness */}
          <div className="iv-section-label" style={{ marginTop: 12 }}>Questions Practiced (mark readiness)</div>
          <div className="iv-qs-grid">
            {(session.qs || []).map((sq, i) => {
              const qa = qbank.find(q => q.id === sq.qid)
              return (
                <div key={i} className="iv-sq-row">
                  <div className="iv-sq-q">{qa?.question || sq.qid}</div>
                  <select className="jrn-input jrn-select iv-sq-status"
                    value={sq.status || 'needs_work'}
                    style={{ color: READINESS[sq.status || 'needs_work']?.color }}
                    onChange={e => {
                      const next = [...(session.qs || [])]
                      next[i] = { ...sq, status: e.target.value }
                      upd('qs', next)
                    }}>
                    {Object.entries(READINESS).map(([k, v]) => (
                      <option key={k} value={k} style={{ color: v.color }}>{v.label}</option>
                    ))}
                  </select>
                  <button className="jrn-del small" onClick={() => {
                    const next = (session.qs || []).filter((_, j) => j !== i)
                    upd('qs', next)
                  }}>✕</button>
                </div>
              )
            })}
          </div>

          {/* Add question picker */}
          <AddQuestionPicker session={session} qbank={qbank} onAdd={sq => upd('qs', [...(session.qs || []), sq])} />

          {/* Journal */}
          <div className="iv-journal">
            <div className="jrn-wins-losses">
              <div className="jrn-col">
                <div className="jrn-label" style={{ color: 'var(--jrn-green)' }}>✅ What went well</div>
                {(session.went_well || []).map((w, i) => (
                  <div key={i} className="jrn-list-item">
                    <input className="jrn-input" value={w}
                      onChange={e => {
                        const next = [...(session.went_well || [])]; next[i] = e.target.value; upd('went_well', next)
                      }} />
                    <button className="jrn-del small" onClick={() => upd('went_well', (session.went_well || []).filter((_, j) => j !== i))}>✕</button>
                  </div>
                ))}
                <button className="jrn-add-item" onClick={() => upd('went_well', [...(session.went_well || []), ''])}>+ add</button>
              </div>
              <div className="jrn-col">
                <div className="jrn-label" style={{ color: 'var(--jrn-red)' }}>🔴 What to improve</div>
                {(session.to_improve || []).map((t, i) => (
                  <div key={i} className="jrn-list-item">
                    <input className="jrn-input" value={t}
                      onChange={e => {
                        const next = [...(session.to_improve || [])]; next[i] = e.target.value; upd('to_improve', next)
                      }} />
                    <button className="jrn-del small" onClick={() => upd('to_improve', (session.to_improve || []).filter((_, j) => j !== i))}>✕</button>
                  </div>
                ))}
                <button className="jrn-add-item" onClick={() => upd('to_improve', [...(session.to_improve || []), ''])}>+ add</button>
              </div>
            </div>
            <div className="jrn-field" style={{ marginTop: 10 }}>
              <div className="jrn-label">Notes</div>
              <textarea className="jrn-input" rows={2} value={session.notes || ''}
                placeholder="Key takeaways, topics to revisit, recruiter feedback…"
                onChange={e => upd('notes', e.target.value)} />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function AddQuestionPicker({ session, qbank, onAdd }) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const usedIds = new Set((session.qs || []).map(q => q.qid))
  const filtered = qbank.filter(q => !usedIds.has(q.id) &&
    (!search || q.question.toLowerCase().includes(search.toLowerCase()) || q.topic.toLowerCase().includes(search.toLowerCase())))

  if (!open) return (
    <button className="jrn-add-item" style={{ marginTop: 8 }} onClick={() => setOpen(true)}>+ add question to session</button>
  )

  return (
    <div className="iv-picker">
      <input className="jrn-search" placeholder="Search questions…" value={search}
        onChange={e => setSearch(e.target.value)} autoFocus />
      <div className="iv-picker-list">
        {filtered.slice(0, 8).map(q => (
          <button key={q.id} className="iv-picker-item" onClick={() => {
            onAdd({ qid: q.id, status: 'needs_work' })
            setOpen(false); setSearch('')
          }}>
            <span className="iv-topic-tag">{q.topic}</span>
            <span>{q.question}</span>
          </button>
        ))}
        {filtered.length === 0 && <div style={{ padding: '10px', color: 'var(--text-3)', fontSize: 13 }}>No more questions to add</div>}
      </div>
      <button className="jrn-del" style={{ fontSize: 12, padding: '5px 10px' }} onClick={() => setOpen(false)}>Cancel</button>
    </div>
  )
}

// ─── Quiz Mode ─────────────────────────────────────────────────────────────
const RATINGS = {
  easy:   { label: 'Easy',   emoji: '✅', weight: 0.5,  color: '#22c55e' },
  medium: { label: 'Got it', emoji: '🟡', weight: 1,    color: '#f59e0b' },
  hard:   { label: 'Shaky',  emoji: '🔴', weight: 2.5,  color: '#ef4444' },
}

function weightedShuffle(qbank, history) {
  // questions rated hard/never-seen appear more frequently
  return [...qbank].map(q => {
    const hist = history[q.id]
    const lastRating = hist?.ratings?.slice(-1)[0]
    const weight = lastRating ? (RATINGS[lastRating]?.weight ?? 1) : 2  // unseen = high weight
    return { q, sort: Math.random() * weight }
  }).sort((a, b) => b.sort - a.sort).map(x => x.q)
}

function QuizMode({ data, actions }) {
  const qbank = useMemo(() => normalizeQuestionBank(data.interview?.qbank || []), [data.interview?.qbank])
  const history = data.interview?.quiz_history || {}

  const [deck, setDeck] = useState(() => weightedShuffle(qbank, history))
  const [idx, setIdx] = useState(0)
  const [revealed, setRevealed] = useState(false)
  const [showCode, setShowCode] = useState(false)
  const [sessionStats, setSessionStats] = useState({ easy: 0, medium: 0, hard: 0, seen: 0 })
  const [topicFilter, setTopicFilter] = useState('All')
  const [done, setDone] = useState(false)

  const topics = ['All', ...new Set(qbank.map(q => q.topic))]
  const filtered = topicFilter === 'All' ? deck : deck.filter(q => q.topic === topicFilter)

  function restart() {
    setDeck(weightedShuffle(qbank, history))
    setIdx(0); setRevealed(false); setShowCode(false)
    setSessionStats({ easy: 0, medium: 0, hard: 0, seen: 0 })
    setDone(false)
  }

  function rate(rating) {
    const q = filtered[idx]
    actions.recordQuizAnswer(q.id, rating)
    setSessionStats(s => ({ ...s, [rating]: s[rating] + 1, seen: s.seen + 1 }))
    if (idx + 1 >= filtered.length) { setDone(true) }
    else { setIdx(idx + 1); setRevealed(false); setShowCode(false) }
  }

  if (!qbank.length) return (
    <div className="empty-state">No questions in the bank yet. Add some in the Question Bank tab.</div>
  )

  const total = filtered.length
  const current = filtered[idx]
  const qHistory = history[current?.id]
  const lastRating = qHistory?.ratings?.slice(-1)[0]
  const neverSeen = !qHistory?.ratings?.length

  if (done) return (
    <div className="quiz-done">
      <div className="quiz-done-icon">🎯</div>
      <h2>Session Complete</h2>
      <p className="view-sub">You went through {sessionStats.seen} questions</p>
      <div className="quiz-done-stats">
        {Object.entries(RATINGS).map(([k, v]) => (
          <div key={k} className="quiz-done-stat">
            <span className="quiz-done-num" style={{ color: v.color }}>{sessionStats[k]}</span>
            <span className="quiz-done-label">{v.emoji} {v.label}</span>
          </div>
        ))}
      </div>
      <button className="btn-primary" style={{ marginTop: 20 }} onClick={restart}>↺ Shuffle Again</button>
    </div>
  )

  const progress = total > 0 ? (idx / total) * 100 : 0

  return (
    <div className="quiz-wrap">
      {/* Topic filter + progress */}
      <div className="quiz-topbar">
        <div className="iv-topic-filters" style={{ marginBottom: 0 }}>
          {topics.map(t => (
            <button key={t} className={`iv-topic-btn${topicFilter === t ? ' active' : ''}`}
              onClick={() => { setTopicFilter(t); setIdx(0); setRevealed(false) }}>
              {t}
            </button>
          ))}
        </div>
        <div className="quiz-progress-wrap">
          <div className="quiz-progress-bar">
            <div className="quiz-progress-fill" style={{ width: `${progress}%` }} />
          </div>
          <span className="quiz-progress-label">{idx + 1} / {total}</span>
          <button className="iv-toggle-code" onClick={restart} title="Reshuffle">↺</button>
        </div>
      </div>

      {/* Card */}
      <div className="quiz-card">
        <div className="quiz-card-top">
          <div className="quiz-meta-row">
            <span className="iv-topic-tag">{current.topic}</span>
            {neverSeen && <span className="quiz-badge new">new</span>}
            {lastRating && <span className="quiz-badge" style={{ color: RATINGS[lastRating]?.color }}>last: {RATINGS[lastRating]?.emoji}</span>}
          </div>
          <div className="quiz-question">{current.question}</div>
        </div>

        {!revealed ? (
          <div className="quiz-reveal-wrap">
            <button className="quiz-reveal-btn" onClick={() => setRevealed(true)}>
              Show Answer ↓
            </button>
          </div>
        ) : (
          <div className="quiz-answer-wrap">
            <div className="quiz-answer-label">Answer</div>
            <div className="quiz-answer-text">{current.answer}</div>

            {current.code && (
              <div style={{ marginTop: 12 }}>
                <button className="iv-toggle-code" onClick={() => setShowCode(!showCode)}>
                  {showCode ? 'Hide' : 'Show'} code ↕
                </button>
                {showCode && <pre className="iv-code-block"><code>{current.code.replace(/\\n/g, '\n')}</code></pre>}
              </div>
            )}

            {current.file_refs?.length > 0 && (
              <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {current.file_refs.map((r, i) => <span key={i} className="iv-ref-pill file">{r}</span>)}
              </div>
            )}

            <div className="quiz-rate-row">
              <span className="quiz-rate-label">How well did you answer?</span>
              <div className="quiz-rate-btns">
                {Object.entries(RATINGS).map(([k, v]) => (
                  <button key={k} className="quiz-rate-btn"
                    style={{ '--rate-color': v.color }}
                    onClick={() => rate(k)}>
                    {v.emoji} {v.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Session mini-stats */}
      <div className="quiz-session-stats">
        {Object.entries(RATINGS).map(([k, v]) => (
          <span key={k} style={{ color: v.color }}>{v.emoji} {sessionStats[k]}</span>
        ))}
        <span style={{ color: 'var(--text-3)' }}>· {sessionStats.seen} answered this session</span>
      </div>
    </div>
  )
}

// ─── Main Interview View ───────────────────────────────────────────────────
export default function Interview({ data, actions }) {
  const [subtab, setSubtab] = useState('bank')
  const [topic, setTopic] = useState('All')
  const [search, setSearch] = useState('')
  const [flashSearch, setFlashSearch] = useState('')
  const [difficulty, setDifficulty] = useState('All')
  const [quickStudy, setQuickStudy] = useState(false)
  const [quickIndex, setQuickIndex] = useState(0)
  const [quickRevealed, setQuickRevealed] = useState(false)
  const [openFlashcards, setOpenFlashcards] = useState(() => new Set())
  const [bookmarks, setBookmarks] = useState(() => {
    try { return new Set(JSON.parse(localStorage.getItem('iv_bookmarks') || '[]')) } catch { return new Set() }
  })

  const interview = data.interview || { qbank: [], sessions: [] }
  const qbank = useMemo(() => normalizeQuestionBank(interview.qbank || []), [interview.qbank])
  const flashcards = useMemo(() => mergeDefaultFlashcards(interview.flashcards), [interview.flashcards])
  const sessions = [...(interview.sessions || [])].sort((a, b) => b.date.localeCompare(a.date))
  const quizHistory = interview.quiz_history || {}

  const q = search.toLowerCase()
  const fs = flashSearch.toLowerCase()
  const filteredQ = qbank.filter(qa =>
    (topic === 'All' || qa.topic === topic) &&
    (!q || qa.question.toLowerCase().includes(q) || qa.answer.toLowerCase().includes(q))
  )
  const filteredFlashcards = flashcards.filter(card =>
    (difficulty === 'All' || card.difficulty === difficulty) &&
    (
      !fs ||
      card.term.toLowerCase().includes(fs) ||
      card.one_liner.toLowerCase().includes(fs) ||
      card.example.toLowerCase().includes(fs) ||
      card.category.toLowerCase().includes(fs)
    )
  )
  const groupedFlashcards = useMemo(() => {
    const grouped = { Beginner: [], Intermediate: [], Advanced: [] }
    filteredFlashcards.forEach(card => {
      grouped[card.difficulty] = grouped[card.difficulty] || []
      grouped[card.difficulty].push(card)
    })
    return grouped
  }, [filteredFlashcards])
  const quickCard = filteredFlashcards[quickIndex] || null
  const readinessSummary = sessions.reduce(
    (acc, s) => {
      const key = s.overall || 'needs_work'
      acc[key] = (acc[key] || 0) + 1
      return acc
    },
    { ready: 0, needs_work: 0, shaky: 0 }
  )
  const weakQuestionCount = Object.values(quizHistory).filter(hist => {
    const last = hist?.ratings?.slice(-1)[0]
    return last === 'hard'
  }).length

  useEffect(() => {
    if (quickIndex < filteredFlashcards.length) return
    setQuickIndex(0)
  }, [quickIndex, filteredFlashcards.length])

  useEffect(() => {
    if (!quickStudy || !quickRevealed || filteredFlashcards.length === 0) return
    const timer = setTimeout(() => {
      setQuickRevealed(false)
      setQuickIndex(i => (i + 1) % filteredFlashcards.length)
    }, 1800)
    return () => clearTimeout(timer)
  }, [quickStudy, quickRevealed, filteredFlashcards.length])

  function toggleBookmark(id) {
    const next = new Set(bookmarks)
    next.has(id) ? next.delete(id) : next.add(id)
    setBookmarks(next)
    localStorage.setItem('iv_bookmarks', JSON.stringify([...next]))
  }

  function toggleFlashcard(id) {
    const next = new Set(openFlashcards)
    next.has(id) ? next.delete(id) : next.add(id)
    setOpenFlashcards(next)
  }

  const bookmarkedQs = qbank.filter(qa => bookmarks.has(qa.id))
  const topicCounts = {}
  qbank.forEach(qa => { topicCounts[qa.topic] = (topicCounts[qa.topic] || 0) + 1 })
  const topicOptions = useMemo(() => {
    const dynamicTopics = [...new Set(qbank.map(qa => qa.topic).filter(Boolean))]
    const curated = TOPICS.filter(t => t !== 'All')
    return ['All', ...new Set([...curated, ...dynamicTopics])]
  }, [qbank])

  return (
    <div className="view">
      <div className="jrn-header">
        <div>
          <h1>Interview Prep</h1>
          <p className="view-sub">
            {qbank.length} questions · {sessions.length} practice sessions ·
            {bookmarkedQs.length} bookmarked · {flashcards.length} flash cards · linked to real codebase
          </p>
          <div className="interview-summary-row">
            <span className="interview-summary-chip">Ready sessions: {readinessSummary.ready}</span>
            <span className="interview-summary-chip">Needs-work sessions: {readinessSummary.needs_work}</span>
            <span className="interview-summary-chip">Weak questions (last rated hard): {weakQuestionCount}</span>
          </div>
        </div>
        {subtab === 'sessions' &&
          <button className="btn-primary" onClick={() => actions.addInterviewSession()}>+ New Session</button>}
      </div>

      <div className="jrn-tabs">
        <button className={`jrn-tab${subtab === 'bank' ? ' active' : ''}`} onClick={() => setSubtab('bank')}>
          🎯 Question Bank ({qbank.length})
        </button>
        <button className={`jrn-tab${subtab === 'quiz' ? ' active' : ''}`} onClick={() => setSubtab('quiz')}>
          ⚡ Test Me
        </button>
        <button className={`jrn-tab${subtab === 'bookmarks' ? ' active' : ''}`} onClick={() => setSubtab('bookmarks')}>
          ★ Bookmarked ({bookmarkedQs.length})
        </button>
        <button className={`jrn-tab${subtab === 'flashcards' ? ' active' : ''}`} onClick={() => setSubtab('flashcards')}>
          🧩 Flash Cards ({flashcards.length})
        </button>
        <button className={`jrn-tab${subtab === 'sessions' ? ' active' : ''}`} onClick={() => setSubtab('sessions')}>
          📋 Practice Sessions ({sessions.length})
        </button>
      </div>

      {subtab === 'quiz' && (
        <QuizMode data={data} actions={actions} />
      )}

      {subtab === 'bank' && (
        <>
          <div className="iv-topic-filters">
            {topicOptions.map(t => (
              <button key={t} className={`iv-topic-btn${topic === t ? ' active' : ''}`}
                onClick={() => setTopic(t)}>
                {t}{t !== 'All' && topicCounts[t] ? ` (${topicCounts[t]})` : ''}
              </button>
            ))}
          </div>
          <input className="jrn-search" placeholder="Search questions and answers…"
            value={search} onChange={e => setSearch(e.target.value)} />
          <div className="jrn-list">
            {filteredQ.length === 0
              ? <div className="empty-state">No questions match your filter.</div>
              : filteredQ.map(qa => (
                  <QACard key={qa.id} qa={qa}
                    bookmarked={bookmarks.has(qa.id)}
                    onToggleBookmark={toggleBookmark} />
                ))
            }
          </div>
        </>
      )}

      {subtab === 'bookmarks' && (
        <div className="jrn-list">
          {bookmarkedQs.length === 0
            ? <div className="empty-state">Star questions in the Question Bank to bookmark them here.</div>
            : bookmarkedQs.map(qa => (
                <QACard key={qa.id} qa={qa} bookmarked={true} onToggleBookmark={toggleBookmark} />
              ))
          }
        </div>
      )}

      {subtab === 'flashcards' && (
        <>
          <input
            className="jrn-search"
            placeholder="Search terms, one-line explanations, or examples..."
            value={flashSearch}
            onChange={e => setFlashSearch(e.target.value)}
          />

          <div className="flash-toolbar">
            <div className="flash-difficulty-filters">
              {DIFFICULTIES.map(level => (
                <button
                  key={level}
                  className={`flash-difficulty-btn${difficulty === level ? ' active' : ''}`}
                  onClick={() => {
                    setDifficulty(level)
                    setQuickIndex(0)
                    setQuickRevealed(false)
                  }}
                >
                  {level}
                </button>
              ))}
            </div>
            <button
              className={`flash-mode-toggle${quickStudy ? ' active' : ''}`}
              onClick={() => {
                setQuickStudy(v => !v)
                setQuickRevealed(false)
              }}
            >
              ⚡ Quick Study: {quickStudy ? 'On' : 'Off'}
            </button>
          </div>

          {quickStudy && (
            <div className="flash-quick-wrap">
              {quickCard
                ? (
                  <article className="flash-card open flash-card-quick">
                    <div className="flash-head">
                      <span className="iv-topic-tag">{quickCard.category}</span>
                      <span className="flash-cue">{quickCard.difficulty}</span>
                    </div>
                    <h3 className="flash-term">{quickCard.term}</h3>
                    {!quickRevealed
                      ? <p className="flash-collapsed-hint">Click Reveal to show the one-liner and auto-advance.</p>
                      : (
                        <>
                          <p className="flash-one-liner">{quickCard.one_liner}</p>
                          <div className="flash-example"><span>Example:</span> {quickCard.example}</div>
                          <p className="flash-next-hint">Auto-advancing...</p>
                        </>
                      )}

                    <div className="flash-quick-actions">
                      <button
                        className="flash-quick-btn"
                        onClick={() => {
                          setQuickRevealed(false)
                          setQuickIndex(i => (i - 1 + filteredFlashcards.length) % filteredFlashcards.length)
                        }}
                      >
                        ← Prev
                      </button>
                      <button className="flash-quick-btn primary" onClick={() => setQuickRevealed(true)}>
                        Reveal
                      </button>
                      <button
                        className="flash-quick-btn"
                        onClick={() => {
                          setQuickRevealed(false)
                          setQuickIndex(i => (i + 1) % filteredFlashcards.length)
                        }}
                      >
                        Next →
                      </button>
                    </div>
                    <div className="flash-quick-progress">
                      Card {quickIndex + 1} of {filteredFlashcards.length}
                    </div>
                  </article>
                )
                : <div className="empty-state">No flash cards match this difficulty/search filter.</div>}
            </div>
          )}

          {!quickStudy && (
            <div className="flash-groups">
              {DIFFICULTY_ORDER.map(level => (
                groupedFlashcards[level]?.length > 0 && (
                  <section key={level} className="flash-group">
                    <h3 className="flash-group-title">{level} ({groupedFlashcards[level].length})</h3>
                    <div className="flash-grid">
                      {groupedFlashcards[level].map(card => (
                        <article
                          key={card.id}
                          className={`flash-card${openFlashcards.has(card.id) ? ' open' : ''}`}
                          onClick={() => toggleFlashcard(card.id)}
                          onKeyDown={e => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault()
                              toggleFlashcard(card.id)
                            }
                          }}
                          role="button"
                          tabIndex={0}
                          aria-expanded={openFlashcards.has(card.id)}
                        >
                          <div className="flash-head">
                            <span className="iv-topic-tag">{card.category}</span>
                            <span className="flash-cue">{openFlashcards.has(card.id) ? 'Hide answer' : 'Show answer'}</span>
                          </div>
                          <h3 className="flash-term">{card.term}</h3>
                          {openFlashcards.has(card.id)
                            ? (
                              <>
                                <p className="flash-one-liner">{card.one_liner}</p>
                                <div className="flash-example">
                                  <span>Example:</span> {card.example}
                                </div>
                              </>
                            )
                            : <p className="flash-collapsed-hint">Click to reveal one-line definition and example.</p>
                          }
                        </article>
                      ))}
                    </div>
                  </section>
                )
              ))}
              {filteredFlashcards.length === 0 && <div className="empty-state">No flash cards match your search.</div>}
            </div>
          )}
        </>
      )}

      {subtab === 'sessions' && (
        <div className="jrn-list">
          {sessions.length === 0
            ? <div className="empty-state">No practice sessions yet. Click "+ New Session".</div>
            : sessions.map(s => (
                <SessionCard key={s.id} session={s} qbank={qbank} actions={actions} />
              ))
          }
        </div>
      )}
    </div>
  )
}
