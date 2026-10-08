"""Routes for Alation glossary write-back (curation) operations."""

from fastapi import APIRouter, Depends, HTTPException, Request

from linker_agent.clients.alation_client import SwaggerAPIClient
from linker_agent.models.curation_models import (
    ErrorResponse,
    UpdateCustomFieldValuesRequest,
    UpdateTermDescriptionRequest,
    WriteResponse,
)
from linker_agent.services.curation_service import CurationService

router = APIRouter(prefix="/curation", tags=["curation"])


def get_client(request: Request) -> SwaggerAPIClient:
    return request.app.state.alation_client


@router.put("/term-description", response_model=WriteResponse)
async def update_term_description(
    request: UpdateTermDescriptionRequest,
    client: SwaggerAPIClient = Depends(get_client),
):
    """Update a glossary term's description in Alation."""
    service = CurationService(client)
    result = await service.update_term_description(
        term_id=request.term_id,
        description=request.description,
        template_id=request.template_id,
    )
    if isinstance(result, ErrorResponse):
        raise HTTPException(status_code=result.status_code or 500, detail=result.detail)
    return result


@router.put("/custom-field-values", response_model=WriteResponse)
async def update_custom_field_values(
    request: UpdateCustomFieldValuesRequest,
    client: SwaggerAPIClient = Depends(get_client),
):
    """Batch-update custom field values on a glossary term in Alation."""
    service = CurationService(client)
    result = await service.update_custom_field_values(
        term_id=request.term_id,
        field_updates=request.field_updates,
        template_id=request.template_id,
    )
    if isinstance(result, ErrorResponse):
        raise HTTPException(status_code=result.status_code or 500, detail=result.detail)
    return result
