"""End-to-end agentic workflow: PowerCenter XML -> PySpark + Iceberg.

Mirrors the runtime wiring of both des_ reference repos:
- CLIENT_B_backend pc_extraction_workflow.py: SingleThreadedAgentRuntime, register the
  extractor + collector, set the barrier expected_count BEFORE publishing PCMessages,
  wait_for_results().
- dbt_codegen moa_dbt_codegen.py: register orchestrator + worker agents, send a UserTask
  to the orchestrator, receive a FinalResult.

Two phases on one runtime:
  Phase 1 (pub/sub + barrier): PCExtractorAgent normalizes every node; PCResultCollectorAgent
                               gathers them via CollectorState.
  Phase 2 (orchestrator/worker): OrchestratorAgent compiles nodes -> PySpark, then Iceberg,
                                 then Review, returning a FinalResult.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from autogen_core import (
    AgentId,
    DefaultTopicId,
    SingleThreadedAgentRuntime,
    TypeSubscription,
)

from app.agents.critic_agent import CriticAgent
from app.agents.data_modeller_agent import DataModellerAgent
from app.agents.iceberg_writer_agent import IcebergWriterAgent
from app.agents.orchestrator_agent import OrchestratorAgent
from app.agents.pc_extractor_agent import PCExtractorAgent
from app.agents.pyspark_generation_agent import PySparkGenerationAgent
from app.agents.result_collector_agent import CollectorState, PCResultCollectorAgent
from app.agents.review_agent import ReviewAgent
from app.communication.pyspark_topics import (
    PC_EXTRACTION_RESPONSE_TOPIC_TYPE,
    PC_EXTRACTION_TOPIC_TYPE,
)
from app.communication.pyspark_types import PCMessage, UserTask
from app.config.azure_openai import azure_client
from app.guardrails import default_input_engine
from app.observability import InstrumentedChatClient, RunRecorder, build_tracer
from app.rag.knowledge_base import build_knowledge_base
from app.utils.logger import get_logger
from app.utils.pc_file_processor import pre_process_shared_folder

logger = get_logger(__name__)


async def run_codegen(
    input_folder: str,
    focus_mapping: Optional[str] = None,
    meta_data: Optional[Dict[str, Any]] = None,
    model_client=None,
    node_limit: Optional[int] = None,
    human_mode: str = "auto",
    record: bool = True,
    trace: bool = True,
) -> Dict[str, Any]:
    """Run the full agentic pipeline and return the FinalResult dict.

    Observability
    -------------
    When ``record`` is true, every step (parsed nodes, redacted nodes, RAG context, each
    LLM call's input/output, the final result) is persisted under ``runs/<ts>_<mapping>/``.
    When ``trace`` is true and Langfuse is configured, the same lifecycle is sent to
    Langfuse; otherwise tracing is a silent no-op.
    """
    client = model_client or azure_client
    if client is None:
        raise RuntimeError("No Azure OpenAI client configured (set api_key in env).")

    meta_data = meta_data or {}
    mapping_label = focus_mapping or meta_data.get("mapping_name") or "mapping"

    # --- Observability: per-run recorder + tracer ---
    recorder = RunRecorder(mapping=mapping_label, enabled=record)
    tracer = build_tracer(
        run_name=f"pyspark_codegen:{mapping_label}",
        metadata={"input_folder": input_folder, "node_limit": node_limit},
        enabled=trace,
    )

    nodes: List[Dict[str, Any]] = pre_process_shared_folder(
        input_folder, focus_mapping=focus_mapping
    )
    if node_limit:
        nodes = nodes[:node_limit]
    logger.info("Pre-processed %s canonical nodes", len(nodes))
    recorder.save_json("00_parsed_nodes", nodes)
    tracer.event("parsed_xml", {"node_count": len(nodes), "mapping": mapping_label})

    # --- Input guardrails: redact PII/secrets from node payloads before the LLM ---
    input_guardrails = default_input_engine()
    safe_nodes: List[Dict[str, Any]] = []
    for node in nodes:
        report = input_guardrails.run(json.dumps(node))
        try:
            safe_nodes.append(json.loads(report.text))
        except Exception:
            safe_nodes.append(node)  # if redaction broke JSON, keep original
    nodes = safe_nodes
    recorder.save_json("01_redacted_nodes", nodes)

    # --- RAG: build cross-file knowledge base (chunk + embed + index) ---
    # The DataModellerAgent uses this as a tool to build a field-level source-to-target map.
    knowledge_base = None
    retrieved_context = ""
    try:
        knowledge_base = build_knowledge_base(input_folder)
        query = focus_mapping or meta_data.get("mapping_name", "") or "data model"
        retrieved_context = knowledge_base.build_context(query, k=8)
        logger.info("RAG retrieved %s chars of cross-file context", len(retrieved_context))
        recorder.save_text("02_rag_context", retrieved_context)
        try:
            recorder.save_json("02_rag_hits", knowledge_base.retrieve(query, k=8))
        except Exception:
            pass
        tracer.event(
            "rag_retrieval",
            {"query": query, "chars": len(retrieved_context), "backend": knowledge_base.backend},
        )
    except Exception as exc:
        logger.warning("RAG context unavailable: %s", exc)
    meta_data["retrieved_context"] = retrieved_context
    rag_tool = knowledge_base.as_tool() if knowledge_base is not None else None

    # --- Wrap the model client so every agent's LLM call is recorded + traced ---
    def labelled(step: str):
        return InstrumentedChatClient(client, step, recorder=recorder, tracer=tracer)

    runtime = SingleThreadedAgentRuntime()
    collector_state = CollectorState()

    # --- Phase 1: pub/sub extractor + collector ---
    await PCExtractorAgent.register(
        runtime, "pc_extractor", lambda: PCExtractorAgent(labelled("pc_extractor"))
    )
    await runtime.add_subscription(
        TypeSubscription(topic_type=PC_EXTRACTION_TOPIC_TYPE, agent_type="pc_extractor")
    )

    await PCResultCollectorAgent.register(
        runtime, "pc_collector", lambda: PCResultCollectorAgent(collector_state)
    )
    await runtime.add_subscription(
        TypeSubscription(
            topic_type=PC_EXTRACTION_RESPONSE_TOPIC_TYPE, agent_type="pc_collector"
        )
    )

    # --- Phase 2: orchestrator + workers ---
    await OrchestratorAgent.register(
        runtime, "orchestrator", lambda: OrchestratorAgent(human_mode=human_mode)
    )
    await DataModellerAgent.register(
        runtime,
        "data_modeller",
        lambda: DataModellerAgent(labelled("data_modeller"), rag_tool=rag_tool),
    )
    await PySparkGenerationAgent.register(
        runtime,
        "pyspark_generation",
        lambda: PySparkGenerationAgent(labelled("pyspark_generation")),
    )
    await IcebergWriterAgent.register(
        runtime, "iceberg_writer", lambda: IcebergWriterAgent(labelled("iceberg_writer"))
    )
    await ReviewAgent.register(runtime, "review", lambda: ReviewAgent(labelled("review")))
    await CriticAgent.register(runtime, "critic", lambda: CriticAgent(labelled("critic")))

    runtime.start()

    # Set the barrier BEFORE publishing (reference invariant).
    collector_state.set_expected_count(len(nodes))
    for node in nodes:
        await runtime.publish_message(
            PCMessage(content=json.dumps(node)),
            topic_id=DefaultTopicId(type=PC_EXTRACTION_TOPIC_TYPE),
        )

    extracted = await collector_state.wait_for_results(timeout=300)
    logger.info("Extraction barrier released with %s results", len(extracted))
    recorder.save_json("03_extracted_nodes", extracted)
    tracer.event("extraction_barrier", {"results": len(extracted)})

    # Hand the normalized nodes to the orchestrator.
    final = await runtime.send_message(
        UserTask(task={"nodes": extracted}, meta_data=meta_data),
        AgentId("orchestrator", "default"),
    )

    await runtime.stop_when_idle()

    # --- Observability: persist the final result + close out the run ---
    recorder.save_json("99_final_result", final.result)
    recorder.write_manifest(
        metadata={
            "mapping": mapping_label,
            "input_folder": input_folder,
            "node_count": len(nodes),
            "human_mode": human_mode,
        }
    )
    tracer.event("final_result", {"mapping": mapping_label})
    tracer.flush()
    if recorder.enabled:
        logger.info("Run artifacts written to %s", recorder.run_dir)
        if isinstance(final.result, dict):
            final.result["_run_dir"] = str(recorder.run_dir)
    return final.result
