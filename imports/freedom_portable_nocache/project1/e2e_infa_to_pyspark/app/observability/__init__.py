"""Observability for the agentic pipeline.

Two cooperating pieces:

- ``RunRecorder`` — persists every artifact of a run to disk (the parsed XML/canonical
  nodes, redacted nodes, RAG context, each LLM call's input + output, and the final
  result) under ``runs/<timestamp>_<mapping>/``.
- ``Tracer`` — emits the same lifecycle to Langfuse when configured, otherwise a no-op.
- ``InstrumentedChatClient`` — a drop-in wrapper around the autogen model client that
  records and traces every ``.create()`` call, labelled with the owning step/agent.
"""

from __future__ import annotations

from app.observability.instrumented_client import InstrumentedChatClient
from app.observability.run_recorder import RunRecorder
from app.observability.tracing import Tracer, build_tracer

__all__ = [
    "RunRecorder",
    "Tracer",
    "build_tracer",
    "InstrumentedChatClient",
]
