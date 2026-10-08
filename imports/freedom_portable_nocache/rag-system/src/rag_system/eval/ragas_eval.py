"""RAGAS evaluation harness for /answer endpoint.

Week 3 component: faithfulness + answer relevance scoring against a
JSONL answer dataset.

Dataset JSONL row schema (minimal):
    {
      "id": "qa_001",
      "query": "How is InteractionEvent_Id used?",
      "ground_truth": "InteractionEvent_Id flows through transformations and lineage paths..."
    }

Optional fields per row:
    - mode: hybrid|vector|bm25|auto (default: hybrid)
    - k: int (default from CLI)
    - rerank: bool (default from CLI)

Run:
    python -m rag_system.eval.ragas_eval \
      --base-url http://localhost:8000 \
      --dataset eval/golden_answer_eval.jsonl \
      --output eval/ragas_report_latest.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from dotenv import load_dotenv


@dataclass(frozen=True)
class AnswerCase:
    """Normalized answer-evaluation row consumed by the RAGAS harness."""

    id: str
    query: str
    ground_truth: str
    mode: str = "hybrid"
    k: int = 6
    rerank: bool = False


def _load_dataset(dataset_path: Path, default_k: int, default_mode: str, rerank: bool) -> list[AnswerCase]:
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    rows: list[AnswerCase] = []
    for line_no, raw in enumerate(dataset_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at line {line_no}: {exc}") from exc

        query = (obj.get("query") or "").strip()
        gt = (obj.get("ground_truth") or "").strip()
        if not query or not gt:
            raise ValueError(f"Line {line_no} must include non-empty query and ground_truth")

        rows.append(
            AnswerCase(
                id=str(obj.get("id") or f"row_{line_no}"),
                query=query,
                ground_truth=gt,
                mode=str(obj.get("mode") or default_mode),
                k=int(obj.get("k") or default_k),
                rerank=bool(obj.get("rerank") if obj.get("rerank") is not None else rerank),
            )
        )

    if not rows:
        raise ValueError("Dataset is empty")
    return rows


def _call_answer(
    base_url: str,
    case: AnswerCase,
    timeout: float,
    llm: bool,
    llm_model: str | None,
    use_graph: bool,
    relevancy_boost: bool,
    require_modern_contract: bool,
) -> dict[str, Any]:
    params = {
        "q": case.query,
        "k": str(case.k),
        "mode": case.mode,
        "rerank": str(case.rerank).lower(),
        "llm": str(llm).lower(),
        "use_graph": str(use_graph).lower(),
        "relevancy_boost": str(relevancy_boost).lower(),
    }
    if llm_model:
        params["llm_model"] = llm_model

    url = f"{base_url.rstrip('/')}/answer?{urlencode(params)}"
    try:
        with urlopen(url, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Failed to call {url}: {exc}") from exc

    if not isinstance(payload, dict):
        return {}

    if require_modern_contract:
        legacy_markers = {
            "smart_retrieval_requested",
            "friendly",
            "friendly_summary",
            "smart_plan",
        }
        if any(marker in payload for marker in legacy_markers):
            raise RuntimeError(
                "Detected legacy /answer response contract from server. "
                "RAGAS run is pointed at an outdated API instance that still emits deprecated fields. "
                "Restart the API on latest code before evaluating."
            )

        modern_markers = {
            "relevancy_boost_requested",
            "relevancy_boost_applied",
            "answer_strategy",
        }
        if not modern_markers.issubset(set(payload.keys())):
            raise RuntimeError(
                "Server /answer payload is missing modern relevancy fields "
                f"({', '.join(sorted(modern_markers))}). "
                "Likely stale deployment; restart API and rerun RAGAS."
            )

    return payload


def _extract_ragas_scores(result: Any) -> dict[str, float]:
    # RAGAS API shape may differ by version; handle dict-like and pandas export paths.
    out: dict[str, float] = {}

    for key in ("faithfulness", "answer_relevancy", "answer_relevance"):
        try:
            val = result[key]  # type: ignore[index]
            out[key] = float(val)
        except Exception:
            pass

    if out:
        return out

    if hasattr(result, "to_pandas"):
        df = result.to_pandas()
        for key in ("faithfulness", "answer_relevancy", "answer_relevance"):
            if key in df.columns:
                out[key] = float(df[key].mean())

    return out


def _configure_ragas_runtime(llm_model_override: str | None) -> tuple[Any, Any, str]:
    """Build explicit RAGAS runtime from project .env.

    Returns:
        (judge_llm, judge_embeddings, resolved_model)
    """
    project_root = Path(__file__).resolve().parents[3]
    load_dotenv(project_root / ".env", override=False)

    azure_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    azure_endpoint = (
        os.getenv("AZURE_OPENAI_API_BASE", "").strip()
        or os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    )
    azure_api_version = os.getenv("AZURE_API_VERSION", "2024-12-01-preview").strip()

    resolved_model = (
        (llm_model_override or "").strip()
        or os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "").strip()
        or os.getenv("AZURE_CHAT_DEPLOYMENT", "").strip()
        or os.getenv("OPENAI_MODEL", "").strip()
        or "gpt-4o"
    )

    if not azure_key:
        raise RuntimeError("AZURE_OPENAI_API_KEY is not configured in .env")
    if not azure_endpoint:
        raise RuntimeError("AZURE_OPENAI_API_BASE (or AZURE_OPENAI_ENDPOINT) is not configured in .env")
    if not resolved_model:
        raise RuntimeError(
            "No Azure chat deployment configured. Set AZURE_OPENAI_CHAT_DEPLOYMENT in .env"
        )

    try:
        from openai import AzureOpenAI
        from langchain_community.embeddings import HuggingFaceEmbeddings as LangchainHuggingFaceEmbeddings
        from ragas.llms import llm_factory
    except Exception as exc:
        raise RuntimeError("Missing runtime dependencies for Azure RAGAS setup") from exc

    azure_client = AzureOpenAI(
        api_key=azure_key,
        api_version=azure_api_version,
        azure_endpoint=azure_endpoint,
    )

    # Use local sentence-transformer embeddings for answer_relevancy metric.
    local_embedding_model = os.getenv("LOCAL_EMBEDDING_MODEL", "all-mpnet-base-v2").strip() or "all-mpnet-base-v2"
    judge_embeddings = LangchainHuggingFaceEmbeddings(
        model_name=local_embedding_model,
        encode_kwargs={"normalize_embeddings": True},
    )

    # For Azure OpenAI, the model argument is the Azure deployment name.
    judge_llm = llm_factory(model=resolved_model, provider="openai", client=azure_client)

    # Azure deployments may be named like "gpt5-mini" (without "gpt-" prefix).
    # RAGAS parameter auto-mapping only detects "gpt-5*", so enforce compatible
    # args for GPT-5 style deployments here.
    if re.match(r"^gpt\s*5", resolved_model.lower().replace("-", "").replace("_", "")):
        if hasattr(judge_llm, "model_args") and isinstance(judge_llm.model_args, dict):
            max_tokens_val = judge_llm.model_args.pop("max_tokens", 2048)
            judge_llm.model_args["max_completion_tokens"] = max(max_tokens_val, 2048)
            judge_llm.model_args["temperature"] = 1.0
            judge_llm.model_args.pop("top_p", None)

    return judge_llm, judge_embeddings, resolved_model


def run_eval(
    base_url: str,
    dataset_path: Path,
    default_k: int,
    default_mode: str,
    rerank: bool,
    timeout: float,
    llm: bool,
    llm_model: str | None,
    use_graph: bool,
    relevancy_boost: bool,
    require_modern_contract: bool,
    judge_timeout: int,
    judge_max_retries: int,
    judge_max_wait: int,
    judge_max_workers: int,
    ragas_raise_exceptions: bool,
) -> dict[str, Any]:
    # Local imports keep retrieval-only eval usable even if ragas is not installed.
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.run_config import RunConfig
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                category=DeprecationWarning,
                message=r"Importing .* from 'ragas\.metrics' is deprecated.*",
            )
            from ragas.metrics import answer_relevancy, faithfulness
    except Exception as exc:
        raise RuntimeError(
            "RAGAS dependencies are missing. Install with: pip install ragas datasets"
        ) from exc

    judge_llm, judge_embeddings, resolved_model = _configure_ragas_runtime(llm_model)

    cases = _load_dataset(
        dataset_path=dataset_path,
        default_k=default_k,
        default_mode=default_mode,
        rerank=rerank,
    )

    ragas_rows: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []

    for case in cases:
        payload = _call_answer(
            base_url=base_url,
            case=case,
            timeout=timeout,
            llm=llm,
            llm_model=llm_model,
            use_graph=use_graph,
            relevancy_boost=relevancy_boost,
            require_modern_contract=require_modern_contract,
        )

        evidence = payload.get("evidence") or []
        contexts = [str(e.get("cited_text") or "") for e in evidence if str(e.get("cited_text") or "").strip()]
        answer_text = str(payload.get("answer_text") or "")

        ragas_rows.append(
            {
                "question": case.query,
                "answer": answer_text,
                "contexts": contexts,
                "ground_truth": case.ground_truth,
            }
        )

        details.append(
            {
                "id": case.id,
                "query": case.query,
                "mode": case.mode,
                "k": case.k,
                "refused": bool(payload.get("refused")),
                "llm_used": bool(payload.get("llm_used")),
                "llm_error": payload.get("llm_error"),
                "evidence_count": len(contexts),
                "answer_chars": len(answer_text),
            }
        )

    ds = Dataset.from_list(ragas_rows)
    run_config = RunConfig(
        timeout=judge_timeout,
        max_retries=judge_max_retries,
        max_wait=judge_max_wait,
        max_workers=judge_max_workers,
    )

    try:
        result = evaluate(
            ds,
            metrics=[faithfulness, answer_relevancy],
            llm=judge_llm,
            embeddings=judge_embeddings,
            run_config=run_config,
            raise_exceptions=ragas_raise_exceptions,
        )
    except Exception as exc:
        msg = str(exc)
        if "OPENAI_API_KEY" in msg or "Missing credentials" in msg:
            raise RuntimeError(
                "RAGAS scoring requires an OpenAI API key for judge-model calls. "
                "Set OPENAI_API_KEY in your shell and retry."
            ) from exc
        if "incorrect api key" in msg.lower() or "invalid_api_key" in msg.lower():
            raise RuntimeError(
                "Azure OpenAI authentication failed for RAGAS judge model. "
                "Verify AZURE_OPENAI_API_KEY and AZURE_OPENAI_API_BASE in .env."
            ) from exc
        if "virtual network is configured for this resource" in msg.lower():
            raise RuntimeError(
                "Azure OpenAI denied access due to VNet restrictions. Use the private/correct network endpoint "
                "for this resource or run from an allowed network."
            ) from exc
        if "deployment" in msg.lower() and "not found" in msg.lower():
            raise RuntimeError(
                "Azure deployment was not found. Set AZURE_OPENAI_CHAT_DEPLOYMENT in .env to a valid deployed model name."
            ) from exc
        if "IncompleteOutputException" in msg or "max_tokens length limit" in msg:
            raise RuntimeError(
                "RAGAS judge output was truncated by token limits. Reduce per-row k in the dataset "
                "(for example 6), or increase judge max completion tokens for the Azure deployment."
            ) from exc
        raise
    scores = _extract_ragas_scores(result)

    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "dataset": str(dataset_path),
        "query_count": len(cases),
        "judge_model": resolved_model,
        "scores": scores,
        "details": details,
    }

    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RAGAS eval harness for /answer")
    parser.add_argument("--base-url", default="http://localhost:8000", help="RAG API base URL")
    parser.add_argument("--dataset", default="eval/golden_answer_eval.jsonl", help="Answer eval JSONL dataset")
    parser.add_argument("--k", type=int, default=6, help="Default top-k")
    parser.add_argument("--mode", default="hybrid", help="Default retrieval mode")
    parser.add_argument("--rerank", action="store_true", help="Enable reranker")
    parser.add_argument("--use-graph", action="store_true", help="Call /answer with use_graph=true")
    parser.add_argument(
        "--no-relevancy-boost",
        dest="relevancy_boost",
        action="store_false",
        help="Disable query-focused grounded rewrite/fallback in /answer.",
    )
    parser.add_argument(
        "--allow-legacy-answer-contract",
        dest="require_modern_contract",
        action="store_false",
        help="Do not fail fast when /answer returns legacy payload fields.",
    )
    parser.add_argument("--timeout", type=float, default=45.0, help="HTTP timeout seconds")
    parser.add_argument("--llm", action="store_true", help="Call /answer with llm=true")
    parser.add_argument("--llm-model", default="", help="Optional model override")
    parser.add_argument(
        "--judge-timeout",
        type=int,
        default=180,
        help="RAGAS judge-call timeout seconds.",
    )
    parser.add_argument(
        "--judge-max-retries",
        type=int,
        default=3,
        help="RAGAS judge-call max retries.",
    )
    parser.add_argument(
        "--judge-max-wait",
        type=int,
        default=20,
        help="RAGAS judge-call max backoff wait seconds.",
    )
    parser.add_argument(
        "--judge-max-workers",
        type=int,
        default=4,
        help="Parallel workers for RAGAS judge evaluation.",
    )
    parser.add_argument(
        "--allow-ragas-metric-errors",
        dest="ragas_raise_exceptions",
        action="store_false",
        help="Do not abort whole run on per-sample RAGAS metric errors.",
    )
    parser.add_argument("--output", default="", help="Optional output JSON path")
    parser.set_defaults(relevancy_boost=True)
    parser.set_defaults(require_modern_contract=True)
    parser.set_defaults(ragas_raise_exceptions=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    try:
        report = run_eval(
            base_url=args.base_url,
            dataset_path=Path(args.dataset),
            default_k=args.k,
            default_mode=args.mode,
            rerank=args.rerank,
            timeout=args.timeout,
            llm=args.llm,
            llm_model=(args.llm_model.strip() or None),
            use_graph=args.use_graph,
            relevancy_boost=bool(args.relevancy_boost),
            require_modern_contract=bool(args.require_modern_contract),
            judge_timeout=int(args.judge_timeout),
            judge_max_retries=int(args.judge_max_retries),
            judge_max_wait=int(args.judge_max_wait),
            judge_max_workers=int(args.judge_max_workers),
            ragas_raise_exceptions=bool(args.ragas_raise_exceptions),
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1

    print("\nRAGAS Eval")
    print(f"Base URL: {report['base_url']}")
    print(f"Dataset:  {report['dataset']}")
    print(f"Queries:  {report['query_count']}")
    for key, value in (report.get("scores") or {}).items():
        print(f"{key}: {value:.4f}")

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nWrote report: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
