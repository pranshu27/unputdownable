# Agentic Informatica PowerCenter → PySpark Code Generation (wf_4202)

A multi-agent **AutoGen** backend that reverse-engineers Informatica PowerCenter mappings
into production **PySpark + Apache Iceberg** code. The architecture mirrors two real
production repos (the `des_*` reference backends): a **pub/sub extraction stage** and an
**orchestrator/worker generation stage**, both running on a single
`SingleThreadedAgentRuntime`.

This is **not** an ETL/compiler. Every transformation is done by an LLM-backed agent that
communicates over typed topics and message contracts.

- Input XML: `../app_CALCULATE_EINTERACTION/wf_4202_fnd_rltinteraction.XML`
  (medium complexity: 20 transformations — 10 Source Qualifier, 5 Expression, 2 Joiner,
  2 Aggregator, 1 Custom; 253 connectors)
- Focus mapping: `m_4202_dt_chn_rltinteractionagreement`

## Agents

| Agent | Pattern | Responsibility |
|-------|---------|----------------|
| `PCExtractorAgent` | pub/sub (`@type_subscription`) | Normalizes one PowerCenter node at a time into canonical metadata; publishes to the response topic. Soft-fails so the barrier always completes. |
| `PCResultCollectorAgent` | pub/sub + barrier | Collects extractor responses into `CollectorState` (asyncio.Event + expected_count). |
| `OrchestratorAgent` | orchestrator/worker | Handles a `UserTask`, dispatches node-by-node to workers via `send_message(AgentId(...))`, returns a `FinalResult`. |
| `DataModellerAgent` | worker (RAG-grounded) | Designs a logical model (entities, grain, PKs, SCD strategy) from the mapping + retrieved cross-file context. |
| `PySparkGenerationAgent` | worker | Compiles one canonical node into a PySpark DataFrame/Spark SQL fragment. |
| `IcebergWriterAgent` | worker | Produces the Iceberg `MERGE`/write statement for the target. |
| `ReviewAgent` | worker | Validates parity-readiness of the generated bundle. |
| `CriticAgent` | worker (adversarial) | Scores the artifact 0–1 (correctness/completeness/sql_fidelity/safety/determinism), emits a verdict and `requires_human_review`. |

Additional non-agent components: a **RAG knowledge base** (`app/rag/`), **input/output
guardrails** (`app/guardrails/`), an **evaluation harness** (`app/evaluation/`), and a
**human-in-the-loop gate** (`app/agents/human_gate.py`). See
[architecture/03-rag-eval-guardrails.md](architecture/03-rag-eval-guardrails.md).

## Communication contracts

- **Topics** (`app/communication/pyspark_topics.py`): string constants used by
  `@type_subscription` / `TopicId` — `PC_EXTRACTION_TOPIC_TYPE`,
  `PC_EXTRACTION_RESPONSE_TOPIC_TYPE`, `PYSPARK_GENERATION_TOPIC_TYPE`,
  `ICEBERG_WRITER_TOPIC_TYPE`, `REVIEW_TOPIC_TYPE`.
- **Messages** (`app/communication/pyspark_types.py`): dataclasses `PCMessage`,
  `PCFlowExtractionResponse`, `UserTask`, `WorkerTask`, `WorkerTaskResult`, `FinalResult`.

## Flow

```text
PowerCenter XML
   │  pre_process_shared_folder() → canonical node payloads
   ▼
[Phase 1 — pub/sub + barrier]
   PCMessage ──publish(PC_EXTRACTION_TOPIC_TYPE)──▶ PCExtractorAgent
                                                      │ PCFlowExtractionResponse
                                                      ▼
                                          PCResultCollectorAgent → CollectorState
   (set_expected_count(n) BEFORE publishing; wait_for_results())
   ▼
[Phase 2 — orchestrator/worker]
   UserTask ─▶ OrchestratorAgent
                 ├─ send_message ─▶ DataModellerAgent       (RAG-grounded logical model)
                 ├─ send_message ─▶ PySparkGenerationAgent  (per node) ─▶ output guardrails
                 ├─ send_message ─▶ IcebergWriterAgent       (target merge)
                 ├─ send_message ─▶ ReviewAgent              (parity verdict)
                 ├─ send_message ─▶ CriticAgent              (adversarial scoring)
                 └─ human_review_gate                        (auto / interactive approval)
                 ▼
              FinalResult { data_model, pyspark_nodes, iceberg_write, review, guardrails, critic, human_decision }
```

Input guardrails (PII/secrets/injection redaction) run on every node **before** the LLM,
and a RAG knowledge base over the whole XML dump is built and injected as
`meta_data["retrieved_context"]` **before** Phase 2.

## Repository layout

```text
e2e_infa_to_pyspark/
  app/
    main.py                              # FastAPI entrypoint (/codegen, /health)
    config/
      azure_openai.py                    # shared azure_client (gpt-4o, temperature=0, seed=8350)
      settings.py
    communication/
      pyspark_topics.py                  # topic type constants
      pyspark_types.py                   # message dataclasses
    agents/
      pc_extractor_agent.py              # pub/sub extractor (RoutedAgent + @type_subscription)
      result_collector_agent.py          # CollectorState barrier + collector agent
      orchestrator_agent.py              # handle_task(UserTask) -> FinalResult (6-step flow)
      data_modeller_agent.py             # RAG-grounded logical model worker
      pyspark_generation_agent.py        # worker
      iceberg_writer_agent.py            # worker
      review_agent.py                    # worker
      critic_agent.py                    # adversarial critic worker
      human_gate.py                      # human-in-the-loop approval gate
    rag/
      knowledge_base.py                  # TF-IDF RAG over the Informatica XML dump
    guardrails/
      engine.py                          # PII/secrets/injection + destructive-SQL/schema guardrails
    evaluation/
      metrics.py                         # ROUGE-N/L + structural eval harness
    orchestrators/
      pyspark_codegen_workflow.py        # SingleThreadedAgentRuntime wiring (both phases)
    prompt_engineering/prompts/
      pc_extractor_prompt.py
      pyspark_generation_prompt.py
      iceberg_prompt.py
      review_prompt.py
    utils/
      xml_parser.py                      # PowerCenter XML → canonical dicts
      pc_file_processor.py               # get_export_type / pre_process_shared_folder
      logger.py
  configs/pipeline.yml
  docs/architecture-diagrams.md
  tests/test_parser_smoke.py
  requirements.txt
```

## Determinism

The shared `azure_client` is created with `temperature=0`, `seed=8350`, and
`max_retries=5`, so PowerCenter → PySpark generation is reproducible. SQL overrides are
extracted **verbatim** and never rewritten by the LLM.

## Run

```powershell
# Install
pip install -r requirements.txt

# Smoke tests (deterministic parts, no Azure needed)
python -m pytest tests/ -q

# Full pipeline CLI (Azure required). --limit caps nodes for a cheap smoke run.
python -m app.run --limit 3                 # auto human-gate (CI mode)
python -m app.run --human interactive       # console approval of critic verdict

# API (requires Azure OpenAI env: api_key, base_url, api_version, AZURE_DEPLOYMENT)
python -m app.main
# POST /codegen { "input_folder": "../app_CALCULATE_EINTERACTION",
#                 "focus_mapping": "m_4202_dt_chn_rltinteractionagreement",
#                 "target_table": "lakehouse.gold_rltinteractionagreement",
#                 "merge_keys": ["InteractionGroup_Id","EIntrSource_Cd"] }
```

## Reference pedigree

The agent names, topic constants, message dataclasses, barrier sync, and runtime wiring
mirror the two production `des_*` backends studied for this build (a PC/IICS/SSIS/BTEQ
extraction backend and a dbt codegen backend), adapted to a PySpark + Iceberg target.
