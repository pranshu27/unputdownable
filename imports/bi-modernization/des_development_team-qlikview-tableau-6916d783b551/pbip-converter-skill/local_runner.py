"""
local_runner.py — Run the full PBIP conversion pipeline on a local JSON file.

Usage:
    cd pbip-converter-skill

    # Single-extraction PBIX (everything in one JSON):
    python local_runner.py inputs/GA-32000.json
    python local_runner.py inputs/GA-31999.json --output-dir outputs/

    # Thin / live-connected PBIX (semantic model + report as two JSONs):
    python local_runner.py inputs/thinfiledata.json inputs/thinfilereport.json
    #   ^ order does not matter — the runner auto-detects which side is which.

The script imports the pipeline functions directly (no subprocess calls):
    parse_common_model  ->  map_intermediate  ->  write_pbip  ->  validate
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Avoid noisy "Event loop is closed" tracebacks from Windows ProactorEventLoop
# finalizers running after asyncio.run() closes the loop. Selector loop works
# fine for the Azure OpenAI HTTP calls and doesn't have the GC race.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

load_dotenv()

# Make the package importable when run from this folder.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from skills.json_to_pbip.src.parser import detect_source, parse_common_model
from skills.json_to_pbip.src.mapper import map_intermediate
from skills.json_to_pbip.src.writer import write_pbip
from skills.json_to_pbip.src.validator import validate
from skills.json_to_pbip.src.merger import merge_thin_live, check_visual_bindings


def _load_raw(path: str) -> dict:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Input JSON not found: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_pipeline(input_paths, output_dir: str = "outputs") -> dict:
    """Run the full conversion. `input_paths` is one path (single-extraction
    PBIX) or two paths (thin / live-connect: data + report, any order).
    """
    if isinstance(input_paths, str):
        input_paths = [input_paths]
    input_paths = [os.path.abspath(p) for p in input_paths]
    output_dir = os.path.abspath(output_dir)

    if len(input_paths) == 1:
        print(f"\n[1/4] Loading {input_paths[0]}")
        raw = _load_raw(input_paths[0])
    elif len(input_paths) == 2:
        print(f"\n[1/4] Loading + merging two inputs (thin / live-connect):")
        for p in input_paths:
            print(f"      - {p}")
        a, b = _load_raw(input_paths[0]), _load_raw(input_paths[1])
        raw = merge_thin_live(a, b)
        # Diagnostic: warn (don't fail) on any visual field that doesn't
        # resolve to a merged table column or measure.
        broken = check_visual_bindings(raw["result"])
        if broken:
            print(f"      Unresolved bindings: {len(broken)} (first 10 shown)")
            for b_ in broken[:10]:
                print(f"        - {b_}")
        else:
            print("      Unresolved bindings: 0")
    else:
        raise ValueError(
            f"Expected 1 (single PBIX) or 2 (thin/live-connect data+report) "
            f"input paths, got {len(input_paths)}."
        )

    # Some extractors wrap the common-model under a top-level "result" key
    # (alongside report_id, tool_type, status, etc.). Unwrap so the parser
    # sees the schema directly; preserve top-level tool_type as a fallback
    # source hint when the inner dict doesn't carry it.
    if isinstance(raw.get("result"), dict) and "schema_version" in raw["result"]:
        data = raw["result"]
        if raw.get("tool_type") and not data.get("tool_type"):
            data["tool_type"] = raw["tool_type"]
    else:
        data = raw

    print("[2/4] Parsing common-model JSON")
    source = detect_source(data)
    intermediate = parse_common_model(data, source, None)
    n_tables = len(intermediate.get("tables", []))
    n_measures = sum(len(t.get("measures", [])) for t in intermediate.get("tables", []))
    n_rels = len(intermediate.get("relationships", []))
    n_pages = len(intermediate.get("pages", []))
    n_visuals = sum(len(p.get("visuals", [])) for p in intermediate.get("pages", []))
    print(f"      source={source}  tables={n_tables}  measures={n_measures}  "
          f"relationships={n_rels}  pages={n_pages}  visuals={n_visuals}")

    print("[3/4] Mapping (LLM only for measures without expressions.dax)")
    mapped = map_intermediate(intermediate)
    report_name = mapped.get("reportName") or "MyReport"
    report_dir = os.path.join(output_dir, report_name)
    print(f"      report_name={report_name}")

    print(f"[4/4] Writing .pbip folder to {report_dir}")
    files = write_pbip(mapped, report_dir)
    print(f"      files_written={len(files)}")

    print("\nValidating output structure")
    errors = validate(report_dir)
    if errors:
        print("VALIDATION FAILED:")
        for e in errors:
            print(f"  x {e}")
    else:
        print("VALIDATION PASSED")

    pbip_files = [f for f in files if f.endswith(".pbip")]
    pbip_entry = os.path.join(report_dir, pbip_files[0]) if pbip_files else None
    print(f"\nOpen this in Power BI Desktop:\n  {pbip_entry}\n")

    return {
        "inputs": input_paths,
        "output_dir": report_dir,
        "report_name": report_name,
        "files": files,
        "errors": errors,
        "pbip_entry": pbip_entry,
    }


def main():
    ap = argparse.ArgumentParser(
        description="Run the PBIP conversion pipeline on a local JSON file "
                    "(or two JSONs for a thin / live-connected PBIX).",
    )
    ap.add_argument(
        "inputs",
        nargs="+",
        help="One JSON path (single-extraction PBIX), or two JSON paths "
             "(thin/live-connect: data + report, any order).",
    )
    ap.add_argument(
        "--output-dir",
        default=str(_HERE / "outputs"),
        help="Output directory (a subfolder named after the report is created here).",
    )
    args = ap.parse_args()

    if len(args.inputs) not in (1, 2):
        ap.error("expected 1 or 2 input JSON paths")

    result = run_pipeline(args.inputs, args.output_dir)
    sys.exit(0 if not result["errors"] else 1)


if __name__ == "__main__":
    main()
