import json, os
from abc import ABC, abstractmethod
from typing import Any


class BaseLLMClient(ABC):
    @abstractmethod
    def chat(self, messages: list[dict], tools: list[dict] | None = None,
             tool_choice: str = "auto", max_tokens: int = 4096) -> Any:
        """Send messages, get response. Returns raw SDK response object."""


class AzureOpenAIClient(BaseLLMClient):
    def __init__(self, endpoint: str, api_key: str, deployment: str,
                 api_version: str = "2024-12-01-preview"):
        from openai import AzureOpenAI
        self._client     = AzureOpenAI(azure_endpoint=endpoint, api_key=api_key,
                                        api_version=api_version)
        self._deployment = deployment

    @classmethod
    def from_env(cls) -> "AzureOpenAIClient":
        for var in ["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_KEY", "AZURE_OPENAI_DEPLOYMENT"]:
            if not os.environ.get(var):
                raise EnvironmentError(f"Missing env var: {var}")
        return cls(
            endpoint    = os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key     = os.environ["AZURE_OPENAI_KEY"],
            deployment  = os.environ["AZURE_OPENAI_DEPLOYMENT"],
            api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
        )

    def chat(self, messages, tools=None, tool_choice="auto", max_tokens=4096):
        kwargs = dict(model=self._deployment, messages=messages, max_tokens=max_tokens)
        if tools:
            kwargs["tools"]       = tools
            kwargs["tool_choice"] = tool_choice
        return self._client.chat.completions.create(**kwargs)


class MockLLMClient(BaseLLMClient):
    """For unit testing — no API calls made. Queue up responses."""

    def __init__(self):
        self._queue = []

    def queue_text(self, text: str) -> "MockLLMClient":
        self._queue.append(self._text_resp(text))
        return self

    def queue_tool(self, tool_name: str, args: dict) -> "MockLLMClient":
        self._queue.append(self._tool_resp(tool_name, args))
        return self

    def chat(self, messages, tools=None, tool_choice="auto", max_tokens=4096):
        if not self._queue:
            raise RuntimeError("MockLLMClient queue empty")
        return self._queue.pop(0)

    @staticmethod
    def _text_resp(text):
        import types
        msg = types.SimpleNamespace(content=text, tool_calls=None)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    @staticmethod
    def _tool_resp(tool_name, args):
        import types
        tc  = types.SimpleNamespace(
            id=f"tc_{tool_name}",
            function=types.SimpleNamespace(name=tool_name, arguments=json.dumps(args))
        )
        msg = types.SimpleNamespace(content=None, tool_calls=[tc])
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])
