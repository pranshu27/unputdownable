"""Service layer for glossary term curation write-back operations."""

import asyncio
import logging
from typing import Optional

import aiohttp

from linker_agent.clients.alation_client import SwaggerAPIClient
from linker_agent.models.curation_models import (
    ErrorResponse,
    FieldUpdate,
    WriteResponse,
)

logger = logging.getLogger(__name__)


class CurationService:
    """Orchestrates validation and delegates write operations to SwaggerAPIClient."""

    def __init__(self, client: SwaggerAPIClient):
        self._client = client

    async def update_term_description(
        self,
        term_id: int,
        description: str,
        template_id: Optional[int] = None,
    ) -> WriteResponse | ErrorResponse:
        """Validate inputs and update a glossary term's description.

        Returns:
            WriteResponse on success, ErrorResponse on failure.
        """
        logger.info(f"Updating description for term_id={term_id}, template_id={template_id}")

        if not description or not description.strip():
            logger.error(f"Empty description for term_id={term_id}")
            return ErrorResponse(
                term_id=term_id,
                detail="Description must not be empty.",
                status_code=400,
            )

        try:
            resolved_tid = await self._client._resolve_template_id(term_id, template_id)
            result = await self._client.update_term_description(
                term_id=term_id,
                description=description,
                template_id=resolved_tid,
            )
            logger.debug(f"Alation response: {result}")
            return WriteResponse(
                success=True,
                term_id=term_id,
                detail="Description updated successfully.",
                alation_response=result,
            )
        except aiohttp.ClientResponseError as exc:
            status = exc.status
            mapped_status = 502 if status >= 500 else status
            logger.error(f"Alation HTTP {status} for term_id={term_id}: {exc.message}")
            return ErrorResponse(
                term_id=term_id,
                detail=f"Alation API error: {exc.message}",
                status_code=mapped_status,
            )
        except aiohttp.ClientConnectorError as exc:
            logger.error(f"Connection error updating term_id={term_id}: {exc}")
            return ErrorResponse(
                term_id=term_id,
                detail=f"Could not reach Alation: {exc}",
                status_code=503,
            )
        except asyncio.TimeoutError:
            logger.error(f"Timeout updating term_id={term_id}")
            return ErrorResponse(
                term_id=term_id,
                detail="Request to Alation timed out.",
                status_code=503,
            )

    async def update_custom_field_values(
        self,
        term_id: int,
        field_updates: list[FieldUpdate],
        template_id: Optional[int] = None,
    ) -> WriteResponse | ErrorResponse:
        """Validate inputs and batch-update custom field values on a term.

        Returns:
            WriteResponse on success, ErrorResponse on failure.
        """
        field_ids = [fu.field_id for fu in field_updates] if field_updates else []
        logger.info(
            f"Updating custom fields for term_id={term_id}, "
            f"field_ids={field_ids}, template_id={template_id}"
        )

        if not field_updates:
            logger.error(f"Empty field_updates for term_id={term_id}")
            return ErrorResponse(
                term_id=term_id,
                detail="field_updates must not be empty.",
                status_code=400,
            )

        resolved_tid = await self._client._resolve_template_id(term_id, template_id)
        logger.info(f"Resolved template_id={resolved_tid} for term_id={term_id}")

        payload = []
        for fu in field_updates:
            entry: dict = {
                "field_id": fu.field_id,
                "otype": "glossary_term",
                "oid": term_id,
                "value": fu.value,
            }
            if resolved_tid is not None:
                entry["template_id"] = resolved_tid
            payload.append(entry)

        try:
            result = await self._client.update_custom_field_values(payload)
            logger.debug(f"Alation response: {result}")
            return WriteResponse(
                success=True,
                term_id=term_id,
                detail="Custom field values updated successfully.",
                alation_response=result,
            )
        except aiohttp.ClientResponseError as exc:
            status = exc.status
            mapped_status = 502 if status >= 500 else status
            logger.error(
                f"Alation HTTP {status} for term_id={term_id}, field_ids={field_ids}: {exc.message}"
            )
            return ErrorResponse(
                term_id=term_id,
                detail=f"Alation API error: {exc.message}",
                status_code=mapped_status,
            )
        except aiohttp.ClientConnectorError as exc:
            logger.error(f"Connection error for term_id={term_id}, field_ids={field_ids}: {exc}")
            return ErrorResponse(
                term_id=term_id,
                detail=f"Could not reach Alation: {exc}",
                status_code=503,
            )
        except asyncio.TimeoutError:
            logger.error(f"Timeout for term_id={term_id}, field_ids={field_ids}")
            return ErrorResponse(
                term_id=term_id,
                detail="Request to Alation timed out.",
                status_code=503,
            )
