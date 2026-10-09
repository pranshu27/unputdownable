export const STATUSES = {
  'not-started': { label: 'Not Started', color: '#94a3b8' },
  'in-progress':  { label: 'In Progress', color: '#6366f1' },
  'blocked':      { label: 'Blocked',     color: '#ef4444' },
  'done':         { label: 'Done',        color: '#10b981' }
}

export const PROJECT_COLORS = { 1: '#6366f1', 2: '#8b5cf6', 3: '#0ea5e9', 4: '#f59e0b', 5: '#10b981' }
export const PROJECT_NAMES  = {
  1: 'RAG System',
  2: 'Local Benchmarking',
  3: 'Observability',
  4: 'Fine-Tuning',
  5: 'Realtime Multimodal'
}

export const INITIAL_DATA = {
  program: {
    name:      'Senior GenAI Engineer Portfolio',
    owner:     'Pranshu Sahijwani',
    techLead:  'Pranshu Sahijwani',
    startDate: '2026-08-11',
    endDate:   '2026-11-17'
  },
  projects: [
    {
      id: 1, color: '#6366f1', weekRange: 'Weeks 1–4', status: 'in-progress',
      name: 'Production-Grade RAG System',
      description: 'Semantic-first Informatica copilot with deterministic lineage/impact truth, NetworkX graph traversal, and citation-grounded RAG assistance.',
      stack: ['Python + FastAPI', 'LangChain / LlamaIndex', 'pgvector / Weaviate', 'RAGAS', 'GitHub Actions'],
      kpis: [
        'Retrieval hit rate @k ≥ 0.85',
        'Citation correctness ≥ 0.9',
        'Hallucination rate ≤ 0.08',
        'P95 response latency ≤ 2.5 s'
      ],
      milestones: [
        { id: 'p1-1', done: true, label: 'Architecture + schemas; PowerCenter XML ingestion baseline; chunking baseline' },
        { id: 'p1-2', done: true, label: 'Hybrid retrieval (BM25 + vector) + cross-encoder reranker + citation output' },
        { id: 'p1-3', done: true, label: 'Refusal policy + prompt versioning + citation-backed answer path' },
        { id: 'p1-4', done: true, label: 'Golden dataset (50-200 QA pairs), baseline RAGAS scorecard' },
        { id: 'p1-5', done: true, label: 'CI quality gates (block PR on metric regression), staging deployment, dashboard' },
        { id: 'p1-6', done: false, label: 'Canary release, incident drill, final architecture diagram + README demo' },
        { id: 'p1-7', done: true, label: 'NetworkX lineage engine + cross-workflow field trace + semantic graph health telemetry' }
      ],
      lld: { title: 'P1 - Production-Grade RAG System LLD', path: 'rag-system/SYSTEM_E2E_FLOW.md' },
      notes: 'W1-W4 completion now includes semantic-first pivot, graph/legacy parity stabilization, capability-aware chat UX, and new NetworkX lineage intelligence with cross-workflow field tracing. Latest smoke validation: 51 passed after semantic graph routing and SQL fallback hardening.'
    },
    {
      id: 2, color: '#8b5cf6', weekRange: 'Weeks 5–6', status: 'not-started',
      name: 'Local AI Assistant + Model Benchmarking',
      description: 'Offline-first assistant benchmarking 3+ small models on quality, latency, and memory across quantization levels.',
      stack: ['Ollama / llama.cpp', 'Llama 3.1 8B / Mistral 7B / Phi-4 mini', 'pytest-benchmark', 'Streamlit / Gradio'],
      kpis: [
        '100% offline execution',
        'Benchmark reproducibility across 3 runs',
        'Structured output validity ≥ 99% (with 1 retry)',
        'Clear quality/latency frontier chart per use-case'
      ],
      milestones: [
        { id: 'p2-1', done: false, label: 'Offline runtime setup (Ollama) + base inference CLI/API' },
        { id: 'p2-2', done: false, label: 'JSON schema enforcement, Pydantic validation, retry-on-invalid policy' },
        { id: 'p2-3', done: false, label: 'Benchmark harness: 30-50 fixed prompts across 3 task types (Q&A, sum, extraction)' },
        { id: 'p2-4', done: false, label: '3-model comparison on identical hardware (TTFT, tokens/sec, memory, quality)' },
        { id: 'p2-5', done: false, label: 'Q4 vs Q5 quantization experiments + final recommendation playbook' }
      ],
      lld: { title: 'P2 - Local AI Assistant + Benchmarking LLD', path: 'documents/lld/P2_LOCAL_BENCHMARKING_LLD.md' },
      notes: ''
    },
    {
      id: 3, color: '#0ea5e9', weekRange: 'Weeks 7–8', status: 'in-progress',
      name: 'Observability & Monitoring for RAG',
      description: 'Full request traceability, golden-signal dashboards, and regression-gated CI for the RAG system from Project 1.',
      stack: ['Langfuse / LangSmith', 'OpenTelemetry', 'Prometheus + Grafana', 'Loki / ELK'],
      kpis: [
        'MTTD ≤ 5 min for severity-1 regressions',
        'MTTR ≤ 30 min for known failure classes',
        'Trace completeness ≥ 99% of requests',
        'Alert precision ≥ 80%'
      ],
      milestones: [
        { id: 'p3-1', done: true, label: 'Week +1 delivered: response trace envelope + stage timing + event schema + usage placeholders' },
        { id: 'p3-2', done: false, label: 'Dashboards: P50/P95/P99 latency, faithfulness trend, citation/refusal/failure metrics' },
        { id: 'p3-3', done: false, label: 'Alerting thresholds + chaos scenarios + incident runbook (top-10 failures)' },
        { id: 'p3-4', done: false, label: 'CI regression/latency gates + canary rollout drill + simulated incident writeup' }
      ],
      lld: { title: 'P3 - Observability and Monitoring LLD', path: 'documents/lld/P3_OBSERVABILITY_LLD.md' },
      notes: 'Week +1 observability foundation is complete in API responses (trace + telemetry contract). Remaining Weeks 7-8 scope is OTel/Langfuse integration, dashboards, alerting, chaos drills, and CI operational gates.'
    },
    {
      id: 4, color: '#f59e0b', weekRange: 'Weeks 9–11', status: 'not-started',
      name: 'Fine-Tuning with Measurable Gain',
      description: 'SFT (LoRA/QLoRA) → DPO preference tuning on a narrow task where prompt-only performance plateaus.',
      stack: ['Hugging Face TRL', 'PEFT / QLoRA', 'Axolotl', 'W&B / MLflow', 'Fireworks AI'],
      kpis: [
        'Primary task metric improvement ≥ 10 pp absolute',
        'Error class reduction in top-2 failure categories',
        'No regression on generic out-of-domain prompts',
        'Inference latency within deployment budget'
      ],
      milestones: [
        { id: 'p4-1', done: false, label: 'Define task, prompt-only baseline, error taxonomy, labeling rubric' },
        { id: 'p4-2', done: false, label: 'Curate 2k-10k SFT examples; leakage + duplicate checks; data card' },
        { id: 'p4-3', done: false, label: 'SFT with LoRA/QLoRA; holdout eval: JSON validity, exact match, refusal' },
        { id: 'p4-4', done: false, label: 'DPO preference tuning; re-evaluate vs SFT baseline' },
        { id: 'p4-5', done: false, label: 'Before/after metrics table, training curves, model card, published endpoint' }
      ],
      lld: { title: 'P4 - Fine-Tuning with Measurable Gain LLD', path: 'documents/lld/P4_FINE_TUNING_LLD.md' },
      notes: ''
    },
    {
      id: 5, color: '#10b981', weekRange: 'Weeks 12–14', status: 'not-started',
      name: 'Realtime Multimodal App',
      description: 'Low-latency voice/vision streaming pipeline with per-stage latency budgets, graceful degradation, and chaos testing.',
      stack: ['FastAPI WebSockets / gRPC streaming', 'Whisper / Deepgram (ASR)', 'ElevenLabs / Cartesia (TTS)', 'WebRTC', 'Redis Streams'],
      kpis: [
        'P95 end-to-end latency ≤ 1200 ms',
        'Session success rate ≥ 99%',
        'Graceful fallback on ≥ 95% of injected failures',
        'No memory leak in 30-min soak test'
      ],
      milestones: [
        { id: 'p5-1', done: false, label: 'Streaming skeleton + single-modal baseline (voice OR vision)' },
        { id: 'p5-2', done: false, label: 'Second modality integration + session management with correlation IDs' },
        { id: 'p5-3', done: false, label: 'Per-stage latency instrumentation + budget enforcement + decomposition viz' },
        { id: 'p5-4', done: false, label: 'Circuit breaker, graceful fallback, chaos test matrix, 30-min soak test, demo video' }
      ],
      lld: { title: 'P5 - Realtime Multimodal App LLD', path: 'documents/lld/P5_REALTIME_MULTIMODAL_LLD.md' },
      notes: ''
    }
  ],
  weeks: [
    {
      week: 1, project: 1, focus: 'P1 — Ingestion + Chunking + Index + API', notes: 'W1 shipped: full XML parse->chunk->embed->pgvector pipeline, retrieval API, and green smoke/integration tests.',
      tasks: [
        { id: 'w1-1', done: true, label: 'Set up mono-repo project structure and CI skeleton' },
        { id: 'w1-2', done: true, label: 'Ingest Informatica PowerCenter XML corpus with metadata enrichment' },
        { id: 'w1-3', done: true, label: 'Chunking strategy: 500-800 tokens, ~100 token overlap' },
        { id: 'w1-4', done: true, label: 'Embedding + vector index baseline (pgvector or Chroma)' },
        { id: 'w1-5', done: true, label: 'Baseline retrieval API (top-k chunks)' }
      ]
    },
    {
      week: 2, project: 1, focus: 'P1 — Lineage + Hybrid Retrieval + Citation', notes: 'W2 shipped lineage BFS chunks, BM25+vector hybrid retrieval, reranker integration, refusal policy, prompt versioning, and index parity validation.',
      tasks: [
        { id: 'w2-0', done: true, label: 'Field-level lineage parser (CONNECTOR BFS) + LINEAGE chunk generation' },
        { id: 'w2-1', done: true, label: 'BM25 + semantic vector hybrid retrieval' },
        { id: 'w2-2', done: true, label: 'Cross-encoder reranker integration' },
        { id: 'w2-3', done: true, label: 'Citation-backed answer generation (source + cited paragraph)' },
        { id: 'w2-4', done: true, label: 'Decline-on-insufficient-evidence refusal policy' },
        { id: 'w2-5', done: true, label: 'Prompt versioning: prompts as config files in version control' },
        { id: 'w2-6', done: true, label: 'Index audit: vector(768), row-count parity, and source-file coverage validation' }
      ]
    },
    {
      week: 3, project: 1, focus: 'P1 — Eval Dataset + RAGAS', notes: 'Week 3 complete: 53-query retrieval baseline captured and answer-level RAGAS executed end-to-end (faithfulness 0.4000, answer_relevancy 0.0000) with report artifacts generated.',
      tasks: [
        { id: 'w3-0', done: true, label: 'Kickoff baseline run: refresh retrieval_eval report and document starting metrics' },
        { id: 'w3-1', done: true, label: 'Build 50-200 QA golden evaluation set (manually verified)' },
        { id: 'w3-2', done: true, label: 'Automated RAGAS faithfulness + answer relevance scoring' },
        { id: 'w3-3', done: true, label: 'Retrieval nDCG@10 and recall@k baseline measurement' },
        { id: 'w3-4', done: true, label: 'Evaluation harness scripts (repeatable offline run)' }
      ]
    },
    {
      week: 4, project: 1, focus: 'P1 — CI Gates + Deploy + Docs', notes: 'W4 foundation complete for quality gate + architecture/docs. Remaining carryover backlog: staging deploy hardening, dashboard baseline, and canary/incident drill; these are now sequenced under Weeks 7-8 observability execution.',
      tasks: [
        { id: 'w4-1', done: true, label: 'CI quality gate: fail PR if faithfulness drops > 2 pts from baseline' },
        { id: 'w4-2', done: false, label: 'Carryover: staging deployment hardening (Docker + API + env matrix)' },
        { id: 'w4-3', done: false, label: 'Carryover: baseline dashboard pack (latency, citation coverage, refusal/failure rate)' },
        { id: 'w4-4', done: false, label: 'Carryover: canary release + simulated incident drill + rollback checklist' },
        { id: 'w4-5', done: true, label: 'Architecture diagram + README + demo notebook' }
      ]
    },
    {
      week: 5, project: 2, focus: 'P2 — Offline Runtime + Inference API', notes: '',
      tasks: [
        { id: 'w5-1', done: false, label: 'Install Ollama + run 3B-7B class model (Llama 3.1 / Mistral 7B / Phi-4 mini)' },
        { id: 'w5-2', done: false, label: 'CLI + FastAPI inference wrapper (100% local, no external calls)' },
        { id: 'w5-3', done: false, label: 'Measure TTFT, tokens/sec, total latency baselines' },
        { id: 'w5-4', done: false, label: 'JSON schema enforcement + Pydantic validation' },
        { id: 'w5-5', done: false, label: 'Retry-on-invalid (1 reprompt) + graceful-fail policy' }
      ]
    },
    {
      week: 6, project: 2, focus: 'P2 — Benchmarking + Model Comparison', notes: '',
      tasks: [
        { id: 'w6-1', done: false, label: '30-50 standardized prompt suite across Q&A, summarization, extraction' },
        { id: 'w6-2', done: false, label: 'Benchmark harness: memory, throughput, output quality (BLEU/ROUGE)' },
        { id: 'w6-3', done: false, label: '3-model head-to-head comparison on identical hardware' },
        { id: 'w6-4', done: false, label: 'Q4 vs Q5 quantization (GGUF) — speed/quality tradeoff' },
        { id: 'w6-5', done: false, label: 'Comparison report + model selection playbook by use-case profile' }
      ]
    },
    {
      week: 7, project: 3, focus: 'P3 — Trace Foundation (done) + OTel/Langfuse Integration', notes: 'Plan: lock Week +1 foundation as complete, then implement telemetry export path. D1-D2: OTel context + spans. D3: Langfuse/LangSmith capture with prompt/model version tags. D4-D5: validation on retrieve/answer/semantic/chat flows.',
      tasks: [
        { id: 'w7-1', done: true, label: 'Delivered: request trace envelope (request_id, endpoint, timestamp, intent/workflow/orchestration)' },
        { id: 'w7-2', done: true, label: 'Delivered: structured stage telemetry (timing_ms + events + usage placeholders)' },
        { id: 'w7-3', done: false, label: 'Remaining: OpenTelemetry context propagation + service spans (retrieve/rerank/generate/semantic)' },
        { id: 'w7-4', done: false, label: 'Remaining: Langfuse/LangSmith capture (prompt, chunks, response, tokens, prompt/model versions)' }
      ]
    },
    {
      week: 8, project: 3, focus: 'P3 — Dashboards + Alerts + Chaos + CI Ops Gates', notes: 'Plan: D1 metric export wiring -> D2 dashboard build -> D3 alert thresholds -> D4 chaos scenarios and runbook -> D5 CI gate extension + simulated incident report (MTTD/MTTR). Includes closure of W4 carryover dashboard/canary items.',
      tasks: [
        { id: 'w8-1', done: false, label: 'Export telemetry to metrics backend and build P50/P95/P99 endpoint latency dashboards' },
        { id: 'w8-2', done: false, label: 'Add quality dashboards: faithfulness trend, citation coverage, refusal and failure metrics' },
        { id: 'w8-3', done: false, label: 'Define alert thresholds and execute chaos scenarios (provider timeout, DB slowdown, reranker failure)' },
        { id: 'w8-4', done: false, label: 'Extend CI gates (quality + latency), then publish simulated incident writeup with MTTD/MTTR' }
      ]
    },
    {
      week: 9, project: 4, focus: 'P4 — Task Definition + Dataset', notes: '',
      tasks: [
        { id: 'w9-1', done: false, label: 'Define fine-tuning task (structured JSON extraction or tool-call selection)' },
        { id: 'w9-2', done: false, label: 'Prompt-only baseline metrics + error taxonomy (top failure classes)' },
        { id: 'w9-3', done: false, label: 'Labeling guide + edge-case rules + quality bar' },
        { id: 'w9-4', done: false, label: 'Curate 2k-10k SFT examples; leakage + duplicate checks; data card' }
      ]
    },
    {
      week: 10, project: 4, focus: 'P4 — SFT Run + Eval', notes: '',
      tasks: [
        { id: 'w10-1', done: false, label: 'LoRA/QLoRA fine-tune on Qwen 3 8B class model (Hugging Face TRL)' },
        { id: 'w10-2', done: false, label: 'Holdout eval: JSON validity rate, exact match, refusal correctness' },
        { id: 'w10-3', done: false, label: 'W&B / MLflow training run tracking + training curves' },
        { id: 'w10-4', done: false, label: 'Robustness check: no regression on out-of-domain generic prompts' }
      ]
    },
    {
      week: 11, project: 4, focus: 'P4 — DPO + Final Report', notes: '',
      tasks: [
        { id: 'w11-1', done: false, label: 'Generate multiple outputs per prompt; label better/worse pairs (DPO data)' },
        { id: 'w11-2', done: false, label: 'DPO preference tuning run (Hugging Face TRL)' },
        { id: 'w11-3', done: false, label: 'Before/after metrics table: baseline → SFT → DPO' },
        { id: 'w11-4', done: false, label: 'Data card + model card + published endpoint + README' }
      ]
    },
    {
      week: 12, project: 5, focus: 'P5 — Streaming Skeleton', notes: '',
      tasks: [
        { id: 'w12-1', done: false, label: 'FastAPI WebSocket or gRPC streaming transport layer' },
        { id: 'w12-2', done: false, label: 'Single-modal baseline (voice: ASR→LLM→TTS or vision: webcam→VLM)' },
        { id: 'w12-3', done: false, label: 'Session manager with correlation IDs and event structure' },
        { id: 'w12-4', done: false, label: 'Initial per-stage latency measurement (ASR, LLM TTFT, TTS TTFB, overhead)' }
      ]
    },
    {
      week: 13, project: 5, focus: 'P5 — Second Modality + Latency Engineering', notes: '',
      tasks: [
        { id: 'w13-1', done: false, label: 'Second modality integration + session handoff logic' },
        { id: 'w13-2', done: false, label: 'Per-stage latency budget enforcement (hard limits per component)' },
        { id: 'w13-3', done: false, label: 'Latency decomposition visualization (stacked bar per request)' },
        { id: 'w13-4', done: false, label: 'Timeout handling + retry policy (no indefinite hangs)' }
      ]
    },
    {
      week: 14, project: 5, focus: 'P5 — Resilience + Demo', notes: '',
      tasks: [
        { id: 'w14-1', done: false, label: 'Circuit breaker + graceful fallback for each service failure mode' },
        { id: 'w14-2', done: false, label: 'Chaos test matrix: network jitter, dropped frames, model timeout, queue overflow' },
        { id: 'w14-3', done: false, label: 'Replay mode for deterministic debugging with recorded inputs' },
        { id: 'w14-4', done: false, label: '30-minute soak test — confirm no memory leak' },
        { id: 'w14-5', done: false, label: 'Demo video: normal path + failure-path behavior with measured latency' }
      ]
    }
  ],
  risks: [
    {
      id: 'r1', status: 'open', likelihood: 'high', impact: 'high',
      description: 'Answer-level evaluation quality remains unstable (answer_relevancy persistently near zero despite successful runs)',
      mitigation: 'Track graph/legacy deltas per release, separate retrieval acceptance from generation quality, and iterate prompts plus evidence shaping before tightening CI metric floors'
    },
    {
      id: 'r2', status: 'open', likelihood: 'medium', impact: 'high',
      description: 'GPU unavailable for fine-tuning (Project 4)',
      mitigation: 'Use Fireworks AI managed compute or Colab Pro+ as backup'
    },
    {
      id: 'r3', status: 'open', likelihood: 'medium', impact: 'medium',
      description: 'Golden answer set can drift when acceptance policy and endpoint contract change',
      mitigation: 'Keep candidates and golden split artifacts, regenerate golden from deterministic acceptance checks, and store parity reports for each contract migration'
    },
    {
      id: 'r4', status: 'open', likelihood: 'low', impact: 'medium',
      description: 'Lineage-to-chunk cross-mapping gaps: some fields trace back to unmapped SOURCE nodes',
      mitigation: 'Add coverage metric to ingest: log % of TARGET fields with resolved vs unresolved lineage chains; set minimum 80% resolution threshold before W3'
    },
    {
      id: 'r5', status: 'open', likelihood: 'medium', impact: 'medium',
      description: 'Graph memory overhead can grow during large multi-workflow lineage traversals',
      mitigation: 'Use PostgreSQL semantic fallback, cap traversal limits per query, and monitor networkx node/edge counts through /health lineage_graph telemetry'
    }
  ],

  journal: {
    daily: [
      {
        id: 'j-w4d2-20260819', date: '2026-08-19',
        title: 'W4 Day 2 — Conversational RAG Chatbot Hardening',
        mood: '🟢', energy: 5,
        wins: [
          'Implemented conversational chat workflow with session APIs, follow-up contextualization, and non-empty response safeguards',
          'Added capability-aware context agent so prompts like "what can this bot do" return indexed XML coverage and supported actions',
          'Shipped editable conversation memory (summary inspect/save/clear) and persistence-backed chat sessions via SQLite',
          'Upgraded assistant bubble rendering to markdown and added starter prompt chips to guide first user interactions',
          'Validated stability with expanded smoke coverage for chat, context-agent routing, and persistence reload behavior',
          'Completed RCA and fix for usage-query drift: added usage-entity retrieval guardrails so field-usage questions ground on correct mappings (e.g., BeginInteractionGroup_Id -> wf_4205)'
        ],
        losses: [
          'Intent routing was initially too strict for natural phrasing and required broader detection for capability prompts',
          'One test run failed due to indentation drift during rapid patching and was corrected in the same session',
          'Natural-language usage queries initially retrieved semantically similar but incorrect chunks before entity-first fallback was introduced'
        ]
      },
      {
        id: 'j-w4d1-20260818', date: '2026-08-18',
        title: 'W4 Day 1 — Graph Contract Simplification + Parity Validation',
        mood: '🟢', energy: 4,
        wins: [
          'Removed deprecated smart/friendly retrieval controls and aligned API, eval scripts, and tests to the simplified contract',
          'Fixed LangGraph state handoff issue by declaring retrieval handoff keys in AnswerGraphState, preventing empty-evidence graph outputs',
          'Generated graph-vs-legacy regression artifact showing parity on accepted candidate rows (22 accepted in each mode)',
          'Re-ran answer-level RAGAS in graph mode and captured updated runtime metrics in eval/ragas_report_latest.json'
        ],
        losses: [
          'Initial graph path silently dropped planner outputs and produced blanket refusals until state schema was corrected',
          'answer_relevancy stayed at 0.0000 in the latest graph-mode run, requiring prompt/evidence tuning next'
        ]
      },
      {
        id: 'j-w3d4-20260818', date: '2026-08-18',
        title: 'W3 Day 4 — LLD Viewer Delivery + Runtime Hardening',
        mood: '🟢', energy: 4,
        wins: [
          'Added a per-project LLD API route with safe workspace-root path resolution and read-only file access',
          'Shipped Projects UI LLD support with markdown rendering, reload, and full-screen reading mode',
          'Created placeholder LLD docs for P2-P5 so every project card has a resolvable design document',
          'Resolved stale backend behavior in Docker by rebuilding services and validating route availability from the running container'
        ],
        losses: [
          'Direct npm package installation was network-constrained during implementation',
          'Browser automation click stability was intermittent, so validation required selector retries and fresh page sessions'
        ]
      },
      {
        id: 'j-w3d3-20260817', date: '2026-08-17',
        title: 'W3 Day 3 — RAGAS Evaluation Closure',
        mood: '🟢', energy: 4,
        wins: [
          'Completed full RAGAS run on the 12-query answer dataset with report artifact generation',
          'Standardized evaluation runtime configuration loading from .env for repeatable local runs',
          'Aligned answer-generation and eval parameter handling in the same execution path',
          'Captured retrieval and answer-level baselines for Week 4 quality tuning'
        ],
        losses: [
          'First retry failed due to runtime configuration mismatch before the final successful run',
          'answer_relevancy baseline is currently 0.0000 and needs Week 4 prompt/retrieval quality iteration'
        ]
      },
      {
        id: 'j-w2d3-20260814', date: '2026-08-14',
        title: 'W2 Day 3 — 768-Dim Index Audit + Portfolio Tracker Wrap',
        mood: '🟢', energy: 4,
        wins: [
          'Validated pgvector index state end-to-end: rag.rag_chunks exists, vector(768), 4033 rows',
          'Confirmed corpus coverage parity: 25 PowerCenter XML files on disk vs 25 distinct source_file values in DB',
          'Verified retrieval indexes are present (ivfflat embedding + GIN FTS)',
          'Backfilled portfolio tracker weekly notes and preserved continuity for 2026-08-13 and 2026-08-14'
        ],
        losses: [
          'MCP Postgres connector was unavailable in-session, so validation required direct docker/psql checks',
          'PowerShell 5.1 null-coalescing operator (??) is unsupported and broke the first coverage-check command'
        ]
      },
      {
        id: 'j-w2d2-20260813', date: '2026-08-13',
        title: 'W2 Day 2 — Hybrid Retrieval + Citations + Refusal + Prompts',
        mood: '🟢', energy: 5,
        wins: [
          'BM25 (PostgreSQL tsvector GENERATED + GIN index) + RRF hybrid retrieval live',
          '/answer endpoint with [chunk_id]-cited evidence blocks and versioned prompts',
          'Refusal policy calibrated: cosine_score < 0.60 → refused=true for out-of-domain queries',
          'Cross-encoder reranker (ms-marco-MiniLM-L-6-v2) wired behind rerank=true flag',
          '20/20 smoke tests still passing; CHANGELOG + tracker updated'
        ],
        losses: [
          'bge-small-en-v1.5 takes 46s to load from HuggingFace cache on OneDrive — needs pre-warming',
          'PowerShell Set-Content corrupted unicode icons (mojibake) — fixed same session with Python'
        ]
      },
      {
        id: 'j-w2d1-20260812', date: '2026-08-12',
        title: 'W2 Day 1 — Field-Level Lineage Parser',
        mood: '🟢', energy: 4,
        wins: [
          'Discovered 13,237 CONNECTOR edges silently ignored by W1 parser',
          'Built BFS backward resolver: lineage_parser.py traces every TARGET field → SOURCE node',
          'LINEAGE chunks now indexed: NODE_CLASS: LINEAGE, TARGET:, SOURCE:, HOP_COUNT:, PATH:',
          '6 new smoke tests for lineage chains (20/20 total passing)'
        ],
        losses: [
          'Lineage coverage % unknown until full re-ingest with XML files accessible',
          'uvicorn --reload on OneDrive paths is unreliable — must kill and restart manually'
        ]
      },
      {
        id: 'j-w1-20260811', date: '2026-08-11',
        title: 'W1 — RAG System Foundation (P1)',
        mood: '🟢', energy: 5,
        wins: [
          'Stood up rag-system/ from scratch: xml_parser → chunker → embeddings → pgvector → FastAPI',
          '703 unique chunks indexed from 7 Informatica PowerCenter XML files (~8.6 MB)',
          'Pivoted from Azure embeddings (0.09 scores) to local bge-small-en-v1.5 (0.74-0.80 scores)',
          '30/30 tests passing (14 smoke + 16 integration)',
          'Object-boundary chunking: 1 ETL node = 1 chunk, preserves full SQL override + port context'
        ],
        losses: [
          'Azure OpenAI had no embedding model deployed — lost ~30 min debugging connection',
          '131 chunk ID collisions on first ingest; fixed with content-hash suffix in chunk_id'
        ]
      }
    ],
    stories: [
      {
        id: 'star-observability-week-plus-1-20260827', date: '2026-08-27',
        title: 'Implemented Week +1 observability without breaking semantic-first truth boundaries',
        category: 'Delivery',
        situation: 'We had committed to a two-week observability extension, but lineage/impact correctness could not be put at risk by instrumentation side effects. The challenge was to add actionable diagnostics while preserving deterministic authority boundaries.',
        task: 'I needed to deliver Week +1 instrumentation in live API responses, prove payload consistency through tests, and keep semantic-primary guardrails unchanged.',
        action: 'I added a standardized trace envelope and stage timing telemetry across retrieve/answer/semantic routes, plus structured events and usage placeholders. I propagated timing across semantic and retrieval branches, then updated smoke assertions to validate trace/telemetry contracts and refreshed API testing docs and E2E architecture notes to match implementation.',
        result: 'Week +1 observability moved from plan to implementation with additive diagnostics, targeted smoke validations passed, and semantic authority boundaries remained intact. This gave us measurable latency/debug signals without changing truth behavior.'
      },
      {
        id: 'star-usage-entity-guardrail-20260819', date: '2026-08-19',
        title: 'Fixed a misleading lineage answer by adding usage-entity guardrails',
        category: 'Debugging',
        situation: 'A user asked, "Where is BeginInteractionGroup_Id used across mappings?" and the chatbot answered with unrelated wf_2201/wf_2210 transformations, even though wf_4205 clearly contained many direct usages. The failure was risky because the answer looked confident but was wrong.',
        task: 'I needed to find the root cause and make the bot reliably ground usage questions on the actual field token, not semantically similar but irrelevant chunks.',
        action: 'I validated ground truth directly in XML, then inspected retrieval behavior for the exact natural-language prompt versus the raw field token. The full sentence query drifted to unrelated chunks, while token-only retrieval returned the correct wf_4205 evidence. I patched retrieval with a usage-intent guardrail: extract usage entity, run entity-first fallback queries (bm25/hybrid/vector) when needed, and restore pre-rerank entity hits if reranking drops the requested field.',
        result: 'After the patch, the same user question resolves to effective_query=BeginInteractionGroup_Id, top evidence comes from wf_4205_calculate_dm_facts.XML, and the bot now returns field-grounded mapping usage details instead of false negatives.'
      },
      {
        id: 'star-conversational-rag-20260819', date: '2026-08-19',
        title: 'Turned RAG answers into a conversational chatbot in one session',
        category: 'Delivery',
        situation: 'The RAG could answer focused technical questions, but users still struggled with natural onboarding prompts like "what can this bot do". Responses were often hard to read in long bubbles, session continuity was volatile after restarts, and first-time users had no guided starting path.',
        task: 'I needed to make the assistant feel genuinely conversational in one working session: robust capability introspection, readable outputs, persistent session memory, and clear UI entry points.',
        action: 'I implemented a capability-aware context route that detects natural phrasing and returns an indexed corpus inventory (chunk totals, XML coverage, node classes, mappings, folders). I added chat memory controls in the UI, upgraded assistant rendering to markdown for structured readability, and added clickable starter prompts so users can begin with high-signal questions immediately. I then moved session state from memory-only behavior to SQLite-backed persistence so sessions/messages/summary survive cache clears and restarts, and expanded smoke coverage for routing plus persistence reload behavior.',
        result: 'The chatbot now supports conversational onboarding, context self-description, persistent memory, and cleaner readable answers in one integrated flow. Chat/context test suites passed after the rollout, and users can reliably ask capability/coverage questions without prompt-engineering their first message.'
      },
      {
        id: 'star-graph-state-fix-20260818', date: '2026-08-18',
        title: 'Recovered graph orchestration by fixing silent state handoff loss',
        category: 'Debugging',
        situation: 'After simplifying smart/friendly controls, graph-mode answers began refusing almost all questions while legacy still returned evidence. The failure looked like retrieval quality, but behavior divergence suggested orchestration loss between nodes.',
        task: 'I needed to restore graph reliability quickly without rolling back the API simplification and prove parity against the legacy path before preserving the new contract.',
        action: 'I compared legacy and graph payloads on identical queries and found planner outputs were not present at executor time. In LangGraph, keys not declared in TypedDict state are dropped, so I extended AnswerGraphState with retrieval handoff fields (hits, plan, resolved_mode, effective_query, source_file_hints). I also widened file-scoped retrieval fan-out before source-file preference so hinted workflow files were not lost in top-k truncation, then reran candidate parity checks and targeted tests.',
        result: 'Graph and legacy returned matching acceptance outcomes on the candidate set (22 accepted each, zero delta), and the full smoke/ragas/integration suite passed (44 tests). The key lesson was to treat state-schema completeness as a hard requirement in graph orchestration, not an implementation detail.'
      },
      {
        id: 'star-lld-viewer-delivery-20260818', date: '2026-08-18',
        title: 'Delivered project-wide markdown LLD access under runtime constraints',
        category: 'Delivery',
        situation: 'The tracker had no way to surface low-level design documents per project, so architecture context lived outside the product. During implementation, backend container drift and package-install constraints risked delaying delivery.',
        task: 'I needed to ship a reliable, interview-ready LLD viewing flow in the tracker the same day, with markdown rendering and full-screen readability across all five projects.',
        action: 'I added a backend LLD registry and project-specific endpoint, implemented safe workspace-relative path handling, and mounted workspace docs into the backend container. On the frontend, I wired on-demand LLD fetch, markdown rendering, reload controls, and an Escape-enabled full-screen modal. When npm installs were unreliable, I used a CDN markdown parser fallback so delivery stayed unblocked. I then rebuilt the tracker stack and revalidated the route plus UI behavior end to end.',
        result: 'All 5 project cards can now open LLD content as rendered markdown, including a full-screen reading mode for long documents. We removed doc-discovery friction from interview prep flows and closed the feature without introducing diagnostics regressions in the touched files.'
      },
      {
        id: 'star-azure-gpt5-ragas-20260817', date: '2026-08-17',
        title: 'Closed Week 3 RAGAS execution gap with a repeatable eval flow',
        category: 'Problem Solving',
        situation: 'Week 3 required a real answer-level evaluation report, but the execution path was inconsistent across retrieval, answer generation, and eval harness configuration. We needed a complete run artifact, not a partial status update.',
        task: 'I needed to deliver a repeatable end-to-end RAGAS run in the same session and produce a tracker-ready report artifact with usable baseline metrics.',
        action: 'I standardized runtime configuration loading, aligned parameter handling between the API answer path and eval harness, and validated the run on a clean API lifecycle using blocking connect before execution. Then I reran the full 12-query answer dataset and captured per-query diagnostics and summary scores.',
        result: 'RAGAS completed successfully with report output and non-NaN faithfulness score (0.4000). The team now has a stable evaluation baseline and can focus Week 4 on measurable quality improvements (answer_relevancy 0.0000) instead of run reliability.'
      },
      {
        id: 'star-index-validation-20260814', date: '2026-08-14',
        title: 'Proved index completeness under tooling constraints',
        category: 'Problem Solving',
        situation: 'I needed to confirm quickly whether retrieval was truly ready at 768 dimensions before more feature work. The direct MCP DB path was unavailable, and giving a vague answer would risk debugging the wrong layer later.',
        task: 'I had to produce a defensible yes or no on indexing completeness, with evidence across schema, dimension, row count, and source-file coverage for the active corpus.',
        action: 'I switched to direct docker and psql checks, then validated four dimensions in sequence: table presence, embedding type, row volume, and index existence. After that, I compared distinct source_file names in Postgres against XML basenames discovered from INFA_XML_FOLDER. My first PowerShell attempt failed due unsupported null-coalescing syntax on 5.1, so I rewrote with explicit null-safe checks and reran the diff logic.',
        result: 'I confirmed vector(768), 4033 rows, and exact file parity (25 in corpus, 25 in DB, zero missing/extra). That let us close the reindex question confidently and avoid unnecessary re-ingestion. I learned to keep a shell-compatible validation path ready whenever managed DB tooling is unavailable.'
      },
      {
        id: 'star-hybrid-rag-20260813', date: '2026-08-13',
        title: 'Turned retrieval into interview-safe RAG in one W2 session',
        category: 'Delivery',
        situation: 'At the start of W2, the API could retrieve chunks but was risky in interviews and demos. It could miss exact workflow IDs, it could not cite evidence, and it could answer unrelated questions confidently. With one session left, this was a delivery risk.',
        task: 'I had to ship five linked capabilities in order: BM25 precision, hybrid fusion, citation-backed answers, refusal behavior, and prompt versioning, without re-ingesting the corpus or breaking the 20-test smoke suite.',
        action: 'I added PostgreSQL FTS with a generated tsvector column and a GIN index, then implemented hybrid retrieval with RRF at k=60 so exact IDs and semantic matches both surfaced. I tested refusal logic with out-of-domain prompts and learned RRF score was not usable for thresholding because unrelated and related queries clustered near 0.011. I switched refusal to cosine vector_score and calibrated 0.60 as the cutoff. I then added prompt templates with explicit versions and wired /answer to return citations and prompt_version in every response.',
        result: 'All 5 W2 tasks shipped in one session, and smoke tests stayed 20/20. The endpoint now refuses out-of-domain queries, returns chunk-cited evidence, and stamps prompt versions for auditability. I learned that ranking fusion helps retrieval quality, but safety thresholds must use a true similarity signal, not fused rank math.'
      },
      {
        id: 'star-lineage-20260812', date: '2026-08-12',
        title: 'Recovered lineage by fixing 13,237 silently dropped CONNECTOR edges',
        category: 'Debugging',
        situation: 'The morning after W1, I counted 13,237 CONNECTOR elements across 7 XML files, but the RAG had zero lineage chunks. Engineers asking source-trace questions would get no answer, even though the data existed. That silent gap became an immediate credibility risk.',
        task: 'I needed to add field-level lineage without breaking existing W1 retrieval, and I had to keep the current 703 chunk pipeline stable while adding new chunk types and tests.',
        action: 'I traced parsing flow and found _parse_mapping_connectors() already extracted connector data, but flatten_mapping_to_nodes() dropped it with no warning. Instead of rewriting the parser, I added a BFS backward resolver that starts from each TARGET field, walks connector edges, and emits complete SOURCE paths as LINEAGE chunks with hop counts. I also decided unresolved paths should warn, not fail ingest, because some mappings are legitimately incomplete. I added six lineage-focused smoke tests so the failure mode would stay visible.',
        result: 'All 13,237 connector edges are now processed, and lineage queries return explicit field paths instead of empty results. Smoke tests remained green at 20/20 after the change. I learned to add coverage counters early, because silent drops are harder to catch than hard failures.'
      },
      {
        id: 'star-embedding-pivot-20260811', date: '2026-08-11',
        title: 'Pivoted embeddings mid-session when Azure deployment was missing',
        category: 'Problem Solving',
        situation: 'About an hour into W1, Azure had GPT-4o available but no embedding deployment. My fallback hashing vectors produced ~0.09 scores on obviously relevant queries, so retrieval quality was not usable. With five W1 tasks still blocked, waiting on cloud setup was not viable.',
        task: 'I had to restore semantic retrieval the same day, keep local development unblocked, and preserve a clean path back to Azure embeddings once the deployment existed.',
        action: 'I switched to sentence-transformers with BAAI/bge-small-en-v1.5 and updated the provider chain to prefer Azure, then local model, then hashing fallback. Because pgvector had been created at dim=256, I dropped and recreated the table at dim=384 and re-ingested the corpus. I validated improvement by rerunning representative retrieval queries, including SQL-heavy Source Qualifier examples. I also kept the provider abstraction intact so infrastructure changes later would not require business-logic rewrites.',
        result: 'Retrieval scores moved from ~0.09 to ~0.74-0.80, and W1 still shipped on schedule with 30/30 tests passing. The pivot cost about 40 minutes but removed a full-day dependency on cloud provisioning. I learned to design providers as swappable components early, because infrastructure assumptions fail at the worst time.'
      }
    ]
  },

  interview: {
  "qbank": [
    {"id": "q1", "topic": "Architecture", "question": "Walk me through your RAG system architecture end-to-end.", "answer": "The system has four layers. Ingestion: xml_parser.py parses Informatica PowerCenter XML exports into canonical node dicts (SOURCE, TRANSFORMATION, TARGET). Chunking: object-boundary chunking, one ETL node equals one chunk, with 700-token max and 100-token overlap on splits, plus enriched metadata (has_sql_override, has_join, source_db). Embeddings: provider chain Azure > SentenceTransformer (all-MiniLM-L6-v2, dim=384) > HashingEmbedding fallback. Storage: pgvector on Postgres 17 with IVFFlat cosine index. FastAPI exposes GET /retrieve, POST /ingest, POST /connect, GET /health. 703 unique chunks currently indexed from 7 XML files (~8.6 MB total).", "code": "# knowledge_base.py\ndef build_from_folder(self, folder_path, batch_size=64):\n    nodes = walk_xml_folder(folder_path)          # parse XMLs\n    chunks = chunk_nodes(nodes)                    # 700-tok chunks\n    seen = set()\n    unique = [c for c in chunks if c.chunk_id not in seen\n              and not seen.add(c.chunk_id)]        # dedup\n    for i in range(0, len(unique), batch_size):\n        batch = unique[i:i+batch_size]\n        vecs  = self._embedder.embed([c.text for c in batch])\n        self._store.upsert(batch, vecs)            # ON CONFLICT DO UPDATE\n    self._built = True", "file_refs": ["rag-system/src/rag_system/knowledge_base.py", "rag-system/src/rag_system/chunking/chunker.py", "rag-system/weekly/W01_2026-08-11.md"], "upcoming_weeks": [2, 3], "upcoming_context": ["W2: add field-level lineage chunks (13237 CONNECTOR edges)", "W3: add hybrid BM25 + vector retrieval"], "follow_ups": ["How would you add BM25 alongside vector search?", "How does dedup handle the same node name in multiple FOLDER elements?", "What changes when the corpus grows 100x?"]},
    {"id": "q2", "topic": "Chunking", "question": "Why did you choose object-boundary chunking over a sliding window?", "answer": "Informatica XMLs are a graph, not prose. Each node is a complete, indivisible ETL concept. A Source Qualifier IS its SQL override, port list, and join condition together. A sliding window cutting a 130-port Source Qualifier mid-port-list gives the embedding model half a concept. The retrieval granularity engineers care about is exactly one node, so one node equals one chunk. For nodes exceeding 700 tokens we apply a line-aware split with 100-token overlap.", "code": "# chunker.py\ndef _split_with_overlap(text, max_tokens, overlap_tokens):\n    max_chars = max_tokens * _CHARS_PER_TOKEN   # 700 * 4 = 2800\n    if len(text) <= max_chars:\n        return [text]\n    lines = text.splitlines(keepends=True)\n    chunks, buf = [], ''\n    for line in lines:\n        if len(buf) + len(line) > max_chars and buf:\n            chunks.append(buf)\n            buf = buf[-overlap_tokens*_CHARS_PER_TOKEN:]\n        buf += line\n    if buf: chunks.append(buf)\n    return chunks", "file_refs": ["rag-system/src/rag_system/chunking/chunker.py", "rag-system/weekly/W01_2026-08-11.md"], "upcoming_weeks": [2, 3], "upcoming_context": ["W2: parent-document retrieval", "W3: SQL-aware chunking"], "follow_ups": ["Risk of SQL override ending up in a later chunk part?", "How would hierarchical chunking improve lineage queries?", "Why 700 tokens and not 512?"]},
    {"id": "q3", "topic": "Embeddings", "question": "You switched from HashingEmbedding to sentence-transformers mid-session. Walk me through that decision.", "answer": "The Azure OpenAI resource had no embedding model. HashingEmbedding was giving retrieval scores of 0.09 because it is purely lexical. I needed real semantic embeddings immediately. sentence-transformers all-MiniLM-L6-v2 runs fully offline after a one-time 90 MB download, produces 384-dim L2-normalised vectors, and requires no API keys. The provider chain auto-upgrades when Azure eventually has an embedding deployment. Switching required dropping and recreating the pgvector table (dim 256 to 384) and a full re-ingest. Scores jumped from 0.09 to 0.39.", "code": "# provider.py\ndef get_embedding_provider():\n    deployment = os.getenv('AZURE_EMBEDDING_DEPLOYMENT', '').strip()\n    if deployment and os.getenv('AZURE_OPENAI_API_KEY'):\n        try: return AzureOpenAIEmbedding(deployment)\n        except Exception: pass\n    if os.getenv('USE_HASHING_EMBEDDING','').lower() not in ('1','true','yes'):\n        try: return SentenceTransformerEmbedding()\n        except Exception: pass\n    return HashingEmbedding()", "file_refs": ["rag-system/src/rag_system/embeddings/provider.py"], "upcoming_weeks": [2, 4], "upcoming_context": ["W2: evaluate BAAI/bge-small-en-v1.5", "W4: domain-adapted embeddings via fine-tuning"], "follow_ups": ["How to quantify which model is best for this domain?", "Cost difference between hosted vs local at scale?", "Migration strategy if dim changes again?"]},
    {"id": "q4", "topic": "Vector Store", "question": "Why pgvector over Chroma or Weaviate for this use case?", "answer": "Three reasons. First, operational simplicity: pgvector is just a Postgres extension, no extra service. Second, IVFFlat cosine performs sub-millisecond at 703 vectors. Third, metadata is stored as JSONB, enabling SQL filters like WHERE metadata->>'has_sql_override' = 'true' directly in the vector search query without a post-filter round-trip. The trade-off: dropping and recreating the table when embedding dimension changes.", "code": "# vector_store.py\nclass PgVectorStore(VectorStore):\n    def _ensure_schema(self):\n        self._conn.execute(f'''\n            CREATE TABLE IF NOT EXISTS {self.table} (\n                chunk_id  text PRIMARY KEY,\n                metadata  jsonb,\n                embedding vector({self.dim})\n            )\n        ''')\n        self._conn.execute(\n            f'CREATE INDEX IF NOT EXISTS ... USING ivfflat'\n            f' (embedding vector_cosine_ops) WITH (lists = 100)'\n        )", "file_refs": ["rag-system/src/rag_system/store/vector_store.py"], "upcoming_weeks": [2], "upcoming_context": ["W2: add BM25 keyword index for hybrid retrieval"], "follow_ups": ["How to shard pgvector if corpus grew to 10M chunks?", "IVFFlat vs HNSW - when to switch?", "How does ON CONFLICT DO UPDATE make ingest idempotent?"]},
    {"id": "q5", "topic": "API Design", "question": "Explain POST /ingest vs POST /connect, and why you added /connect.", "answer": "POST /ingest triggers the full pipeline: parse XMLs, chunk, embed, upsert into pgvector. Requires XML files on disk, takes ~30 seconds for 703 chunks. POST /connect is lighter: it wires the server's in-process KnowledgeBase object to an existing, already-populated pgvector store. No XML files needed, completes in ~2 seconds. I added /connect because the server process does not survive restarts but pgvector data persists on a named Docker volume. AUTO_CONNECT=true in .env triggers this automatically on startup.", "code": "# app.py\ndef _run_connect():\n    global _kb, _ingest_status\n    try:\n        kb = InformaticaKnowledgeBase()\n        store = kb._make_store()\n        count = store.count()\n        kb._store = store\n        kb._built = True\n        _kb = kb\n        _ingest_status = {'state': 'connected', 'chunks': count}\n    except Exception as exc:\n        _ingest_status = {'state': 'error', 'error': str(exc)}", "file_refs": ["rag-system/src/rag_system/api/app.py"], "upcoming_weeks": [3], "upcoming_context": ["W3: add /reload endpoint for zero-downtime re-ingest"], "follow_ups": ["What happens if /retrieve is called while /ingest is running?", "How to make ingest zero-downtime?", "Why is background=true the default?"]},
    {"id": "q6", "topic": "Evaluation", "question": "How do you plan to ensure retrieval quality does not regress as the system evolves?", "answer": "Three-layer eval strategy. Layer 1 (W1): 16 integration tests as smoke gate. Layer 2 (W3): golden dataset of 50-200 query/expected-node pairs. Compute RAGAS metrics: retrieval hit rate at k >= 0.85, citation correctness >= 0.9, hallucination rate <= 0.08. Layer 3 (W5): CI quality gates in GitHub Actions blocking PRs that degrade hit rate or increase hallucination rate.", "file_refs": ["rag-system/tests/test_integration.py"], "upcoming_weeks": [3, 4, 5], "upcoming_context": ["W3: RAGAS evaluation harness", "W4: baseline scorecard", "W5: CI gates"], "follow_ups": ["How to build golden dataset without ground truth labels?", "Difference between RAGAS faithfulness and answer correctness?", "How to handle evaluation when LLM changes?"]},
    {"id": "q7", "topic": "Governance", "question": "How are you thinking about governance for this GenAI system?", "answer": "Four dimensions. Quality governance (W3-W5): RAGAS metric baselines in CI, no PR merges if hit rate drops. Prompt versioning so every LLM call is traceable. Data governance (W7-W8): full observability, every query and response logged with a trace ID. Safety (W3): refusal policy for out-of-domain queries. Model governance (W9-W11): fine-tuning scorecard comparing base vs fine-tuned on golden dataset before promotion.", "file_refs": ["apps/genai-portfolio-tracker-react/src/data.js"], "upcoming_weeks": [3, 7, 8, 9], "upcoming_context": ["W3: refusal policy + prompt versioning", "W5: CI quality gates", "W7-W8: observability pipeline", "W9-W11: model scorecard"], "follow_ups": ["How to implement PII detection before chunks are indexed?", "Incident runbook if model starts hallucinating?", "How to version and roll back prompt templates?"]},
    {"id": "q8", "topic": "Governance", "question": "What is your observability strategy for the RAG pipeline?", "answer": "Currently (W1): basic health endpoint and ingest status. Plan for W7-W8: trace ID per request propagated through retrieval to LLM to response; structured logging of every chunk retrieved alongside the query; latency metrics at each stage; dashboard showing daily P95 response latency, hit rate trend, and hallucination rate.", "file_refs": ["project1/e2e_infa_to_pyspark/app/observability/run_recorder.py"], "upcoming_weeks": [7, 8], "upcoming_context": ["W7: distributed tracing", "W8: latency dashboard + hallucination rate monitoring"], "follow_ups": ["Which tracing framework: OpenTelemetry, Langfuse, or custom?", "How to detect hallucinations automatically?", "When do you page someone?"]},
    {"id": "q9", "topic": "Problem Solving", "question": "Tell me about a time you had to solve a blocking technical issue mid-session and deliver anyway.", "answer": "The Azure OpenAI embedding deployment issue. The Azure resource only had GPT-4o, no embedding model. HashingEmbedding was giving scores of 0.09. I pivoted to sentence-transformers all-MiniLM-L6-v2: added the class, updated the provider priority chain, dropped and recreated pgvector at dim=384, re-ingested 703 chunks. The whole pivot took about 20 minutes. Scores jumped from 0.09 to 0.39. The system auto-upgrades to Azure embeddings when available.", "file_refs": ["rag-system/src/rag_system/embeddings/provider.py", "rag-system/weekly/W01_2026-08-11.md"], "upcoming_weeks": [], "upcoming_context": [], "follow_ups": ["How did you validate the quality improvement was real?", "What if sentence-transformers was also unavailable?", "How did you communicate this change?"]},
    {"id": "q10", "topic": "Debugging", "question": "Describe a bug you caught in production code during testing and how you fixed it.", "answer": "The double-lock-release bug in POST /ingest?background=false. The ingest endpoint acquired a threading.Lock, then called _do_ingest_locked() which always releases the lock in its own finally block. The outer endpoint also had a finally releasing the lock when background=false, so the lock was released twice, raising RuntimeError. Fix: remove the duplicate release from the outer endpoint's finally block.", "code": "# BROKEN: double release\ndef ingest(background):\n    _ingest_lock.acquire()\n    try:\n        if background: Thread(target=_do_ingest_locked).start()\n        else: _do_ingest_locked(folder)\n    finally:\n        if not background: _ingest_lock.release()  # BUG: already released\n\n# FIXED:\ndef ingest(background):\n    _ingest_lock.acquire()\n    if background: Thread(target=_do_ingest_locked).start()\n    else: _do_ingest_locked(folder)", "file_refs": ["rag-system/src/rag_system/api/app.py"], "upcoming_weeks": [], "upcoming_context": [], "follow_ups": ["How to write a test that catches this before production?", "Difference between non-reentrant and reentrant lock?", "How to handle concurrent ingest requests?"]},
    {"id": "q11", "topic": "Architecture", "question": "What makes Informatica PowerCenter XMLs challenging for RAG specifically?", "answer": "Three domain-specific challenges. First, the data is a graph not prose: nodes have typed relationships and querying a transformation without its upstream source loses critical context. Second, field names are cryptic domain shorthand that semantic queries from engineers may not match. The render_node() function produces label-prefixed text to bridge this. Third, the same node name can appear in multiple FOLDER elements causing chunk ID collisions, fixed with a content-hash suffix.", "file_refs": ["rag-system/src/rag_system/chunking/chunker.py"], "upcoming_weeks": [2, 3], "upcoming_context": ["W2: mapping-level summary chunks for lineage queries", "W3: citation output quoting exact chunk_id and field name"], "follow_ups": ["How to handle a query spanning multiple transformations?", "Strategy for field-level lineage?", "How does this compare to the e2e_infa_to_pyspark pipeline?"]},
    {"id": "q12", "topic": "Testing", "question": "How did you structure the smoke tests versus integration tests for the RAG system, and what does each layer guarantee?", "answer": "The test suite has two layers. test_smoke.py (14 tests, now 20 with lineage) runs entirely offline with no external dependencies. It tests each component in isolation: chunker with synthetic nodes, HashingEmbedding shape and L2-norm, InMemoryVectorStore upsert and cosine search, and FastAPI endpoints. These run in under 5 seconds and are always green. test_integration.py (16 tests) tests against the real 7 XML files and is guarded by a skip_if_offline decorator that checks whether the XML folder is accessible.", "code": "# test_smoke.py\ndef test_hashing_l2_normalized():\n    emb = HashingEmbedding(dim=256)\n    vec = emb.embed_one('Source Qualifier')\n    norm = math.sqrt(sum(v*v for v in vec))\n    assert abs(norm - 1.0) < 1e-6\n\n# test_integration.py\nskip_if_offline = pytest.mark.skipif(\n    not _folder_accessible(),\n    reason='XML folder not accessible'\n)", "file_refs": ["rag-system/tests/test_smoke.py", "rag-system/tests/test_integration.py"], "upcoming_weeks": [3, 5], "upcoming_context": ["W3: golden dataset tests", "W5: CI gates"], "follow_ups": ["How to add a property-based test for the chunker?", "Risk of skip_if_offline vs a proper fixture?", "How to test /retrieve end-to-end in CI without pgvector?"]},
    {"id": "q13", "topic": "DevOps", "question": "Walk through the Docker setup for pgvector and what makes data persist across container restarts.", "answer": "The docker-compose.yml uses pgvector/pgvector:pg17 on port 5433. A named volume pgvector_data mounts to /var/lib/postgresql/data. Named Docker volumes survive docker compose down and even docker compose rm; only docker volume rm would delete data. The healthcheck runs pg_isready every 5 seconds. The RAG system connects via the DSN in .env. The rag schema and rag.rag_chunks table are created by PgVectorStore._ensure_schema() on first connection.", "code": "# docker-compose.yml\nservices:\n  pgvector:\n    image: pgvector/pgvector:pg17\n    ports: ['5433:5432']\n    volumes:\n      - pgvector_data:/var/lib/postgresql/data\n    healthcheck:\n      test: ['CMD-SHELL', 'pg_isready -U raguser']\nvolumes:\n  pgvector_data:   # persists across restarts", "file_refs": ["rag-system/docker-compose.yml"], "upcoming_weeks": [3], "upcoming_context": ["W3: add Redis for background job queue"], "follow_ups": ["Difference between named volume and bind mount?", "How to back up and restore pgvector data?", "Why port 5433 instead of 5432?"]},
    {"id": "q14", "topic": "Architecture", "question": "How does render_node() make chunk text self-describing, and why does that matter for both embedding quality and downstream LLM use?", "answer": "render_node() converts a canonical node dict into a labelled text block with explicit prefixes: FILE:, NODE_CLASS:, NAME:, TYPE:, MAPPING:, PORTS:, SQL_OVERRIDE:, JOIN_CONDITION:, FILTER_CONDITION:. These labels serve dual purpose. For embeddings: the model sees structural signal tokens. For the downstream LLM: the chunk is self-contained context for extracting a field-level STTM directly from the retrieved text.", "code": "# chunker.py\ndef render_node(node, source_file):\n    lines = []\n    lines.append(f'FILE: {source_file}')\n    lines.append(f'NODE_CLASS: {node_class}')\n    lines.append(f'NAME: {name}')\n    if node.get('sql_override'):\n        lines.append(f'SQL_OVERRIDE: {sql}')\n    return '\\n'.join(lines)", "file_refs": ["rag-system/src/rag_system/chunking/chunker.py"], "upcoming_weeks": [3], "upcoming_context": ["W3: citation output will reference chunk_id and field names"], "follow_ups": ["How to handle SQL override that is 5000 characters?", "What labels to add for aggregation queries?", "How does this differ from chunking a plain SQL script?"]},
    {"id": "q15", "topic": "Architecture", "question": "How does ON CONFLICT DO UPDATE make the ingest pipeline idempotent, and why is that important?", "answer": "PgVectorStore uses INSERT ON CONFLICT (chunk_id) DO UPDATE SET for every batch. Re-running POST /ingest on the same XML files is completely safe. This matters when ingest crashes mid-way, when an XML file changes, and for test suite reliability. The chunk_id includes a content hash so if node content changes, its chunk_id changes and you get a new row instead of an update.", "code": "# vector_store.py\ncur.executemany(\n    '''\n    INSERT INTO rag.rag_chunks (chunk_id, text, embedding ...)\n    VALUES (%s, %s, %s ...)\n    ON CONFLICT (chunk_id) DO UPDATE SET\n        text=EXCLUDED.text,\n        embedding=EXCLUDED.embedding\n    ''',\n    rows\n)", "file_refs": ["rag-system/src/rag_system/store/vector_store.py"], "upcoming_weeks": [3], "upcoming_context": ["W3: periodic orphan cleanup"], "follow_ups": ["What are orphaned chunks?", "How to make ingest transactional?", "Difference between upsert and merge semantics?"]},
    {"id": "q16", "topic": "DevOps", "question": "How does FastAPI's lifespan context manager work and why was it the right replacement for the deprecated on_event decorator?", "answer": "The lifespan context manager is a single async generator function. Code before yield runs at startup, code after runs at shutdown. FastAPI passes it to the app constructor. The old on_event decorators were deprecated because they could not share state between startup and shutdown and did not compose well in tests. In the RAG system the lifespan checks AUTO_CONNECT or AUTO_INGEST env vars and kicks off the appropriate background thread.", "code": "# app.py\n@asynccontextmanager\nasync def _lifespan(app: FastAPI):\n    if os.getenv('AUTO_CONNECT', '').lower() in ('1','true','yes'):\n        threading.Thread(target=_run_connect, daemon=True).start()\n    yield\n\napp = FastAPI(lifespan=_lifespan)", "file_refs": ["rag-system/src/rag_system/api/app.py"], "upcoming_weeks": [3], "upcoming_context": ["W3: use lifespan shutdown to flush metrics"], "follow_ups": ["How to write a pytest fixture that uses lifespan?", "What if the background thread raises?", "How does lifespan interact with Uvicorn graceful shutdown?"]},
    {"id": "q17", "topic": "Debugging", "question": "How did you diagnose and fix the wrong Azure OpenAI base URL, and what does that sequence teach about API authentication errors?", "answer": "Initial .env had the wrong base URL. The first signal was a 401 Access Denied. After verifying the key partial matched, I suspected the endpoint. Updating the base URL changed the error from 401 to 404 DeploymentNotFound, confirming auth was now passing. The lesson: a 401 can mean wrong endpoint not just wrong key. Once you get a 404 after a 401 you have isolated the problem to resource configuration.", "file_refs": ["rag-system/.env"], "upcoming_weeks": [], "upcoming_context": [], "follow_ups": ["Difference between 401 and 403 in Azure OpenAI?", "How to write a credential health check?", "Secure API key management in a team?"]},
    {"id": "q18", "topic": "Embeddings", "question": "What happens at the data layer when you change the embedding dimension, and how did you handle the 256 to 384 dim migration?", "answer": "The embedding vector column in pgvector is typed as vector(256), baked into the schema at table creation. You cannot ALTER the column type; you must DROP and recreate. Migration: docker exec psql DROP TABLE rag.rag_chunks; next ingest creates vector(384); POST /ingest?background=false re-ingests 703 chunks. IVFFlat index also recreated automatically. Total downtime was the 30 seconds of re-ingest.", "code": "# Drop table before dim change:\n# docker exec rag-system-pgvector-1 psql -U raguser -d ragdb\n# -c 'DROP TABLE IF EXISTS rag.rag_chunks;'\n# Then POST /ingest?background=false", "file_refs": ["rag-system/src/rag_system/store/vector_store.py"], "upcoming_weeks": [4], "upcoming_context": ["W4: fine-tuned embeddings may have different dim"], "follow_ups": ["Zero-downtime dim migration on live system?", "How should IVFFlat lists scale with corpus size?", "How to handle mixed-dim chunks?"]},
    {"id": "q19", "topic": "Testing", "question": "How does the integration test fixture use module scope to avoid rebuilding the knowledge base for every test?", "answer": "The kb fixture in test_integration.py is decorated with @pytest.fixture(scope='module'). This means pytest builds the InformaticaKnowledgeBase exactly once for the entire test module; all 16 tests share the same in-memory KB instance. The KB uses HashingEmbedding and InMemoryVectorStore so it has no external dependencies.", "code": "# test_integration.py\n@pytest.fixture(scope='module')\ndef kb():\n    instance = InformaticaKnowledgeBase(\n        backend='memory',\n        embedding_provider=HashingEmbedding(dim=256),\n    )\n    instance.build_from_folder(_INFA_FOLDER)  # runs ONCE for all 16 tests\n    return instance", "file_refs": ["rag-system/tests/test_integration.py"], "upcoming_weeks": [3], "upcoming_context": ["W3: golden dataset tests will also use module-scope KB fixture"], "follow_ups": ["Risk of shared mutable state in module-scope fixture?", "How to handle teardown with module scope?", "When to use session scope instead?"]},
    {"id": "q20", "topic": "Architecture", "question": "How does chunk ID collision prevention work when the same transformation name appears in multiple FOLDER elements of one XML file?", "answer": "The chunk_id format is source_file:node_class:slug(name):content_hash[:part]. The content_hash is the first 8 hex chars of the MD5 of the rendered text. Two nodes with the same name but different content have different hashes so their chunk IDs are different. Without the hash, the second occurrence would silently overwrite the first in pgvector. Before this fix we had 131 duplicate IDs. After adding the hash we had 718 generated chunks which deduplication reduced to 703.", "code": "# chunker.py\ndef _content_hash(text: str) -> str:\n    return hashlib.md5(text.encode('utf-8')).hexdigest()[:8]\n\n# chunk_id: 'wf_4201.XML:TRANSFORMATION:sq_sql_override_event:0e1edc3c#0'", "file_refs": ["rag-system/src/rag_system/chunking/chunker.py"], "upcoming_weeks": [], "upcoming_context": [], "follow_ups": ["Why are the remaining 15 deduped chunks truly identical?", "How to detect unexpected dedup rates during ingest?", "Could two different nodes have the same content hash?"]},
    {"id": "q22", "topic": "Architecture", "question": "Your Informatica XMLs have 13,237 CONNECTOR elements that your W1 RAG ignored. How did you discover that and what did you build to fix it?", "answer": "I discovered it by running a regex count: 13,237 CONNECTOR elements across the 7 XMLs, zero captured. The xml_parser.py had _parse_mapping_connectors() already implemented but the output was silently dropped in flatten_mapping_to_nodes(). I built lineage_parser.py which runs a BFS backward from each TARGET field through the CONNECTOR graph until it reaches a SOURCE node. Each resolved path becomes a LINEAGE chunk with labels TARGET:, SOURCE:, HOP_COUNT:, and a full PATH: section. This enables queries like 'where does InteractionEvent_Id in wf_4205 come from?' to return the complete field lineage path.", "code": "# lineage_parser.py\ndef _trace_back(start_inst, start_field, reverse_adj, node_lookup, max_depth=20):\n    queue = [[{'instance': start_inst, 'field': start_field,\n              'node_class': node_lookup.get(start_inst, 'TRANSFORMATION')}]]\n    completed = []\n    while queue:\n        path = queue.pop(0)\n        last = path[-1]\n        parents = reverse_adj.get((last['instance'], last['field']), [])\n        if not parents:\n            completed.append(path)\n            continue\n        for from_inst, from_field in parents:\n            nclass = node_lookup.get(from_inst, 'TRANSFORMATION')\n            new_path = path + [{'instance': from_inst, 'field': from_field, 'node_class': nclass}]\n            if nclass == 'SOURCE': completed.append(new_path)\n            else: queue.append(new_path)\n    return completed", "file_refs": ["rag-system/src/rag_system/ingestion/lineage_parser.py", "rag-system/weekly/W02_2026-08-12.md"], "upcoming_weeks": [3], "upcoming_context": ["W3: node_class=LINEAGE filter on /retrieve endpoint", "W3: golden dataset entries for lineage queries"], "follow_ups": ["How to handle a field through 10+ transformations?", "What happens when a field appears in two branches of a Joiner?", "How does cross-mapping lineage differ?"]},
    {"id": "q23", "topic": "Architecture", "question": "How do LINEAGE chunks differ from TRANSFORMATION chunks in the RAG, and when would you retrieve one versus the other?", "answer": "A TRANSFORMATION chunk describes a single node in isolation: its ports, SQL override, filter condition. It answers 'what does this transformation do?'. A LINEAGE chunk describes a complete field path across multiple nodes: TARGET.field to Expression.field to Source Qualifier.field to SOURCE.field. It answers 'where does this target field come from?'. An engineer asking 'what is the SQL logic in SQ_SQL_Override_InteractionEvent?' should get a TRANSFORMATION chunk. An engineer asking 'what source table provides InteractionEvent_Id to the DM facts target?' should get a LINEAGE chunk. The /retrieve endpoint supports a node_class filter for precisely this distinction.", "file_refs": ["rag-system/src/rag_system/chunking/chunker.py", "rag-system/src/rag_system/api/app.py"], "upcoming_weeks": [3], "upcoming_context": ["W3: citation output will distinguish LINEAGE vs TRANSFORMATION in LLM responses"], "follow_ups": ["How to build a full STTM document from lineage chunks?", "What metadata to add for column-impact analysis?", "How to test lineage retrieval quality against hand-verified mappings?"]},
    {"id": "q24", "topic": "Retrieval", "question": "Why did you add BM25 alongside vector search instead of using vector search alone?", "answer": "Vector search excels at semantic similarity but can miss exact technical identifiers. If an engineer asks 'what is wf_4202_fnd_rltinteractionagreement_ins2?' the embedding similarity for that exact workflow name may be diluted across many similar-sounding chunks. BM25 (PostgreSQL FTS with ts_rank) finds the document containing that exact string reliably. Reciprocal Rank Fusion combines both ranked lists: score = vector_weight * 1/(rrf_k + vector_rank) + bm25_weight * 1/(rrf_k + bm25_rank). With vector_weight=0.7 and bm25_weight=0.3 we get semantic recall plus keyword precision. The implementation uses a GENERATED tsvector column so PostgreSQL maintains the FTS index automatically on upsert.", "code": "-- pgvector schema addition\nALTER TABLE rag.rag_chunks\n  ADD COLUMN fts tsvector\n  GENERATED ALWAYS AS (to_tsvector('english', coalesce(text,''))) STORED;\nCREATE INDEX rag_rag_chunks_fts_idx ON rag.rag_chunks USING GIN (fts);", "file_refs": ["rag-system/src/rag_system/store/vector_store.py"], "upcoming_weeks": [3], "upcoming_context": ["W3: RAGAS hit rate comparison: hybrid vs vector-only"], "follow_ups": ["How to tune rrf_k?", "Does BM25 hurt when text is highly tokenised (port names etc.)?", "Should stop words be removed from technical identifiers?"]},
    {"id": "q25", "topic": "Retrieval", "question": "Walk me through how Reciprocal Rank Fusion works and why rrf_k=60 is the canonical default.", "answer": "RRF merges N ranked lists without knowing their score distributions. Each list assigns a score 1/(rrf_k + rank) where rank is 1-based. For a document appearing at rank 1 in both the vector list and the BM25 list with rrf_k=60: score = 1/61 + 1/61 ≈ 0.033. For a document at rank 10 in both: 1/70 + 1/70 ≈ 0.029. The rrf_k controls how much weight early ranks get relative to later ones. rrf_k=60 was empirically chosen in the original 2009 RRF paper (Cormack et al.) because it smoothly discounts rank without being too aggressive. Smaller rrf_k amplifies the top-1 advantage; larger rrf_k makes all ranks more equal. In my implementation I expose rrf_k as a parameter defaulting to 60 so it can be tuned during RAGAS evaluation.", "file_refs": ["rag-system/src/rag_system/store/vector_store.py", "rag-system/src/rag_system/knowledge_base.py"], "upcoming_weeks": [3], "upcoming_context": ["W3: RAGAS eval will compare rrf_k=60 vs 20 vs 100"], "follow_ups": ["When would you use score normalisation instead of RRF?", "How to extend RRF to 3+ retrieval signals (BM25, vector, metadata)?"]},
    {"id": "q26", "topic": "Architecture", "question": "You built a cross-encoder reranker behind a flag. When would you turn it on in production and what are the latency implications?", "answer": "The cross-encoder (ms-marco-MiniLM-L-6-v2) takes a (query, passage) pair and outputs a relevance score directly rather than computing independent embeddings. This is ~10x more accurate than bi-encoder cosine similarity for passage ranking but ~100x slower because it processes all k*3 pairs in a single model forward pass. In my implementation rerank=true retrieves 3k candidates, scores each pair, and returns the top k. The tradeoff: for a latency-insensitive workflow like generating a migration doc or STTM table, enable it. For sub-second interactive search, disable it. The cross-encoder also loads lazily (first call takes 46s on my machine to warm from HuggingFace cache) so in production it should be pre-warmed at startup using AUTO_CONNECT.", "file_refs": ["rag-system/src/rag_system/reranking/cross_encoder.py", "rag-system/src/rag_system/api/app.py"], "upcoming_weeks": [3], "upcoming_context": ["W3: RAGAS MRR comparison: without reranker vs with reranker"], "follow_ups": ["How to batch cross-encoder inference across concurrent requests?", "Could distilled cross-encoders like TinyBERT-reranker reduce latency?"]},
    {"id": "q27", "topic": "Architecture", "question": "Explain your refusal policy design: why threshold on cosine similarity and not on RRF score?", "answer": "RRF scores are always in a narrow band (~0.008-0.016 for top hits) regardless of domain relevance because the formula normalises by rank, not by actual similarity. 'Capital of France' and 'SQL override RLTInteraction' can both return a top RRF score of 0.011 because both have a top-ranked hit in the vector index — even if that hit is weakly related to the query. Cosine similarity (vector_score) is a true semantic distance: in-domain queries against bge-small-en-v1.5 score 0.75-0.80, while unrelated queries score 0.50-0.55. A threshold of 0.60 cleanly separates them. The /answer endpoint checks vector_score from the hybrid hit, with REFUSAL_SCORE_THRESHOLD configurable via .env for different corpora.", "file_refs": ["rag-system/src/rag_system/api/app.py"], "upcoming_weeks": [3], "upcoming_context": ["W3: threshold calibration from golden dataset with precision/recall curve"], "follow_ups": ["How to auto-calibrate the refusal threshold from a labelled eval set?", "What if the corpus is expanded to include non-Informatica documents?"]},
    {"id": "q28", "topic": "Architecture", "question": "What is prompt versioning and why does it matter for production LLM systems?", "answer": "Prompt versioning treats prompts as configuration artefacts: each template has a name and semver version stored in prompts/prompts.yml alongside the codebase. Every /answer response includes prompt_version in its payload. This gives three production guarantees: (1) Reproducibility — given a query and a prompt_version you can reproduce the exact LLM input. (2) Regression detection — a RAGAS evaluation run records which prompt version was active; a version bump triggers a fresh eval run automatically. (3) Audit trail — for compliance-sensitive systems (insurance, finance) you can prove that the AI response was generated from a specific approved template. In my implementation prompts are rendered with a simple {{ var }} substitution and loaded with lru_cache so the YAML is read once per server lifetime.", "file_refs": ["rag-system/src/rag_system/prompts/__init__.py", "rag-system/prompts/prompts.yml"], "upcoming_weeks": [3, 4], "upcoming_context": ["W3: RAGAS eval records prompt_version per run", "W4: CI gate checks for prompt version bump on template change"], "follow_ups": ["How would you implement A/B testing between prompt versions?", "Should prompt version be tied to model version or independent?"]},
    {"id": "q29", "topic": "Testing", "question": "The /answer endpoint has five failure modes. How would you test each one?", "answer": "(1) KB not built: unit test that /answer returns 503 when _kb is None. (2) Refusal: parameterised test with 10 out-of-domain queries, assert refused=True for all. (3) Citation format: for each evidence chunk in the response, assert the [chunk_id] appears in the prompt body. (4) Prompt template missing: mock get_prompt() to raise KeyError, assert response falls back to inline template with prompt_version='fallback'. (5) Partial retrieval (fewer than k chunks): assert evidence.Count == len(actual_hits) and refused=False if top vector_score >= threshold. All five are deterministic with a frozen test KB using InMemoryVectorStore and HashingEmbedding, keeping tests offline and sub-3-second.", "file_refs": ["rag-system/tests/test_smoke.py"], "upcoming_weeks": [3], "upcoming_context": ["W3: add these 5 /answer tests to test_smoke.py"], "follow_ups": ["How to test the reranker path without loading the model?", "How to golden-test the full prompt output end-to-end?"]},
    {"id": "q30", "topic": "Embeddings", "question": "Your embedding model takes 46 seconds to load from the HuggingFace cache. How would you fix this in production?", "answer": "Three strategies: (1) Pre-warm at startup — set AUTO_CONNECT=true in .env so the model loads during lifespan startup, not lazily on the first /answer request. The user never sees the 46s delay. (2) Model server — deploy sentence-transformers as a separate service (e.g. triton-inference-server or a simple FastAPI sidecar) so it stays loaded permanently and requests call it over HTTP. (3) ONNX export — convert bge-small-en-v1.5 to ONNX with optimum and serve with onnxruntime, which loads in ~2s instead of 46s because it skips the full PyTorch init. The 46s on my machine is partly an OneDrive sync overhead on Windows; on Linux with a local filesystem it's ~8s. For the portfolio project I've accepted the startup latency since it's a dev machine with OneDrive.", "file_refs": ["rag-system/src/rag_system/embeddings/provider.py", "rag-system/.env"], "upcoming_weeks": [2, 3], "upcoming_context": ["W2-W3: keep AUTO_CONNECT=true; W5: ONNX or model server when adding offline Ollama"], "follow_ups": ["How to measure embedding throughput at batch sizes 8, 64, 256?", "When would you switch from bge-small to bge-large-en-v1.5?"]},
    {"id": "q31", "topic": "Architecture", "question": "Your hybrid search returns a vector_score and a bm25_rank alongside the fused score. How do you use those in downstream components?", "answer": "The vector_score and bm25_rank fields flow through to /answer where the refusal policy uses vector_score as the relevance signal (RRF scores are normalised by rank and not reliable for threshold comparisons). In the citation evidence block, the score displayed is the fused RRF score so the LLM sees a consistent value regardless of retrieval mode. When rerank=true, the cross-encoder replaces score with rerank_score and demotes the original score to retrieval_score — this lets observability tooling track both retrieval and reranking quality independently. In the planned W3 RAGAS evaluation I'll log all three per-hit (vector_score, bm25_rank, rerank_score if present) to compute separate ablation metrics.", "file_refs": ["rag-system/src/rag_system/store/vector_store.py", "rag-system/src/rag_system/api/app.py"], "upcoming_weeks": [3], "upcoming_context": ["W3: RAGAS ablation: vector-only vs BM25-only vs hybrid vs hybrid+rerank"], "follow_ups": ["How to surface per-hit retrieval mode in a frontend citation UI?", "Should bm25_rank be stored in pgvector for analytics?"]},
    {"id": "q32", "topic": "Architecture", "question": "How would you extend the prompts/prompts.yml system to support multi-turn conversation memory?", "answer": "Add a third template variable {{ history }} alongside {{ query }} and {{ evidence_blocks }}. The history block is the last N turns (user + assistant) formatted as a string. The prompt loader already supports arbitrary {{ var }} substitution via render_prompt(**kwargs) so no code change is needed. The /answer endpoint would accept an optional history: list[{role, content}] body parameter (switching from GET to POST), format it as 'User: ...\nAssistant: ...' strings, and pass as history= to render_prompt. Prompt versioning still applies: when the multi-turn template changes, bump the version (e.g. 1.0.0 → 1.1.0 for backward-compatible history addition, 2.0.0 for incompatible restructure). This enables the RAGAS evaluator to test single-turn and multi-turn templates independently.", "file_refs": ["rag-system/src/rag_system/prompts/__init__.py", "rag-system/prompts/prompts.yml"], "upcoming_weeks": [4], "upcoming_context": ["W4: POST /answer with history for multi-turn demo"], "follow_ups": ["How to implement context window budgeting when history + evidence exceed max tokens?", "Should conversation history be chunked and retrieved too?"]},
    {"id": "q33", "topic": "Vector Store", "question": "How did you prove the RAG index was fully reindexed at 768 dimensions, not just partially updated?", "answer": "I validated four independent signals. (1) Schema: embedding column type in rag.rag_chunks was vector(768). (2) Volume: row count was 4033. (3) Coverage: distinct source_file count in DB was 25, matching 25 PowerCenter XML files detected in INFA_XML_FOLDER. (4) Set parity: DB source_file names vs filesystem basenames had zero missing and zero extra. I also verified ivfflat and GIN indexes were present. Using all four signals together avoids false confidence from any single metric.", "file_refs": ["rag-system/src/rag_system/store/vector_store.py", "rag-system/weekly/W04_2026-08-14.md"], "upcoming_weeks": [5], "upcoming_context": ["W5: automate a one-command index audit script"], "follow_ups": ["Why is row count alone insufficient?", "How would you detect stale rows after XML deletions?", "Would you run this audit in CI?"]},
    {"id": "q34", "topic": "Debugging", "question": "What did you do when the managed Postgres tooling path was unavailable during a production-style validation?", "answer": "I switched to a direct evidence path using docker exec + psql against the running pgvector container. The key was preserving the same checks I would run through the managed tool: table existence, embedding dimension, row counts, index list, and source-file parity checks. This kept the validation objective identical while changing only the transport. The lesson is to keep a fallback operational path for critical checks.", "file_refs": ["rag-system/weekly/W04_2026-08-14.md", "apps/genai-portfolio-tracker-react/weekly/W04_2026-08-14.md"], "upcoming_weeks": [5], "upcoming_context": ["W5: add fallback runbook entries for validation tooling outages"], "follow_ups": ["How do you prevent command drift between primary and fallback checks?", "What evidence would you attach to a release note?"]},
    {"id": "q35", "topic": "Debugging", "question": "You hit a shell compatibility issue in validation scripts. How did you recover without losing confidence in results?", "answer": "A first-pass PowerShell command used the null-coalescing operator ??, which is unsupported in PowerShell 5.1. I replaced it with explicit null-safe checks, reran the full comparison, and confirmed parity results. I then documented the constraint so future checks start from a compatible command set. The recovery was quick because the validation logic stayed the same; only syntax changed.", "file_refs": ["rag-system/weekly/W04_2026-08-14.md"], "upcoming_weeks": [5], "upcoming_context": ["W5: package a PowerShell-5.1-safe audit script"], "follow_ups": ["How would you make the script version-aware automatically?", "Would Python be safer than shell here?"]},
    {"id": "q36", "topic": "API Design", "question": "How does the portfolio tracker avoid losing user data when seeded content changes?", "answer": "The app merges backend/local saved state with INITIAL_DATA. It keeps user completion and notes, while syncing newly seeded qbank items, interview sessions, and canonical STAR story updates. Persist writes go to localStorage and backend, with backend state loaded on mount and migration-aware re-sync when merge introduces new seed content. That model gives backward compatibility plus evolving seed data.", "file_refs": ["apps/genai-portfolio-tracker-react/src/App.jsx", "apps/genai-portfolio-tracker-react/src/data.js"], "upcoming_weeks": [5], "upcoming_context": ["W5: add contract tests for merge behavior across seed versions"], "follow_ups": ["How do you handle schema-breaking changes?", "What fields are user-owned vs seed-owned?"]},
    {"id": "q37", "topic": "Governance", "question": "How do journal entries, STAR stories, and question bank updates help interview readiness governance over time?", "answer": "They create three linked feedback loops. Daily journal tracks execution signal and blockers. STAR stories convert meaningful events into structured narratives with measurable outcomes and learning. Qbank turns those events into repeatable interview drills with follow-ups and readiness ratings. Together they make progress auditable, not anecdotal, and let you target weak topics before interviews.", "file_refs": ["apps/genai-portfolio-tracker-react/src/components/Journal.jsx", "apps/genai-portfolio-tracker-react/src/components/Interview.jsx", "apps/genai-portfolio-tracker-react/src/data.js"], "upcoming_weeks": [5, 6], "upcoming_context": ["W5-W6: raise proportion of STAR-ready stories and 'ready' quiz ratings"], "follow_ups": ["What leading indicators predict interview performance best?", "How often should Qbank be pruned?"]},
    {"id": "q38", "topic": "Delivery", "question": "What does a good end-of-session closeout include for engineering workstreams?", "answer": "A high-quality closeout includes: objective of the session, concrete delivered changes, validation evidence (not just claims), unresolved risks, and next actions. In this workflow it also includes backfilling missed daily notes so weekly continuity stays intact. That standard makes restart cost low for the next session and reduces context loss.", "file_refs": ["apps/genai-portfolio-tracker-react/weekly/W03_2026-08-13.md", "apps/genai-portfolio-tracker-react/weekly/W04_2026-08-14.md"], "upcoming_weeks": [5], "upcoming_context": ["W5: add a reusable closeout checklist template"], "follow_ups": ["How do you verify closeout completeness objectively?", "What should never be left out?"]},
    {"id": "q39", "topic": "Evaluation", "question": "What did Week 3 answer-level evaluation prove, and what remained weak?", "answer": "Week 3 proved the evaluation pipeline can run end-to-end repeatably and produce report artifacts without manual patching. We completed the 12-query answer dataset run and produced eval/ragas_report_latest.json. Baseline outcome: faithfulness=0.4000 and answer_relevancy=0.0000. That means run reliability risk is reduced, but answer quality still needs targeted tuning in Week 4.", "file_refs": ["rag-system/eval/ragas_report_latest.json", "rag-system/weekly/W03_2026-08-13.md", "apps/genai-portfolio-tracker-react/weekly/W06_2026-08-17.md"], "upcoming_weeks": [4], "upcoming_context": ["W4: improve answer_relevancy through retrieval quality and prompt refinement"], "follow_ups": ["What would you change first to move answer_relevancy above 0.20?", "How do you isolate retrieval defects from generation defects?"]},
    {"id": "q40", "topic": "Debugging", "question": "How did you close the Week 3 runtime mismatch that blocked consistent RAGAS execution?", "answer": "I normalized runtime configuration loading and aligned the answer and eval execution paths so both used the same parameter contract. Then I reran with a clean blocking connect flow before evaluation to remove lifecycle race conditions. That shifted us from partial/fragile runs to a completed 12-query output with stable artifact generation.", "file_refs": ["rag-system/src/rag_system/eval/ragas_eval.py", "rag-system/src/rag_system/api/app.py", "apps/genai-portfolio-tracker-react/src/data.js"], "upcoming_weeks": [4], "upcoming_context": ["W4: keep preflight checks before every eval run"], "follow_ups": ["What preflight checks are mandatory before running answer-level eval?", "How do you detect config drift automatically in CI?"]},
    {"id": "q41", "topic": "Governance", "question": "How should Week 3 metrics be used in interview-safe quality governance?", "answer": "Use Week 3 as the baseline checkpoint, not as a victory metric. The governance action is to lock the baseline artifact, record prompt/model/runtime context, and require every Week 4 change to report delta against faithfulness=0.4000 and answer_relevancy=0.0000. That converts discussion from subjective quality opinions to measurable movement.", "file_refs": ["rag-system/eval/ragas_report_latest.json", "rag-system/SYSTEM_E2E_FLOW.md", "apps/genai-portfolio-tracker-react/src/data.js"], "upcoming_weeks": [4, 5], "upcoming_context": ["W4: delta tracking per prompt/retrieval experiment", "W5: add CI gate candidates once metric stability improves"], "follow_ups": ["When is a metric stable enough to gate PR merges?", "How do you avoid overfitting to a small eval set?"]},
    {"id": "q42", "topic": "Architecture", "question": "Why did graph-mode answers fail after refactor even though retrieval logic looked correct?", "answer": "The issue was state-schema loss, not retrieval quality. LangGraph StateGraph with TypedDict only carries declared keys between nodes. Planner callback returned retrieval fields (hits, plan, resolved_mode), but those keys were missing from AnswerGraphState, so executor received empty evidence and validator forced retries/refusals. Fix: declare all handoff fields in AnswerGraphState and re-run parity checks against legacy mode.", "file_refs": ["rag-system/src/rag_system/graph/answer_graph.py", "rag-system/src/rag_system/api/app.py", "rag-system/eval/graph_vs_legacy_answer_regression.json"], "upcoming_weeks": [4], "upcoming_context": ["W4: keep graph/legacy parity regression in release checklist", "W4: tighten state-contract tests for orchestration nodes"], "follow_ups": ["How would you unit-test for undeclared-state key loss?", "When should you choose dataclass state over TypedDict?"]},
    {"id": "q43", "topic": "Architecture", "question": "What did you change to make your RAG feel like a real conversational chatbot instead of a single-turn answer API?", "answer": "I added four layers together: (1) session state with transcript continuity, (2) compressed memory summary plus manual controls, (3) capability-aware context routing for natural prompts like 'what can it do' and 'what XMLs are indexed', and (4) output readability upgrades via markdown-rendered assistant bubbles with starter prompts. The important point is these were shipped as one integrated flow, not disconnected features, so onboarding, follow-up quality, and persistence improved together.", "file_refs": ["rag-system/src/rag_system/api/app.py", "rag-system/src/rag_system/api/static/chat_ui.html", "rag-system/tests/test_smoke.py"], "upcoming_weeks": [4, 5], "upcoming_context": ["W4: citation cards and richer evidence UI", "W5: paginated session lifecycle APIs"], "follow_ups": ["How do you measure conversational quality beyond single-turn RAGAS?", "What is your fallback when capability intent is ambiguous?"]},
    {"id": "q44", "topic": "API Design", "question": "How did you implement persistent chat sessions without introducing heavy infrastructure?", "answer": "I used SQLite as a pragmatic persistence layer for sessions, messages, and summary memory. The API writes through on session create/message append/summary update, and lazily reloads from storage when a session is not present in memory. That gives restart-safe conversational continuity with minimal operational overhead, while preserving a clear migration path to Redis/Postgres if multi-instance scaling is required.", "file_refs": ["rag-system/src/rag_system/api/app.py", "rag-system/tests/test_smoke.py"], "upcoming_weeks": [5], "upcoming_context": ["W5: session list/archive/delete endpoints with pagination"], "follow_ups": ["How would you migrate existing SQLite sessions to Postgres?", "What retention policy would you apply to old chat sessions?"]},
    {"id": "q45", "topic": "Operations", "question": "What exactly did Week +1 observability add to API responses, and why is that useful in production debugging?", "answer": "Week +1 added an additive diagnostics contract: a trace envelope (`request_id`, `endpoint`, `timestamp_utc` + context fields) and telemetry payload (`timing_ms`, `events`, `usage`) on key API routes. This lets us correlate a failing answer or latency spike to a precise request path and stage-level timings without parsing logs first. The design intentionally avoids behavior coupling: telemetry explains execution, but does not influence semantic routing or refusal logic.", "file_refs": ["rag-system/src/rag_system/api/app.py", "rag-system/tests/test_smoke.py", "rag-system/SYSTEM_E2E_FLOW.md"], "upcoming_weeks": [5], "upcoming_context": ["W5: introduce p50/p95/p99 rollups and alert thresholds from response telemetry"], "follow_ups": ["Which timing fields matter most for lineage vs generic queries?", "How would you correlate trace IDs with server logs and APM spans?", "What should happen if telemetry collection partially fails?"]},
    {"id": "q46", "topic": "Governance", "question": "How did you ensure observability changes did not weaken semantic-first correctness guarantees?", "answer": "I enforced an observability contract rule: telemetry is additive only. For semantic-first intents, routing and refusal behavior remains driven by deterministic semantic evidence and status codes, independent of telemetry values. I validated this by adding trace/telemetry assertions in smoke tests for semantic and retrieval routes, while keeping the existing semantic-primary behavior checks unchanged. That separation ensures we gain diagnostics without introducing hidden control flow risk.", "file_refs": ["rag-system/src/rag_system/api/app.py", "rag-system/tests/test_smoke.py", "rag-system/CHANGELOG.md"], "upcoming_weeks": [5], "upcoming_context": ["W5: add incident runbook entries that map refusal reasons to observability indicators"], "follow_ups": ["Where should we enforce this contract in code review checklists?", "How do you detect accidental telemetry-to-control coupling?", "What test would catch a future violation quickly?"]}
  ],
  "sessions": [
    {
      "date": "2026-08-27",
      "title": "S11 — Week +1 Observability Delivery + Documentation Consolidation",
      "summary": "Implemented Week +1 observability in rag-system responses by adding trace metadata, stage timing telemetry, structured event summaries, and usage placeholders across retrieve/answer/semantic routes. Updated smoke tests, API testing checklist, changelog, and E2E LLD to reflect implemented status.",
      "star_story": "S: Observability was planned, but we needed real diagnostics now without risking semantic-first correctness. T: Deliver production-useful request tracing and timing telemetry while preserving authority boundaries for lineage/impact truth. A: I instrumented response-level trace and telemetry contracts in API routes, propagated timing across retrieval/semantic branches, added focused smoke assertions, and aligned architecture/testing docs to implementation. R: Week +1 moved from plan to shipping behavior with targeted tests passing, and deterministic semantic guardrails remained unchanged."
    },
    {
      "date": "2026-08-19",
      "title": "W4 Day 2 — Conversational Chatbot Hardening",
      "summary": "Shipped conversational RAG upgrades end-to-end: capability-aware context routing, markdown answer rendering, starter prompt guidance, memory controls, and SQLite-backed persistent sessions. Added tests for natural capability phrasing and persistence reload behavior.",
      "star_story": "S: Users could retrieve answers but struggled to start naturally and did not trust the bot's awareness of indexed context. T: Deliver a conversational experience that can explain capabilities, retain memory, and survive restarts without new infra complexity. A: I added context-agent routing for natural capability prompts, upgraded UI rendering to markdown with starter chips, and persisted sessions/messages/summaries in SQLite with lazy reload semantics. R: The chatbot now supports conversational onboarding and durable continuity, with expanded chat/context smoke coverage passing after rollout."
    },
    {
      "date": "2026-08-11",
      "title": "W1 Complete — RAG System Foundation",
      "summary": "Built the full RAG system from scratch in one session. Set up rag-system/ package with FastAPI, pgvector (port 5433), object-boundary chunking (700 tok / 100 overlap), SentenceTransformer bge-small-en-v1.5 embeddings (dim=384), IVFFlat cosine index. Pivoted from Azure embeddings (no deployment) to local sentence-transformers after scores hit 0.09. Ingested 7 Informatica PowerCenter XML files → 703 unique chunks. 14/14 smoke tests + 16 integration tests passing.",
      "star_story": "S: Azure had no embedding deployment and fallback vectors scored ~0.09 on relevant queries. T: Restore semantic retrieval in the same session without blocking W1 delivery. A: I switched to local bge-small-en-v1.5, migrated pgvector from 256 to 384 dimensions, re-ingested all chunks, and kept provider fallback ordering for future Azure recovery. R: Scores improved to ~0.74-0.80, 703 chunks re-indexed, and W1 shipped with 30/30 tests; I learned to make providers swappable before infra fails."
    },
    {
      "date": "2026-08-12",
      "title": "W2 Day 1 — Field-Level Lineage Parser",
      "summary": "Discovered 13,237 CONNECTOR elements across 7 XMLs were silently dropped by W1 parser. Built lineage_parser.py: BFS backward resolver that traces every TARGET field through the CONNECTOR graph to its SOURCE. Produces LINEAGE chunks with TARGET:, SOURCE:, HOP_COUNT:, PATH: labels. Added chunk_lineage_chains() to chunker, wired into build_from_folder(). 6 new smoke tests (all passing). Total: 20/20. Weekly doc W02 with Mermaid diagrams written.",
      "star_story": "S: The corpus had 13,237 CONNECTOR edges, but lineage retrieval returned nothing. T: Add field-level lineage without breaking existing W1 chunks. A: I traced the silent drop in flatten_mapping_to_nodes(), added BFS backward lineage resolution, emitted LINEAGE chunks with path metadata, and introduced six lineage smoke tests. R: All 13,237 edges are now processed and lineage answers return full paths with 20/20 tests green; I learned silent-drop counters should exist from day one."
    },
    {
      "date": "2026-08-13",
      "title": "W2 Complete — BM25 + Hybrid + Citations + Refusal + Prompt Versioning",
      "summary": "Completed all 5 W2 tasks in a single session. Added PostgreSQL FTS (tsvector GENERATED + GIN index) and Reciprocal Rank Fusion hybrid retrieval. Wired cross-encoder reranker (ms-marco-MiniLM-L-6-v2) behind rerank=true flag. Built /answer endpoint with citation-backed evidence blocks, versioned prompt templates (prompts/prompts.yml), and a refusal policy that checks cosine vector_score >= 0.60 against the bge-small-en-v1.5 threshold. Fixed FastAPI regex→pattern deprecation. 20/20 smoke tests pass. Added 9 new interview questions q24-q32 covering RRF, refusal calibration, prompt versioning, and reranker latency trade-offs.",
      "star_story": "S: Retrieval worked, but exact identifier recall, citation traceability, and refusal safety were missing. T: Ship BM25 + hybrid retrieval + citation-backed /answer in one W2 session. A: I added PostgreSQL FTS, RRF fusion, prompt versioning, and switched refusal thresholding to cosine vector_score after RRF score proved non-discriminative. R: Five W2 tasks shipped with 20/20 smoke tests, out-of-domain queries now refuse correctly, and every answer carries evidence plus prompt_version; I learned safety thresholds must use true similarity signals."
    },
    {
      "date": "2026-08-14",
      "title": "W2 Day 3 — 768-Dim Index Validation + Portfolio Closeout",
      "summary": "Validated index integrity for the active corpus under 768-dim embeddings: rag.rag_chunks at vector(768), 4033 rows, and exact source-file parity (25 DB files vs 25 corpus XML basenames, zero missing/extra). Confirmed ivfflat + GIN indexes were present. Then backfilled portfolio tracker weekly continuity and added new journal/STAR/question-bank seed content.",
      "star_story": "S: We needed a definitive answer on whether reindexing was complete before moving ahead, but the managed DB tool path was unavailable. T: Prove or disprove index completeness with defensible evidence, not assumptions. A: I switched to direct docker/psql checks, verified schema, counts, and indexes, then ran set-diff coverage checks between DB source_file values and filesystem XML basenames. After a PowerShell 5.1 syntax mismatch, I rewrote commands to compatible null-safe syntax and reran all checks. R: Validation showed vector(768), 4033 rows, and full 25/25 file parity with no gaps, so we avoided unnecessary reindex and closed the session with confidence."
    },
    {
      "date": "2026-08-17",
      "title": "W3 Complete — Answer-Level RAGAS Execution",
      "summary": "Completed Week 3 evaluation closure by running RAGAS end-to-end on the 12-query answer dataset and generating eval/ragas_report_latest.json. Standardized runtime config loading and aligned answer/eval execution paths to make runs repeatable. Final baseline: query_count=12, faithfulness=0.4000, answer_relevancy=0.0000.",
      "star_story": "S: Week 3 required a real answer-level score run, but the execution path was inconsistent and not reliably repeatable. T: Deliver a successful, evidence-backed RAGAS run in-session with tracker-ready artifacts. A: I standardized runtime configuration loading, aligned answer-generation and eval parameter handling, and reran evaluation after a clean blocking connect flow. R: We moved from partial runs to a completed 12-query report with measurable output, giving Week 4 a clear quality-optimization baseline."
    },
    {
      "date": "2026-08-18",
      "title": "W3 Day 4 — LLD Viewer in Tracker",
      "summary": "Implemented project-level LLD retrieval and rendering in the portfolio tracker. Added backend endpoint and workspace-safe file mapping, connected Projects UI to fetch markdown LLD per project, and added full-screen reading support. Also stabilized local workflow by ensuring dockerized tracker/backend rebuild path and a dedicated node utility service for npm operations.",
      "star_story": "S: We needed LLD visibility for every project inside the tracker, but docs were external and delivery was at risk due to container drift plus package-install constraints. T: Ship a production-style LLD viewer quickly without regressing existing tracker behavior. A: I added a per-project LLD backend API, wired markdown rendering with a resilient frontend fallback, and implemented a full-screen reader with reload controls. I rebuilt containers and revalidated endpoint/UI behavior until responses and rendering were consistent. R: All five projects now expose readable LLD directly in the app, improving interview storytelling readiness and reducing context-switching overhead during reviews."
    },
    {
      "date": "2026-08-18",
      "title": "W4 Day 1 — Graph Simplification + RAGAS Graph Run",
      "summary": "Completed contract simplification by removing smart/friendly retrieval controls across API and eval paths, fixed LangGraph state handoff field loss, updated architecture docs, and generated graph-vs-legacy parity evidence (22 accepted each on candidate set). Ran answer-level RAGAS in graph mode on current golden set (22 queries).",
      "star_story": "S: Graph mode started refusing broadly after API contract cleanup, risking rollback. T: Preserve simplification, restore graph correctness, and prove parity with measurable evidence. A: I traced payload divergence, added missing state keys to AnswerGraphState, tuned source-hint fan-out, reran parity and tests, then executed graph-mode RAGAS. R: Graph parity was restored and regression suites passed; latest run produced faithfulness 0.2857 with answer_relevancy 0.0000, clarifying that next work is quality tuning rather than orchestration stability."
    }
  ],
  "quiz_history": {}
}
}