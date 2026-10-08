"""Pydantic models for glossary curation requests and responses."""

from typing import Any, Optional

from pydantic import BaseModel


class UpdateTermDescriptionRequest(BaseModel):
    """Request to update a glossary term's description."""

    term_id: int
    description: str
    template_id: Optional[int] = None


class FieldUpdate(BaseModel):
    """A single custom field value update."""

    field_id: int
    value: Any


class UpdateCustomFieldValuesRequest(BaseModel):
    """Request to batch-update custom field values on a glossary term."""

    term_id: int
    field_updates: list[FieldUpdate]
    template_id: Optional[int] = None


class WriteResponse(BaseModel):
    """Successful write-back response."""

    success: bool
    term_id: int
    detail: str
    alation_response: Optional[dict] = None


class ErrorResponse(BaseModel):
    """Error response for failed write-back operations."""

    success: bool = False
    term_id: Optional[int] = None
    detail: str
    status_code: Optional[int] = None
