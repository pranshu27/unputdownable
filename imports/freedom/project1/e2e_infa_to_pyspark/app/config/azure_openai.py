"""Azure OpenAI client configuration.

Mirrors the des_ reference repos:
- CLIENT_B_insurance_backend-agent-api/app/config/azure_openai.py
- dbt_codegen/app/config/config_config.py

A single shared `azure_client` is created once and injected into every agent. For the
gpt-4o family the client is pinned to ``temperature=0`` + a fixed ``seed`` so the
PowerCenter -> PySpark generation is deterministic and reproducible. The GPT-5 family
(e.g. ``gpt-5-mini``) only supports the default sampling temperature, so those knobs are
omitted automatically and determinism is enforced through the prompts instead.

Secrets are pulled from AWS Secrets Manager at import time in the reference deployment;
locally we fall back to a ``.env`` file.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

try:
    # Same dependency surface as the reference repos.
    from autogen_core.models import ModelInfo
    from autogen_ext.models.openai import AzureOpenAIChatCompletionClient
except Exception:  # pragma: no cover - allows import without autogen installed
    AzureOpenAIChatCompletionClient = None  # type: ignore
    ModelInfo = None  # type: ignore


def _load_secrets() -> None:
    """Load Azure credentials into the environment.

    In the reference deployment this uses SecretsManagerClient /
    KubernetesSecretsClient. Locally we fall back to a .env file.
    """
    try:
        from app.utils.secrets_manager import SecretsManagerClient

        SecretsManagerClient(
            aws_profile_name=os.getenv("AWS_PROFILE_NAME", ""),
            aws_secret_name=os.getenv("AWS_SECRET_NAME", ""),
            aws_region_name=os.getenv("AWS_REGION_NAME", "us-east-2"),
        ).load_secrets_to_env()
    except Exception:
        # Local dev path — rely on environment / .env only.
        pass

    load_dotenv()


_load_secrets()


def _get(*names: str, default: str = "") -> str:
    """First non-empty environment variable among ``names`` (supports aliases)."""
    for n in names:
        v = os.getenv(n)
        if v:
            return v
    return default


def _is_gpt5(model: str) -> bool:
    m = model.lower().replace("-", "").replace("_", "")
    return m.startswith("gpt5")


def build_azure_client():
    """Construct the shared Azure OpenAI chat client.

    The model name is derived from the deployment so a single ``AZURE_DEPLOYMENT`` value
    (e.g. ``gpt5-mini``) configures everything. Sampling controls are applied only for
    models that support them.
    """
    if AzureOpenAIChatCompletionClient is None:
        raise RuntimeError(
            "autogen-ext is not installed. Install requirements.txt to build the client."
        )

    deployment = _get("AZURE_DEPLOYMENT", "azure_deployment", default="gpt-4o")
    # Normalize the deployment name into a canonical model id (gpt5-mini -> gpt-5-mini).
    model = _get("AZURE_OPENAI_MODEL", "model", default=deployment)
    if _is_gpt5(model) and "gpt-5" not in model:
        model = "gpt-5-mini"
    kwargs = dict(
        azure_deployment=deployment,
        azure_endpoint=_get("AZURE_OPENAI_API_BASE", "base_url"),
        model=model,
        api_version=_get("AZURE_API_VERSION", "api_version", default="2024-08-01-preview"),
        api_key=_get("AZURE_OPENAI_API_KEY", "api_key"),
        max_retries=5,
    )

    # Help autogen reason about a deployment whose model id it may not ship metadata for.
    if ModelInfo is not None:
        kwargs["model_info"] = ModelInfo(
            vision=False,
            function_calling=True,
            json_output=True,
            family="gpt-5" if _is_gpt5(model) else "gpt-4o",
            structured_output=True,
        )

    if not _is_gpt5(model):
        # Deterministic decoding for the gpt-4o family.
        kwargs["temperature"] = 0
        kwargs["seed"] = 8350

    return AzureOpenAIChatCompletionClient(**kwargs)


# Shared client instance used by every agent (lazy so imports never fail).
azure_client = None
if AzureOpenAIChatCompletionClient is not None and _get(
    "AZURE_OPENAI_API_KEY", "api_key"
):
    azure_client = build_azure_client()
