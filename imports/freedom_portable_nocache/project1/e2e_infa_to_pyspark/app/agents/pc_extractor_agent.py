"""PowerCenter extractor agent (pub/sub).

Mirrors farmers_backend app/agents/pc_extractor_agent.py:
- RoutedAgent subscribed to PC_EXTRACTION_TOPIC_TYPE via @type_subscription.
- @message_handler consumes one PCMessage (a canonical node), asks the LLM to extract
  normalized metadata, and publishes a PCFlowExtractionResponse to BOTH the default topic
  and the response topic (for the collector).
- Soft-fail: on any error it publishes an error dict instead of raising, so the barrier
  always completes.
"""

from __future__ import annotations

import json

from autogen_core import MessageContext, RoutedAgent, TopicId, message_handler
from autogen_core import DefaultTopicId
from autogen_core.models import SystemMessage, UserMessage

from app.communication.pyspark_topics import (
    PC_EXTRACTION_RESPONSE_TOPIC_TYPE,
    PC_EXTRACTION_TOPIC_TYPE,
)
from app.communication.pyspark_types import PCFlowExtractionResponse, PCMessage
from app.prompt_engineering.prompts.pc_extractor_prompt import PC_EXTRACTOR_SYSTEM_PROMPT
from app.utils.logger import get_logger

logger = get_logger(__name__)


class PCExtractorAgent(RoutedAgent):
    """Extracts normalized metadata from one PowerCenter node at a time."""

    def __init__(self, model_client) -> None:
        super().__init__(description="PowerCenter node metadata extractor")
        self._model_client = model_client
        self._system_message = SystemMessage(content=PC_EXTRACTOR_SYSTEM_PROMPT)

    @message_handler
    async def handle_node(self, message: PCMessage, ctx: MessageContext) -> None:
        try:
            response = await self._model_client.create(
                [
                    self._system_message,
                    UserMessage(content=message.content, source="user"),
                ],
                cancellation_token=ctx.cancellation_token,
            )
            content = response.content
            parsed = json.loads(_strip_fences(content))
            result = PCFlowExtractionResponse(content=parsed)
        except Exception as exc:  # soft-fail so the barrier still completes
            logger.error("PCExtractorAgent failed: %s", exc)
            result = PCFlowExtractionResponse(
                content={"error": str(exc), "raw": message.content}
            )

        # Publish to the response topic (collector) and the default topic.
        await self.publish_message(
            result,
            topic_id=TopicId(PC_EXTRACTION_RESPONSE_TOPIC_TYPE, source=self.id.key),
        )
        await self.publish_message(result, topic_id=DefaultTopicId())


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t[: -3]
        if t.lstrip().startswith("json"):
            t = t.lstrip()[4:]
    return t.strip()
