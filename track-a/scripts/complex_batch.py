"""Week 1 follow-up - COMPLEX BATCH benchmark.

Extends the Day-3 measurement run with 4 harder input documents that stress the
ADR-001 pipeline along the dimensions called out in daily-goals.md Week 1:
  acme-financials-10k.html      merged header cells (colspan/rowspan), parenthesized
                                negatives, inline XBRL tags, footnotes, units rows
  incident-postmortem.md        deep heading hierarchy, nested lists, fenced code
                                blocks, blockquote, links, exact identifiers
  scanned-lease-agreement.html  scanned-page / OCR noise stand-in: broken hyphens,
                                OCR confusions (l/1, 0/O), header/footer cruft,
                                misaligned tables, split amounts
  research-paper-two-column.html  CSS two-column layout, abstract, figure caption
                                in-flow, data table, citation identifiers

The golden-query set adds hard *lexical* queries (exact identifiers like ERR-4021,
CIK 0001874410, deploy-de7a2b91) where dense-only retrieval is expected to fail -
making the Delta Recall@5 (hybrid - dense) measurement meaningful.

Usage:  python scripts/complex_batch.py [--reset]
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
from app.core.search_service import SearchService
from app.schemas.common import DocumentFormat
from app.schemas.documents import DocumentUpload

DATA = Path(__file__).resolve().parent.parent / "data"

BATCH = [
    ("Apple FY2023 Form 10-K", "aapl-10k-2023.htm", DocumentFormat.PDF),
    ("ACME Robotics FY2023 Form 10-K", "acme-financials-10k.html", DocumentFormat.PDF),
    ("Product Notes: Payments Platform", "product-notes.md", DocumentFormat.MARKDOWN),
    ("Vector Database Primer", "vector-db-primer.md", DocumentFormat.MARKDOWN),
    ("Incident Postmortem: Payment Authorization Degradation", "incident-postmortem.md", DocumentFormat.MARKDOWN),
    ("Commercial Lease Agreement (Scanned OCR)", "scanned-lease-agreement.html", DocumentFormat.PDF),
    ("Two-Column Layout RAG Paper", "research-paper-two-column.html", DocumentFormat.PDF),
    ("Q3 Retrieval Sync Transcript", "meeting-transcript.txt", DocumentFormat.DOCX),
]

# Golden queries: keyword sets define the relevant chunk(s) (keyword-containment ground truth).
# "lexical-hard" queries target exact identifiers where dense embeddings are expected
# to fail and the sparse/BM25 leg of the hybrid (ADR-002) should carry the hit.
GOLDEN = [
    # ---- original Day-3 batch ----
    ("what was apple net sales in fiscal 2023", {"383,285"}),
    ("iphone revenue mac revenue segment breakdown", {"iphone", "mac"}),
    ("gross margin percentage fiscal 2023", {"gross margin"}),
    ("domestic fee cross-border fee tier", {"cross-border"}),
    ("hnsw ef_search recall latency trade-off", {"ef_search"}),
    ("quantization memory reduction per million vectors", {"quantization"}),
    ("reciprocal rank fusion decision sprint", {"reciprocal rank fusion"}),
    ("reranker candidate cap fifty", {"fifty"}),
    ("total operating expenses research development", {"research and development"}),
    ("services revenue growth drivers", {"services"}),
    # ---- ACME 10-K (merged headers, XBRL, negatives) ----
    ("what is the ACMR CIK number", {"0001874410"}),  # lexical-hard
    ("ACME restructuring charges severance impairment Hannover", {"Hannover"}),
    ("Series B term loan interest rate basis points", {"275 basis points"}),
    ("ACME warehouse fulfillment segment revenue growth percent", {"38.0%"}),
    ("ACME diluted earnings per share fiscal 2023", {"0.31"}),
    # ---- incident postmortem (exact identifiers) ----
    ("ERR-4021 ledger journal write timeout", {"ERR-4021"}),  # lexical-hard
    ("which deploy caused the canary rollback", {"deploy-de7a2b91"}),  # lexical-hard
    ("trace id fraud scoring span budget breach", {"8f3a9c2e41d7"}),  # lexical-hard
    ("remediation owner canary blast radius tier-0", {"RAG-482-3"}),  # lexical-hard (table)
    # ---- scanned OCR lease ----
    ("lease monthly base rent lease year three", {"4,535.35"}),  # lexical-hard (table)
    ("security deposit amount Sundial Analytics", {"$8,550.00"}),  # lexical-hard
    ("proportionate share operating expenses base year", {"8.6%"}),
    # ---- two-column paper ----
    ("two-column degradation dense right half recall", {"0.49"}),  # lexical-hard (table)
    ("column-aware pre-pass latency milliseconds per page", {"6.1ms"}),
    ("synthetic corpus citation key retrieval", {"RETR-2023-0447"}),  # lexical-hard
]


def pct95(values: list[float]) -> float:
    return statistics.quantiles(values, n=20)[-1] if len(values) >= 2 else (values[0] if values else 0.0)


def table_corruption_check(parsed, chunks) -> tuple[int, int]:
    """(tables, corrupted): a table chunk is corrupted if any source row is missing
    from the serialized table text (i.e. the table was split/truncated)."""
    total = corrupted = 0
    src_tables = [b for b in parsed.blocks if b.is_table]
    chunk_tables = [c for c in chunks if c.is_table]
    for st in src_tables:
        total += 1
        match = [c for c in chunk_tables if len(c.table_rows or []) == len(st.table_rows or [])]
        if not match:
            corrupted += 1
            continue
        # every source cell must survive serialization
        ok = any(
            all(all(cell in c.text for cell in row) for row in st.table_rows)
            for c in match
        )
        if not ok:
            corrupted += 1
    return total, corrupted


def recall_at_k(results, relevant_keywords, k=5) -> float:
    top = results[:k]
    hits = sum(
        1 for r in top if all(kw.lower() in r.text.lower() for kw in relevant_keywords)
    )
    return 1.0 if hits else 0.0  # query-level relevant-set hit within top-k


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="drop + recreate the collection first")
    ap.add_argument("--out", default="scripts/complex_results.json")
    args = ap.parse_args()

    settings = get_settings()
    client = get_qdrant_client(settings)
    client.get_collections()  # fail fast if Qdrant is down
    if args.reset:
        client.delete_collection(settings.qdrant_collection)
        time.sleep(0.5)
    ensure_collection(client, settings)

    embedder = get_embedding_backend(settings)
    ingest = IngestService(client, embedder, settings)
    search = SearchService(client, embedder, settings)

    # ---------------- ingest phase ----------------
    ingest_rows = []
    parse_failures = 0
    tables_total = tables_corrupted = 0
    for title, filename, fmt in BATCH:
        text = load_source(filename, str(DATA))
        upload = DocumentUpload(
            document_id=uuid4(), title=title, source_format=fmt, source_uri=str(DATA / filename)
        )
        result = ingest.ingest(upload, source_text=text)
        s = result.stats
        if s.parse_failed:
            parse_failures += 1
        row = {
            "title": title,
            "source_tokens": s.source_tokens,
            "chunks": s.chunks_created,
            "table_chunks": s.table_chunks,
            "parse_ms": round(s.parse_ms, 1),
            "embed_ms": round(s.embed_ms, 1),
            "upsert_ms": round(s.upsert_ms, 1),
            "total_ms": round(s.total_ms, 1),
            "failed": s.parse_failed,
        }
        if result.parsed is not None:
            # re-run chunker for corruption check (cheap, no embedding)
            from app.core.chunker import chunk_source as _cs

            _, chunks2 = _cs(
                text, title, upload.document_id, fmt,
                target_tokens=settings.chunk_target_tokens,
                overlap_tokens=settings.chunk_overlap_tokens,
            )
            t, c = table_corruption_check(result.parsed, chunks2)
            tables_total += t
            tables_corrupted += c
            row["tables"] = t
        ingest_rows.append(row)
        print(f"ingested {title!r}: {row}")

    totals = [r["total_ms"] for r in ingest_rows if not r["failed"]]
    docs = len(totals)
    total_seconds = sum(totals) / 1000.0

    # ---------------- search phase ----------------
    dense_scores, hybrid_scores = [], []
    lexical_hard_dense, lexical_hard_hybrid = [], []
    span_rows = []
    for query, kws in GOLDEN:
        d = search.search(query, top_k=5, mode="dense")
        h = search.search(query, top_k=5, mode="hybrid")
        dense_scores.append(recall_at_k(d.results, kws))
        hybrid_scores.append(recall_at_k(h.results, kws))
        # lexical-hard subset: keyword is an exact identifier / number (>= 6 chars w/ a digit)
        kw = sorted(kws)[0]
        if len(kw) >= 6 and any(ch.isdigit() for ch in kw):
            lexical_hard_dense.append(dense_scores[-1])
            lexical_hard_hybrid.append(hybrid_scores[-1])
        span_rows.append(
            {
                "query": query,
                "embed_ms": round(h.spans.embed_ms, 1),
                "dense_ms": round(h.spans.retrieve_dense_ms, 1),
                "sparse_ms": round(h.spans.retrieve_sparse_ms, 1),
                "fuse_ms": round(h.spans.fuse_ms, 2),
                "total_ms": round(h.spans.total_ms, 1),
            }
        )
        print(f"query {query!r}: dense={dense_scores[-1]} hybrid={hybrid_scores[-1]} spans={span_rows[-1]}")

    dense_recall = sum(dense_scores) / len(dense_scores)
    hybrid_recall = sum(hybrid_scores) / len(hybrid_scores)
    delta_recall = hybrid_recall - dense_recall
    lh_dense = sum(lexical_hard_dense) / len(lexical_hard_dense) if lexical_hard_dense else 0.0
    lh_hybrid = sum(lexical_hard_hybrid) / len(lexical_hard_hybrid) if lexical_hard_hybrid else 0.0

    # ---------------- cost ----------------
    info = client.get_collection(settings.qdrant_collection)
    points = info.points_count
    dense_bytes = points * settings.dense_vector_size * 4
    sparse_est_bytes = points * 220  # ~110 avg hashed terms x (4B idx + 4B val), rough
    payload_tokens = sum(r["source_tokens"] for r in ingest_rows)
    storage_gb = (dense_bytes + sparse_est_bytes) / 1e9
    storage_cost_per_1k_pages = (
        storage_gb * 0.10 / max(points, 1) * 1000 * (500 / 1)  # ~500 tokens/page -> pages scale
    )
    embed_cost_per_1k_pages = payload_tokens / 500 * 1000 / 1e6 * 0.02  # $0.02/1M tokens

    report = {
        "quality": {
            "parse_failures": parse_failures,
            "parse_failure_rate": parse_failures / len(BATCH),
            "tables_total": tables_total,
            "tables_corrupted": tables_corrupted,
            "table_corruption_rate": (tables_corrupted / tables_total) if tables_total else 0.0,
            "recall_at5_dense": dense_recall,
            "recall_at5_hybrid": hybrid_recall,
            "delta_recall_at5": delta_recall,
            "recall_at5_dense_lexical_hard": lh_dense,
            "recall_at5_hybrid_lexical_hard": lh_hybrid,
            "delta_recall_at5_lexical_hard": lh_hybrid - lh_dense,
        },
        "latency": {
            "ingest_total_ms": totals,
            "ingest_p95_ms": round(pct95(totals), 1),
            "throughput_docs_per_sec": round(docs / total_seconds, 3) if total_seconds else 0.0,
            "search_spans": span_rows,
            "search_p50_ms": round(statistics.median([r["total_ms"] for r in span_rows]), 1),
            "search_p95_ms": round(pct95([r["total_ms"] for r in span_rows]), 1),
            "fuse_p95_ms": round(pct95([r["fuse_ms"] for r in span_rows]), 3),
        },
        "cost": {
            "points": points,
            "dense_index_bytes": dense_bytes,
            "sparse_index_est_bytes": sparse_est_bytes,
            "storage_gb_month_usd": round(storage_gb * 0.10, 6),
            "embedding_tokens": payload_tokens,
            "embed_cost_usd_per_1k_pages_reference": round(embed_cost_per_1k_pages, 4),
            "storage_cost_usd_per_1k_pages_reference": round(storage_cost_per_1k_pages, 4),
        },
        "ingest_rows": ingest_rows,
    }
    out = Path(args.out)
    out.write_text(json.dumps(report, indent=2))
    print("\n=== SUMMARY ===")
    print(json.dumps({k: report[k] for k in ("quality", "latency", "cost")}, indent=2))
    print(f"saved -> {out}")


if __name__ == "__main__":
    main()


