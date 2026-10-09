"""Result collector agent with a barrier (mirrors CLIENT_B_backend result_collector_agent.py).

CollectorState holds an asyncio.Event plus an expected_count. The workflow calls
set_expected_count(n) BEFORE publishing the n extractor tasks. Each PCFlowExtractionResponse
increments the counter; when counter >= expected_count the event is set and the workflow's
wait_for_results() unblocks.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from autogen_core import MessageContext, RoutedAgent, message_handler

from app.communication.pyspark_types import PCFlowExtractionResponse
from app.utils.logger import get_logger

logger = get_logger(__name__)


class CollectorState:
    """Shared barrier state between the workflow and the collector agent."""

    def __init__(self) -> None:
        self.event = asyncio.Event()
        self.expected_count = 0
        self.response_counter = 0
        self.results: List[Dict[str, Any]] = []

    def set_expected_count(self, count: int) -> None:
        self.expected_count = count
        self.response_counter = 0
        self.results = []
        self.event.clear()

    async def wait_for_results(self, timeout: int = 300) -> List[Dict[str, Any]]:
        try:
            await asyncio.wait_for(self.event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.error(
                "Collector timed out: %s/%s responses",
                self.response_counter,
                self.expected_count,
            )
        return self.results


class PCResultCollectorAgent(RoutedAgent):
    """Subscribes to the extraction response topic and fills CollectorState."""

    def __init__(self, state: CollectorState) -> None:
        super().__init__(description="PowerCenter extraction result collector")
        self._state = state

    @message_handler
    async def collect(
        self, message: PCFlowExtractionResponse, ctx: MessageContext
    ) -> None:
        self._state.results.append(message.content)
        self._state.response_counter += 1
        logger.info(
            "Collected %s/%s extraction responses",
            self._state.response_counter,
            self._state.expected_count,
        )
        if self._state.response_counter >= self._state.expected_count:
            self._state.event.set()
