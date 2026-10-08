"""
conftest.py — pytest configuration for security tests.

Adds the parent directory (qlikview-tableau/) to sys.path so
all imports in test files resolve correctly without needing
to install the package.
"""

import sys
import os
from unittest.mock import MagicMock

# Add qlikview-tableau/ to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set POSTGRES_URL before any module imports so create_engine doesn't get None
os.environ.setdefault("POSTGRES_URL", "postgresql://test:test@localhost:5432/test")

# Mock all heavy dependencies before any test module imports them
_mock_modules = [
    "config",
    "autogen_core",
    "autogen_core.models",
    "autogen_core._default_subscription",
    "autogen_core._default_topic",
    "autogen_ext",
    "autogen_ext.models",
    "autogen_ext.models.openai",
    "autogen_agentchat",
    "semantic_kernel",
    "semantic_kernel.connectors",
    "semantic_kernel.connectors.ai",
    "semantic_kernel.connectors.ai.google",
    "semantic_kernel.connectors.ai.google.google_ai",
    "semantic_kernel.connectors.ai.google.google_ai.services",
    "semantic_kernel.connectors.ai.google.google_ai.services.google_ai_chat_completion",
    "semantic_kernel.memory",
    "semantic_kernel.memory.null_memory",
    "semantic_kernel.kernel_pydantic",
    "AWSSecretsManager",
    "databricks",
    "databricks.sql",
    "sequentialworkflow",
    "agents_qlikview",
    "agents_powerbi",
    "agents_tableau",
    "powerbi_extractor",
    "layout_mapper",
    "prompts_powerbi",
    "prompts_qlikview",
    "extraction_schema",
]

for mod in _mock_modules:
    sys.modules[mod] = MagicMock()
