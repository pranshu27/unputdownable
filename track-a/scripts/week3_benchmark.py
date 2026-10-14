"""Week 3 Day 3 - INTEGRATE & MEASURE: query transformation + reflection (ADR 003).

Measures the ADR-003 pipeline against the baseline on the SAME collection (no reset -
run after week2_benchmark.py has rebuilt the 1024-d index):

  baseline : SearchService hybrid (+rerank if enabled)
  pipeline : QueryService (transform -> multi-variant retrieve -> fuse -> rerank -> reflect)

Captures: Recall@5 overall + lexical-hard, compound-query subset, transform/reflect/
retrieval spans, retry counts, and the honest LLM-token line (0 until Week 7).

Usage:  python scripts/week3_benchmark.py [--reset]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from app.config import get_settings
from app.core.embeddings import get_embedding_backend
from app.core.ingest_service import IngestService, load_source
from app.core.qdrant import ensure_collection, get_qdrant_client
from app.core.query_service import QueryService
from app.core.reranker import CrossEncoderReranker
from app.core.search_service import SearchService

sys.path.insert(0, str(Path(__file__).resolve().parent))
from complex_batch import BATCH, GOLDEN, table_corruption_check  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"

# Compound queries that should benefit from sub-query decomposition
COMPOUND = [
    ("fee schedule and latency budget", {"cross-border", "fraud scoring"}),
    ("revenue by segment and gross margin", {"iphone", "gross margin"}),
    ("incident timeline and remediation owners", {"deploy-de7a2b91", "RAG-482"}),
]


def pct95(values: list[float]) -> float:
    return statistics.quantiles(values, n=20)[-1] if len(values) >= 2 else (values[0] if values else 0.0)


def recall_at_k(results, relevant_keywords, k=5) -> float:
    top = results[:k]
    hits = sum(1 for r in top if all(kw.lower() in r.text.lower() for kw in relevant_keywords))
    return 1.0 if hits else 0.0

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--out", default="scripts/week3_results.json")
    args = ap.parse_args()

    settings = get_settings()
    print(f"dense: {settings.embedding_model}@{settings.dense_vector_size}d | rerank: {settings.rerank_enabled} | "
          f"pipeline: {settings.query_transform_pipeline} | reflection: {settings.reflection_enabled}")
    client = get_qdrant_client(settings)
    client.get_collections()
    if args.reset:
        client.delete_collection(settings.qdrant_collection)
        time.sleep(0.5)
    ensure_collection(client, settings)

    # ensure the corpus exists (cheap no-op if week2 already built it)
    embedder = get_embedding_backend(settings)
    ingest = IngestService(client, embedder, settings)
    probe = client.count(settings.qdrant_collection, exact=True).count
    if probe == 0 or args.reset:
        print(f"collection empty ({probe}) - ingesting the batch...")
        for title, filename, fmt in BATCH:
            text = load_source(filename, str(DATA))
            upload = DocumentUpload(document_id=uuid4(), title=title, source_format=fmt,
                                    source_uri=str(DATA / filename))
            result = ingest.ingest(upload, source_text=text)
            if result.parsed is not None:
                from app.core.chunker import chunk_source as _cs

                _, chunks2 = _cs(text, title, upload.document_id, fmt,
                                 target_tokens=settings.chunk_target_tokens,
                                 overlap_tokens=settings.chunk_overlap_tokens)
                t, c = table_corruption_check(result.parsed, chunks2)
                print(f"  {title!r}: tables={t} corrupted={c}")

    base = SearchService(client, embedder, settings)
    query_svc = QueryService(base, settings)

    evals = [("simple", q, kws) for q, kws in GOLDEN] + [("compound", q, kws) for q, kws in COMPOUND]
    rows = []
    base_scores, pipe_scores = [], []
    base_compound, pipe_compound = [], []
    retries_seen = 0
    for kind, query, kws in evals:
        b = base.search(query, top_k=5, mode="hybrid")
        p = query_svc.search(query, top_k=5)
        bs = recall_at_k(b.results, kws)
        ps = recall_at_k(p.results, kws)
        base_scores.append(bs)
        pipe_scores.append(ps)
        if kind == "compound":
            base_compound.append(bs)
            pipe_compound.append(ps)
        retries_seen += p.spans.retries
        rows.append({"kind": kind, "query": query,
                     "baseline_recall": bs, "pipeline_recall": ps,
                     "variants": p.variants, "retries": p.spans.retries,
                     "transform_ms": round(p.spans.transform_ms, 2),
                     "reflect_ms": round(p.spans.reflection_ms, 2),
                     "pipeline_total_ms": round(p.spans.total_ms, 1),
                     "baseline_total_ms": round(b.spans.total_ms, 1)})
        print(f"  [{kind}] {query!r}: base={bs} pipe={ps} variants={len(p.variants)} retries={p.spans.retries}")

    def avg(xs):
        return round(sum(xs) / len(xs), 3) if xs else 0.0

    report = {
        "config": {"pipeline": settings.query_transform_pipeline, "reflection": settings.reflection_enabled,
                   "rerank": settings.rerank_enabled, "dense_dims": settings.dense_vector_size},
        "quality": {
            "recall_at5_baseline_hybrid": avg(base_scores),
            "recall_at5_pipeline": avg(pipe_scores),
            "delta_pipeline_minus_baseline": round(avg(pipe_scores) - avg(base_scores), 3),
            "compound_baseline": avg(base_compound),
            "compound_pipeline": avg(pipe_compound),
            "compound_delta": round(avg(pipe_compound) - avg(base_compound), 3),
            "retries_total": retries_seen,
        },
        "latency": {
            "transform_p95_ms": round(pct95([r["transform_ms"] for r in rows]), 2),
            "reflect_p95_ms": round(pct95([r["reflect_ms"] for r in rows]), 2),
            "pipeline_total_p50_ms": round(statistics.median([r["pipeline_total_ms"] for r in rows]), 1),
            "pipeline_total_p95_ms": round(pct95([r["pipeline_total_ms"] for r in rows]), 1),
            "overhead_vs_baseline_p50": round(
                statistics.median([r["pipeline_total_ms"] for r in rows])
                - statistics.median([r["baseline_total_ms"] for r in rows]), 1),
        },
        "cost": {"added_llm_tokens_per_query": 0,  # rule-based strategies; HyDE tokens land Week 7
                 "note": "transform+reflection are LLM-free by design in Week 3"},
        "rows": rows,
    }
    Path(args.out).write_text(json.dumps(report, indent=2))
    print("\n=== SUMMARY ===")
    print(json.dumps({k: report[k] for k in ("quality", "latency", "cost")}, indent=2))
    print(f"saved -> {args.out}")


if __name__ == "__main__":
    main()

