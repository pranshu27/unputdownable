"""Auto-curate answer eval dataset from real Informatica XML files.

Workflow:
1) Discover and parse XML files under an Informatica root folder.
2) Generate realistic candidate questions from real entities in each XML.
3) Evaluate each candidate through the local /answer path (in-process).
4) Keep only acceptable questions in the golden dataset.

This script is designed to keep the golden dataset realistic and grounded:
questions must be answerable from currently indexed content.

Run:
    python -m rag_system.eval.curate_answer_dataset \
      --infa-root ../../project1 \
      --candidates-out eval/golden_answer_eval_candidates.jsonl \
      --golden-out eval/golden_answer_eval.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from dotenv import load_dotenv

from rag_system.embeddings import HashingEmbedding
from rag_system.ingestion.xml_parser import parse_powercenter_xml
from rag_system.knowledge_base import InformaticaKnowledgeBase


def _dedupe_keep_order(values: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for value in values:
        v = (value or "").strip()
        if not v:
            continue
        key = v.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(v)
    return out


def _discover_xml_files(root: Path, max_files: int) -> List[Path]:
    files = sorted(root.rglob("*.XML"), key=lambda p: p.name.lower())
    if max_files > 0:
        files = files[:max_files]
    return files


def _extract_entities(parsed: Dict[str, Any]) -> Dict[str, List[str]]:
    sources = _dedupe_keep_order(src.get("name", "") for src in parsed.get("sources", []))
    targets = _dedupe_keep_order(tgt.get("name", "") for tgt in parsed.get("targets", []))

    tx_names: List[str] = []
    tx_sql_names: List[str] = []
    tx_types: List[str] = []
    connector_fields: List[str] = []

    for mapping in parsed.get("mappings", []):
        for tx in mapping.get("transformations", []):
            tx_name = str(tx.get("name") or "").strip()
            tx_type = str(tx.get("type") or "").strip()
            sql_override = str(tx.get("sql_override") or "").strip()

            if tx_name:
                tx_names.append(tx_name)
            if tx_type:
                tx_types.append(tx_type)
            if tx_name and sql_override:
                tx_sql_names.append(tx_name)

        for conn in mapping.get("connectors", []):
            from_field = str(conn.get("from_field") or "").strip()
            to_field = str(conn.get("to_field") or "").strip()
            if from_field:
                connector_fields.append(from_field)
            if to_field:
                connector_fields.append(to_field)

    return {
        "sources": _dedupe_keep_order(sources),
        "targets": _dedupe_keep_order(targets),
        "tx_names": _dedupe_keep_order(tx_names),
        "tx_sql_names": _dedupe_keep_order(tx_sql_names),
        "tx_types": _dedupe_keep_order(tx_types),
        "connector_fields": _dedupe_keep_order(connector_fields),
    }


def _candidate_rows_for_xml(
    xml_file: Path,
    parsed: Dict[str, Any],
    max_candidates_per_file: int,
) -> List[Dict[str, Any]]:
    fname = xml_file.name
    entities = _extract_entities(parsed)

    tx_names = entities["tx_names"]
    tx_sql_names = entities["tx_sql_names"]
    sources = entities["sources"]
    targets = entities["targets"]
    connector_fields = entities["connector_fields"]

    rows: List[Dict[str, Any]] = []

    # 1) Per-workflow logic question.
    expected_logic = _dedupe_keep_order((tx_names[:2] + sources[:1] + targets[:1]))[:3]
    if expected_logic:
        rows.append(
            {
                "query": f"What logic exists in {fname}?",
                "ground_truth": (
                    f"{fname} includes logic across source, transformation, and target steps. "
                    f"Notable entities include {', '.join(expected_logic)}."
                ),
                "mode": "hybrid",
                "k": 6,
                "source_file": fname,
                "expected_entities": expected_logic,
            }
        )

    # 2) Transformation usage question.
    if tx_names:
        tx_name = tx_names[0]
        rows.append(
            {
                "query": f"Where is {tx_name} used?",
                "ground_truth": f"{tx_name} is used in {fname} as part of the mapping transformation flow.",
                "mode": "hybrid",
                "k": 6,
                "source_file": fname,
                "expected_entities": [tx_name],
            }
        )

    # 3) SQL override question when available.
    if tx_sql_names:
        sql_tx = tx_sql_names[0]
        expected_sql = _dedupe_keep_order([sql_tx, "Sql Query"])
        rows.append(
            {
                "query": f"Find SQL override in {fname}",
                "ground_truth": f"{fname} contains Source Qualifier SQL override logic, including {sql_tx}.",
                "mode": "hybrid",
                "k": 6,
                "source_file": fname,
                "expected_entities": expected_sql,
            }
        )

    # 4) Lineage/connector question when connectors exist.
    if connector_fields:
        fields = connector_fields[:2]
        expected_lineage = _dedupe_keep_order(["CONNECTOR"] + fields)
        rows.append(
            {
                "query": f"Find lineage records in {fname}",
                "ground_truth": (
                    f"{fname} has field-level lineage through CONNECTOR paths. "
                    f"Key fields include {', '.join(fields)}."
                ),
                "mode": "hybrid",
                "k": 6,
                "source_file": fname,
                "expected_entities": expected_lineage,
            }
        )

    return rows[:max_candidates_per_file]


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _evaluate_acceptability(
    payload: Dict[str, Any],
    source_file: str,
    expected_entities: List[str],
    min_entity_hits: int,
) -> Tuple[bool, str]:
    if payload.get("refused"):
        return False, "refused answer"

    answer_text = str(payload.get("answer_text") or "").strip()
    if not answer_text:
        return False, "empty answer_text"

    evidence = payload.get("evidence") or []
    if not evidence:
        return False, "no evidence returned"

    src_lower = source_file.strip().lower()
    source_match = any(str(e.get("source_file") or "").strip().lower() == src_lower for e in evidence)
    if src_lower and not source_match:
        return False, f"evidence missing required source_file {src_lower}"

    combined = (
        answer_text
        + " "
        + " ".join(str(e.get("cited_text") or "") for e in evidence)
    ).lower()
    entity_hits = sum(1 for ent in expected_entities if ent.lower() in combined)

    if entity_hits < min_entity_hits:
        return False, f"expected entity hits {entity_hits} < {min_entity_hits}"

    return True, f"accepted (entity_hits={entity_hits})"


def _answer_in_process(
    query: str,
    k: int,
    mode: str,
    llm: bool,
    llm_model: Optional[str],
    llm_max_tokens: int,
    use_graph: bool,
) -> Dict[str, Any]:
    import rag_system.api.app as api_app

    return api_app.answer(
        q=query,
        k=k,
        mode=mode,
        rerank=False,
        prompt_name="answer_with_citations",
        llm=llm,
        llm_model=llm_model,
        llm_temperature=0.0,
        llm_max_tokens=llm_max_tokens,
        use_graph=use_graph,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Auto-curate golden answer dataset from XML evidence")
    parser.add_argument("--infa-root", default="", help="Root folder containing Informatica XML files")
    parser.add_argument(
        "--candidates-out",
        default="eval/golden_answer_eval_candidates.jsonl",
        help="Output JSONL for generated candidate questions",
    )
    parser.add_argument(
        "--golden-out",
        default="eval/golden_answer_eval.jsonl",
        help="Output JSONL for accepted golden questions",
    )
    parser.add_argument(
        "--report-out",
        default="eval/answer_curation_report_latest.json",
        help="Output JSON report path",
    )
    parser.add_argument("--max-files", type=int, default=0, help="Max XML files to scan (0 = all)")
    parser.add_argument(
        "--max-candidates-per-file",
        type=int,
        default=4,
        help="Maximum generated candidates per XML file",
    )
    parser.add_argument(
        "--min-entity-hits",
        type=int,
        default=0,
        help="Minimum expected entity matches required to accept a question",
    )
    parser.add_argument(
        "--consistency-runs",
        type=int,
        default=2,
        help="Runs per candidate; must pass all runs to be accepted",
    )
    parser.add_argument("--llm", action="store_true", help="Use llm=true during answer evaluation")
    parser.add_argument("--llm-model", default="", help="Optional llm_model override")
    parser.add_argument("--llm-max-tokens", type=int, default=800, help="Max tokens for answer generation")
    parser.add_argument("--use-graph", action="store_true", help="Use graph orchestration during evaluation")
    parser.add_argument(
        "--skip-eval",
        action="store_true",
        help="Only generate candidates and write candidates-out; do not curate golden",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    project_root = Path(__file__).resolve().parents[3]
    load_dotenv(project_root / ".env", override=False)

    infa_root_raw = args.infa_root.strip() or os.getenv("INFA_XML_FOLDER", "").strip()
    if not infa_root_raw:
        infa_root_raw = str((project_root / "../project1").resolve())

    infa_root = Path(infa_root_raw)
    if not infa_root.exists():
        print(f"ERROR: INFA root does not exist: {infa_root}", file=sys.stderr)
        return 2

    max_files = max(0, int(args.max_files))
    max_candidates_per_file = max(1, int(args.max_candidates_per_file))
    min_entity_hits = max(0, int(args.min_entity_hits))
    consistency_runs = max(1, int(args.consistency_runs))

    xml_files = _discover_xml_files(infa_root, max_files=max_files)
    if not xml_files:
        print(f"ERROR: no XML files found under {infa_root}", file=sys.stderr)
        return 2

    candidate_rows: List[Dict[str, Any]] = []
    for xml_file in xml_files:
        try:
            parsed = parse_powercenter_xml(str(xml_file))
        except Exception:
            continue
        candidate_rows.extend(
            _candidate_rows_for_xml(
                xml_file=xml_file,
                parsed=parsed,
                max_candidates_per_file=max_candidates_per_file,
            )
        )

    if not candidate_rows:
        print("ERROR: no candidate questions were generated", file=sys.stderr)
        return 2

    # Assign stable IDs once, after generation.
    for idx, row in enumerate(candidate_rows, start=1):
        row["id"] = f"ans_{idx:03d}"

    candidates_out = Path(args.candidates_out)
    if not candidates_out.is_absolute():
        candidates_out = project_root / candidates_out
    _write_jsonl(candidates_out, candidate_rows)

    if args.skip_eval:
        print(f"Generated {len(candidate_rows)} candidates")
        print(f"Wrote candidates: {candidates_out}")
        return 0

    # Build local KB across the selected INFA root and run in-process answers.
    kb = InformaticaKnowledgeBase(
        backend="memory",
        embedding_provider=HashingEmbedding(dim=256),
    )
    kb.build_from_folder(str(infa_root))

    import rag_system.api.app as api_app

    original_kb = api_app._kb
    original_status = dict(api_app._ingest_status)
    api_app._kb = kb
    api_app._ingest_status = {"state": "done", "chunks": kb.count(), "error": None}

    accepted_rows: List[Dict[str, Any]] = []
    rejected: List[Dict[str, str]] = []

    try:
        for row in candidate_rows:
            row_id = str(row["id"])
            query = str(row.get("query") or "").strip()
            source_file = str(row.get("source_file") or "").strip()
            expected_entities = [str(e).strip() for e in (row.get("expected_entities") or []) if str(e).strip()]

            run_failures: List[str] = []
            for run_idx in range(consistency_runs):
                payload = _answer_in_process(
                    query=query,
                    k=int(row.get("k") or 6),
                    mode=str(row.get("mode") or "hybrid"),
                    llm=bool(args.llm),
                    llm_model=(args.llm_model.strip() or None),
                    llm_max_tokens=int(args.llm_max_tokens),
                    use_graph=bool(args.use_graph),
                )
                ok, reason = _evaluate_acceptability(
                    payload=payload,
                    source_file=source_file,
                    expected_entities=expected_entities,
                    min_entity_hits=min_entity_hits,
                )
                if not ok:
                    run_failures.append(f"run_{run_idx + 1}: {reason}")

            if run_failures:
                rejected.append({"id": row_id, "reason": " | ".join(run_failures)})
            else:
                accepted_rows.append(row)
    finally:
        api_app._kb = original_kb
        api_app._ingest_status = original_status

    golden_out = Path(args.golden_out)
    if not golden_out.is_absolute():
        golden_out = project_root / golden_out
    _write_jsonl(golden_out, accepted_rows)

    report_out = Path(args.report_out)
    if not report_out.is_absolute():
        report_out = project_root / report_out
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "infa_root": str(infa_root),
        "xml_file_count": len(xml_files),
        "candidate_count": len(candidate_rows),
        "accepted_count": len(accepted_rows),
        "rejected_count": len(rejected),
        "consistency_runs": consistency_runs,
        "min_entity_hits": min_entity_hits,
        "llm": bool(args.llm),
        "use_graph": bool(args.use_graph),
        "candidates_out": str(candidates_out),
        "golden_out": str(golden_out),
        "rejected": rejected,
    }
    report_out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("Answer Dataset Curation")
    print(f"INFA root:      {infa_root}")
    print(f"XML files:      {len(xml_files)}")
    print(f"Candidates:     {len(candidate_rows)}")
    print(f"Accepted:       {len(accepted_rows)}")
    print(f"Rejected:       {len(rejected)}")
    print(f"Wrote:          {candidates_out}")
    print(f"Wrote:          {golden_out}")
    print(f"Wrote report:   {report_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
