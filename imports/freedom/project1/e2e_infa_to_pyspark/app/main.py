"""FastAPI entrypoint for the agentic Infa->PySpark codegen backend.

Mirrors the des_ reference repos' app/main.py: a FastAPI app exposing a single endpoint
that kicks off the multi-agent workflow on a SingleThreadedAgentRuntime.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config.settings import settings
from app.orchestrators.pyspark_codegen_workflow import run_codegen

app = FastAPI(title="Infa->PySpark Agentic Codegen")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CodegenRequest(BaseModel):
    input_folder: str
    focus_mapping: Optional[str] = None
    mapping_name: Optional[str] = None
    target_table: Optional[str] = None
    merge_keys: List[str] = []
    update_strategy: str = "DD_UPDATE"


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok", "app": settings.app_name}


@app.post("/codegen")
async def codegen(req: CodegenRequest) -> Dict[str, Any]:
    meta_data = {
        "mapping_name": req.mapping_name or req.focus_mapping,
        "target_table": req.target_table,
        "merge_keys": req.merge_keys,
        "update_strategy": req.update_strategy,
    }
    result = await run_codegen(
        input_folder=req.input_folder,
        focus_mapping=req.focus_mapping,
        meta_data=meta_data,
    )
    return {"result": result}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", str(settings.port))))
