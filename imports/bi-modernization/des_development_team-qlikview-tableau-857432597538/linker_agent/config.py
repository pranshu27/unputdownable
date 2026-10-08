"""
Configuration for Linker Agent
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel


class Setting(BaseModel):
    """Typed, validated configuration loaded from environment variables."""

    base_url: str
    api_key: str
    depl_name: str
    api_ver: str

    alation_base: str
    alation_api_token: str
    glossary_id: int
    alation_verify_ssl: bool = True

    confidence_threshold: int
    cache_hours: int
    cache_dir: str

    # PostgreSQL — KPI rationalization catalog
    # POSTGRES_URL takes precedence; individual fields are used as fallback.
    postgres_url: str = ""
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = ""
    postgres_user: str = ""
    postgres_password: str = ""
    postgres_schema: str = "public"

    @property
    def postgres_conn_str(self) -> str:
        """Full asyncpg connection string. POSTGRES_URL wins if set."""
        if self.postgres_url:
            return self.postgres_url
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


def get_config() -> Setting:
    load_dotenv()
    return Setting(
        base_url=os.environ.get("AZURE_OPENAI_API_BASE", ""),
        api_key=os.environ.get("AZURE_OPENAI_API_KEY", ""),
        depl_name=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4"),
        api_ver=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
        alation_base=os.environ.get("ALATION_BASE_URL", ""),
        alation_api_token=os.environ.get("ALATION_API_TOKEN", ""),
        glossary_id=int(os.environ.get("ALATION_GLOSSARY_ID", "1")),
        alation_verify_ssl=os.environ.get("ALATION_VERIFY_SSL", "true").lower() != "false",
        confidence_threshold=int(os.environ.get("LINKER_CONFIDENCE_THRESHOLD", "60")),
        cache_hours=int(os.environ.get("LINKER_CACHE_HOURS", "24")),
        cache_dir=os.environ.get("LINKER_CACHE_DIR", "./cache"),
        postgres_url=os.environ.get("POSTGRES_URL", ""),
        postgres_host=os.environ.get("POSTGRES_HOST", "localhost"),
        postgres_port=int(os.environ.get("POSTGRES_PORT", "5432")),
        postgres_db=os.environ.get("POSTGRES_DB", ""),
        postgres_user=os.environ.get("POSTGRES_USER", ""),
        postgres_password=os.environ.get("POSTGRES_PASSWORD", ""),
        postgres_schema=os.environ.get("POSTGRES_SCHEMA", "public"),
    )


# ---------------------------------------------------------------------------
# Backward-compatible module-level constants (kept for existing imports)
# ---------------------------------------------------------------------------

CACHE_DIR = os.getenv("LINKER_CACHE_DIR", "./cache")
Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)

AZURE_OPENAI_API_BASE = os.getenv("AZURE_OPENAI_API_BASE", "")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")

ALATION_BASE_URL = os.getenv("ALATION_BASE_URL", "")
ALATION_API_TOKEN = os.getenv("ALATION_API_TOKEN", "")
ALATION_GLOSSARY_ID = int(os.getenv("ALATION_GLOSSARY_ID", "1"))

CONFIDENCE_THRESHOLD = int(os.getenv("LINKER_CONFIDENCE_THRESHOLD", "60"))
CACHE_HOURS = int(os.getenv("LINKER_CACHE_HOURS", "24"))
