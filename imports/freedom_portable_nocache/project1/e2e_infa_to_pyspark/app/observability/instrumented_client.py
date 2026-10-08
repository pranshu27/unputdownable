"""InstrumentedChatClient — record + trace every LLM call, transparently.

This is a drop-in proxy around the autogen ``ChatCompletionClient`` (e.g. the shared
``AzureOpenAIChatCompletionClient``). Every agent receives a wrapper *labelled with its
step name*, so when the agent calls ``self._model_client.create(...)`` we can:

1. persist the exact input messages and the produced output via the ``RunRecorder``, and
2. emit a Langfuse *generation* via the ``Tracer``.

All other attributes/methods (``count_tokens``, ``model_info``, ``close`` …) are delegated
to the wrapped client through ``__getattr__``, so the proxy behaves like the real client.
No agent code changes are required — the workflow simply hands each agent a labelled proxy.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.observability.run_recorder import RunRecorder
from app.observability.tracing import Tracer
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _message_to_dict(msg: Any) -> Dict[str, Any]:
    """Best-effort serialization of an autogen model message."""
    content = getattr(msg, "content", msg)
    if not isinstance(content, (str, list, dict, int, float, bool, type(None))):
        content = str(content)
    return {
        "type": type(msg).__name__,
        "source": getattr(msg, "source", None),
        "content": content,
    }


def _messages_to_list(messages: Any) -> List[Dict[str, Any]]:
    try:
        return [_message_to_dict(m) for m in messages]
    except TypeError:
        return [_message_to_dict(messages)]


def _usage_to_dict(usage: Any) -> Optional[Dict[str, Any]]:
    if usage is None:
        return None
    prompt = getattr(usage, "prompt_tokens", None)
    completion = getattr(usage, "completion_tokens", None)
    if prompt is None and completion is None:
        return None
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": (prompt or 0) + (completion or 0),
    }


class InstrumentedChatClient:
    """Proxy that records and traces ``create`` calls for one labelled step/agent."""

    def __init__(
        self,
        inner: Any,
        step: str,
        recorder: Optional[RunRecorder] = None,
        tracer: Optional[Tracer] = None,
        model: Optional[str] = None,
    ) -> None:
        self._inner = inner
        self._step = step
        self._recorder = recorder
        self._tracer = tracer
        self._model = model or getattr(inner, "model", None)

    def __getattr__(self, name: str) -> Any:
        # Delegate everything we don't override to the wrapped client.
        return getattr(self._inner, name)

    async def create(self, messages: Any, *args: Any, **kwargs: Any) -> Any:
        input_payload = _messages_to_list(messages)
        gen = None
        if self._tracer is not None:
            gen = self._tracer.generation_start(self._step, input_payload, self._model)
        try:
            response = await self._inner.create(messages, *args, **kwargs)
        except Exception as exc:
            if self._recorder is not None:
                self._recorder.save_llm_call(self._step, input_payload, f"ERROR: {exc}")
            if self._tracer is not None and gen is not None:
                self._tracer.generation_end(gen, f"ERROR: {exc}")
            raise

        output = str(getattr(response, "content", response))
        usage = _usage_to_dict(getattr(response, "usage", None))
        if self._recorder is not None:
            self._recorder.save_llm_call(self._step, input_payload, output, usage)
        if self._tracer is not None and gen is not None:
            self._tracer.generation_end(gen, output, usage)
        return response
