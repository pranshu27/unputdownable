"""Routes for read-only Alation data access."""

from typing import Optional

from fastapi import APIRouter, Depends, Request

from linker_agent.clients.alation_client import SwaggerAPIClient

router = APIRouter(prefix="/alation", tags=["alation"])


def get_client(request: Request) -> SwaggerAPIClient:
    return request.app.state.alation_client


@router.get("/terms")
async def get_terms(
    glossary_id: int = 1,
    limit: Optional[int] = None,
    client: SwaggerAPIClient = Depends(get_client),
):
    """List business glossary terms."""
    terms = await client.get_terms(glossary_id=glossary_id, limit=limit)
    return {"status": "ok", "term_count": len(terms), "terms": terms}


@router.get("/glossary-tree")
async def get_glossary_tree(
    glossary_id: int = 1,
    client: SwaggerAPIClient = Depends(get_client),
):
    """Fetch all terms from a glossary AND its sub-glossaries."""
    return await client.get_glossary_tree(glossary_id=glossary_id)


@router.get("/terms-with-columns")
async def get_terms_with_columns(
    glossary_id: int = 2,
    client: SwaggerAPIClient = Depends(get_client),
):
    """List terms with their linked Alation column details."""
    terms = await client.get_terms_with_columns(glossary_id=glossary_id)
    return {"status": "ok", "term_count": len(terms), "terms": terms}
