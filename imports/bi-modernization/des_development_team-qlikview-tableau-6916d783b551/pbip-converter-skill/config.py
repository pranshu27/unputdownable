from dotenv import load_dotenv
from pathlib import Path
import os
from autogen_ext.models.openai import AzureOpenAIChatCompletionClient

# ── Secrets: loaded from .env (migrate to Azure Key Vault once available) ──────
# ── AWS SecretsManager (commented out — using .env instead) ──────────────────
# from AWSSecretsManager import SecretsManagerClient
# secrets_manager_client_key = SecretsManagerClient(
#     AWS_PROFILE_NAME="409344278376_LLM_Developer",
#     AWS_SECRET_NAME="arn:aws:secretsmanager:us-east-2:409344278376:secret:/LLM/Citi/tableau-prep-autogen/Application/ApplicationAccessKeys/Azure/dataeconomyllm2/AccessCredentials-prLjs4",
#     AWS_REGION_NAME="us-east-2"
# )
# secrets_manager_client_key.load_secrets_to_env()

load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)

azure_client = AzureOpenAIChatCompletionClient(
    azure_deployment=os.getenv("AZURE_DEPLOYMENT"),
    azure_endpoint=os.getenv("AZURE_OPENAI_API_BASE"),
    model=os.getenv("AZURE_DEPLOYMENT", "gpt5-mini"),
    api_version=os.getenv("AZURE_API_VERSION"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    seed=8350,
    max_retries=5,
    model_info={
        "vision": False,
        "function_calling": True,
        "json_output": True,
        "family": "unknown",
        "structured_output": True,
    },
)
