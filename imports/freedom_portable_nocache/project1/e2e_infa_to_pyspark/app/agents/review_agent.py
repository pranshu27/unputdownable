"""Review worker agent (orchestrator/worker pattern)."""

from __future__ import annotations

import json

from autogen_core import MessageContext, RoutedAgent, message_handler
from autogen_core.models import SystemMessage, UserMessage

from app.communication.pyspark_types import WorkerTask, WorkerTaskResult
from app.prompt_engineering.prompts.review_prompt import REVIEW_SYSTEM_PROMPT
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ReviewAgent(RoutedAgent):
    def __init__(self, model_client) -> None:
        super().__init__(description="Reviews generated PySpark for parity readiness")
        self._model_client = model_client
        self._system_message = SystemMessage(content=REVIEW_SYSTEM_PROMPT)

    @message_handler
    async def handle_task(
        self, message: WorkerTask, ctx: MessageContext
    ) -> WorkerTaskResult:
        try:
            response = await self._model_client.create(
                [
                    self._system_message,
                    UserMessage(content=message.task, source="user"),
                ],
                cancellation_token=ctx.cancellation_token,
            )
            logger.info("ReviewAgent produced a verdict")
            return WorkerTaskResult(result=str(response.content))
        except Exception as exc:  # soft-fail
            logger.error("ReviewAgent failed: %s", exc)
            return WorkerTaskResult(result=json.dumps({"error": str(exc)}))
