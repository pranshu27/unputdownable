"""CLI runner for the agentic pipeline.

Usage:
    python -m app.run --input ../app_CALCULATE_EINTERACTION \
        --mapping m_4202_dt_chn_rltinteractionagreement

Loads config from configs/pipeline.yml (overridable via flags), runs the full
multi-agent workflow, prints the FinalResult, and writes it to generated/.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

import yaml

from app.orchestrators.pyspark_codegen_workflow import run_codegen
from app.utils.logger import get_logger

logger = get_logger("app.run")

ROOT = Path(__file__).resolve().parents[1]


def load_config(path: str) -> dict:
    cfg_path = (ROOT / path) if not os.path.isabs(path) else Path(path)
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    return {}


async def _main(args: argparse.Namespace) -> None:
    cfg = load_config(args.config)

    input_folder = args.input or cfg.get("input_folder", "../app_CALCULATE_EINTERACTION")
    focus_mapping = args.mapping or cfg.get("focus_mapping")
    # Resolve input folder relative to the project root.
    if not os.path.isabs(input_folder):
        input_folder = str((ROOT / input_folder).resolve())

    meta_data = {
        "mapping_name": focus_mapping,
        "target_table": cfg.get("target_table"),
        "merge_keys": cfg.get("merge_keys", []),
        "update_strategy": cfg.get("update_strategy", "DD_UPDATE"),
    }
    if args.limit:
        meta_data["_node_limit"] = args.limit

    logger.info("Running pipeline | folder=%s | mapping=%s", input_folder, focus_mapping)
    result = await run_codegen(
        input_folder=input_folder,
        focus_mapping=focus_mapping,
        meta_data=meta_data,
        node_limit=args.limit,
        human_mode=args.human,
        record=not args.no_record,
        trace=not args.no_trace,
    )

    out_dir = ROOT / "generated"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"{focus_mapping or 'mapping'}.result.json"
    out_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
    logger.info("Wrote %s", out_file)

    print("\n================ FINAL RESULT ================")
    print(json.dumps(result, indent=2)[:6000])


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the agentic Infa->PySpark pipeline")
    parser.add_argument("--config", default="configs/pipeline.yml")
    parser.add_argument("--input", default=None, help="Input folder of PowerCenter XML")
    parser.add_argument("--mapping", default=None, help="Focus mapping name")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of nodes (smoke run to save tokens)",
    )
    parser.add_argument(
        "--human",
        choices=["auto", "interactive"],
        default="auto",
        help="Human-in-the-loop gate mode (auto=CI, interactive=console approval)",
    )
    parser.add_argument(
        "--no-record",
        action="store_true",
        help="Disable persisting per-step artifacts under runs/",
    )
    parser.add_argument(
        "--no-trace",
        action="store_true",
        help="Disable Langfuse tracing even when credentials are present",
    )
    asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    main()
