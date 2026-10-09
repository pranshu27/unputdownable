"""Runtime settings for the agentic codegen backend."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class Settings:
    app_name: str = "infa-to-pyspark-agentic"
    port: int = int(os.getenv("PORT", "3001"))

    # Iceberg / lakehouse target settings used by the generation prompts.
    catalog_name: str = os.getenv("ICEBERG_CATALOG", "lakehouse")
    warehouse_path: str = os.getenv("ICEBERG_WAREHOUSE", "s3://CLIENT_B-lakehouse/warehouse")

    # Field batching for large transformations (mirrors PC extractor batching).
    field_batch_size: int = 30

    # Collector barrier timeout (seconds).
    collector_timeout: int = 300

    cors_allow_origins: List[str] = field(default_factory=lambda: ["*"])


settings = Settings()
