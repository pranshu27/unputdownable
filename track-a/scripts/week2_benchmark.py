"""Week 2 Day 3 - INTEGRATE & MEASURE: 1024-d upgrade + cross-encoder rerank benchmark.

Modes measured per golden query: dense-only / sparse-only / hybrid (RRF) / hybrid+rerank.
Collection is rebuilt with the configured dense model (run with TRACKA_EMBEDDING_MODEL=
BAAI/bge-large-en-v1.5 TRACKA_DENSE_VECTOR_SIZE=1024 to replicate the Week-2 upgrade).

Captures: Delta Recall@5 across modes (incl. lexical-hard subset), rerank span p50/p95,
ingest p95/throughput by stage, index bytes, and rerank $/1k queries (CPU-second method).

Usage:  python scripts/week2_benchmark.py [--reset]
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
from app.core.reranker import CrossEncoderReranker
from app.core.search_service import SearchService
from app.schemas.common import DocumentFormat
from app.schemas.documents import DocumentUpload

sys.path.insert(0, str(Path(__file__).resolve().parent))
from complex_batch import BATCH, GOLDEN, table_corruption_check  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"


def pct95(values: list[float]) -> float:
    return statistics.quantiles(values, n=20)[-1] if len(values) >= 2 else (values[0] if values else 0.0)


def recall_at_k(results, relevant_keywords, k=5) -> float:
    top = results[:k]
    hits = sum(1 for r in top if all(kw.lower() in r.text.lower() for kw in relevant_keywords))
    return 1.0 if hits else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="drop + recreate the collection first")
    ap.add_argument("--skip-ingest", action="store_true",
                    help="reuse the existing collection (no re-ingest) - reruns the eval only")
    ap.add_argument("--out", default="scripts/week2_results.json")
    args = ap.parse_args()

    settings = get_settings()
    print(f"dense model: {settings.embedding_model} @ {settings.dense_vector_size}d")
    client = get_qdrant_client(settings)
    client.get_collections()
    if args.reset:
        client.delete_collection(settings.qdrant_collection)
        time.sleep(0.5)
    ensure_collection(client, settings)

    embedder = get_embedding_backend(settings)
    ingest = IngestService(client, embedder, settings)

    # ---- ingest phase (rebuild at the new dims) ----
    ingest_rows, parse_failures = [], 0
    tables_total = tables_corrupted = 0
    existing = client.count(settings.qdrant_collection, exact=True).count
    if existing and args.skip_ingest:
        print(f"skipping ingest ({existing} points present)")
    else:
        for title, filename, fmt in BATCH:
            text = load_source(filename, str(DATA))
            upload = DocumentUpload(document_id=uuid4(), title=title, source_format=fmt,
                                    source_uri=str(DATA / filename))
            result = ingest.ingest(upload, source_text=text)
            s = result.stats
            parse_failures += 1 if s.parse_failed else 0
            ingest_rows.append({"title": title, "chunks": s.chunks_created, "table_chunks": s.table_chunks,
                                "source_tokens": s.source_tokens, "parse_ms": round(s.parse_ms, 1),
                                "embed_ms": round(s.embed_ms, 1), "upsert_ms": round(s.upsert_ms, 1),
                                "total_ms": round(s.total_ms, 1), "failed": s.parse_failed})
            if result.parsed is not None:
                from app.core.chunker import chunk_source as _cs

                _, chunks2 = _cs(text, title, upload.document_id, fmt,
                                 target_tokens=settings.chunk_target_tokens,
                                 overlap_tokens=settings.chunk_overlap_tokens)
                t, c = table_corruption_check(result.parsed, chunks2)
                tables_total += t
                tables_corrupted += c
            print(f"ingested {title!r}: chunks={s.chunks_created} embed_ms={s.embed_ms:.0f}")
    totals = [r["total_ms"] for r in ingest_rows if not r["failed"]]

    # ---- search phase: 4 modes ----
    # The baseline MUST be rerank-free regardless of the environment (TRACKA_RERANK_ENABLED
    # would otherwise silently rerank every mode and 4x the cost — the 15s/query bug).
    base_settings = settings.model_copy(update={"rerank_enabled": False})
    base_search = SearchService(client, embedder, base_settings)
    rerank_settings = settings.model_copy(update={"rerank_enabled": True})
    reranker = CrossEncoderReranker(rerank_settings)
    rerank_search = SearchService(client, embedder, rerank_settings, reranker=reranker)

    modes = {"dense": base_search, "sparse": base_search, "hybrid": base_search,
             "hybrid_rerank": rerank_search}
    scores = {m: [] for m in modes}
    lh_scores = {m: [] for m in modes}  # lexical-hard subset
    rerank_spans = []
    span_rows = []
    for query, kws in GOLDEN:
        row = {"query": query}
        for mode, svc in modes.items():
            outcome = svc.search(query, top_k=5, mode="hybrid" if mode.startswith("hybrid") else mode)
            scores[mode].append(recall_at_k(outcome.results, kws))
            row[f"{mode}_ms"] = round(outcome.spans.total_ms, 1)
            row[f"{mode}_recall"] = scores[mode][-1]
            if mode == "hybrid_rerank":
                row["rerank_ms"] = round(outcome.spans.rerank_ms, 1)
                if outcome.spans.rerank_ms:
                    rerank_spans.append(outcome.spans.rerank_ms)
            kw = sorted(kws)[0]
            if len(kw) >= 6 and any(ch.isdigit() for ch in kw):
                lh_scores[mode].append(scores[mode][-1])
        span_rows.append(row)
        print(f"  {query!r}: " + " ".join(f"{m}={scores[m][-1]:.0f}" for m in modes))

    summary_quality = {}
    for mode in modes:
        rec = sum(scores[mode]) / len(scores[mode])
        lh = sum(lh_scores[mode]) / len(lh_scores[mode]) if lh_scores[mode] else 0.0
        summary_quality[f"recall_at5_{mode}"] = round(rec, 3)
        summary_quality[f"recall_at5_{mode}_lexical_hard"] = round(lh, 3)
    summary_quality["delta_hybrid_minus_dense"] = round(
        summary_quality["recall_at5_hybrid"] - summary_quality["recall_at5_dense"], 3)
    summary_quality["delta_rerank_minus_hybrid"] = round(
        summary_quality["recall_at5_hybrid_rerank"] - summary_quality["recall_at5_hybrid"], 3)
    summary_quality["delta_rerank_minus_dense"] = round(
        summary_quality["recall_at5_hybrid_rerank"] - summary_quality["recall_at5_dense"], 3)

    # ---- cost ----
    info = client.get_collection(settings.qdrant_collection)
    points = info.points_count
    dense_bytes = points * settings.dense_vector_size * 4
    sparse_est_bytes = points * 220
    payload_tokens = sum(r["source_tokens"] for r in ingest_rows)
    # rerank cost: CPU-second method. c6i.xlarge ~ $0.17/h -> $4.7e-5 per CPU-second.
    avg_rerank_s = (statistics.mean(rerank_spans) / 1000) if rerank_spans else 0.0
    rerank_usd_per_1k = avg_rerank_s * 4.7e-5 * 1000

    report = {
        "config": {"dense_model": settings.embedding_model, "dense_dims": settings.dense_vector_size,
                   "reranker_model": settings.reranker_model, "rerank_candidates": settings.rerank_candidates},
        "quality": {"parse_failures": parse_failures, "parse_failure_rate": parse_failures / len(BATCH),
                    "tables_total": tables_total, "tables_corrupted": tables_corrupted,
                    "table_corruption_rate": (tables_corrupted / tables_total) if tables_total else 0.0,
                    **summary_quality},
        "latency": {"ingest_p95_ms": round(pct95(totals), 1),
                    "throughput_docs_per_sec": round(len(totals) / (sum(totals) / 1000.0), 3) if totals else 0.0,
                    "rerank_p50_ms": round(statistics.median(rerank_spans), 1) if rerank_spans else 0.0,
                    "rerank_p95_ms": round(pct95(rerank_spans), 1) if rerank_spans else 0.0,
                    "search_rows": span_rows},
        "cost": {"points": points, "dense_index_bytes": dense_bytes,
                 "sparse_index_est_bytes": sparse_est_bytes, "embedding_tokens": payload_tokens,
                 "rerank_avg_seconds_per_query": round(avg_rerank_s, 3),
                 "rerank_usd_per_1k_queries_cpu_second_method": round(rerank_usd_per_1k, 3)},
        "ingest_rows": ingest_rows,
    }
    Path(args.out).write_text(json.dumps(report, indent=2))
    print("\n=== SUMMARY ===")
    print(json.dumps({k: report[k] for k in ("quality", "latency", "cost")}, indent=2))
    print(f"saved -> {args.out}")


if __name__ == "__main__":
    main()



