"""FastAPI application entry point for Linker Agent."""

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from linker_agent.api.routes.alation_route import router as alation_router
from linker_agent.api.routes.assets import router as assets_router
from linker_agent.api.routes.column_route import router as column_router
from linker_agent.api.routes.curation_route import router as curation_router
from linker_agent.clients.alation_client import SwaggerAPIClient, SwaggerAPIConfig
from linker_agent.config import get_config
from linker_agent.utils.logger import configure_logger

logger = configure_logger(__file__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_config()
    logger.info(f"Connecting to Alation at {cfg.alation_base}")
    api_config = SwaggerAPIConfig(
        base_url=cfg.alation_base,
        api_token=cfg.alation_api_token,
        verify_ssl=cfg.alation_verify_ssl,
    )
    async with SwaggerAPIClient(api_config) as client:
        app.state.alation_client = client
        logger.info("Alation client ready")
        yield
    logger.info("Alation client closed")


app = FastAPI(
    title="Linker Agent API",
    description=(
        "Intelligent data catalog linkage: match database columns to business "
        "glossary terms using a 3-tier pipeline (direct → semantic → generated), "
        "and write enrichment back to Alation."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(alation_router)
app.include_router(assets_router)
app.include_router(column_router)
app.include_router(curation_router)


@app.get("/", tags=["meta"])
def index():
    return {
        "service": "Linker Agent API",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3005)
