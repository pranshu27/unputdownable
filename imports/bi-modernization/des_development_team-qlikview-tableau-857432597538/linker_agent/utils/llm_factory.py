import logging

from openai import AzureOpenAI

from linker_agent.config import get_config
from linker_agent.llm.azure_client import AzureOpenAIChatClient

logger = logging.getLogger(__name__)


def get_azure_open_ai() -> AzureOpenAI:
    """Return a synchronous AzureOpenAI client using config."""
    cfg = get_config()
    return AzureOpenAI(
        api_key=cfg.api_key,
        api_version=cfg.api_ver,
        azure_endpoint=cfg.base_url,
    )


def get_azure_chat_client() -> AzureOpenAIChatClient:
    """Return an AzureOpenAIChatClient using config."""
    logger.debug("Initializing Azure OpenAI Chat Client")
    cfg = get_config()
    return AzureOpenAIChatClient(
        endpoint=cfg.base_url,
        deployment_name=cfg.depl_name,
        api_key=cfg.api_key,
        api_version=cfg.api_ver,
    )
