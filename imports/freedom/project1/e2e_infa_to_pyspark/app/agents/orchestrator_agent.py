"""Orchestrator agent (mirrors dbt_codegen app/agents/orchestrator_agent.py).

Handles a single UserTask containing the collected/extracted canonical nodes plus
meta_data. The full agentic flow it coordinates:

  1. DataModellerAgent  - propose a target model (RAG-grounded) for the modellers.
  2. PySparkGenerationAgent - generate PySpark node-by-node (output guardrails applied).
  3. IcebergWriterAgent - generate the Iceberg write/merge.
  4. ReviewAgent        - parity-readiness review.
  5. CriticAgent        - independent adversarial verdict + confidence.
  6. human_review_gate  - final human-in-the-loop sign-off.

Each LLM dispatch uses send_message to a worker AgentId (request/response); the aggregated
output, guardrail report, critic verdict, and human decision are returned as a FinalResult.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from autogen_core import AgentId, MessageContext, RoutedAgent, message_handler

from app.agents.human_gate import human_review_gate
from app.communication.pyspark_types import (
    FinalResult,
    HumanReviewRequest,
    UserTask,
    WorkerTask,
    WorkerTaskResult,
)
from app.guardrails import default_output_engine
from app.utils.logger import get_logger

logger = get_logger(__name__)


def clean_content(text: str) -> str:
    """Strip markdown code fences from a worker result (same helper as the reference)."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t[:-3]
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
    return t.strip()


class OrchestratorAgent(RoutedAgent):
    def __init__(self, human_mode: str = "auto") -> None:
        super().__init__(description="Coordinates PySpark codegen across worker agents")
        self._modeller_id = AgentId("data_modeller", "default")
        self._generation_id = AgentId("pyspark_generation", "default")
        self._iceberg_id = AgentId("iceberg_writer", "default")
        self._review_id = AgentId("review", "default")
        self._critic_id = AgentId("critic", "default")
        self._human_mode = human_mode
        self._output_guardrails = default_output_engine()

    @message_handler
    async def handle_task(self, message: UserTask, ctx: MessageContext) -> FinalResult:
        nodes: List[dict] = message.task.get("nodes", [])
        meta = message.meta_data
        logger.info(
            "Orchestrator received %s nodes for mapping %s",
            len(nodes),
            meta.get("mapping_name"),
        )

        # 1) Field-level STTM + target model (RAG-grounded; data modeller queries the KB tool).
        modeller_result: WorkerTaskResult = await self.send_message(
            WorkerTask(task=json.dumps(nodes), meta_data=meta),
            self._modeller_id,
        )
        data_model = clean_content(modeller_result.result)
        # Parse the STTM so PySpark generation can be field-accurate.
        try:
            sttm_obj = json.loads(data_model)
        except Exception:
            sttm_obj = {}
        source_to_target = sttm_obj.get("source_to_target", [])
        # Augmented meta carries the field-level mapping into each generation call.
        gen_meta: Dict[str, Any] = {**meta, "source_to_target": source_to_target}

        # 2) Generate PySpark node-by-node, threading prior results for context.
        generated: List[str] = []
        guardrail_reports: List[Dict[str, Any]] = []
        for node in nodes:
            result: WorkerTaskResult = await self.send_message(
                WorkerTask(
                    task=json.dumps(node),
                    previous_results=generated,
                    meta_data=gen_meta,
                ),
                self._generation_id,
            )
            code = clean_content(result.result)
            # Output guardrails: block destructive SQL / leaked secrets in generated code.
            report = self._output_guardrails.run(code)
            guardrail_reports.append(report.to_dict())
            if report.blocked:
                logger.error("Guardrail blocked a generated node: %s", report.findings)
            generated.append(report.text)

        # 3) Iceberg write/merge for the target.
        iceberg_task = {
            "target_table": meta.get("target_table"),
            "key_columns": meta.get("merge_keys", []),
            "update_strategy": meta.get("update_strategy", "DD_UPDATE"),
        }
        iceberg_result: WorkerTaskResult = await self.send_message(
            WorkerTask(task=json.dumps(iceberg_task), meta_data=meta),
            self._iceberg_id,
        )
        iceberg_sql = clean_content(iceberg_result.result)

        # 4) Review the full bundle.
        review_task = {
            "mapping_name": meta.get("mapping_name"),
            "nodes": generated,
            "iceberg_write": iceberg_sql,
            "merge_keys": meta.get("merge_keys", []),
        }
        review_result: WorkerTaskResult = await self.send_message(
            WorkerTask(task=json.dumps(review_task), meta_data=meta),
            self._review_id,
        )
        review = clean_content(review_result.result)

        # 5) Independent critic verdict (drives the human gate).
        critic_task = {
            "mapping_name": meta.get("mapping_name"),
            "pyspark_nodes": generated,
            "iceberg_write": iceberg_sql,
            "extracted_nodes": nodes,
        }
        critic_result: WorkerTaskResult = await self.send_message(
            WorkerTask(task=json.dumps(critic_task), meta_data=meta),
            self._critic_id,
        )
        critic = clean_content(critic_result.result)
        try:
            critic_obj = json.loads(critic)
        except Exception:
            critic_obj = {"requires_human_review": True, "confidence": 0.0}

        artifact = {
            "mapping_name": meta.get("mapping_name"),
            "data_model": data_model,
            "pyspark_nodes": generated,
            "iceberg_write": iceberg_sql,
            "review": review,
            "guardrails": guardrail_reports,
        }

        # 6) Human-in-the-loop final sign-off.
        decision = await human_review_gate(
            HumanReviewRequest(
                mapping_name=meta.get("mapping_name", ""),
                artifact=artifact,
                critic=critic_obj,
            ),
            mode=self._human_mode,
        )

        return FinalResult(
            result={
                **artifact,
                "critic": critic_obj,
                "human_decision": {
                    "approved": decision.approved,
                    "reviewer": decision.reviewer,
                    "comments": decision.comments,
                },
            }
        )
