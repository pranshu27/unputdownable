"""Critic agent — independent adversarial validator (orchestrator/worker pattern).

The orchestrator calls the Critic AFTER generation + review. The Critic returns a
structured verdict with a confidence score and a `requires_human_review` flag that drives
the human-in-the-loop gate.
"""

from __future__ import annotations

import json

from autogen_core import MessageContext, RoutedAgent, message_handler
from autogen_core.models import SystemMessage, UserMessage

from app.communication.pyspark_types import WorkerTask, WorkerTaskResult
from app.prompt_engineering.prompts.critic_prompt import CRITIC_SYSTEM_PROMPT
from app.utils.logger import get_logger

logger = get_logger(__name__)


class CriticAgent(RoutedAgent):
    def __init__(self, model_client) -> None:
        super().__init__(description="Adversarial critic for generated PySpark")
        self._model_client = model_client
        self._system_message = SystemMessage(content=CRITIC_SYSTEM_PROMPT)

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
            logger.info("CriticAgent produced a verdict")
            return WorkerTaskResult(result=str(response.content))
        except Exception as exc:  # soft-fail; force human review on critic failure
            logger.error("CriticAgent failed: %s", exc)
            return WorkerTaskResult(
                result=json.dumps(
                    {
                        "verdict": "revise",
                        "confidence": 0.0,
                        "blocking_issues": [f"critic_error: {exc}"],
                        "requires_human_review": True,
                    }
                )
            )
