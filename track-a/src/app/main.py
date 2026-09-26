"""FastAPI application factory and lifespan."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.routes import documents, health, search
from .config import get_settings
from .core.qdrant import ensure_collection, get_qdrant_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    app.state.qdrant = None
    app.state.qdrant_error = None
    app.state.qdrant_collection_created = False
    # Best-effort: Qdrant may be down during the skeleton phase. We do not fail startup.
    try:
        client = get_qdrant_client(settings)
        app.state.qdrant_collection_created = ensure_collection(client, settings)
        app.state.qdrant = client
    except Exception as exc:  # pragma: no cover - depends on live infra
        app.state.qdrant_error = str(exc)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Track A Agentic RAG",
        version="0.1.0",
        description="Skeleton: async FastAPI + Pydantic v2 schemas + Qdrant (dense + sparse).",
        lifespan=lifespan,
    )
    app.include_router(health.router, tags=["health"])
    app.include_router(documents.router, prefix="/api/v1/documents", tags=["documents"])
    app.include_router(search.router, prefix="/api/v1/search", tags=["search"])
    return app


app = create_app()
