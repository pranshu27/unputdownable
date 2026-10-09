from dotenv import load_dotenv
import os
from autogen_ext.models.openai import AzureOpenAIChatCompletionClient

# ── Google Gemini client (commented out — not in use, GPT-5 mini is active) ──
# from autogen_ext.models.semantic_kernel import SKChatCompletionAdapter
# from autogen_core.models import ModelFamily
# from semantic_kernel import Kernel
# from semantic_kernel.connectors.ai.google.google_ai import (
#     GoogleAIChatCompletion,
#     GoogleAIChatPromptExecutionSettings,
# )
# from semantic_kernel.memory.null_memory import NullMemory


# ── Secrets: loaded from .env (migrate to Azure Key Vault: jnj-demo-poc) ──────
# TODO: replace load_dotenv() with azure-keyvault-secrets client once
#       Key Vault Secrets Officer role is granted to psahijwani@dataeconomy.ai
#
# ── AWS SecretsManager (commented out — using .env / AKV instead) ─────────────
# from AWSSecretsManager import SecretsManagerClient
# secrets_manager_client_key = SecretsManagerClient(
#     AWS_PROFILE_NAME="409344278376_LLM_Developer",
#     AWS_SECRET_NAME="arn:aws:secretsmanager:us-east-2:409344278376:secret:/LLM/Citi/tableau-prep-autogen/...",
#     AWS_REGION_NAME="us-east-2"
# )
# secrets_manager_client_key.load_secrets_to_env()
# secrets_manager_client_key_azure2 = SecretsManagerClient(
#     AWS_PROFILE_NAME="409344278376_LLM_Developer",
#     AWS_SECRET_NAME="arn:aws:secretsmanager:us-east-2:409344278376:secret:CLIENT_B/...",
#     AWS_REGION_NAME="us-east-2"
# )
# secrets_manager_client_key_azure2.load_secrets_to_env()

load_dotenv()

# ── Active client: Azure GPT-5 mini ──────────────────────────────────────────
azure_client = AzureOpenAIChatCompletionClient(
    azure_deployment=os.getenv("AZURE_DEPLOYMENT"),
    azure_endpoint=os.getenv("AZURE_OPENAI_API_BASE"),
    model=os.getenv("AZURE_DEPLOYMENT", "gpt5-mini"),
    api_version=os.getenv("AZURE_API_VERSION"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    seed=8350,
    max_retries=5,
    model_info={
        "vision": True,
        "function_calling": True,
        "json_output": True,
        "family": "unknown",
        "structured_output": True,
    },
)

# ── Google Gemini client (commented out — not in use) ────────────────────────
# sk_client = GoogleAIChatCompletion(
#     gemini_model_id=os.getenv("GCP_MODEL_ID"),
#     api_key=os.getenv("GCP_API_KEY"),
# )
# settings = GoogleAIChatPromptExecutionSettings(
#     temperature=0.0,
#     top_p=0.15,
# )
# kernel = Kernel(memory=NullMemory())
# google_client = SKChatCompletionAdapter(
#     sk_client,
#     kernel=kernel,
#     prompt_settings=settings,
#     model_info={
#         "family": ModelFamily.GEMINI_2_0_FLASH,
#         "function_calling": False,
#         "json_output": False,
#         "vision": False,
#     },
# )
