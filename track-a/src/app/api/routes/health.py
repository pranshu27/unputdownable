"""Health check endpoint."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    app: str
    qdrant: str


@router.get("/health", response_model=HealthResponse, summary="Liveness + dependency status")
async def health(request: Request) -> HealthResponse:
    """Report app liveness and whether Qdrant is reachable.

    The app stays healthy even when Qdrant is down during the skeleton phase
    (stub-and-advance rule from ``plan.md``).
    """
    return HealthResponse(
        status="ok",
        app=request.app.title,
        qdrant="connected" if request.app.state.qdrant is not None else "unavailable",
    )
