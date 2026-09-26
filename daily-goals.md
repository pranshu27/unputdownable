# Daily Goals — INTERVIEW-CRACKER EDITION (Architecture-First, Hands-On-Verified)
**Duration:** Mon, Sep 28, 2026 → Fri, Jan 15, 2027 (16 weeks) · **Job search launches Mon, Jan 18, 2027**

## Mission
You will do BOTH: **build the real portfolio** (Track A: Agentic RAG · Track B: AWS Enterprise · Track C: Resilient Gateway) **and** become an interview cracker. The formula: **Architect it → Build it → Measure it → Defend it.** Every week produces working, committed code AND interview artifacts. Your reading superpower feeds the design; the running system supplies real numbers and credibility; the drills and mocks convert it all into interview wins.

## The Weekly Operating System (every week, same shape)
- **Day 1 (Mon) — READ & DESIGN:** Read the primary source → 1-page mental model in `architecture-notes/` → write the week's ADR in `adr/` (decision, alternatives, trade-offs, expected numbers). **No code before the ADR exists.**
- **Day 2 (Tue) — BUILD:** Implement the week's component per the ADR. **2.5–3 hr cap** (plan.md timebox). Boilerplate may come from reference repos; core logic is yours, committed to GitHub daily.
- **Day 3 (Wed) — INTEGRATE & MEASURE:** Wire into the full stack, run end-to-end, capture **3 real measured numbers — one per category: quality (Δ Recall@5), latency (TTFT/TPOT by span), cost ($/1k queries or VRAM/user)** (see Operational Guardrails §1). Measured numbers from *your own system* are the strongest things you can say in an interview. Blocked by end of Day 3 → **stub with mock data and advance** (plan.md rule).
- **Day 4 (Thu) — DRILL:** DSA *pattern-first*: verbalize the pattern aloud, then 2 timed problems (20-min caps; read the editorial if stuck > 15 min). Then speak a 15-min LLD design. **Talking > typing.**
- **Day 5 (Fri) — MOCK & BANK:** Whiteboard **the system you actually built** from memory (10 min, photo → `whiteboards/`), recorded mock (rotating archetype from Week 4), one STAR story aloud, **+10 Q&As into `interview-bank.md`**, 10-min mental math flashcards (daily habit).

## Standing Rules
- **Design before code.** A design flaw caught on paper Monday costs minutes; caught in code Tuesday costs hours.
- **Build timebox:** 2.5–3 hrs on Build days; never debug > 45 min — note blocker, stub, advance. Dev never touches Days 4–5 (scrutiny guardrail).
- **Company-project parallel track (Weeks 1–3):** convert current-company RAG + AutoGen work into 3 ADRs + 6 STAR stories. *Company projects = ownership evidence; portfolio = breadth proof.*
- **GPU logistics:** confirm GPU access (≥24GB VRAM or RunPod/Lambda budget) **by end of Week 6** — needed for Week 7 (vLLM) and QLoRA.
- **Spaced repetition:** review 20 old bank Q&As every Friday + 10 min mental math daily (VRAM formula, KV-cache sizing, token cost).
- **DSA philosophy:** enough to clear bank screens (2 Mediums in 45 min by Week 12) — pattern fluency and verbal walkthroughs, not competitive programming.
- **Job search starts after Week 16** — Week 16 builds the application machine so applications go out Jan 18.

## Artifacts You Will Own by Week 16
- **Track A repo** — working Agentic RAG (FastAPI, LangGraph, vLLM, Qdrant, Redis, Phoenix, Ragas CI) — **v1.0 tagged**
- **Track B stack** — AWS enterprise doc intelligence (Bedrock, Guardrails, OpenSearch, Step Functions, DynamoDB audit) — deployed + documented
- **Track C** — Resilient LLM Gateway (LiteLLM, circuit breaker, rate limiting, OTel) — chaos-tested
- `architecture-notes/` — 16 mental models · `adr/` — 16+ decision records (incl. 3 from company projects) · `measurements.md` — 3 measured numbers/week (quality / latency / cost)
- `interview-bank.md` — 300+ Q&As · `whiteboards/` — 16 from-memory diagrams of systems you built
- 14 STAR stories recorded · 10+ recorded mocks/simulations · 1 QLoRA fine-tune run · 3 LinkedIn write-ups
- Application machine (resume, 30-company target list, referral map) — ready Jan 18

---

# MONTH 1 — Build Track A: Ingestion, Hybrid Retrieval & Agentic RAG Foundations

## Week 1 (Sep 28 – Oct 2) — Chunking, Ingestion & Vector Index Foundations
- **Mon Sep 28 · READ & DESIGN:** HNSW paper (skim algorithm + complexity) + Qdrant hybrid docs → mental model: HNSW vs. IVF-PQ (memory vs. recall; ef/M/efSearch). ADR #1: parsing + chunking pipeline (Strategy Pattern; semantic chunks, contextual headers, table-aware rules for 10-Ks).
- **Tue Sep 29 · BUILD:** FastAPI async skeleton with Pydantic v2 schemas. Qdrant in Docker with dense + sparse vector config. Commit skeleton.
- **Wed Sep 30 · INTEGRATE & MEASURE:** Implement semantic chunking + table-aware ingestion (scanned PDFs, multi-column, balance sheets). Ingest a real document batch incl. one 10-K. **Measure (quality / latency / cost):** parse failure + table-corruption rate (quality) · ingest p95 latency + throughput in docs/sec (latency) · embedding + index storage cost per 1k pages (cost).
- **Thu Oct 1 · DRILL:** DSA: two pointers/sliding window/prefix sums — Subarray Sum Equals K + Longest Substring Without Repeating Characters (20-min caps, verbalize first). LLD spoken: Extensible Document Parser.
- **Fri Oct 2 · MOCK & BANK:** Whiteboard the ingestion pipeline from memory. STAR 1: Production Ingestion Bottleneck (anchor to company work). Bank +10. **Company track:** list current-company GenAI projects; pick ADR topic #1.

## Week 2 (Oct 5 – Oct 9) — Hybrid Retrieval, RRF & Reranking
- **Mon Oct 5 · READ & DESIGN:** RRF paper (Cormack et al.) + BGE-M3 paper + cross-encoder reranking explainer. ADR #2: hybrid fusion (RRF k=60, rerank top-50 → top-5, latency budget).
- **Tue Oct 6 · BUILD:** Generate BGE-M3 dense + sparse vectors into Qdrant. **Implement RRF from scratch** (not a library call — this is a whiteboard-flex).
- **Wed Oct 7 · INTEGRATE & MEASURE:** Integrate BGE-Reranker-Large (top-50 → top-5). Benchmark hybrid vs. dense-only vs. sparse-only. **Measure (quality / latency / cost):** Δ Recall@5 across dense/hybrid/RRF (quality) · rerank + end-to-end query latency (latency) · $ per 1k queries (cost).
- **Thu Oct 8 · DRILL:** DSA: heaps/hash-maps — Top K Frequent Elements + Find Median from Data Stream. LLD spoken: in-memory RRF ranker with configurable weights.
- **Fri Oct 9 · MOCK & BANK:** Whiteboard hybrid search at 10M docs (sharding, cache tiers). **MBB Case 1 (spoken, 30 min):** Legal Document Review Platform — 6-step MECE aloud. STAR 2: Search Degradation. Bank +10. **Company track:** draft company ADR #1.

## Week 3 (Oct 12 – Oct 16) — Query Rewriting & Self-RAG
- **Mon Oct 12 · READ & DESIGN:** HyDE paper + Self-RAG paper (reflection tokens, sufficiency verification). ADR #3: query transformation pipeline (when HyDE vs. sub-query decomposition vs. rewrite; latency budget per strategy).
- **Tue Oct 13 · BUILD:** Implement HyDE + sub-query decomposition nodes as pluggable, config-driven transformations.
- **Wed Oct 14 · INTEGRATE & MEASURE:** Implement Self-RAG reflection (LLM verifies context sufficiency → triggers rewrite loop). **Measure (quality / latency / cost):** retrieval precision delta before vs. after rerank (quality) · rewrite-loop latency overhead (latency) · added LLM tokens for HyDE/rewrite → $/1k queries (cost).
- **Thu Oct 15 · DRILL:** DSA: trees/BST/BFS-DFS — Lowest Common Ancestor + Binary Tree Maximum Path Sum. LLD spoken: Query Rewriter pipeline (Chain of Responsibility).
- **Fri Oct 16 · MOCK & BANK:** Whiteboard enterprise KB search with context-aware filtering. STAR 3: Solving Hallucinations in Production (anchor to company validation loops). Bank +10. **Company track:** finalize company ADRs #1–2; STAR stories 1–2 rewritten from company work.

## Week 4 (Oct 19 – Oct 23) — Caching, Streaming & Containerization
- **Mon Oct 19 · READ & DESIGN:** Semantic caching patterns (GPTCache: similarity threshold, staleness) + SSE/backpressure mechanics + Redis TTL/eviction. ADR #4: semantic cache (threshold choice, invalidation) + streaming path.
- **Tue Oct 20 · BUILD:** Redis semantic cache (cosine similarity on query embeddings). SSE token streaming in FastAPI with backpressure handling.
- **Wed Oct 21 · INTEGRATE & MEASURE:** Docker Compose the full Track A baseline; end-to-end test ingest → retrieve → stream. **Measure (quality / latency / cost):** cache hit-rate + relevance parity on cache hits (quality) · cached vs. uncached latency delta (latency) · token cost avoided via cache → $/1k queries (cost).
- **Thu Oct 22 · DRILL:** DSA: graphs/topological sort — Course Schedule + Word Ladder. LLD spoken: thread-safe token-bucket rate limiter (Redis backend).
- **Fri Oct 23 · MOCK & BANK:** **MOCK #1 (recorded, 60 min, startup archetype):** "Design a low-latency RAG platform" — whiteboard end-to-end. STAR 4: Cost Spikes. Bank +10. **Company track:** company ADR #3 + 6 company STAR stories drafted. Month-1 review: reread mental models 1–4 aloud.

---

# MONTH 2 — Build Track A: Agents, vLLM & the Resilient Gateway (Track C)

## Week 5 (Oct 26 – Oct 30) — LangGraph State Machines
- **Mon Oct 26 · READ & DESIGN:** LangGraph docs (state schemas, conditional edges, checkpointing) + AutoGen vs. LangGraph essays. ADR #5: deterministic agent graph (TypedDict state, max-loops=3 cycle bound, Postgres checkpointing) — contrast with your company's AutoGen patterns.
- **Tue Oct 27 · BUILD:** Build the LangGraph workflow: typed state, conditional edges, cycle prevention; PostgreSQL checkpointer wired.
- **Wed Oct 28 · INTEGRATE & MEASURE:** Connect the agent graph to the Week 1–4 RAG pipeline; test checkpoint/resume after interruption. **Measure (quality / latency / cost):** checkpoint/resume correctness after interruption (quality) · checkpoint write overhead per node (latency) · Postgres state size per session → storage cost (cost).
- **Thu Oct 29 · DRILL:** DSA: DP 1D/2D — Coin Change + Longest Increasing Subsequence. LLD spoken: agent state machine with checkpoint/rewind (State & Memento).
- **Fri Oct 30 · MOCK & BANK:** **MOCK #2 (recorded, 60 min, bank archetype):** "Design a secure enterprise RAG for a regulated bank." STAR 5: Taming Uncontrolled Agents — **use your real AutoGen migration story**. Bank +10.

## Week 6 (Nov 2 – Nov 6) — Tool Calling, Sandboxing & HITL
- **Mon Nov 2 · READ & DESIGN:** Tool/function-calling specs (OpenAI + Anthropic docs) + OWASP LLM Top 10 (agentic + injection risks). ADR #6: secure tool execution (sandbox, permission model, timeout guards, self-repair loop).
- **Tue Nov 3 · BUILD:** Structured function calling with Pydantic output validation. Error-recovery nodes feeding tool exceptions back for self-repair.
- **Wed Nov 4 · INTEGRATE & MEASURE:** HITL interrupt points (graph pauses for external approval payload); test the full approve/reject flow. **Measure (quality / latency / cost):** tool-call failure + self-repair success rate (quality) · tool-call + repair-loop latency (latency) · tokens per tool call → $/1k calls (cost).
- **Thu Nov 5 · DRILL:** DSA: monotonic stacks/intervals — Daily Temperatures + Merge Intervals. LLD spoken: secure tool execution sandbox.
- **Fri Nov 6 · MOCK & BANK:** **MBB Case 2 (spoken, 30 min):** Enterprise Code Migration Assistant — MECE aloud, answer-first. STAR 6: Production Agent Failure Mode (company story). Bank +10. ⚠️ **Confirm GPU access today (RunPod/Lambda budget) for Week 7.**

## Week 7 (Nov 9 – Nov 13) — vLLM, PagedAttention & the QLoRA Proof
- **Mon Nov 9 · READ & DESIGN:** **The PagedAttention paper (vLLM, SOSP'23) — your crown-jewel read** + KV-cache formula (plan.md Module 1). Mental model: prefill (compute-bound) vs. decode (memory-bandwidth-bound). ADR #7: self-hosted inference vs. API (batching, tensor parallelism, TTFT/TPS trade-offs).
- **Tue Nov 10 · BUILD:** Stand up vLLM serving Llama 3.1 8B (continuous batching, tensor parallelism); wire Track A's LLM calls to the OpenAI-compatible endpoint.
- **Wed Nov 11 · INTEGRATE & MEASURE:** Benchmark vLLM vs. HF pipeline under concurrent load — capture three quotable numbers — **TTFT + tokens/sec** (latency) · **output-quality parity vs. HF baseline** (quality) · **VRAM per concurrent user + $/1k queries** (cost). Then run **one guided QLoRA fine-tune** (Unsloth/PEFT notebook, small domain dataset) — enough to honestly say "I've fine-tuned."
- **Thu Nov 12 · DRILL:** DSA: tries/string matching — Implement Trie + Design Add and Search Words. LLD spoken: inference client connection pool (keep-alive, retry budgets).
- **Fri Nov 13 · MOCK & BANK:** STAR 7: Infrastructure Optimization (API vs. self-hosting). **LoRA defense drill (spoken, 10 min):** fine-tune 8B vs. few-shot 70B; catastrophic forgetting. **LinkedIn write-up #1:** your vLLM benchmark numbers + capacity math. Bank +10.

## Week 8 (Nov 16 – Nov 20) — Resilient LLM Gateway (Track C)
- **Mon Nov 16 · READ & DESIGN:** *Release It!* circuit-breaker & bulkhead chapters + LiteLLM proxy docs. ADR #8: gateway (fallback routing, distributed token-bucket limits, half-open probes, egress DLP).
- **Tue Nov 17 · BUILD:** Async reverse proxy routing traffic between vLLM and fallback APIs. Implement the circuit breaker (trip on consecutive timeouts/5xx → degraded fallback).
- **Wed Nov 18 · INTEGRATE & MEASURE:** OTel spans on all gateway spans. **Chaos test:** kill vLLM mid-load — verify trip + fallback + recovery. **Measure (quality / latency / cost):** failover success + half-open probe success rate (quality) · failover time (latency) · $/1k routed requests across providers (cost).
- **Thu Nov 19 · DRILL:** DSA: Union-Find — Number of Connected Components + Redundant Connection. LLD spoken: thread-safe circuit breaker with half-open states.
- **Fri Nov 20 · MOCK & BANK:** **MOCK #3 (recorded, 60 min, MBB archetype):** "A client wants a centralized AI platform — TCO and rollout plan." STAR 8: Cross-Functional Alignment (company story). Bank +10. Month-2 review: mental models 1–8 + cumulative mental math self-test.

---

# MONTH 3 — Build Track B: AWS Cloud-Native, Governance & Compliance

## Week 9 (Nov 23 – Nov 27) — Bedrock, Guardrails & Security Architecture *(US Thanksgiving Nov 26–27: protect Thu DRILL; fold Fri mock/bank into the weekend if needed)*
- **Mon Nov 23 · READ & DESIGN:** Bedrock Guardrails docs (PII filters, topic denies, injection filters) + AWS Well-Architected ML Lens (security) + plan.md Module 3 (Dual-LLM pattern, egress DLP). ADR #9: regulated-bank GenAI architecture (API GW → Lambda → Bedrock; VPC endpoints, ZDR, KMS, least-privilege IAM).
- **Tue Nov 24 · BUILD:** Deploy API Gateway → Lambda → Bedrock (Claude 3.5 Sonnet/Haiku) with strictly scoped IAM execution roles.
- **Wed Nov 25 · INTEGRATE & MEASURE:** Configure Guardrails (PII redaction, blocked financial topics, injection heuristics); test the full secure request path end-to-end. **Measure (quality / latency / cost):** PII redaction rate on seeded test set (quality) · guardrail latency overhead (latency) · $/1k guarded requests (cost).
- **Thu Nov 26 · DRILL:** DSA: DP/backtracking — Word Break + Subsets (or Combination Sum). LLD spoken: PII redaction & sanitization engine (Composite Pattern).
- **Fri Nov 27 · MOCK & BANK:** **Threat-model drill (spoken, 10 min):** defend the Dual-LLM pattern against data exfiltration via retrieved context. STAR 9: Security Audit Defense (company InfoSec story). Bank +10.

## Week 10 (Nov 30 – Dec 4) — OpenSearch Serverless & Multi-Tenant RBAC
- **Mon Nov 30 · READ & DESIGN:** OpenSearch Serverless vector docs + Titan Embeddings docs + multi-tenant isolation patterns (filter-level vs. index-level). ADR #10: event-driven ingestion (S3 → EventBridge → Lambda → Titan → OpenSearch; DLQ, KMS CMK, chunk-level RBAC).
- **Tue Dec 1 · BUILD:** Provision the OpenSearch Serverless vector collection (KMS CMK). Build the S3 → EventBridge → Lambda → Titan → OpenSearch ingestion pipeline.
- **Wed Dec 2 · INTEGRATE & MEASURE:** Test chunk-level RBAC; attempt cross-tenant queries and prove isolation. **Measure (quality / latency / cost):** cross-tenant isolation + recall (quality) · ingestion p95 latency (latency) · GB per 1M vectors × dims → storage $ (cost) — MBB-style quant you can do live.
- **Thu Dec 3 · DRILL:** DSA: design-data-structures — LRU Cache + LFU Cache. LLD spoken: event-driven ingestion queue with DLQ.
- **Fri Dec 4 · MOCK & BANK:** **MBB Case 3 (spoken, 30 min):** AML Assistant for a Tier-1 Bank (ZDR & auditability). STAR 10: Multi-Tenant Isolation (company story). Bank +10. **Optional AWS SA Associate study begins** (30 min/day reading; exam target Week 13).

## Week 11 (Dec 7 – Dec 11) — Step Functions & Regulated Human-in-the-Loop
- **Mon Dec 7 · READ & DESIGN:** Step Functions docs (`.waitForTaskToken`, Standard vs. Express) + DynamoDB best practices + event-sourcing/immutable-audit patterns. ADR #11: regulated HITL workflow (task tokens, escalation, hash-chained immutable history).
- **Tue Dec 8 · BUILD:** Build the Step Functions state machine (multi-step document verification); DynamoDB tables for audit logs + execution history; `.waitForTaskToken` reviewer halt.
- **Wed Dec 9 · INTEGRATE & MEASURE:** Complete the reviewer loop (approve/reject payload resumes or halts execution); hash-chained audit records; end-to-end compliance test. **Measure (quality / latency / cost):** hash-chain integrity + approval correctness (quality) · approval round-trip time (latency) · audit size → DynamoDB $/1k approvals (cost).
- **Thu Dec 10 · DRILL:** DSA (bank screening style): custom sorts, interval merging, graph reachability — verbal walkthroughs first. LLD spoken: auditable transaction logger with cryptographic hash chaining.
- **Fri Dec 11 · MOCK & BANK:** STAR 11: Handling Model Disagreements. **LinkedIn write-up #2:** HITL compliance patterns with Step Functions. **MOCK #4 (recorded, 75 min, bank archetype):** DSA screen sim + mortgage underwriting design. Bank +10.

## Week 12 (Dec 14 – Dec 18) — Observability, X-Ray & Cost Governance
- **Mon Dec 14 · READ & DESIGN:** CloudWatch alarms/metrics + X-Ray tracing docs + FinOps chargeback models. ADR #12: cost governance (spend-per-department attribution, throttling alarms, p95/p99 SLOs).
- **Tue Dec 15 · BUILD:** CloudWatch alarms for Bedrock throttling + latency percentiles (p95/p99); X-Ray traces across API GW → Lambda → Bedrock → OpenSearch.
- **Wed Dec 16 · INTEGRATE & MEASURE:** Cost-attribution dashboard verified against real traffic — **spend-per-department $** (cost) · **alarm accuracy on p95/p99** (quality) · **request latency percentiles** (latency). Then **work the Module-1 problem aloud:** H100 cluster sizing for 200 concurrent users at 16k context on Llama 3.1 70B (VRAM + KV-cache + throughput).
- **Thu Dec 17 · DRILL:** **DSA mock screen (recorded): 2 LeetCode Mediums in 45 min** — talk through your approach as you code. LLD spoken: metrics collector & aggregator.
- **Fri Dec 18 · MOCK & BANK:** STAR 12: Trade-offs Under Budget Constraints (accuracy vs. cloud cost). Bank +10. Month-3 review: mental models 9–12 + **optional AWS SA Associate exam window.**

---

# MONTH 4 — Evals, Tracing, Polish & the Interview Gauntlet

## Week 13 (Dec 21 – Dec 25) — Evaluation Harness (Ragas & DeepEval) *(Christmas week: shift missed days to the weekend — protect the CI eval gate build Tue–Wed)*
- **Mon Dec 21 · READ & DESIGN:** Ragas docs (Faithfulness, Context Precision/Recall definitions) + DeepEval + eval-driven-development essays. ADR #13: continuous eval (golden dataset, CI gate at 0.85, shadow testing, rollback triggers).
- **Tue Dec 22 · BUILD:** Stand up the Ragas + DeepEval pipeline; generate the synthetic golden dataset of 50 question-answer-context pairs.
- **Wed Dec 23 · INTEGRATE & MEASURE:** CI/CD GitHub Action that **blocks PRs** if Context Precision or Faithfulness < 0.85; run a red/green test to prove the gate fires. **Measure (quality / latency / cost):** Faithfulness + Context Precision vs. 0.85 gate (quality) · eval pipeline duration (latency) · eval cost per run (cost).
- **Thu Dec 24 · DRILL:** DSA review speed-run: arrays/graphs/DP — rebuild pattern flashcards, quiz aloud. LLD spoken: eval runner with pluggable metrics.
- **Fri Dec 25 · MOCK & BANK:** STAR 13: Preventing Bad Deployments (silent prompt regression caught by evals). Bank +10.

## Week 14 (Dec 28 – Jan 1) — OpenTelemetry & Arize Phoenix
- **Mon Dec 28 · READ & DESIGN:** OTel spec basics (spans, context propagation, sampling) + Phoenix docs + Google SRE monitoring chapters. ADR #14: distributed tracing for the multi-service AI pipeline.
- **Tue Dec 29 · BUILD:** Deploy self-hosted Phoenix; instrument OTel tracers across Track A (LangGraph, Qdrant, FastAPI).
- **Wed Dec 30 · INTEGRATE & MEASURE:** Visualize execution DAGs; document cold-start vs. warm-cache latency. **Measure (quality / latency / cost):** trace/span coverage completeness (quality) · TTFT decomposition by span (latency) · $/1k queries with tracing enabled (cost).
- **Thu Dec 31 · DRILL:** DSA review: trees/heaps/concurrency (spoken pattern quiz). LLD spoken: OTel span exporter middleware for streaming LLM calls.
- **Fri Jan 1 · MOCK & BANK:** STAR 14: Debugging a Distributed Latency Spike. **LinkedIn write-up #3:** "Evals + tracing: what separates production AI teams from demo teams." Bank +10. *(Holiday flexibility: shift missed days to the weekend — protect Week 15.)*

## Week 15 (Jan 4 – Jan 8) — Portfolio Polish & the Full Interview Gauntlet
- **Mon Jan 4 · POLISH:** Finalize Track A + Track B documentation and architecture diagrams — READMEs must read as **architecture essays** (problem → constraints → decisions → *measured numbers* → trade-offs), with ADR links, not code dumps. Code freeze.
- **Tue Jan 5 · WALKTHROUGHS:** Record 3-minute architecture walkthroughs of both projects. Replay, critique, re-record until sharp and answer-first.
- **Wed Jan 6 · GAUNTLET A:** **Round 1 (Bank/Barclays style):** DSA screen sim + "Design a secure financial chatbot with audit logs & KYC data." **Round 2 (Startup style):** "Design async streaming with retry logic" + spoken deep dive on vLLM/PagedAttention — *cite your own Week 7 measurements.*
- **Thu Jan 7 · GAUNTLET B:** **Round 3 (Consultancy style):** 12-month GenAI migration case for a legacy enterprise (MECE, answer-first, TCO + ROI). **McKinsey PEI sim:** 5–6 levels deep on your strongest company story (Personal Impact, Inclusive Leadership, Entrepreneurial Drive).
- **Fri Jan 8 · GAUNTLET C:** **BCG X fit sim** + executive-translation drill: 5 technical concepts (PagedAttention, HNSW recall, continuous batching, RRF, eval gates) → business value in **60 seconds each**. Review 100 bank Q&As aloud.

## Week 16 (Jan 11 – Jan 15) — Release, Behavioral Mastery & the Application Machine
- **Mon Jan 11 · RELEASE:** End-to-end integration tests across both repos; fix only critical failures; tag **v1.0 releases** on GitHub with open licenses.
- **Tue Jan 12 · BEHAVIORAL:** Final interrogation of all 10 core leadership questions (disagreement with leadership, ambiguity, technical debt, mentoring); replay every STAR recording; polish the weakest three.
- **Wed Jan 13 · NEGOTIATION + APPLICATION MACHINE:** Compensation benchmarks for all 3 archetypes; write and rehearse negotiation scripts. Architecture-led resume (decisions & outcomes first, tools second). LinkedIn overhaul. Target list of **30 companies** across the 3 archetypes + referral map + outreach drafts.
- **Thu Jan 14 · PORTFOLIO FREEZE:** Verify every repo README leads with the architecture diagram, links its ADRs, and demos in one command. Final mental math review — full worked example aloud.
- **Fri Jan 15 · FINALE:** Rehearse your 2-minute "who I am" pitch (Minto Pyramid). Full spoken speed-run of the bank's hardest 50 questions. **Applications go out Monday, Jan 18, 2027. You are interview-ready.** 🎯

---

## The Interview-Cracker Loop (memorize this)
> **READ → DESIGN IT → BUILD IT → MEASURE IT → SAY IT ALOUD → DRAW IT FROM MEMORY → DEFEND IT UNDER PRESSURE**
Every topic passes all 7 stages before it counts as "learned." The running system is your proof; the reps are your edge.

## Weekly Output Checklist (self-audit every Friday)
1. ✅ 1 mental model page + 1 ADR written **before** code (Mon)
2. ✅ Working, committed code for the week's component (Tue)
3. ✅ End-to-end integration green + **3 measured numbers captured — one per category: quality / latency / cost** (Wed)
4. ✅ 2 timed DSA problems + 1 spoken LLD (Thu)
5. ✅ Whiteboard-from-memory + 10 new bank Q&As + 1 STAR rehearsal (+ mock on mock weeks) (Fri)
6. ✅ 20 old bank Q&As reviewed + daily 10-min mental math
7. ✅ Build time stayed within the 2.5–3 hr cap — if you blew through it, you're building instead of architecting; stub and advance

## Mock Interview Rotation (recorded — always out loud, always timed)
- **Week 4, 5, 8:** Startup → Bank → MBB (60-min full system-design mocks)
- **Week 11:** Bank DSA screen simulation (75 min) · **Week 12 Thu:** recorded DSA mock screen (2 Mediums / 45 min)
- **Week 15:** Full gauntlet — 3 rounds + McKinsey PEI + BCG X fit
- **Total reps by Jan 15: 4 full system-design mocks + 2 DSA screens + the Week 15 gauntlet; 30+ spoken case/STAR drills; 300+ rehearsed Q&As — backed by Track A + Track B v1.0 releases and a chaos-tested Track C gateway.**


---

## Operational Guardrails (added from external review — execute from Day 1)

### 1. Day 3 measurement = 3 FIXED categories (never ad-hoc)
Every week's three numbers must cover quality, latency, and cost — never three of the same kind:
- **Quality:** Δ Recall@5 (dense vs. hybrid vs. RRF) or eval-score delta vs. last week's baseline.
- **Latency:** TTFT + TPOT decomposition by span (ingest / retrieve / rerank / generate).
- **Cost:** $ per 1k queries, or GPU VRAM per concurrent user.
Log all three in `measurements.md` — these ARE the empirical evidence you cite in interviews.

### 2. OpenSearch Serverless billing trap (Weeks 9–10, Track B)
- Default min capacity = 4 OCUs (2 indexing + 2 search) ≈ $0.24/OCU/hr ≈ **~$700/mo if left idle**.
- **Local-first:** ALL integration runs against a containerized local OpenSearch (`opensearchproject/opensearch:2.x`, single node, security plugin disabled).
- Deploy to AWS **only** for the final measurement run — time-boxed to ≤2 hrs, then **teardown immediately** (`aws opensearchserverless delete-collection`). Script both create + delete in `track-b/scripts/`.
- Before ANY AWS resource is provisioned: AWS Budgets alert + billing alarm at **$10**.
- Never leave a Serverless collection running overnight. Verify teardown before ending the session.

### 3. Stub-and-advance ≠ writing boilerplate from scratch
- Pre-stage reference repos and templates on the **Sunday before each build week** (30 min):
  - Before Week 5: LangGraph state-graph examples + Pydantic v2 validation patterns, pinned into `templates/`.
  - Before Week 9: CDK/Terraform module skeletons + docker-compose for local OpenSearch.
- During the 2.5–3 hr build cap, boilerplate (auth stubs, Dockerfiles, clients) is COPIED from templates; only core business logic is hand-written.

### 4. daily-goals.md vs plan.md — no duplication drift
- `plan.md` = single source of truth for scope, architecture, decisions. This file = execution log + weekly checklists only.
- Any scope change is recorded in plan.md FIRST; never re-specify architecture here.
- Friday self-audit: reconcile the two — a mismatch gets fixed in plan.md, not in this file.

### 5. Thursday LeetCode cap (protects the 2 problems/week cadence)
- 60–90 min hard cap. Target: 2 problems, 100% test pass.
- Not passing at 45 min/problem → read the editorial, re-solve cold Sunday morning. Never bleeds into Friday's mock slot.
- 16 weeks × 2 = 32 problems. That's the plan — do not chase volume.

### 6. Monday ADR load — Sunday pre-read
- Sunday 45-min pre-read: ONLY the paper's Architecture / Complexity / Empirical Evaluation sections (skip intro + related work).
- Monday is for DRAFTING the mental model + ADR — never first contact with the paper.

### 7. Festival-week buffer (Weeks 5–6, late Oct–early Nov, Pune)
- Treat lost dev days as pre-planned: the stub-and-advance rule applies with extra force that fortnight.
- Move template pre-staging (Guardrail 3) into Week 4's Sunday.
- Holiday-safe fallback: company-track artifacts (ADR #3, STAR stories 5–6) — no GPU, no AWS, no blockers.

### Day 1 Preparation (Mon, Sep 28, 2026) — repo setup
```bash
mkdir -p track-a/{src,tests,adr} track-b/{src,scripts,adr} track-c/{src,adr} \
         architecture-notes adr whiteboards templates
touch measurements.md
git init && git branch -m main
```
First commit = this file + plan.md. Every subsequent commit maps to a week number.
