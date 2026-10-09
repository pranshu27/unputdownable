## Source Video
- 5 AI Engineer Projects to Build in 2026 | Ex-Google, Microsoft
- https://www.youtube.com/watch?v=9WIsvEswZTk

## Extracted Project Ideas
These are the five project ideas explicitly summarized in the video transcript:

1. Production RAG system with proper evaluation and CI gating.
2. Local model benchmarking application (offline AI assistant with small models).
3. Monitoring and observability layer for the RAG system.
4. Fine-tuning project with measurable before and after improvements.
5. Realtime multimodal application with latency analysis and resilience testing.

## End-to-End Project Plans

### Project 1: Production RAG System With Evaluation and CI Gating

Goal:
Build a domain-specific Q and A assistant that answers with citations and fails quality checks in CI if answer quality regresses.

Use case:
Internal knowledge assistant for policy docs, runbooks, architecture docs, or legal text.

End-to-end scope:
- Data ingestion pipeline for PDF, DOCX, Markdown, and HTML.
- Document chunking strategy with metadata (source, section, date).
- Embedding + vector index + metadata filtering.
- Retrieval plus reranking pipeline.
- LLM answer generation with source-grounded citations.
- Offline evaluation set with golden questions.
- CI gate that blocks merges if metrics drop below threshold.

Suggested stack:
- App: Python + FastAPI
- RAG orchestration: LangChain or LlamaIndex
- Embeddings: OpenAI text-embedding-3-large or bge-large
- Vector DB: pgvector, Qdrant, or Weaviate
- Reranker: cross-encoder/ms-marco or Cohere rerank
- Eval: RAGAS + custom pass/fail checks
- CI: GitHub Actions

Architecture flow:
Ingest docs -> clean/chunk -> embed -> index -> retrieve -> rerank -> generate with citations -> evaluate -> CI gate -> deploy.

Milestones:
- Week 1: Ingestion, chunking, index creation, baseline retrieval API.
- Week 2: Add reranking, citation formatting, and prompt hardening.
- Week 3: Build evaluation dataset and automated RAGAS checks.
- Week 4: Add CI gating, dashboards, production deployment, and README demo.

Success metrics:
- Retrieval hit rate at k >= 0.85
- Citation correctness >= 0.9
- Hallucination rate <= 0.08
- P95 response latency <= 2.5s

Portfolio deliverables:
- System architecture diagram
- Public API and sample notebook
- Eval report with baseline vs improved metrics
- CI workflow file showing quality gate

---

### Project 2: Local AI Assistant and Model Benchmarking

Goal:
Build an offline assistant and benchmark at least 3 small models for quality, latency, memory, and throughput across CPU/GPU setups.

Use case:
Privacy-sensitive environments, low-connectivity edge deployments, and cost-sensitive workloads.

End-to-end scope:
- Local inference pipeline with Ollama or llama.cpp.
- Prompt templates for 3 task types (Q and A, summarization, extraction).
- Quantized model runs (for example Q4 and Q5).
- Benchmark harness capturing latency, token throughput, memory, and quality scores.
- Recommendation engine selecting best model per task profile.

Suggested stack:
- Inference: Ollama or llama.cpp
- Models: Llama 3.1 8B Instruct, Mistral 7B Instruct, Phi-4 mini (or similar)
- Benchmark runner: Python + pytest-benchmark
- Eval: BLEU/ROUGE/BERTScore plus task-specific rubric
- UI: Streamlit or Gradio

Architecture flow:
Task input -> local model inference -> response capture -> evaluator -> benchmark DB -> comparison dashboard.

Milestones:
- Week 1: Setup local runtime + baseline prompts for 3 models.
- Week 2: Build benchmark runner with reproducible test suite.
- Week 3: Add quantization experiments and tradeoff analysis.
- Week 4: Build dashboard and publish model selection playbook.

Success metrics:
- 100 percent offline execution
- Benchmark reproducibility across 3 runs
- Clear quality/latency frontier chart
- Recommended model policy by use case

Portfolio deliverables:
- Benchmark report with charts
- Experiment config files
- Repeatable scripts for machine setup and reruns

---

### Project 3: Monitoring and Observability Layer for AI Systems

Goal:
Extend Project 1 with production-grade observability for prompt, retrieval, generation, and user feedback loops.

Use case:
Detect quality regressions, monitor failure modes, and speed up incident triage.

End-to-end scope:
- Structured logging at each stage (ingest, retrieve, rerank, generate).
- Trace IDs across request lifecycle.
- Online eval probes for factuality and toxicity.
- Feedback capture (thumbs up/down + annotation tags).
- Alerting for latency spikes, failure rates, and drift.
- Daily or hourly quality rollups.

Suggested stack:
- Observability: Langfuse, OpenTelemetry, or Phoenix/Arize
- Metrics: Prometheus + Grafana
- Logs: ELK or Loki
- Alerts: Grafana Alerting or PagerDuty webhook

Architecture flow:
User request -> traced pipeline -> logs/metrics/traces -> online evaluators -> dashboards/alerts -> root-cause workflow.

Milestones:
- Week 1: Add trace context and structured event schema.
- Week 2: Build dashboards for latency, errors, hallucination proxy.
- Week 3: Implement alert thresholds and incident runbook.
- Week 4: Add feedback loop and quality trend analytics.

Success metrics:
- MTTD <= 5 minutes for major incidents
- MTTR <= 30 minutes for common failures
- 100 percent of requests traceable end to end
- Weekly quality trend reports generated automatically

Portfolio deliverables:
- Dashboard screenshots and schema docs
- Incident drill report (simulated outage)
- Observability README with alert logic

---

### Project 4: Fine-Tuning With Measurable Before/After Impact

Goal:
Fine-tune a small model on a narrowly defined task where prompt-only performance plateaus, and demonstrate measurable improvements.

Use case:
Domain extraction, classification, or strict structured generation (for example insurance claim field extraction).

End-to-end scope:
- Problem framing and failure analysis of prompt-only baseline.
- Dataset creation and labeling guidelines.
- Train/validation/test split and leakage checks.
- Parameter-efficient fine-tuning (LoRA/QLoRA).
- Safety and regression checks on out-of-domain prompts.
- Before and after comparison report.

Suggested stack:
- Training: Hugging Face Transformers + PEFT + TRL
- Infra: Single GPU or cloud notebook
- Tracking: Weights and Biases or MLflow
- Evaluation: exact match/F1/task-specific validators

Architecture flow:
Task definition -> baseline prompts -> error taxonomy -> curated dataset -> fine-tune -> eval + ablation -> deployment candidate.

Milestones:
- Week 1: Define task, baseline, and labeling rubric.
- Week 2: Build dataset and run first fine-tune.
- Week 3: Hyperparameter sweeps, eval, and robustness checks.
- Week 4: Publish before/after report and deploy model endpoint.

Success metrics:
- Primary task metric improvement >= 10 percent absolute
- Error class reduction in top 2 failure categories
- No major regression on generic prompts
- Inference latency within deployment budget

Portfolio deliverables:
- Data card and model card
- Reproducible training scripts
- Before/after metrics table and qualitative examples

---

### Project 5: Realtime Multimodal App With Latency and Resilience Analysis

Goal:
Build a realtime app that handles streaming inputs and outputs under tight latency constraints with graceful degradation during failures.

Use case options:
- Voice assistant: ASR -> LLM -> TTS
- Vision assistant: Webcam -> detector -> VLM/LLM response
- Meeting copilot: live transcript -> summarization/actions

End-to-end scope:
- Streaming transport and session manager.
- Multimodal pre-processing pipeline.
- Realtime inference with latency budget per stage.
- Resilience features (timeouts, retries, fallbacks, circuit breaker).
- Chaos tests (network jitter, dropped frames, model timeout).
- Latency and reliability scorecard.

Suggested stack:
- Backend: FastAPI WebSockets or gRPC streaming
- Realtime media: WebRTC or websocket audio/video frames
- Models: Whisper/Faster-Whisper, VLM, low-latency LLM endpoint
- Queueing: Redis streams or Kafka (optional)

Architecture flow:
Stream input -> preprocess -> infer -> postprocess -> stream response -> telemetry -> fallback on failure.

Milestones:
- Week 1: Build streaming skeleton and single-modal baseline.
- Week 2: Integrate second modality and session management.
- Week 3: Add latency instrumentation and budget enforcement.
- Week 4: Add resilience patterns and chaos testing report.

Success metrics:
- End-to-end P95 latency within target (for example <= 1200 ms)
- Session success rate >= 99 percent
- Graceful fallback for >= 95 percent injected failures
- No memory leak in 30-minute soak test

Portfolio deliverables:
- Latency breakdown by pipeline stage
- Resilience test matrix and outcomes
- Demo video with normal and failure-path behavior

## Recommended Execution Roadmap (14 Weeks)

1. Weeks 1 to 4: Project 1 (RAG foundation).
2. Weeks 5 to 6: Project 2 (local benchmarking).
3. Weeks 7 to 8: Project 3 (observability extension).
4. Weeks 9 to 11: Project 4 (fine-tuning).
5. Weeks 12 to 14: Project 5 (realtime multimodal).

## Hiring Narrative You Can Reuse
- I can build a production RAG system with measurable quality gates.
- I understand cost/privacy constraints and can run local models effectively.
- I instrument systems for reliability, not just demos.
- I can fine-tune models with evidence-based evaluation.
- I can build low-latency multimodal systems with resilience engineering.

## Detailed Transcript Capture (Step-by-Step)

This section captures the detailed implementation guidance from your longer transcript version, including specific phase sequencing, metrics, and engineering signals expected by hiring managers.

### Project 1 Detailed: Production-Grade RAG

Core objective:
Build a domain-specific Ask-My-Docs system that answers with grounded citations and refuses unsupported answers.

Phase 1 (Fundamentals):
- Ingest PDF, Markdown, and web content.
- Chunk into 500 to 800 token segments with around 100 token overlap.
- Store embeddings in a vector store (Chroma or Weaviate class of tools).
- Retrieve top-k chunks and generate citation-backed answers.
- Deliverable: Show source document, answer, and exact cited paragraph.

Phase 2 (Production Quality):
- Add hybrid retrieval: BM25 plus vector semantic retrieval.
- Add cross-encoder reranking for query-chunk pair rescoring.
- Enforce citation-backed answering: decline when evidence is insufficient.
- Store prompts in versioned config files (treat prompts as architecture).

Phase 3 (Shippable Discipline):
- Build a golden evaluation set of 50 to 200 manually verified QA pairs.
- Add offline evaluation with faithfulness metrics.
- Integrate into CI so every PR runs quality checks.
- Fail build when metrics drop below threshold.

Recommended stack from transcript:
- LangChain or LangGraph
- ChromaDB or Weaviate-style vector store
- Cohere reranker or sentence-transformer cross-encoder rerankers
- RAGAS for RAG-centric evaluation

Interview signal this project proves:
- You understand the gap between a demo and a production-ready RAG system.

Definition of done:
- At least one CI run shown where a quality regression blocks merge.
- At least one example where unsupported answers are declined.

---

### Project 2 Detailed: Local Offline Assistant + Benchmarking

Core objective:
Run small models fully offline and make model-selection decisions with benchmark evidence.

Phase 1 (Local Inference + Baseline Measurement):
- Install Ollama and run a 3B to 7B class model locally.
- Build CLI or FastAPI wrapper.
- Measure tokens/sec, time-to-first-token, and total response latency.
- Include these measurements in technical docs.

Phase 2 (Reliability + Determinism):
- Enforce JSON output schema.
- Validate with Pydantic.
- Implement retry-on-invalid-output with one reprompt, then graceful fail.
- Compare temperature 0 vs 0.7 across same prompt set; document variance.

Phase 3 (Model Comparison Study):
- Benchmark 3 models on identical hardware.
- Evaluate memory usage, tokens/sec, and output quality on 30 to 50 standardized prompts.
- Publish concise comparison report with data-backed recommendation.
- Stretch goal: compare quantized variants (GGUF Q4 vs Q5) and document quality/speed tradeoffs.

Interview signal this project proves:
- You can operate under privacy, cost, latency, and connectivity constraints.

Definition of done:
- Reproducible benchmark script and report with fixed prompt suite.
- Explicit recommendation matrix by use case.

---

### Project 3 Detailed: Observability and Monitoring for RAG

Core objective:
Turn the RAG app into an operable system with traceability, metrics, and regression controls.

Phase 1 (Full Request Tracing):
- Trace each request end-to-end.
- Capture retrieved chunks, reranker ordering, prompt sent, response, and token consumption.
- Candidate tools: LangSmith, Langfuse, Braintrust.
- Practical recommendation from transcript: start with Langfuse (open-source, self-hostable).

Phase 2 (Quality and Reliability Metrics):
- Track P50 and P95 latency (not just average).
- Track cost per request.
- Track citation coverage percentage.
- Track failure rate (errors or unsupported responses).
- Build dashboard that supports root-cause analysis of quality degradation events.

Phase 3 (Regression Gating):
- Reuse Project 1 evaluation set in CI pipeline.
- Block merges when faithfulness or key KPIs fall below thresholds.
- Version prompts and config files alongside code changes.

Interview signal this project proves:
- You can diagnose and stabilize AI systems, not just build first-pass features.

Definition of done:
- You can explain one simulated quality incident from dashboard evidence.
- CI gate demonstrates operational discipline on every PR.

---

### Project 4 Detailed: Fine-Tuning With Measurable Gain

Core objective:
Show when fine-tuning is justified and quantify improvement over prompt-only baselines.

Important framing:
- Fine-tuning is for specific, well-defined tasks where prompting plateaus.
- It is not for making a model generally smarter.

Suggested tasks from transcript:
- Structured JSON extraction from messy unstructured text.
- Tool-call selection and parameter accuracy.

Phase 1 (SFT With Clean Data):
- Prepare 2,000 to 10,000 high-quality, consistently formatted examples.
- Train with LoRA or QLoRA.
- Suggested base model class: Qwen 3 8B class model.
- Evaluate on holdout with:
	- JSON validity rate
	- Exact match accuracy
	- Refusal correctness

Phase 2 (Preference Tuning):
- Generate multiple outputs per prompt.
- Label better/worse outputs.
- Train with DPO-style preference optimization.
- Re-evaluate and report incremental gain over SFT baseline.

Suggested tools from transcript:
- Hugging Face TRL (SFT + DPO)
- Axolotl for simplified training orchestration
- Fireworks AI as managed compute option

Required portfolio evidence:
- Training curves
- Before/after metrics table
- Honest discussion of failures and iteration decisions

Interview signal this project proves:
- You can run modern adaptation workflows and reason with metrics.

Definition of done:
- Measurable, repeatable improvement over baseline with clear evaluation protocol.

---

### Project 5 Detailed: Realtime Multimodal System

Core objective:
Design and operate low-latency streaming AI with clear latency budgets and fault handling.

Track options from transcript:
- Voice assistant: ASR -> LLM -> TTS
- Vision assistant: webcam -> object detection -> reasoning layer
- Streaming log analyzer: live logs -> anomaly detection -> LLM explanations

Recommended track from transcript:
- Voice assistant (strong market demand + mature tooling)

Possible tooling:
- ASR: Deepgram or Whisper
- Reasoning: capable LLM endpoint
- TTS: ElevenLabs or Cartesia
- Transport/orchestration: WebSockets

Phase 1 (Streaming E2E):
- Establish full streaming pipeline with correct event structure.
- Prioritize functionality over optimization.

Phase 2 (Latency Engineering):
- Decompose latency budget by component.
- Track ASR latency, LLM time-to-first-token, TTS time-to-first-byte, and orchestration overhead.
- Build per-request latency breakdown visualization.

Phase 3 (Resilience):
- Implement graceful degradation when services fail.
- Add timeout handling to avoid indefinite hangs.
- Add replay mode for deterministic debugging with recorded inputs.

Interview signal this project proves:
- You can engineer for real-time performance and failure recovery.

Definition of done:
- You can show normal and degraded-path behavior with measured latency and fallback outcomes.

---

## Ensure-That Checklist (Portfolio Quality Bar)

Use this checklist across all five projects so your portfolio signals production readiness:

- Ensure each project has explicit phases (fundamentals -> production quality -> shippable discipline).
- Ensure every project includes measurable KPIs (quality, latency, reliability, cost).
- Ensure every system has failure behavior (decline, fallback, timeout, retry) not just happy path output.
- Ensure prompts and configs are versioned and reviewed like code.
- Ensure at least one CI quality gate is visible and blocks regressions.
- Ensure each README contains architecture, setup, runbook, eval protocol, and known limitations.
- Ensure each project has an evidence artifact: dashboard screenshot, benchmark table, eval report, or incident analysis.

## Senior GenAI Engineer Production Plan (Detailed)

This section upgrades each project into an industry-standard production plan expected from a senior GenAI engineer building reliable systems.

### Common Engineering Standards (Apply to all 5 Projects)

1. Platform and architecture standards
- Service boundaries are explicit: API, orchestration, model adapters, evaluation, observability.
- All external dependencies are abstracted behind provider interfaces.
- Every request carries a correlation_id and tenant_id.
- Config is environment-driven and typed.

2. Security and governance baseline
- Secrets only from secret manager, never from source code.
- PII controls: redaction at ingestion, encrypted storage at rest, TLS in transit.
- RBAC for admin endpoints and dataset mutation operations.
- Full audit log for dataset changes, prompt changes, and release events.

3. Reliability and SRE baseline
- SLOs defined before release.
- Error budgets tracked weekly.
- Retry, timeout, circuit breaker, and fallback behavior documented.
- Runbooks for top 10 failure modes.

4. MLOps and SDLC baseline
- Prompt, dataset, and model versioning as first-class artifacts.
- CI gates for unit, integration, regression, and safety checks.
- Release strategy: dev -> staging -> canary -> production.
- Rollback strategy with max 15-minute recovery target.

5. Portfolio evidence baseline
- Architecture diagram.
- Design doc with tradeoffs.
- KPI dashboard screenshots.
- Postmortem example for one simulated incident.

---

### Project 1: Production RAG With Evaluation and CI Gates

Role expectation:
Own full lifecycle from data ingestion to gated deployment with measurable grounding quality.

Business outcome:
Reduce wrong or unsupported answers while preserving fast response latency.

System architecture:
- Ingestion service: parse PDF/MD/HTML, normalize, deduplicate, chunk, enrich metadata.
- Retrieval service: BM25 + vector hybrid retrieval, metadata filtering.
- Rerank service: cross-encoder reranker with configurable candidate depth.
- Generation service: answer synthesis with citation constraints and refusal policy.
- Evaluation service: offline and periodic online scoring.
- Delivery service: API and minimal UI for human validation.

Data contracts:
- Document schema: doc_id, source, version, section_path, text, checksum, access_scope.
- Chunk schema: chunk_id, doc_id, token_range, text, embedding_id, created_at.
- Retrieval event schema: query_id, top_k, retrieved_ids, reranked_ids, confidence.
- Answer schema: answer_text, citations[], grounded_boolean, refusal_reason.

NFRs and SLOs:
- Availability: 99.9 percent monthly.
- P95 latency: <= 2.5 seconds for <= 15k token context window.
- Citation coverage: >= 95 percent of non-refusal answers include valid citations.
- Faithfulness: >= 0.88 on golden dataset.
- Cost target: <= fixed threshold per 1k requests (define for your provider).

Quality gates in CI:
- Unit test coverage >= 80 percent on core logic.
- Retrieval regression gate: nDCG@10 and recall@k non-decreasing within tolerance.
- Faithfulness gate: fail PR if drop > 2 points from baseline.
- Safety gate: prompt injection test suite pass rate >= 98 percent.

Security and compliance controls:
- Document ACL metadata enforced at query time.
- Prompt injection defense: content sanitization plus tool-use restrictions.
- Data retention policy per source type.

Testing strategy:
- Unit: chunking, ranking logic, citation formatter.
- Integration: end-to-end query path with mocked and real model providers.
- Load: concurrent query simulation at peak QPS target.
- Adversarial: jailbreak prompts, policy bypass attempts, malformed docs.

6-week delivery plan:
- Week 1: architecture, schemas, ingestion MVP, chunking baseline.
- Week 2: hybrid retrieval + reranker + citation output.
- Week 3: refusal policy, prompt versioning, evaluation harness.
- Week 4: golden dataset (50-200 QA pairs), baseline scorecard.
- Week 5: CI gates, staging deployment, dashboard.
- Week 6: canary release, incident drill, final technical writeup.

Definition of done:
- System declines unsupported queries reliably.
- PR is blocked automatically on quality regression.
- Dashboard shows retrieval quality, grounding, latency, and cost.

---

### Project 2: Local AI Assistant and Model Benchmarking Lab

Role expectation:
Engineer offline-first assistant with deterministic outputs and defensible model selection framework.

Business outcome:
Deliver privacy-safe inference option with quantified performance/quality tradeoffs.

System architecture:
- Runtime layer: Ollama or llama.cpp adapter with model registry.
- API layer: command-line and HTTP inference endpoints.
- Guardrails layer: JSON schema constraints, validation, retry strategy.
- Benchmark layer: scenario runner, metrics collector, report generator.
- Storage layer: benchmark results history and environment metadata.

Benchmark design:
- Prompt suite: 30-50 prompts across extraction, summarization, reasoning.
- Controlled environment: fixed hardware profile, identical generation params.
- Metrics:
	- time_to_first_token
	- tokens_per_second
	- total_latency
	- peak_memory
	- structured_output_validity
	- task_quality_score

NFRs and SLOs:
- 100 percent local/offline mode supported.
- P95 latency target by task tier.
- Structured output validity >= 99 percent with one retry.
- Recovery behavior: graceful failure within timeout window.

Determinism strategy:
- Temperature profiles documented by task type.
- Temperature 0 and 0.7 variance report included.
- Seed controls and parameter lock in benchmark mode.

Security and compliance controls:
- No external network calls in offline mode.
- Local disk encryption for cached prompts/responses.
- Optional on-device redaction before persistence.

Testing strategy:
- Unit: schema validation and retry policy.
- Integration: offline end-to-end run with network disabled.
- Benchmark regression: compare model versions against reference baselines.

5-week delivery plan:
- Week 1: offline runtime setup and base inference API.
- Week 2: schema validation, retry, graceful error handling.
- Week 3: benchmark harness and fixed prompt suite.
- Week 4: 3-model comparison on same hardware.
- Week 5: quantization experiments (Q4/Q5), final recommendation report.

Definition of done:
- Repeatable benchmark runs produce stable ranking.
- Report clearly maps use-case profiles to recommended models.

---

### Project 3: Observability and AI Reliability Layer

Role expectation:
Operate RAG as a production service with full traceability, measurable health, and fast incident response.

Business outcome:
Cut detection and diagnosis time for quality regressions and runtime failures.

System architecture:
- Telemetry collector: OpenTelemetry traces, structured logs, metrics.
- AI trace model: request -> retrieval -> rerank -> generation -> postprocess.
- Quality monitor: citation coverage, refusal accuracy, faithfulness proxy.
- Alerting pipeline: threshold and anomaly-based alerts.
- Incident console: dashboards, timeline, correlated traces.

Golden signals:
- Latency: P50/P95/P99 by endpoint.
- Errors: 4xx/5xx, tool failures, timeout rate.
- Throughput: requests per minute and burst behavior.
- Cost: model spend per request and per tenant.
- Quality: faithfulness trend, citation coverage, unsupported-answer rate.

NFRs and SLOs:
- MTTD <= 5 minutes for severity-1 regressions.
- MTTR <= 30 minutes for known failure classes.
- Trace completeness >= 99 percent requests.
- Alert precision target >= 80 percent.

Operational controls:
- Prompt/config/model version tags attached to every trace.
- Change intelligence: correlate quality shifts to releases.
- Incident runbooks with first-response decision trees.

Testing strategy:
- Chaos tests: provider timeout, reranker failure, vector DB slowdown.
- Synthetic monitoring: fixed query probes every N minutes.
- Alert validation drills: test alert routes and escalation timing.

4-week delivery plan:
- Week 1: tracing and event schema rollout.
- Week 2: dashboard and SLO implementation.
- Week 3: alerting policies and chaos scenarios.
- Week 4: regression gate integration and incident simulation writeup.

Definition of done:
- You can explain a degradation event from telemetry to root cause to remediation.

---

### Project 4: Fine-Tuning Program With Measured ROI

Role expectation:
Lead data-centric adaptation program with reproducible improvements and alignment controls.

Business outcome:
Increase consistency and accuracy on a narrow high-value task where prompting alone underperforms.

Task selection criteria:
- Task has clear objective metric.
- Baseline prompt performance is below required threshold.
- Dataset can be curated with consistent labeling standards.

System architecture:
- Data pipeline: curation, normalization, split, lineage.
- Training pipeline: SFT (LoRA/QLoRA) then DPO preference tuning.
- Evaluation pipeline: benchmark suite with holdout and adversarial sets.
- Registry pipeline: model versions, training configs, and metrics lineage.

Dataset standards:
- 2k to 10k clean examples minimum for SFT.
- Labeling guide with edge-case rules.
- Leakage checks and duplicate detection.
- Data card with provenance and limitations.

Evaluation framework:
- JSON validity rate.
- Exact match / F1.
- Tool-call accuracy (selection + argument correctness).
- Refusal correctness and policy compliance.
- Latency and memory impact post fine-tuning.

NFRs and SLOs:
- Quality improvement target: >= 10 percent absolute on primary metric.
- Regression budget: <= 2 percent degradation on secondary metrics.
- Inference P95 within deployment latency SLO.

Governance and safety controls:
- Red-team prompts for unsafe completion checks.
- Prompt- and policy-regression test suite required for release.
- Approval checkpoint before promoting tuned model.

6-week delivery plan:
- Week 1: task framing, baseline, metric contract.
- Week 2: dataset curation and validation.
- Week 3: SFT run and baseline tuned evaluation.
- Week 4: DPO preference dataset and tuning.
- Week 5: robustness, ablations, safety checks.
- Week 6: production candidate release, model card, ROI summary.

Definition of done:
- Before/after report shows statistically credible lift and controlled regressions.

---

### Project 5: Realtime Multimodal Application (Latency + Resilience)

Role expectation:
Build and run low-latency streaming system with explicit performance budgets and robust failure handling.

Business outcome:
Deliver responsive multimodal experience with reliable degraded-mode behavior under faults.

Preferred implementation track:
- Voice assistant: ASR -> LLM reasoning -> TTS over WebSockets.

System architecture:
- Session gateway: websocket auth, session lifecycle, heartbeats.
- Streaming ASR adapter: partial transcript events.
- Reasoning engine: incremental context and interruption handling.
- TTS adapter: chunked audio response streaming.
- Control plane: retries, deadlines, fallback policies.
- Replay harness: deterministic playback for debugging.

Latency budget design:
- ASR latency budget.
- LLM time-to-first-token budget.
- TTS time-to-first-byte budget.
- Transport and orchestration overhead budget.
- End-to-end P95 budget (target around 1.2s if feasible).

Resilience design:
- Timeout hierarchy per component.
- Circuit breakers for unstable providers.
- Fallback modes:
	- text-only fallback
	- shorter response fallback
	- apology plus retry prompt
- Backpressure handling for burst traffic.

NFRs and SLOs:
- Session success rate >= 99 percent.
- End-to-end P95 latency within target budget.
- Graceful degradation success >= 95 percent in injected failure tests.
- No unbounded queue growth under stress test.

Testing strategy:
- Soak test: 30-60 minute continuous sessions.
- Fault injection: dropped packets, provider timeouts, delayed responses.
- Replay tests for deterministic regression verification.

6-week delivery plan:
- Week 1: streaming backbone and session protocol.
- Week 2: ASR + LLM + TTS full loop.
- Week 3: latency instrumentation and per-stage dashboards.
- Week 4: timeout/fallback/circuit breaker rollout.
- Week 5: fault injection and soak testing.
- Week 6: performance tuning, postmortem-style documentation, demo.

Definition of done:
- Normal-path and failure-path demos both meet documented acceptance criteria.

---

## Program-Level Execution Strategy (How a Senior Engineer Runs All 5)

1. Sequencing
- Build Project 1 first as the shared foundation.
- Build Project 2 in parallel with Project 1 week 3 onward if resources allow.
- Layer Project 3 directly on top of Project 1 once baseline is stable.
- Start Project 4 only after metric contracts are mature.
- Execute Project 5 last to showcase advanced systems maturity.

2. Portfolio packaging
- One mono-repo with shared platform modules.
- One architecture index document linking all project diagrams.
- One consolidated KPI dashboard page across projects.

3. Senior-level review rubric
- Production readiness: security, reliability, observability, rollback.
- Scientific rigor: baselines, controlled experiments, reproducibility.
- Operational excellence: CI gates, incident handling, runbooks.
- Communication quality: clear tradeoffs and measured outcomes.

4. Final hiring package deliverables
- Executive summary (1 page) with quantified outcomes.
- Technical deep dive (5-10 pages) with architecture and metrics.
- Demo videos for normal path and failure path.
- Public roadmap of future improvements and known limitations.

## Portfolio Program Tracker (14 Weeks)

Use this tracker to run all 5 projects as a production delivery program.

### Program Metadata

- Program owner:
- Technical lead:
- Start date:
- Target completion date:
- Review cadence: weekly demo + weekly risk review + bi-weekly architecture review
- Status scale: Not started | In progress | Blocked | Done
- Health scale: Green | Amber | Red

### Project Ownership Matrix

| Project | Primary owner | Secondary owner | Repo/module path | Current status | Health | Target end week |
|---|---|---|---|---|---|---|
| Project 1: Production RAG |  |  |  | Not started | Green | Week 6 |
| Project 2: Local Assistant + Benchmarking |  |  |  | Not started | Green | Week 8 |
| Project 3: Observability Layer |  |  |  | Not started | Green | Week 10 |
| Project 4: Fine-Tuning Program |  |  |  | Not started | Green | Week 12 |
| Project 5: Realtime Multimodal App |  |  |  | Not started | Green | Week 14 |

### Weekly Execution Tracker

#### Week 1

- Program goals:
	- [ ] Finalize architecture baseline for Project 1.
	- [ ] Finalize schemas and data contracts.
	- [ ] Set up repo standards, linting, testing, and CI skeleton.
- Owner:
- Planned demo:
- Exit criteria:
	- [ ] Approved architecture doc.
	- [ ] Ingestion MVP committed and runnable.
	- [ ] CI runs unit tests successfully.
- Risks/blockers:
- Decisions made:

#### Week 2

- Program goals:
	- [ ] Implement hybrid retrieval design for Project 1.
	- [ ] Add reranking and citation output path.
	- [ ] Baseline latency and retrieval quality metrics pipeline.
- Owner:
- Planned demo:
- Exit criteria:
	- [ ] Top-k retrieval and reranking integrated.
	- [ ] Citation fields present in responses.
	- [ ] Initial KPI dashboard populated.
- Risks/blockers:
- Decisions made:

#### Week 3

- Program goals:
	- [ ] Implement refusal policy and prompt versioning.
	- [ ] Build evaluation harness for Project 1.
	- [ ] Start Project 2 runtime setup (offline local inference).
- Owner:
- Planned demo:
- Exit criteria:
	- [ ] Refusal behavior validated on unsupported queries.
	- [ ] Prompt/config version tags available.
	- [ ] Local inference endpoint online for at least one model.
- Risks/blockers:
- Decisions made:

#### Week 4

- Program goals:
	- [ ] Curate Project 1 golden dataset (50-200 QA pairs).
	- [ ] Run baseline RAG evaluation and publish scorecard.
	- [ ] Implement Project 2 schema validation and retry strategy.
- Owner:
- Planned demo:
- Exit criteria:
	- [ ] Golden dataset reviewed and checked in.
	- [ ] Baseline faithfulness and citation metrics reported.
	- [ ] JSON validity guardrail working in Project 2.
- Risks/blockers:
- Decisions made:

#### Week 5

- Program goals:
	- [ ] Add CI quality gates for Project 1.
	- [ ] Build Project 2 benchmark harness.
	- [ ] Define standard prompt suite for model comparison.
- Owner:
- Planned demo:
- Exit criteria:
	- [ ] PR fails on RAG quality regression.
	- [ ] Benchmark harness captures TTFT, TPS, latency, and memory.
	- [ ] Prompt suite documented and versioned.
- Risks/blockers:
- Decisions made:

#### Week 6

- Program goals:
	- [ ] Complete Project 1 canary release + incident drill.
	- [ ] Complete Project 2 three-model comparison run.
	- [ ] Publish Project 1 production readout.
- Owner:
- Planned demo:
- Exit criteria:
	- [ ] Project 1 SLO dashboard live.
	- [ ] Incident drill report completed.
	- [ ] Project 2 benchmark v1 report published.
- Risks/blockers:
- Decisions made:

#### Week 7

- Program goals:
	- [ ] Start Project 3 telemetry instrumentation.
	- [ ] Add trace IDs through full RAG pipeline.
	- [ ] Begin quantization experiments for Project 2.
- Owner:
- Planned demo:
- Exit criteria:
	- [ ] End-to-end trace for each request available.
	- [ ] Core telemetry schema documented.
	- [ ] Q4/Q5 benchmark run started.
- Risks/blockers:
- Decisions made:

#### Week 8

- Program goals:
	- [ ] Build Project 3 dashboards (latency, cost, quality, errors).
	- [ ] Finalize Project 2 recommendation matrix.
	- [ ] Validate offline/no-network compliance mode.
- Owner:
- Planned demo:
- Exit criteria:
	- [ ] P50/P95/P99 and failure rate visible.
	- [ ] Model recommendation by use-case published.
	- [ ] Offline mode validation complete.
- Risks/blockers:
- Decisions made:

#### Week 9

- Program goals:
	- [ ] Add Project 3 alerting and anomaly thresholds.
	- [ ] Start Project 4 task framing and baseline evaluation.
	- [ ] Finalize Project 4 metric contract.
- Owner:
- Planned demo:
- Exit criteria:
	- [ ] Alert routes tested and confirmed.
	- [ ] Baseline prompt-only metrics published.
	- [ ] Fine-tuning task accepted with measurable KPI.
- Risks/blockers:
- Decisions made:

#### Week 10

- Program goals:
	- [ ] Integrate Project 3 regression gate in CI.
	- [ ] Build Project 4 dataset curation pipeline.
	- [ ] Complete data card and labeling standards.
- Owner:
- Planned demo:
- Exit criteria:
	- [ ] Build blocks on reliability/quality regression.
	- [ ] Dataset quality checks automated.
	- [ ] Data card completed and reviewed.
- Risks/blockers:
- Decisions made:

#### Week 11

- Program goals:
	- [ ] Run Project 4 SFT (LoRA/QLoRA) training.
	- [ ] Evaluate holdout performance and regressions.
	- [ ] Start Project 5 streaming architecture skeleton.
- Owner:
- Planned demo:
- Exit criteria:
	- [ ] SFT run reproducible from config.
	- [ ] Before/after interim metrics available.
	- [ ] Project 5 session protocol and websocket baseline up.
- Risks/blockers:
- Decisions made:

#### Week 12

- Program goals:
	- [ ] Execute Project 4 DPO-style preference tuning.
	- [ ] Complete Project 4 model card and ROI readout.
	- [ ] Integrate ASR and reasoning layer for Project 5.
- Owner:
- Planned demo:
- Exit criteria:
	- [ ] DPO improvement over SFT baseline measured.
	- [ ] Safety and policy checks pass.
	- [ ] Project 5 real-time request/response loop functional.
- Risks/blockers:
- Decisions made:

#### Week 13

- Program goals:
	- [ ] Add Project 5 latency budget instrumentation.
	- [ ] Add TTS and per-stage timing visualizations.
	- [ ] Implement timeout and fallback control plane.
- Owner:
- Planned demo:
- Exit criteria:
	- [ ] Stage-by-stage latency breakdown live.
	- [ ] Timeout handling verified in tests.
	- [ ] Fallback behavior works for injected failures.
- Risks/blockers:
- Decisions made:

#### Week 14

- Program goals:
	- [ ] Run Project 5 resilience and soak tests.
	- [ ] Package final hiring portfolio artifacts.
	- [ ] Publish executive summary and technical deep dive.
- Owner:
- Planned demo:
- Exit criteria:
	- [ ] Session success and latency SLOs met.
	- [ ] Final dashboards and reports complete.
	- [ ] End-to-end demo videos recorded (normal + failure paths).
- Risks/blockers:
- Decisions made:

### Weekly Status Snapshot Template

Use this every Friday for stakeholder updates.

| Field | Value |
|---|---|
| Week # |  |
| Overall status |  |
| Overall health |  |
| Top 3 wins |  |
| Top 3 risks |  |
| Mitigation actions |  |
| Decisions needed |  |
| KPI trend summary |  |
| Planned next week |  |

### Program Risk Register

| Risk ID | Risk description | Impact | Probability | Owner | Mitigation | Trigger | Status |
|---|---|---|---|---|---|---|---|
| R1 | Model/provider instability | High | Medium |  | Multi-provider abstraction + fallback | Increased timeout/error rate | Open |
| R2 | Evaluation set quality drift | High | Medium |  | Data review cadence + label audits | Unexpected score volatility | Open |
| R3 | Cost overrun in experimentation | Medium | Medium |  | Cost budgets and per-run limits | Cost threshold breach | Open |
| R4 | Latency SLO misses in realtime app | High | Medium |  | Stage-level budget optimization | P95 exceeds target | Open |
| R5 | Security/compliance gaps | High | Low |  | Secret manager + access reviews + audit logs | Failed security review | Open |

### Milestone Gate Checklist (Senior Review)

- [ ] Design gate passed: architecture, threat model, and NFRs approved.
- [ ] Build gate passed: unit/integration tests and CI quality gates active.
- [ ] Reliability gate passed: SLO dashboards and alerts validated.
- [ ] Security gate passed: secrets, RBAC, and audit controls verified.
- [ ] Release gate passed: rollback plan tested and canary strategy documented.
- [ ] Portfolio gate passed: metrics narrative and evidence artifacts complete.
