"""Shared enums used across the API schemas."""

from enum import Enum


class DocumentFormat(str, Enum):
    """Supported source document formats (Strategy Pattern dispatch key)."""

    PDF = "pdf"
    MARKDOWN = "md"
    DOCX = "docx"


class ChunkStatus(str, Enum):
    """Lifecycle status of an ingested document/chunk."""

    PENDING = "pending"
    EMBEDDED = "embedded"
    FAILED = "failed"
