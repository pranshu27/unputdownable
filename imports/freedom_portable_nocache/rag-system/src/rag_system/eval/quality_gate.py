"""Quality gate checks for answer-level evaluation reports.

Week 4 objective: fail CI when faithfulness drops by more than an allowed
threshold from a locked baseline.

Example:
    python -m rag_system.eval.quality_gate \
      --baseline eval/ragas_baseline_w3.json \
      --current eval/ragas_report_latest.json \
      --metric faithfulness \
      --max-drop 0.02
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Report not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def _extract_metric(report: dict[str, Any], metric: str) -> float:
    scores = report.get("scores")
    if not isinstance(scores, dict):
        raise ValueError("Report is missing a 'scores' object")
    if metric not in scores:
        raise ValueError(f"Metric '{metric}' not found in report scores")
    try:
        return float(scores[metric])
    except Exception as exc:
        raise ValueError(f"Metric '{metric}' is not numeric: {scores[metric]!r}") from exc


def evaluate_drop_gate(
    baseline_report: dict[str, Any],
    current_report: dict[str, Any],
    metric: str,
    max_drop: float,
) -> tuple[bool, dict[str, float]]:
    baseline = _extract_metric(baseline_report, metric)
    current = _extract_metric(current_report, metric)

    drop = baseline - current
    allowed_min = baseline - max_drop
    # Numeric comparisons at exact boundaries can drift slightly due to float precision.
    passed = drop <= (max_drop + 1e-12)

    return passed, {
        "baseline": baseline,
        "current": current,
        "drop": drop,
        "allowed_min": allowed_min,
        "max_drop": max_drop,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Quality gate for RAGAS metrics")
    parser.add_argument("--baseline", required=True, help="Baseline report JSON path")
    parser.add_argument("--current", required=True, help="Current report JSON path")
    parser.add_argument("--metric", default="faithfulness", help="Metric key in report['scores']")
    parser.add_argument(
        "--max-drop",
        type=float,
        default=0.02,
        help="Maximum allowed regression from baseline (absolute points)",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    try:
        baseline_report = _load_json(Path(args.baseline))
        current_report = _load_json(Path(args.current))
        passed, stats = evaluate_drop_gate(
            baseline_report=baseline_report,
            current_report=current_report,
            metric=args.metric,
            max_drop=args.max_drop,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print("Quality Gate")
    print(f"metric:      {args.metric}")
    print(f"baseline:    {stats['baseline']:.4f}")
    print(f"current:     {stats['current']:.4f}")
    print(f"drop:        {stats['drop']:.4f}")
    print(f"allowed_min: {stats['allowed_min']:.4f}")

    if not passed:
        print(
            f"FAIL: metric '{args.metric}' dropped by {stats['drop']:.4f}, "
            f"which exceeds max_drop={stats['max_drop']:.4f}",
            file=sys.stderr,
        )
        return 1

    print("PASS: quality gate satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
