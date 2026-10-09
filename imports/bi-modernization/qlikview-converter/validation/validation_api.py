"""
validation_api.py
=================
FastAPI router that exposes the Tier 1 validation logic as HTTP endpoints.

Endpoints
---------
POST /validation/validate
    Runs validation against a homogeneous JSON file (and optionally a .pbix
    file).  Returns a JSON body with the overall score, per-check breakdown,
    gap count and a download URL for the Excel report.

GET  /validation/download/{workbook_id}
    Streams the generated Excel (.xlsx) report back to the caller.

Usage (include in main.py)
--------------------------
    from validation.validation_api import router as validation_router
    app.include_router(validation_router)
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import FileResponse

# ── Load the validator module (filename contains a space, so use importlib) ──
_VALIDATOR_PATH = Path(__file__).parent / "step2_validator 4.py"

_spec   = importlib.util.spec_from_file_location("step2_validator", _VALIDATOR_PATH)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

run_validation: callable = _module.run_validation  # programmatic entry point

# ── In-memory store mapping workbook_id → excel path (per process) ──────────
_excel_store: dict[str, str] = {}

router = APIRouter(prefix="/validation", tags=["Validation"])


@router.post("/validate", summary="Run Tier 1 validation on a homogeneous JSON")
async def validate(
    json_file: str = Form(
        ...,
        description="Absolute or relative path to the homogeneous JSON file to validate.",
    ),
    pbix_file: Optional[str] = Form(
        None,
        description=(
            "Absolute or relative path to the source .pbix file. "
            "When omitted the validator runs in cross-validation mode "
            "(validates the JSON internally without comparing to a PBIX)."
        ),
    ),
    bim_file: Optional[str] = Form(
        None,
        description=(
            "Absolute or relative path to a model.bim file exported from "
            "Tabular Editor 2. Enables full D1-D5 semantic checks even when "
            "the DataModel inside the PBIX is binary."
        ),
    ),
    out_dir: str = Form(
        "./validation_output",
        description="Directory where the output files (JSON, CSV, Excel) are written.",
    ),
) -> dict:
    """
    Run the full Tier 1 validation (D1–D7 checks) and return:

    - **score** — overall validation score (0-100 %)
    - **verdict** — PASS / FAIL
    - **check_summary** — per-check (D1–D7) breakdown
    - **gaps_count** — number of FAIL / MISSING items
    - **excel_download_url** — relative URL to download the Excel report
    """
    # ── Validate inputs ───────────────────────────────────────────────
    json_path = Path(json_file)
    if not json_path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"JSON file not found: {json_file}",
        )

    if pbix_file:
        pbix_path = Path(pbix_file)
        if not pbix_path.exists():
            raise HTTPException(
                status_code=400,
                detail=f"PBIX file not found: {pbix_file}",
            )
        pbix_file = str(pbix_path.resolve())

    if bim_file:
        bim_path = Path(bim_file)
        if not bim_path.exists():
            raise HTTPException(
                status_code=400,
                detail=f"model.bim file not found: {bim_file}",
            )
        bim_file = str(bim_path.resolve())

    # ── Run validation ────────────────────────────────────────────────
    try:
        result = run_validation(
            json_path  = str(json_path.resolve()),
            pbix_path  = pbix_file,
            bim_path   = bim_file,
            out_dir    = out_dir,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Validation failed: {exc}",
        ) from exc

    # ── Register Excel path for download ─────────────────────────────
    workbook_id = result["workbook_id"]
    excel_path  = result.get("excel_path")
    if excel_path:
        _excel_store[workbook_id] = excel_path

    # ── Build response ────────────────────────────────────────────────
    response = {
        "workbook_id":          workbook_id,
        "score":                result["score"],
        "verdict":              result["verdict"],
        "total_checks":         result["total_checks"],
        "gaps_count":           result["gaps_count"],
        "timestamp":            result["timestamp"],
        "check_summary":        result["check_summary"],
        "excel_download_url":   (
            f"/validation/download/{workbook_id}"
            if excel_path else None
        ),
        "output_directory":     out_dir,
    }
    return response


@router.get(
    "/download/{workbook_id}",
    summary="Download the Excel validation report",
    response_class=FileResponse,
)
async def download_excel(workbook_id: str) -> FileResponse:
    """
    Stream the Excel (.xlsx) validation report for *workbook_id* back to the
    caller.  The report is generated by a prior call to **POST /validation/validate**.
    """
    excel_path = _excel_store.get(workbook_id)
    if not excel_path or not Path(excel_path).exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"No Excel report found for workbook_id '{workbook_id}'. "
                "Run POST /validation/validate first."
            ),
        )
    filename = f"validation_report_{workbook_id}.xlsx"
    return FileResponse(
        path=excel_path,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        filename=filename,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
