"""Validate that answer-eval questions are grounded in real Informatica XML files.

Checks:
1) Every row has a source_file.
2) source_file exists under INFA_XML_FOLDER.
3) Every expected entity appears in that source file content (case-insensitive).

Run:
    python -m rag_system.eval.validate_answer_dataset_grounding \
      --dataset eval/golden_answer_eval.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at line {line_no}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"Line {line_no} is not a JSON object")
        rows.append(row)

    if not rows:
        raise ValueError("Dataset is empty")
    return rows


def _discover_xml_files(root: Path) -> dict[str, Path]:
    mapping: dict[str, Path] = {}
    for p in root.rglob("*.XML"):
        mapping[p.name.lower()] = p
    return mapping


def validate_dataset(dataset: Path, infa_root: Path) -> tuple[bool, list[str]]:
    rows = _load_jsonl(dataset)
    xml_files = _discover_xml_files(infa_root)

    errors: list[str] = []
    for idx, row in enumerate(rows, start=1):
        row_id = row.get("id", f"row_{idx}")
        src = str(row.get("source_file") or "").strip()
        if not src:
            errors.append(f"{row_id}: missing source_file")
            continue

        xml_path = xml_files.get(src.lower())
        if xml_path is None:
            errors.append(f"{row_id}: source_file not found under INFA_XML_FOLDER: {src}")
            continue

        expected = row.get("expected_entities") or []
        if not isinstance(expected, list):
            errors.append(f"{row_id}: expected_entities must be a list")
            continue

        if not expected:
            errors.append(f"{row_id}: expected_entities is empty")
            continue

        content = xml_path.read_text(encoding="utf-8", errors="ignore").lower()
        for term in expected:
            term_s = str(term).strip()
            if not term_s:
                continue
            if term_s.lower() not in content:
                errors.append(f"{row_id}: expected term '{term_s}' not found in {src}")

    return (len(errors) == 0), errors


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate grounding of answer eval dataset")
    parser.add_argument("--dataset", default="eval/golden_answer_eval.jsonl", help="Answer eval JSONL path")
    parser.add_argument("--infa-root", default="", help="Override INFA_XML_FOLDER path")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    project_root = Path(__file__).resolve().parents[3]
    load_dotenv(project_root / ".env", override=False)

    infa_root_raw = args.infa_root.strip() or os.getenv("INFA_XML_FOLDER", "").strip()
    if not infa_root_raw:
        print("ERROR: INFA_XML_FOLDER is not set and --infa-root was not provided", file=sys.stderr)
        return 2

    dataset = Path(args.dataset)
    if not dataset.is_absolute():
        dataset = project_root / dataset

    infa_root = Path(infa_root_raw)
    if not infa_root.exists():
        print(f"ERROR: INFA root does not exist: {infa_root}", file=sys.stderr)
        return 2

    try:
        ok, errors = validate_dataset(dataset=dataset, infa_root=infa_root)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not ok:
        print("Grounding validation FAILED", file=sys.stderr)
        for err in errors:
            print(f"- {err}", file=sys.stderr)
        return 1

    print("Grounding validation PASSED")
    print(f"dataset: {dataset}")
    print(f"infa_root: {infa_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
