"""Data Modelling agent (RAG-grounded, orchestrator/worker pattern).

Runs after extraction and before PySpark generation. It receives the current mapping's
extracted nodes and uses a RAG *tool* (the Informatica knowledge base) to retrieve
cross-file context, then produces a field-level source-to-target mapping (STTM) plus a
compact target model. The STTM is what the PySpark generation agent consumes.

RAG-as-a-tool
-------------
Instead of receiving a single pre-baked context blob, this agent actively queries the
knowledge base with targeted questions derived from the mapping (its target, its sources,
likely lookups). This mirrors how an agent calls a tool to gather just-in-time evidence.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from autogen_core import MessageContext, RoutedAgent, message_handler
from autogen_core.models import SystemMessage, UserMessage

from app.communication.pyspark_types import WorkerTask, WorkerTaskResult
from app.prompt_engineering.prompts.data_modeller_prompt import (
    DATA_MODELLER_SYSTEM_PROMPT,
)
from app.rag.knowledge_base import RagTool
from app.utils.logger import get_logger

logger = get_logger(__name__)


class DataModellerAgent(RoutedAgent):
    def __init__(self, model_client, rag_tool: Optional[RagTool] = None) -> None:
        super().__init__(description="RAG-grounded field-level STTM + model producer")
        self._model_client = model_client
        self._rag = rag_tool
        self._system_message = SystemMessage(content=DATA_MODELLER_SYSTEM_PROMPT)

    def _gather_rag_context(self, nodes: List[Dict[str, Any]], mapping: str) -> str:
        """Use the RAG tool to retrieve just-in-time context for this mapping."""
        if self._rag is None:
            return ""

        # Build targeted queries from the mapping's own nodes (sources, target, names).
        queries: List[str] = []
        if mapping:
            queries.append(mapping)
        for n in nodes:
            name = n.get("name", "")
            node_class = n.get("node_class", "")
            if node_class in ("SOURCE", "TARGET") and name:
                queries.append(f"{node_class} {name} fields and keys")
            if n.get("sql_override"):
                queries.append(f"SQL override for {name}")

        seen: set = set()
        blocks: List[str] = []
        for q in queries[:8]:  # cap tool calls for determinism/cost
            for hit in self._rag.search(q, 3):
                if hit["chunk_id"] in seen:
                    continue
                seen.add(hit["chunk_id"])
                blocks.append(
                    f"[{hit['source_file']} · {hit['node_class']} · {hit['name']} "
                    f"(score={hit['score']})]\n{hit['text']}"
                )
        context = "\n\n---\n\n".join(blocks)
        logger.info("DataModellerAgent gathered %s RAG chunks via tool", len(blocks))
        return context[:8000]

    @message_handler
    async def handle_task(
        self, message: WorkerTask, ctx: MessageContext
    ) -> WorkerTaskResult:
        try:
            nodes = json.loads(message.task) if isinstance(message.task, str) else message.task
        except Exception:
            nodes = []
        mapping = message.meta_data.get("mapping_name", "")

        # Prefer querying the RAG tool live; fall back to any pre-injected context.
        rag_context = self._gather_rag_context(nodes, mapping)
        if not rag_context:
            rag_context = message.meta_data.get("retrieved_context", "")

        user_content = (
            f"RAG_CONTEXT (retrieved via the knowledge-base tool):\n{rag_context}\n\n"
            f"CURRENT MAPPING ({mapping}) extracted nodes:\n{json.dumps(nodes)}"
        )
        try:
            response = await self._model_client.create(
                [self._system_message, UserMessage(content=user_content, source="user")],
                cancellation_token=ctx.cancellation_token,
            )
            logger.info("DataModellerAgent produced an STTM + model")
            return WorkerTaskResult(result=str(response.content))
        except Exception as exc:  # soft-fail
            logger.error("DataModellerAgent failed: %s", exc)
            return WorkerTaskResult(result=json.dumps({"error": str(exc)}))
