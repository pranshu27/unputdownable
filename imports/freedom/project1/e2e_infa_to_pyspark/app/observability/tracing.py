"""Tracer — Langfuse tracing for the agentic pipeline, with a no-op fallback.

Why a wrapper
-------------
We don't want Langfuse to be a hard dependency or to break offline/CI runs. ``build_tracer``
returns a real Langfuse-backed tracer only when the SDK is importable *and* the credentials
are present (``LANGFUSE_PUBLIC_KEY`` + ``LANGFUSE_SECRET_KEY``). Otherwise it returns a
``NoOpTracer`` whose methods do nothing. Agent/workflow code calls the same interface in
both cases.

What we trace
-------------
- one **trace** per pipeline run (mapping name + metadata),
- one **generation** per LLM ``.create()`` call (input messages, output, token usage,
  labelled with the owning step/agent),
- arbitrary **events** for non-LLM milestones (parsed nodes, RAG retrieval, barrier, etc.).
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)


class _Generation:
    """Opaque handle returned by ``generation_start`` and closed by ``generation_end``."""

    def __init__(self, handle: Any = None) -> None:
        self.handle = handle


class Tracer:
    """Base interface. The no-op implementation is the default."""

    enabled: bool = False

    def event(self, name: str, data: Optional[Dict[str, Any]] = None) -> None:  # noqa: D401
        """Record a non-LLM milestone."""

    def generation_start(
        self, name: str, input_payload: Any, model: Optional[str] = None
    ) -> _Generation:
        return _Generation()

    def generation_end(
        self,
        generation: _Generation,
        output: Any,
        usage: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Close a generation started with ``generation_start``."""

    def flush(self) -> None:
        """Flush buffered events to the backend."""


class NoOpTracer(Tracer):
    enabled = False


class LangfuseTracer(Tracer):
    """Thin adapter over the Langfuse Python SDK (v2 ``trace``/``generation`` API)."""

    enabled = True

    def __init__(
        self,
        client: Any,
        run_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._client = client
        self._trace = None
        try:
            self._trace = client.trace(name=run_name, metadata=metadata or {})
        except Exception as exc:  # pragma: no cover - network/SDK variance
            logger.warning("Langfuse trace() failed, continuing untraced: %s", exc)
            self.enabled = False

    def event(self, name: str, data: Optional[Dict[str, Any]] = None) -> None:
        if not self.enabled or self._trace is None:
            return
        try:
            self._trace.event(name=name, metadata=data or {})
        except Exception as exc:  # pragma: no cover
            logger.debug("Langfuse event failed: %s", exc)

    def generation_start(
        self, name: str, input_payload: Any, model: Optional[str] = None
    ) -> _Generation:
        if not self.enabled or self._trace is None:
            return _Generation()
        try:
            gen = self._trace.generation(name=name, input=input_payload, model=model)
            return _Generation(gen)
        except Exception as exc:  # pragma: no cover
            logger.debug("Langfuse generation() failed: %s", exc)
            return _Generation()

    def generation_end(
        self,
        generation: _Generation,
        output: Any,
        usage: Optional[Dict[str, Any]] = None,
    ) -> None:
        if generation is None or generation.handle is None:
            return
        try:
            generation.handle.end(output=output, usage=usage)
        except Exception as exc:  # pragma: no cover
            logger.debug("Langfuse generation.end failed: %s", exc)

    def flush(self) -> None:
        if not self.enabled:
            return
        try:
            self._client.flush()
        except Exception as exc:  # pragma: no cover
            logger.debug("Langfuse flush failed: %s", exc)


def build_tracer(
    run_name: str,
    metadata: Optional[Dict[str, Any]] = None,
    enabled: bool = True,
) -> Tracer:
    """Return a Langfuse tracer when configured, else a no-op tracer.

    Enabled only when ``enabled`` is true, the ``langfuse`` SDK imports, and both
    ``LANGFUSE_PUBLIC_KEY`` and ``LANGFUSE_SECRET_KEY`` are set in the environment.
    """
    if not enabled:
        return NoOpTracer()

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    if not (public_key and secret_key):
        logger.info("Langfuse not configured (no keys) — tracing disabled.")
        return NoOpTracer()

    try:
        from langfuse import Langfuse  # type: ignore
    except Exception:
        logger.info("Langfuse SDK not installed — tracing disabled.")
        return NoOpTracer()

    try:
        client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        )
        logger.info("Langfuse tracing enabled for run '%s'", run_name)
        return LangfuseTracer(client, run_name, metadata)
    except Exception as exc:  # pragma: no cover
        logger.warning("Langfuse init failed, tracing disabled: %s", exc)
        return NoOpTracer()
