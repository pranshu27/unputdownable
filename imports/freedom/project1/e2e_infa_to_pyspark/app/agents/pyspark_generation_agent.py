"""PySpark generation worker agent (orchestrator/worker pattern).

Mirrors dbt_codegen GenerationAgent: a RoutedAgent that handles a WorkerTask, calls the
LLM to compile one canonical node into a PySpark fragment, and returns a WorkerTaskResult.
Invoked directly by the orchestrator via send_message(..., AgentId("pyspark_generation", ...)).
"""

from __future__ import annotations

import json

from autogen_core import MessageContext, RoutedAgent, message_handler
from autogen_core.models import SystemMessage, UserMessage

from app.communication.pyspark_types import WorkerTask, WorkerTaskResult
from app.prompt_engineering.prompts.pyspark_generation_prompt import (
    PYSPARK_GENERATION_SYSTEM_PROMPT,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


class PySparkGenerationAgent(RoutedAgent):
    def __init__(self, model_client) -> None:
        super().__init__(description="Generates PySpark code for one node")
        self._model_client = model_client
        self._system_message = SystemMessage(content=PYSPARK_GENERATION_SYSTEM_PROMPT)

    @message_handler
    async def handle_task(
        self, message: WorkerTask, ctx: MessageContext
    ) -> WorkerTaskResult:
        context = "\n\n".join(message.previous_results) if message.previous_results else ""
        # Field-level source-to-target mapping (STTM) produced by the data modeller.
        sttm = message.meta_data.get("source_to_target", [])
        sttm_block = json.dumps(sttm[:60]) if sttm else "(none provided)"
        user_content = (
            f"Field-level source-to-target mapping (STTM) for this target:\n{sttm_block}\n\n"
            f"Previously generated nodes:\n{context}\n\n"
            f"Node to compile to PySpark:\n{message.task}"
        )
        try:
            response = await self._model_client.create(
                [self._system_message, UserMessage(content=user_content, source="user")],
                cancellation_token=ctx.cancellation_token,
            )
            logger.info("PySparkGenerationAgent produced a node fragment")
            return WorkerTaskResult(result=str(response.content))
        except Exception as exc:  # soft-fail so the orchestrator can still assemble output
            logger.error("PySparkGenerationAgent failed: %s", exc)
            return WorkerTaskResult(result=json.dumps({"error": str(exc)}))
