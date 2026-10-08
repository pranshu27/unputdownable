"""
External API clients
"""
from linker_agent.clients.alation_client import (
    SwaggerAPIClient,
    SwaggerAPIConfig
)

__all__ = [
    "SwaggerAPIClient",
    "SwaggerAPIConfig",
]

# Aliases for cleaner API
AlationClient = SwaggerAPIClient
AlationConfig = SwaggerAPIConfig
