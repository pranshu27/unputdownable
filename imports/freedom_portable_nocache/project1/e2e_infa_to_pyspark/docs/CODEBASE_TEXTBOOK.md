# The Agentic Informatica → PySpark Codebase — A Textbook Walkthrough

> Read this top-to-bottom and you will understand the entire system: what problem it solves,
> why each design choice was made, and exactly which file and function implements each idea.
> Every section links to the real code so you can jump straight to the source.

---

## Part 0 — The problem, in one paragraph

A bank/insurer (the `RS_EDW_PROD` repository) has years of ETL logic locked inside
**Informatica PowerCenter** mappings. Those mappings read from a **Teradata** enterprise data
warehouse and write curated tables. The company wants to modernize onto a **PySpark +
Apache Iceberg lakehouse**. Rewriting hundreds of mappings by hand is slow and error-prone.
This project is an **agentic system** that reads the PowerCenter XML exports, understands them,
designs a target model, and **generates PySpark code** — with retrieval grounding, evaluation,
safety guardrails, an automated critic, and a human approval gate.

---

## Part 1 — Where the data actually comes from (and why Iceberg)

You said you're new to Iceberg, so let's ground everything in the real source first.

### 1.1 The original data source

Open any export, e.g. [wf_4202_fnd_rltinteraction.XML](project1/app_CALCULATE_EINTERACTION/wf_4202_fnd_rltinteraction.XML).
Two facts matter:

- The **repository catalog** runs on Oracle:
  `<REPOSITORY NAME="RS_EDW_PROD" ... DATABASETYPE="Oracle">`. This is just where PowerCenter
  stores its *metadata* (the mapping definitions). It is **not** the data.
- The **actual data sources are Teradata**:
  `<SOURCE ... DATABASETYPE="Teradata" DBDNAME="Foundation" OWNERNAME="FND_EINTR_DB" NAME="RLTInteractionAgreement">`.
  The tables live in Teradata layers named *Foundation*, *Work*, and *Shared*.

So the real lineage is:

```
Teradata EDW (Foundation / Work / Shared)
        │   read by
        ▼
Informatica PowerCenter mappings  (logic we are migrating)
        │   wrote to
        ▼
Curated warehouse tables (gold)
```

Our migration target replaces the Informatica+Teradata middle/right with **PySpark on an
Iceberg lakehouse**:

```
Teradata (JDBC)  ──read──▶  PySpark (DataFrame API / Spark SQL)  ──write──▶  Iceberg gold tables
```

The PySpark generation agent emits exactly this: a `spark.read.format('jdbc')` against Teradata
(or `spark.sql(<verbatim override>)`), transformations, and an Iceberg `MERGE`.

### 1.2 What is Apache Iceberg (from scratch)

A plain data lake is "files in a folder" (Parquet on S3/ADLS). That is cheap but dumb: there
are no transactions, no schema rules, and "what did this table look like last Tuesday?" is
unanswerable. **Apache Iceberg is a table format that sits on top of those files and gives a
folder of Parquet the powers of a real database table.** It does this with a layer of metadata
(a current *snapshot* pointing at *manifest* files that list the data files).

What that buys us, and why it matters for *this* migration specifically:

| Iceberg capability | Why this project needs it |
| --- | --- |
| **ACID transactions** | Informatica `Update Strategy` (DD_INSERT/DD_UPDATE) becomes an atomic `MERGE INTO`. No half-written tables. |
| **MERGE / upsert** | The mappings are incremental upserts keyed on business keys (e.g. `InteractionGroup_Id`). Iceberg `MERGE` expresses that natively — see the Iceberg writer agent. |
| **Schema evolution** | Add/rename/drop a column without rewriting the table — safe as the model evolves. |
| **Hidden partitioning** | Partition by a derived value (e.g. month of a date) without callers knowing — fewer human errors than Hive-style partition columns. |
| **Time travel / snapshots** | Parity-test the migration: compare "Iceberg table today" against the legacy output, or roll back a bad load. |
| **Engine-agnostic** | Spark, Trino, Flink, etc. all read the same table. The lakehouse isn't locked to one tool the way Teradata was. |

Mental model: **Parquet = the pages; Iceberg = the table of contents + the librarian that
guarantees everyone sees a consistent book.** That's why the generated code targets Iceberg
instead of writing bare Parquet.

---

## Part 2 — The big picture (architecture)

The system is built on **Microsoft AutoGen** (`autogen_core`). Every step is an **agent** — a
small object that receives a typed message and returns a typed message. Two messaging patterns
run on one `SingleThreadedAgentRuntime`:

```
PowerCenter XML dump
   │   pre_process_shared_folder() → canonical node dicts
   ▼
[Phase 1 — pub/sub + barrier]
   PCMessage ──publish──▶ PCExtractorAgent ──▶ PCResultCollectorAgent (CollectorState barrier)
   ▼
   Input guardrails (PII/secret redaction)   +   RAG knowledge base build (chunk→embed→index)
   ▼
[Phase 2 — orchestrator/worker]
   UserTask ─▶ OrchestratorAgent
                 ├─ 1. DataModellerAgent     → field-level Source-to-Target Mapping (STTM)  [uses RAG as a tool]
                 ├─ 2. PySparkGenerationAgent → PySpark per node (consumes the STTM)  → output guardrails
                 ├─ 3. IcebergWriterAgent     → MERGE / write
                 ├─ 4. ReviewAgent            → static parity review
                 ├─ 5. CriticAgent            → adversarial score + requires_human_review
                 └─ 6. human_review_gate      → approve / hold
                 ▼
              FinalResult { data_model(STTM), pyspark_nodes, iceberg_write, review, guardrails, critic, human_decision }
```

The runtime wiring lives in
[pyspark_codegen_workflow.py](project1/e2e_infa_to_pyspark/app/orchestrators/pyspark_codegen_workflow.py).

### 2.1 Two AutoGen messaging patterns

- **Publish/subscribe (broadcast).** `runtime.publish_message(msg, topic_id=...)` sends to every
  agent subscribed to that topic and returns nothing. Used for fan-out extraction.
- **Send (addressed request/response).** `runtime.send_message(msg, AgentId(name,"default"))`
  sends to one agent and returns its handler's value. Used by the orchestrator to call workers.

The barrier that makes async fan-out behave synchronously is the key trick — see Part 4.

### 2.2 Why AutoGen, not LangChain?

Both frameworks can call an LLM, but they optimise for different shapes of problem. This system
is a **multi-agent, message-passing pipeline with a barrier and a human gate** — which is
AutoGen's *core* model and only an add-on in LangChain.

| Concern | AutoGen (chosen) | LangChain |
| --- | --- | --- |
| Primary abstraction | **Actor / agent** that receives a typed message and returns one | **Chain** of prompt → parser → tool around an LLM |
| Multi-agent coordination | First-class (`RoutedAgent`, runtime, pub/sub + send) | Separate library (LangGraph) bolted on |
| Messaging patterns | **Both** broadcast pub/sub *and* addressed request/response on one runtime | No first-class topic bus; hand-roll asyncio fan-out |
| Inter-agent contracts | **Typed dataclasses** (`PCMessage`, `WorkerTask`, `FinalResult`) | Mostly dicts/strings; contract lives in prompt conventions |
| Determinism | Explicit `SingleThreadedAgentRuntime` loop; easy to test/pin | ReAct-style tool loops add nondeterminism |
| Instrumentation seam | Inject a client into a plain object → wrap it (`InstrumentedChatClient`) with **zero agent edits** | Couples to LangChain's own callback model |

Why each row matters *here*:

1. **The mental model matches the problem.** The pipeline literally *is* N specialized agents
   passing structured work to each other (extractor → modeller → generation → iceberg → review →
   critic → human gate). AutoGen's actor model is that natively; in LangChain the multi-agent
   layer is LangGraph, an extra abstraction on top.
2. **We use both messaging patterns.** Phase 1 fans every node out over **pub/sub**; Phase 2 uses
   **addressed send** for orchestrator→worker calls. AutoGen ships both on one runtime.
3. **The barrier needs a controllable runtime.** The `CollectorState` barrier (set
   `expected_count` *before* publishing, then `wait_for_results`) relies on AutoGen's
   `SingleThreadedAgentRuntime` deterministic message loop (Part 4). In LangChain you'd hand-roll
   the synchronization.
4. **Typed contracts over stringly-typed chains.** Agents declare exactly what they consume and
   produce via dataclasses, so boundaries are explicit and testable (20/20 offline tests).
5. **Determinism for a migration tool.** A code-generation tool must be reproducible; AutoGen's
   explicit runtime plus the pinned client (Part 9) keeps the loop inspectable.
6. **Clean instrumentation.** Because every agent just takes a model client, we added per-step
   recording + Langfuse tracing by *wrapping* that client — no agent code changed (Part 8.5).

**Where LangChain would win:** if the job were mostly RAG plumbing (loaders, splitters,
retrievers, off-the-shelf chains), LangChain's large integration catalog would save time. We
deliberately wrote a small, purpose-built RAG layer (Part 5) instead, so we didn't need it and
avoided the dependency weight. Note Langfuse is framework-agnostic — it works with either, and we
integrated it via the client proxy rather than any AutoGen-specific hook.

> **One-line summary:** AutoGen was chosen because this is a *coordination problem between many
> typed agents with a barrier and a human gate* — AutoGen models that natively, whereas LangChain
> is primarily an LLM-chain/RAG toolkit where multi-agent orchestration is an add-on.

---

## Part 3 — Reading the PowerCenter XML

### 3.1 The parser

[xml_parser.py](project1/e2e_infa_to_pyspark/app/utils/xml_parser.py) turns an export into plain
dicts. Highlights:

- `_parse_source` / `_parse_target` pull field name, datatype, precision, key type.
- `_parse_transformation` pulls ports (with **expressions**), and critically the
  `Sql Query` table attribute → `sql_override`, plus `Filter Condition`, `Join Condition`,
  and group-by ports.
- `parse_powercenter_xml` is **multi-FOLDER aware**: a single export can contain a shared
  source/target folder *and* the application folder that owns the mappings, so it aggregates
  sources/targets/mappings across every `<FOLDER>`.

### 3.2 Flattening to "canonical nodes"

[pc_file_processor.py](project1/e2e_infa_to_pyspark/app/utils/pc_file_processor.py) →
`flatten_mapping_to_nodes` emits an **ordered** list: `SOURCE → TRANSFORMATION → TARGET`. Each
item is a dict like `{"node_class": "SOURCE", "name": ..., "fields": [...], "sql_override": ...}`.
A "canonical node" is the unit of work that flows through the whole pipeline — it is what gets
extracted, chunked for RAG, and compiled to PySpark.

`pre_process_shared_folder(folder, focus_mapping)` walks the dump and returns all canonical
nodes (optionally filtered to one mapping).

---

## Part 4 — Phase 1: extraction (pub/sub + barrier)

### 4.1 The contracts

[pyspark_topics.py](project1/e2e_infa_to_pyspark/app/communication/pyspark_topics.py) holds the
topic-name constants. [pyspark_types.py](project1/e2e_infa_to_pyspark/app/communication/pyspark_types.py)
holds the message dataclasses: `PCMessage`, `UserTask`, `WorkerTask`, `WorkerTaskResult`,
`FinalResult`, `HumanReviewRequest`, `HumanReviewDecision`.

### 4.2 Extractor and collector

- [pc_extractor_agent.py](project1/e2e_infa_to_pyspark/app/agents/pc_extractor_agent.py): a
  `RoutedAgent` subscribed (`@type_subscription`) to the extraction topic. It normalizes one
  node and publishes the result to the response topic. It **soft-fails** (publishes an error
  dict instead of raising) so one bad node never stalls the run.
- [result_collector_agent.py](project1/e2e_infa_to_pyspark/app/agents/result_collector_agent.py):
  holds a `CollectorState` with an `asyncio.Event`, an `expected_count`, and a counter. When the
  count of collected responses reaches the expected number, it sets the event.

### 4.3 The barrier invariant

In the workflow, **`set_expected_count(n)` is called BEFORE publishing** the N messages, then
the workflow `await`s `wait_for_results(timeout=300)`. If you set the count *after* publishing,
a fast extractor could finish before the barrier is armed and you'd deadlock. This ordering is a
load-bearing detail.

---

## Part 5 — RAG: a proper retrieval pipeline

This is the part that gives the data modeller *cross-file* knowledge. It is a real RAG pipeline:
**chunk → embed → index → retrieve**, with a swappable vector backend.

### 5.1 Chunking — and why we chose structure-aware chunks

[chunking.py](project1/e2e_infa_to_pyspark/app/rag/chunking.py) documents the strategy menu and
implements the winner. The trade-off: a chunk is both *the unit you embed* and *the unit you
hand back to the LLM*, so its boundaries decide retrieval quality.

| Strategy | Idea | Why not here |
| --- | --- | --- |
| Fixed-size windows | every N tokens | cuts a field list / expression in half |
| Sliding window + overlap | fixed-size, overlapping | duplicates text, inflates index |
| Sentence / recursive split | split on punctuation hierarchy | XML metadata has no sentences |
| Semantic chunking | new chunk when embedding distance spikes | an embedding call per sentence; overkill |
| **Structure-aware (chosen)** | **one Informatica node = one chunk** | **already-parsed, self-contained, exactly the grain a modeller queries** |

Because `flatten_mapping_to_nodes` already gives us discrete, self-describing nodes, the natural
boundary is **one node = one chunk**. `render_node()` turns a node into a labelled text block
(`NODE_CLASS:`, `FIELDS:`, `SQL_OVERRIDE:` …) so both the embedder and the LLM can read its
structure. For the rare oversized node, `_split_with_overlap` applies a **size-bounded fallback
with overlap** so no chunk blows the embedding window. Output: `Chunk` records ready to embed.

### 5.2 Embeddings — two providers, one interface

[embeddings.py](project1/e2e_infa_to_pyspark/app/rag/embeddings.py):

- `AzureOpenAIEmbedding` — the production path; uses an Azure embedding deployment
  (e.g. `text-embedding-3-small`, 1536 dims). Enabled by setting `AZURE_EMBEDDING_DEPLOYMENT`.
- `HashingEmbedding` — a deterministic **feature-hashing** fallback (the "hashing trick" + a
  sublinear-TF weight + signed buckets + bigrams). No network, fully reproducible, so unit tests
  and air-gapped runs still produce *real* vectors and exercise the *real* nearest-neighbour
  path. Lower semantic quality, identical mechanics.
- `get_embedding_provider()` picks Azure when configured, else hashing. Both return
  **L2-normalized** vectors, so cosine similarity == dot product.

### 5.3 Vector store — in-memory and pgvector

[vector_store.py](project1/e2e_infa_to_pyspark/app/rag/vector_store.py) defines one interface
(`upsert`, `search`, `count`) with two implementations:

- `InMemoryVectorStore` — brute-force cosine in process. Deterministic; used by tests/offline.
- `PgVectorStore` — **Postgres + pgvector**. Stores vectors in a `vector(dim)` column and runs
  nearest-neighbour search *in the database* with the `<=>` cosine-distance operator and an
  IVFFlat index. Notable production-readiness details learned against the real Azure Postgres:
  - On managed Postgres a non-admin **cannot** `CREATE EXTENSION vector`, but an admin may have
    pre-created it. `_ensure_extension()` checks `pg_extension` first and only creates if missing.
  - The login often lacks `CREATE` on `public`, so the store uses a dedicated **`rag` schema**
    it owns (`rag.rag_chunks`).
  - `upsert` uses a single batched `executemany` (row-by-row over VPN was far too slow).

### 5.4 The knowledge base + RAG-as-a-tool

[knowledge_base.py](project1/e2e_infa_to_pyspark/app/rag/knowledge_base.py) ties it together:
`build_from_folder` parses every XML, chunks each node, embeds all chunks, picks a backend
(`RAG_BACKEND=pgvector|memory`), and indexes them. `retrieve(query, k)` embeds the query and
runs nearest-neighbour search. `build_context()` packs top-k hits into a token-budgeted string.

Crucially, `as_tool()` returns a `RagTool` with a `search(query, k)` callable. This is **RAG as a
tool**: the data modeller doesn't get one pre-baked blob — it actively *queries* the KB with
targeted questions (its sources, its target, likely lookups), exactly like an agent calling a
tool to gather just-in-time evidence.

---

## Part 6 — Phase 2: the orchestrator and its workers

[orchestrator_agent.py](project1/e2e_infa_to_pyspark/app/agents/orchestrator_agent.py) handles a
`UserTask` and runs the six-step flow, returning a `FinalResult`. Walk the steps:

### 6.1 Step 1 — the Data Modeller produces a field-level STTM

[data_modeller_agent.py](project1/e2e_infa_to_pyspark/app/agents/data_modeller_agent.py) +
[data_modeller_prompt.py](project1/e2e_infa_to_pyspark/app/prompt_engineering/prompts/data_modeller_prompt.py).

The agent first calls the RAG tool (`_gather_rag_context`) with queries derived from the current
mapping's nodes, assembles the retrieved context, then asks the LLM to emit a **source-to-target
mapping (STTM)**: for *every* target field — its source table, source field(s), transformation
type (`direct | expression | aggregate | lookup | derived | constant`), the exact rule, datatype,
and nullability — plus a compact model (entities, relationships, SCD strategy, conformed dims).

The STTM is the **contract** for code generation: it says precisely how each output column is
built, so the generated PySpark is field-accurate rather than guessed.

### 6.2 Step 2 — PySpark generation, fed by the STTM

The orchestrator parses the STTM JSON and threads `source_to_target` into each generation call
via `gen_meta`. [pyspark_generation_agent.py](project1/e2e_infa_to_pyspark/app/agents/pyspark_generation_agent.py)
includes that STTM block in its prompt, and
[pyspark_generation_prompt.py](project1/e2e_infa_to_pyspark/app/prompt_engineering/prompts/pyspark_generation_prompt.py)
tells the model to treat it as the authoritative field contract. Generation is **node-by-node**,
threading previously generated DataFrame variable names so each fragment references the correct
upstream `_df`. The translation rubric maps Source Qualifier→`spark.sql`/JDBC, Expression→
`withColumn`, Joiner→`join`, Aggregator→`groupBy().agg()`, etc. SQL overrides are wrapped
**verbatim** — never rewritten.

Each generated fragment passes through **output guardrails** before being kept.

### 6.3 Step 3 — Iceberg writer

[iceberg_writer_agent.py](project1/e2e_infa_to_pyspark/app/agents/iceberg_writer_agent.py) emits
the `MERGE INTO <target> ... ON <merge_keys>` (or write) statement — the upsert that realizes the
Informatica Update Strategy on the Iceberg table.

### 6.4 Steps 4–6 — Review, Critic, Human gate

- [review_agent.py](project1/e2e_infa_to_pyspark/app/agents/review_agent.py): a static
  parity-readiness review of the whole bundle.
- [critic_agent.py](project1/e2e_infa_to_pyspark/app/agents/critic_agent.py) +
  [critic_prompt.py](project1/e2e_infa_to_pyspark/app/prompt_engineering/prompts/critic_prompt.py):
  an **adversarial** reviewer that scores correctness / completeness / sql_fidelity / safety /
  determinism (0–1) and returns `verdict ∈ {approve, revise, reject}`, a confidence, blocking
  issues, and `requires_human_review`. It sets `requires_human_review=true` whenever confidence
  < 0.85 or there are blocking issues, and soft-fails *closed* (revise + needs-human on error).
- [human_gate.py](project1/e2e_infa_to_pyspark/app/agents/human_gate.py): `human_review_gate`.
  In `auto` mode it auto-approves only when the critic is confident and unflagged; otherwise it
  holds for a human. In `interactive` mode it prints the verdict and prompts at the console.
  Returns a `HumanReviewDecision` recorded in the `FinalResult`.

This is the "machine validates first, then a human" flow you asked for: the **critic** is the
machine validator, the **gate** is the human one.

---

## Part 7 — Guardrails (safety in both directions)

[engine.py](project1/e2e_infa_to_pyspark/app/guardrails/engine.py). Each guardrail has a `.check`
returning an action (`ALLOW / REDACT / WARN / BLOCK`); the `GuardrailEngine` threads redactions
and yields a `GuardrailReport`.

- **Input** (`default_input_engine`, applied to every node before the LLM in the workflow):
  `PIIGuardrail` (SSN/email/phone/card/IP), `SecretsGuardrail` (passwords/keys/JDBC creds),
  `PromptInjectionGuardrail`.
- **Output** (`default_output_engine`, applied to each generated fragment in the orchestrator):
  `DestructiveSQLGuardrail` (blocks `DROP`/`TRUNCATE`/WHERE-less `DELETE`), `SchemaGuardrail`
  (required keys present), `SQLOverrideFidelityGuardrail`.

---

## Part 8 — Evaluation (offline metrics + production strategies)

### 8.1 Deterministic, CI-friendly metrics

[metrics.py](project1/e2e_infa_to_pyspark/app/evaluation/metrics.py): `rouge_n` (n-gram overlap),
`rouge_l` (LCS — order-aware, good for code line order), `token_f1`, `exact_match`, and
**structural** checks (`is_parseable_python` via `ast.parse`, `references_expected` for required
symbols). `evaluate()` returns an `EvaluationResult`; `evaluate_batch()` averages across a set —
ready to be a **CI gate** that fails a PR when `overall_f1` regresses.

### 8.2 Production strategies

[prod_strategies.py](project1/e2e_infa_to_pyspark/app/evaluation/prod_strategies.py):

1. **`embedding_similarity`** — cosine of embedding vectors; catches semantically-equivalent
   code that ROUGE would mark different (`F.col('a')-F.col('b')` vs `expr('a - b')`).
2. **`execution_parity`** — the gold standard: run the generated PySpark and the legacy/golden
   output on the *same* sample data and diff **row count + schema + per-column checksums**. If
   the data matches, the translation is correct regardless of style. (Scaffold: you pass in two
   Spark DataFrames.)
3. **`llm_judge`** — an async rubric judge (a strong model scores correctness/fidelity/safety),
   pairs with the critic + human gate.
4. **CodeBLEU** (AST + dataflow aware) — noted as a drop-in for CI.

`production_scorecard()` combines offline metrics + embedding similarity in one dict with no
Spark/LLM required.

---

## Part 8.5 — Observability (persist every step + Langfuse tracing)

When something looks wrong, you want to see *exactly* what each step received and produced —
the parsed XML, the redacted nodes, the RAG context, and the precise prompt + output of every
LLM call. The [app/observability/](app/observability/__init__.py) package gives you that, two ways.

### 8.5.1 Persist every step to disk — `RunRecorder`

[run_recorder.py](app/observability/run_recorder.py) writes an ordered, human-readable trail per
run under `runs/<timestamp>_<mapping>/`:

```
runs/20260625_153000_m_4202.../
  manifest.json              # run metadata + ordered index of every artifact
  00_parsed_nodes.json       # canonical nodes parsed from the PowerCenter XML
  01_redacted_nodes.json     # nodes after input guardrails (PII/secret redaction)
  02_rag_context.txt         # cross-file context string handed to the modeller
  02_rag_hits.json           # structured retrieval hits for the focus query
  03_extracted_nodes.json    # normalized nodes after the extraction barrier
  llm/
    01_data_modeller.input.json      / .output.txt   # exact prompt + raw LLM output
    02_pyspark_generation.input.json / .output.txt
    ...                                              # one pair per LLM call, in order
  99_final_result.json       # the orchestrator FinalResult
```

This is the literal answer to “store data at every step, from parsed XML to what the LLM is
producing.” Every method is best-effort: a disk failure logs a warning but never breaks the run.
`runs/` is gitignored because the artifacts contain parsed source data + full LLM payloads.

### 8.5.2 Trace to Langfuse — `Tracer` (no-op fallback)

[tracing.py](app/observability/tracing.py) `build_tracer()` returns a **Langfuse**-backed tracer
*only* when the SDK is importable **and** both `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`
are set; otherwise it returns a silent `NoOpTracer`. So offline/CI runs stay green with no
config. It emits one **trace** per run, one **generation** per LLM call (input, output, token
usage, labelled by step), and **events** for non-LLM milestones (parsed XML, RAG retrieval,
extraction barrier, final result).

### 8.5.3 How it hooks in without touching agents — `InstrumentedChatClient`

The clever bit: agents are untouched. [instrumented_client.py](app/observability/instrumented_client.py)
is a transparent proxy around the Azure client. The workflow hands each agent a copy *labelled*
with its step name:

```python
def labelled(step):
    return InstrumentedChatClient(client, step, recorder=recorder, tracer=tracer)

await DataModellerAgent.register(
    runtime, "data_modeller",
    lambda: DataModellerAgent(labelled("data_modeller"), rag_tool=rag_tool),
)
```

When the agent calls `self._model_client.create(...)`, the proxy records the input/output and
emits a Langfuse generation, then delegates everything else (`count_tokens`, `model_info`, …)
to the real client via `__getattr__`. Wiring lives in
[pyspark_codegen_workflow.py](app/orchestrators/pyspark_codegen_workflow.py); toggle with the
`record` / `trace` params or the `--no-record` / `--no-trace` CLI flags.

---

## Part 9 — Configuration, secrets, and the model client

[azure_openai.py](project1/e2e_infa_to_pyspark/app/config/azure_openai.py) builds the shared
`azure_client`. It reads env aliases (`AZURE_OPENAI_API_KEY/_API_BASE`, `AZURE_DEPLOYMENT`,
`AZURE_API_VERSION`), normalizes `gpt5-mini → gpt-5-mini`, and **omits `temperature`/`seed` for
the GPT-5 family** (which only supports default sampling) while pinning `temperature=0, seed=8350`
for gpt-4o — determinism where the model allows it, prompt-enforced determinism otherwise.

Secrets live in `.env` (gitignored): the Azure key and the **`POSTGRES_URL`** for pgvector.
`RAG_BACKEND` selects `pgvector` (real) or `memory` (offline). `.env.example` documents the keys
with placeholders. **Never commit the real `.env`; rotate the Postgres password after the demo.**

---

## Part 10 — Running it

```powershell
cd project1/e2e_infa_to_pyspark
pip install -r requirements.txt

# Offline tests (no Azure, no Postgres) — RAG/guardrails/eval all covered
python -m pytest tests/ -q

# Full pipeline (Azure required; pgvector used when RAG_BACKEND=pgvector + VPN)
python -m app.run --limit 3                # auto human-gate (CI mode)
python -m app.run --human interactive      # console approval of the critic verdict
python -m app.run --limit 3 --no-trace     # record to runs/ but skip Langfuse
python -m app.run --limit 3 --no-record    # skip per-step artifacts
```

Entry points: the CLI [run.py](run.py) and the FastAPI app
[main.py](app/main.py). Results are written to
`generated/<mapping>.result.json` containing the STTM, PySpark nodes, Iceberg write, review,
guardrail report, critic verdict, and human decision. The full per-step trail (parsed XML → each
LLM call → final result) is written under `runs/<ts>_<mapping>/` (see Part 8.5), and the result
JSON carries a `_run_dir` pointer to it.

---

## Part 11 — A concrete trace (`m_4202_dt_chn_rltinteractionagreement`)

1. `pre_process_shared_folder` reads the export and emits canonical nodes (Teradata sources like
   `RLTInteractionAgreement`, transformations, the gold target).
2. Input guardrails redact any secrets/PII in those node dicts.
3. The RAG KB indexes **~1,189 chunks** across all `wf_42xx` files into `rag.rag_chunks` in
   Azure Postgres (pgvector), or in memory offline.
4. The orchestrator asks the Data Modeller, which **queries the RAG tool** for the sources/target
   and emits an STTM: e.g. target `RltInteractionAgreement_Id ← direct from source`,
   measures `← aggregate (SUM …)`, lookups resolved from conformed dimensions.
5. For each node, the Generation agent compiles PySpark using the STTM (JDBC read from Teradata,
   `withColumn` expressions, joins), threading `_df` variables; output guardrails vet each piece.
6. The Iceberg writer emits `MERGE INTO lakehouse.gold_rltinteractionagreement ... ON
   InteractionGroup_Id, EIntrSource_Cd`.
7. Review → Critic → human gate decide whether it ships. Everything lands in the result JSON.

---

## Part 12 — From "great demo" to "production platform"

Already implemented: RAG (chunk+embed+pgvector), field-level STTM, guardrails (both directions),
ROUGE + production eval strategies, adversarial critic, human-in-the-loop, deterministic config,
**observability (per-step recorder + Langfuse tracing)**.

Natural next steps (also in
[architecture/03-rag-eval-guardrails.md](project1/e2e_infa_to_pyspark/architecture/03-rag-eval-guardrails.md)):
observability/tracing (OpenTelemetry, LangFuse), per-run token/cost accounting, retries +
rate-limiting + dead-letter queue, an embedding model + scheduled re-indexing, OpenLineage data
lineage, a **CI eval gate** wired to `evaluation/`, prompt versioning + A/B tests, agent memory /
feedback loops, and containerization + Helm/CI-CD for AKS.

---

## Appendix — File map

| Area | File |
| --- | --- |
| Runtime wiring | [orchestrators/pyspark_codegen_workflow.py](project1/e2e_infa_to_pyspark/app/orchestrators/pyspark_codegen_workflow.py) |
| Parsing | [utils/xml_parser.py](project1/e2e_infa_to_pyspark/app/utils/xml_parser.py), [utils/pc_file_processor.py](project1/e2e_infa_to_pyspark/app/utils/pc_file_processor.py) |
| Contracts | [communication/pyspark_topics.py](project1/e2e_infa_to_pyspark/app/communication/pyspark_topics.py), [communication/pyspark_types.py](project1/e2e_infa_to_pyspark/app/communication/pyspark_types.py) |
| Phase 1 agents | [agents/pc_extractor_agent.py](project1/e2e_infa_to_pyspark/app/agents/pc_extractor_agent.py), [agents/result_collector_agent.py](project1/e2e_infa_to_pyspark/app/agents/result_collector_agent.py) |
| Orchestrator | [agents/orchestrator_agent.py](project1/e2e_infa_to_pyspark/app/agents/orchestrator_agent.py) |
| Workers | [agents/data_modeller_agent.py](project1/e2e_infa_to_pyspark/app/agents/data_modeller_agent.py), [agents/pyspark_generation_agent.py](project1/e2e_infa_to_pyspark/app/agents/pyspark_generation_agent.py), [agents/iceberg_writer_agent.py](project1/e2e_infa_to_pyspark/app/agents/iceberg_writer_agent.py), [agents/review_agent.py](project1/e2e_infa_to_pyspark/app/agents/review_agent.py), [agents/critic_agent.py](project1/e2e_infa_to_pyspark/app/agents/critic_agent.py), [agents/human_gate.py](project1/e2e_infa_to_pyspark/app/agents/human_gate.py) |
| RAG | [rag/chunking.py](project1/e2e_infa_to_pyspark/app/rag/chunking.py), [rag/embeddings.py](project1/e2e_infa_to_pyspark/app/rag/embeddings.py), [rag/vector_store.py](project1/e2e_infa_to_pyspark/app/rag/vector_store.py), [rag/knowledge_base.py](project1/e2e_infa_to_pyspark/app/rag/knowledge_base.py) |
| Guardrails | [guardrails/engine.py](app/guardrails/engine.py) |
| Evaluation | [evaluation/metrics.py](app/evaluation/metrics.py), [evaluation/prod_strategies.py](app/evaluation/prod_strategies.py) |
| Observability | [observability/run_recorder.py](app/observability/run_recorder.py), [observability/tracing.py](app/observability/tracing.py), [observability/instrumented_client.py](app/observability/instrumented_client.py) |
| Prompts | [prompt_engineering/prompts/](app/prompt_engineering/prompts/data_modeller_prompt.py) |
| Config | [config/azure_openai.py](project1/e2e_infa_to_pyspark/app/config/azure_openai.py) |
| Entry points | [run.py](project1/e2e_infa_to_pyspark/app/run.py), [main.py](project1/e2e_infa_to_pyspark/app/main.py) |
