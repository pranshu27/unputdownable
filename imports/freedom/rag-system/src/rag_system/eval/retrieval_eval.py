"""Retrieval evaluation harness.

Evaluates /retrieve quality against a JSONL golden dataset with:
- recall@k (matcher coverage)
- nDCG@k (graded relevance)

Run:
    python -m rag_system.eval.retrieval_eval --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


@dataclass(frozen=True)
class Matcher:
    """Relevance matcher rule used to score retrieved hits against expectations."""

    score: int = 1
    node_class: str | None = None
    source_file_contains: str | None = None
    name_contains: str | None = None
    text_contains: str | None = None
    metadata_contains: dict[str, str] | None = None


def _contains(value: Any, needle: str | None) -> bool:
    if not needle:
        return True
    if value is None:
        return False
    return needle.lower() in str(value).lower()


def _metadata_contains(metadata: dict[str, Any], required: dict[str, str] | None) -> bool:
    if not required:
        return True
    for key, expected in required.items():
        if key not in metadata:
            return False
        if not _contains(metadata.get(key), expected):
            return False
    return True


def matcher_matches(hit: dict[str, Any], matcher: Matcher) -> bool:
    return (
        _contains(hit.get("node_class"), matcher.node_class)
        and _contains(hit.get("source_file"), matcher.source_file_contains)
        and _contains(hit.get("name"), matcher.name_contains)
        and _contains(hit.get("text"), matcher.text_contains)
        and _metadata_contains(hit.get("metadata") or {}, matcher.metadata_contains)
    )


def _relevance_for_hit(hit: dict[str, Any], matchers: list[Matcher]) -> int:
    best = 0
    for matcher in matchers:
        if matcher_matches(hit, matcher):
            best = max(best, int(matcher.score))
    return best


def _ranked_unique_matcher_scores(hits: list[dict[str, Any]], matchers: list[Matcher], k: int) -> list[int]:
    """Assign at most one matcher per rank position, and each matcher at most once.

    This keeps relevance aligned to matcher-level ground truth and guarantees
    nDCG normalization against the same matcher set.
    """

    remaining = list(matchers)
    scores: list[int] = []

    for hit in hits[:k]:
        best_idx = -1
        best_score = 0

        for idx, matcher in enumerate(remaining):
            if matcher_matches(hit, matcher) and int(matcher.score) > best_score:
                best_idx = idx
                best_score = int(matcher.score)

        if best_idx >= 0:
            scores.append(best_score)
            remaining.pop(best_idx)
        else:
            scores.append(0)

    if len(scores) < k:
        scores.extend([0] * (k - len(scores)))
    return scores


def dcg(scores: list[int]) -> float:
    total = 0.0
    for idx, rel in enumerate(scores):
        total += (2 ** rel - 1) / math.log2(idx + 2)
    return total


def ndcg_at_k(scores: list[int], ideal_scores: list[int], k: int) -> float:
    observed = scores[:k]
    ideal = ideal_scores[:k]
    if len(ideal) < k:
        ideal = ideal + [0] * (k - len(ideal))
    ideal_dcg = dcg(ideal)
    if ideal_dcg == 0:
        return 0.0
    return dcg(observed) / ideal_dcg


def evaluate_hits(hits: list[dict[str, Any]], matchers: list[Matcher], k: int) -> dict[str, Any]:
    top_hits = hits[:k]
    observed_scores = _ranked_unique_matcher_scores(top_hits, matchers, k)

    matched_matchers = 0
    for matcher in matchers:
        if any(matcher_matches(hit, matcher) for hit in top_hits):
            matched_matchers += 1

    total_matchers = max(len(matchers), 1)
    recall = matched_matchers / total_matchers

    ideal_scores = sorted((int(m.score) for m in matchers), reverse=True)
    ndcg = ndcg_at_k(observed_scores, ideal_scores, k)

    return {
        "recall_at_k": round(recall, 6),
        "ndcg_at_k": round(ndcg, 6),
        "matched_matchers": matched_matchers,
        "total_matchers": len(matchers),
        "observed_scores": observed_scores,
        "ideal_scores": ideal_scores,
        "hit_count": len(top_hits),
    }


def _load_dataset(dataset_path: Path) -> list[dict[str, Any]]:
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(dataset_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at line {line_no}: {exc}") from exc
        rows.append(obj)
    if not rows:
        raise ValueError("Dataset is empty")
    return rows


def _to_matchers(query_spec: dict[str, Any]) -> list[Matcher]:
    raw_matchers = query_spec.get("matchers") or []
    out: list[Matcher] = []
    for m in raw_matchers:
        out.append(
            Matcher(
                score=int(m.get("score", 1)),
                node_class=m.get("node_class"),
                source_file_contains=m.get("source_file_contains"),
                name_contains=m.get("name_contains"),
                text_contains=m.get("text_contains"),
                metadata_contains=m.get("metadata_contains"),
            )
        )
    return out


def _call_retrieve(
    base_url: str,
    query: str,
    mode: str,
    k: int,
    node_class: str | None,
    rerank: bool,
    timeout: float,
) -> list[dict[str, Any]]:
    params = {"q": query, "k": str(k), "mode": mode, "rerank": str(rerank).lower()}
    if node_class:
        params["node_class"] = node_class

    url = f"{base_url.rstrip('/')}/retrieve?{urlencode(params)}"
    try:
        with urlopen(url, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Failed to call {url}: {exc}") from exc

    hits = payload.get("hits") or []
    if not isinstance(hits, list):
        return []
    return hits


def _avg(values: list[float]) -> float:
    return (sum(values) / len(values)) if values else 0.0


def summarize_by_bucket(mode_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped_recall: dict[str, list[float]] = defaultdict(list)
    grouped_ndcg: dict[str, list[float]] = defaultdict(list)

    for row in mode_rows:
        bucket = str(row.get("bucket") or "general")
        metrics = row.get("metrics") or {}
        grouped_recall[bucket].append(float(metrics.get("recall_at_k") or 0.0))
        grouped_ndcg[bucket].append(float(metrics.get("ndcg_at_k") or 0.0))

    out: dict[str, dict[str, Any]] = {}
    for bucket in sorted(grouped_recall.keys()):
        out[bucket] = {
            "query_count": len(grouped_recall[bucket]),
            "avg_recall_at_k": round(_avg(grouped_recall[bucket]), 6),
            "avg_ndcg_at_k": round(_avg(grouped_ndcg[bucket]), 6),
        }
    return out


def run_eval(
    base_url: str,
    dataset_path: Path,
    modes: list[str],
    default_k: int,
    rerank: bool,
    timeout: float,
) -> dict[str, Any]:
    dataset = _load_dataset(dataset_path)

    report: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "dataset": str(dataset_path),
        "modes": {},
    }

    for mode in modes:
        mode_rows: list[dict[str, Any]] = []
        recall_values: list[float] = []
        ndcg_values: list[float] = []

        for row in dataset:
            query_id = row.get("id", "unknown")
            query_text = row.get("query", "")
            bucket = str(row.get("bucket") or "general")
            k = int(row.get("k", default_k))
            node_class = row.get("node_class")
            matchers = _to_matchers(row)

            if not matchers:
                raise ValueError(f"Query {query_id} has no matchers")

            hits = _call_retrieve(
                base_url=base_url,
                query=query_text,
                mode=mode,
                k=k,
                node_class=node_class,
                rerank=rerank,
                timeout=timeout,
            )

            metrics = evaluate_hits(hits=hits, matchers=matchers, k=k)
            recall_values.append(float(metrics["recall_at_k"]))
            ndcg_values.append(float(metrics["ndcg_at_k"]))

            mode_rows.append(
                {
                    "id": query_id,
                    "bucket": bucket,
                    "query": query_text,
                    "mode": mode,
                    "k": k,
                    "node_class": node_class,
                    "metrics": metrics,
                    "top_hit": {
                        "chunk_id": (hits[0].get("chunk_id") if hits else None),
                        "name": (hits[0].get("name") if hits else None),
                        "node_class": (hits[0].get("node_class") if hits else None),
                        "score": (hits[0].get("score") if hits else None),
                    },
                }
            )

        summary = {
            "query_count": len(mode_rows),
            "avg_recall_at_k": round(_avg(recall_values), 6),
            "avg_ndcg_at_k": round(_avg(ndcg_values), 6),
        }
        report["modes"][mode] = {
            "summary": summary,
            "by_bucket": summarize_by_bucket(mode_rows),
            "rows": mode_rows,
        }

    return report


def _print_report(report: dict[str, Any]) -> None:
    print("\nRetrieval Eval")
    print(f"Base URL: {report['base_url']}")
    print(f"Dataset:  {report['dataset']}")

    for mode, block in report["modes"].items():
        summary = block["summary"]
        print(
            f"\nMode={mode:>6} | queries={summary['query_count']:>2} "
            f"| avg_recall@k={summary['avg_recall_at_k']:.4f} "
            f"| avg_nDCG@k={summary['avg_ndcg_at_k']:.4f}"
        )

        by_bucket = block.get("by_bucket") or {}
        if len(by_bucket) > 1:
            print("  by_bucket:")
            for bucket, b in by_bucket.items():
                print(
                    f"    - {bucket:<18} queries={b['query_count']:>2} "
                    f"recall@k={b['avg_recall_at_k']:.4f} nDCG@k={b['avg_ndcg_at_k']:.4f}"
                )


def _threshold_failed(report: dict[str, Any], min_recall: float | None, min_ndcg: float | None) -> bool:
    failed = False
    for mode, block in report["modes"].items():
        summary = block["summary"]
        if min_recall is not None and summary["avg_recall_at_k"] < min_recall:
            print(
                f"FAIL threshold: mode={mode} avg_recall@k={summary['avg_recall_at_k']:.4f} < {min_recall:.4f}",
                file=sys.stderr,
            )
            failed = True
        if min_ndcg is not None and summary["avg_ndcg_at_k"] < min_ndcg:
            print(
                f"FAIL threshold: mode={mode} avg_nDCG@k={summary['avg_ndcg_at_k']:.4f} < {min_ndcg:.4f}",
                file=sys.stderr,
            )
            failed = True
    return failed


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Retrieval evaluation harness")
    parser.add_argument("--base-url", default="http://localhost:8000", help="RAG API base URL")
    parser.add_argument(
        "--dataset",
        default="eval/golden_retrieval.jsonl",
        help="Path to JSONL golden retrieval dataset",
    )
    parser.add_argument(
        "--modes",
        default="hybrid,vector,bm25",
        help="Comma-separated retrieval modes",
    )
    parser.add_argument("--k", type=int, default=8, help="Default top-k if query row omits k")
    parser.add_argument("--rerank", action="store_true", help="Evaluate with rerank=true")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout seconds")
    parser.add_argument("--output", default="", help="Optional report JSON path")
    parser.add_argument("--min-recall", type=float, default=None, help="Optional failure threshold")
    parser.add_argument("--min-ndcg", type=float, default=None, help="Optional failure threshold")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]

    report = run_eval(
        base_url=args.base_url,
        dataset_path=Path(args.dataset),
        modes=modes,
        default_k=args.k,
        rerank=args.rerank,
        timeout=args.timeout,
    )

    _print_report(report)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nWrote report: {out_path}")

    failed = _threshold_failed(report, min_recall=args.min_recall, min_ndcg=args.min_ndcg)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
