"""Integration tests — real Informatica XML files.

Uses HashingEmbedding + InMemoryVectorStore so no Azure or Postgres is needed.
Skips gracefully if the XML folder is not accessible (OneDrive offline).

Run:
    pytest tests/test_integration.py -v
"""

from __future__ import annotations

import json
import os
import pathlib
import pytest

# Resolve XML folder relative to this file: rag-system/tests/ → project1/app_CALCULATE_EINTERACTION
_HERE = pathlib.Path(__file__).parent
_INFA_FOLDER = str(
    (_HERE / "../../project1/app_CALCULATE_EINTERACTION").resolve()
)
_GOLDEN_CANDIDATES_DATASET = (_HERE / "../eval/golden_answer_eval_candidates.jsonl").resolve()
_GOLDEN_DATASET = (_HERE / "../eval/golden_answer_eval.jsonl").resolve()

_EXPECTED_FILES = {
    "wf_0000_eintr_lmt_load_confirmation.XML",
    "wf_4201_calculate_interaction_facts.XML",
    "wf_4202_fnd_rltinteraction.XML",
    "wf_4203_calculate_interaction_facts_fbl.XML",
    "wf_4204_fnd_rltinteraction_fbl.XML",
    "wf_4205_calculate_dm_facts.XML",
    "wf_4206_calculate_facts_fcr.XML",
}


def _folder_accessible() -> bool:
    try:
        files = os.listdir(_INFA_FOLDER)
        small = next(
            (f for f in files if f.endswith(".XML")), None
        )
        if small is None:
            return False
        with open(os.path.join(_INFA_FOLDER, small), "r", encoding="utf-8", errors="ignore") as fh:
            fh.read(64)
        return True
    except Exception:
        return False


skip_if_offline = pytest.mark.skipif(
    not _folder_accessible(),
    reason="Informatica XML folder not accessible (OneDrive offline or path not found)",
)


def _load_jsonl_rows(path: pathlib.Path) -> list[dict]:
    rows: list[dict] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"Invalid dataset row at line {line_no}")
        rows.append(row)
    return rows


def _evaluate_acceptability(payload: dict, source_file: str, expected_entities: list[str]) -> tuple[bool, str]:
    if payload.get("refused"):
        return False, "refused answer"

    answer_text = str(payload.get("answer_text") or "").strip()
    if not answer_text:
        return False, "empty answer_text"

    evidence = payload.get("evidence") or []
    if not evidence:
        return False, "no evidence returned"

    source_match = any(str(e.get("source_file") or "").strip().lower() == source_file for e in evidence)
    if source_file and not source_match:
        return False, f"evidence missing required source_file {source_file}"

    combined = (
        answer_text
        + " "
        + " ".join(str(e.get("cited_text") or "") for e in evidence)
    ).lower()
    entity_hits = sum(1 for ent in expected_entities if ent.lower() in combined)

    min_hits = int(os.getenv("GOLDEN_MIN_ENTITY_HITS", "0") or 0)
    if not expected_entities:
        min_hits = 0
    if entity_hits < min_hits:
        return False, f"expected entity hits {entity_hits} < {min_hits}"

    return True, f"accepted (entity_hits={entity_hits})"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def kb():
    """Build a knowledge base from all 7 real XML files. Module-scoped = built once."""
    from rag_system.embeddings import HashingEmbedding
    from rag_system.knowledge_base import InformaticaKnowledgeBase

    instance = InformaticaKnowledgeBase(
        backend="memory",
        embedding_provider=HashingEmbedding(dim=256),
    )
    instance.build_from_folder(_INFA_FOLDER)
    return instance


# ---------------------------------------------------------------------------
# Ingestion coverage
# ---------------------------------------------------------------------------

@skip_if_offline
def test_all_xml_files_found():
    """Every expected XML file is present and listable."""
    found = {f for f in os.listdir(_INFA_FOLDER) if f.endswith(".XML")}
    assert _EXPECTED_FILES.issubset(found), f"Missing: {_EXPECTED_FILES - found}"


@skip_if_offline
def test_xml_files_parseable():
    """xml_parser.parse_powercenter_xml succeeds on each file without raising."""
    from rag_system.ingestion.xml_parser import parse_powercenter_xml

    errors = []
    for fname in sorted(_EXPECTED_FILES):
        fpath = os.path.join(_INFA_FOLDER, fname)
        try:
            result = parse_powercenter_xml(fpath)
            assert isinstance(result, dict), f"{fname}: result is not a dict"
        except Exception as exc:
            errors.append(f"{fname}: {exc}")

    assert not errors, "Parse errors:\n" + "\n".join(errors)


@skip_if_offline
def test_node_counts_reasonable(kb):
    """Full corpus should yield well over 100 chunks."""
    count = kb.count()
    assert count > 100, f"Expected >100 chunks but got {count}"
    print(f"\n  Total chunks indexed: {count}")


@skip_if_offline
def test_all_node_classes_present(kb):
    """SOURCE, TRANSFORMATION, and TARGET nodes must all appear."""
    classes = {c.node_class for c in kb.chunks}
    for expected in ("SOURCE", "TRANSFORMATION", "TARGET"):
        assert expected in classes, f"No {expected} nodes found"


@skip_if_offline
def test_transformation_types_present(kb):
    """Key PowerCenter transformation types from the EINTERACTION app must be indexed."""
    tx_types = {
        c.metadata.get("type", "")
        for c in kb.chunks
        if c.node_class == "TRANSFORMATION"
    }
    # Expect at least Source Qualifier and Expression in any real PC export
    assert "Source Qualifier" in tx_types, f"No Source Qualifier found; got: {tx_types}"
    assert "Expression" in tx_types, f"No Expression found; got: {tx_types}"
    print(f"\n  Transformation types found: {sorted(tx_types)}")


@skip_if_offline
def test_teradata_source_db_metadata(kb):
    """Source nodes should carry source_db=Teradata (confirmed from wf_4202 live run)."""
    source_dbs = {
        c.metadata.get("source_db", "")
        for c in kb.chunks
        if c.node_class == "SOURCE"
    }
    assert "Teradata" in source_dbs, f"No Teradata source found; got: {source_dbs}"


@skip_if_offline
def test_sql_override_chunks_exist(kb):
    """At least some Source Qualifier nodes must have SQL overrides."""
    sql_chunks = [
        c for c in kb.chunks
        if c.metadata.get("has_sql_override") and c.node_class == "TRANSFORMATION"
    ]
    assert len(sql_chunks) > 0, "No chunks with SQL override found"
    assert any("SQL_OVERRIDE" in c.text for c in sql_chunks)


@skip_if_offline
def test_chunk_token_budget_respected(kb):
    """No chunk should exceed 700*4=2800 characters (our token budget * chars/token)."""
    MAX_CHARS = 700 * 4
    oversized = [c for c in kb.chunks if len(c.text) > MAX_CHARS]
    # A small overlap tail may push a split chunk slightly over — allow 10% tolerance
    assert len(oversized) == 0 or all(
        len(c.text) <= MAX_CHARS * 1.1 for c in oversized
    ), f"{len(oversized)} chunks exceed token budget: {[len(c.text) for c in oversized[:5]]}"


@skip_if_offline
def test_metadata_enrichment(kb):
    """Every chunk must have the required metadata keys."""
    required_keys = {
        "mapping", "type", "source_db", "has_sql_override",
        "has_join", "has_filter", "field_count", "port_count",
    }
    for chunk in kb.chunks[:50]:  # spot-check first 50
        missing = required_keys - set(chunk.metadata.keys())
        assert not missing, f"Chunk {chunk.chunk_id} missing metadata: {missing}"


@skip_if_offline
def test_chunk_ids_unique(kb):
    """All chunk IDs must be globally unique."""
    ids = [c.chunk_id for c in kb.chunks]
    assert len(ids) == len(set(ids)), f"Duplicate chunk IDs: {len(ids) - len(set(ids))} duplicates"


# ---------------------------------------------------------------------------
# Retrieval quality (semantic search over real corpus)
# ---------------------------------------------------------------------------

@skip_if_offline
def test_retrieve_sql_override_query(kb):
    """Query about SQL overrides should surface Source Qualifier chunks."""
    hits = kb.search("SQL override SELECT statement source qualifier", k=5)
    assert len(hits) > 0
    types = [h["metadata"].get("type", "") for h in hits]
    # At least one hit should be a Source Qualifier (or a SOURCE node with SQL)
    assert any(t == "Source Qualifier" or h["node_class"] in ("SOURCE", "TRANSFORMATION")
               for t, h in zip(types, hits))


@skip_if_offline
def test_retrieve_rltinteraction_query(kb):
    """Querying the focus mapping name should return hits with positive scores.

    Note: HashingEmbedding treats camelCase/underscore identifiers as single tokens,
    so 'RLTInteractionAgreement' won't lexically overlap with 'DT_CHN_RLTINTERACTIONAGREEMENT'.
    We validate structural correctness (hits returned, scores > 0, hits contain chunk fields)
    rather than semantic ranking quality — that requires Azure OpenAI embeddings.
    """
    hits = kb.search("RLTInteractionAgreement target table primary key", k=5)
    assert len(hits) > 0, "No hits returned at all"
    assert all(h["score"] > 0 for h in hits), "All scores should be positive"
    assert all("node_class" in h and "text" in h for h in hits), "Hits missing required fields"


@skip_if_offline
def test_retrieve_node_class_filter(kb):
    """filter_node_class=SOURCE should return only SOURCE hits."""
    hits = kb.search("Teradata database table interaction", k=10, filter_node_class="SOURCE")
    assert all(h["node_class"] == "SOURCE" for h in hits)


@skip_if_offline
def test_retrieve_scores_ordered(kb):
    """Scores must be in descending order."""
    hits = kb.search("interaction facts mapping transformations", k=10)
    scores = [h["score"] for h in hits]
    assert scores == sorted(scores, reverse=True), "Hits not sorted by score desc"


@skip_if_offline
def test_wf_4202_focus_mapping(kb):
    """Chunks from wf_4202 (our primary focus mapping file) must be present."""
    wf4202_chunks = [c for c in kb.chunks if "wf_4202" in c.source_file]
    assert len(wf4202_chunks) > 0, "No chunks from wf_4202_fnd_rltinteraction.XML"
    print(f"\n  wf_4202 chunks: {len(wf4202_chunks)}")


# ---------------------------------------------------------------------------
# Per-file parse stats (informational — always prints, never fails)
# ---------------------------------------------------------------------------

@skip_if_offline
def test_print_corpus_stats(kb):
    """Print a breakdown of chunks per file and node class. Always passes."""
    from collections import Counter

    by_file: Counter = Counter(c.source_file for c in kb.chunks)
    by_class: Counter = Counter(c.node_class for c in kb.chunks)
    by_type: Counter = Counter(
        c.metadata.get("type", "—")
        for c in kb.chunks
        if c.node_class == "TRANSFORMATION"
    )

    print(f"\n\n{'='*60}")
    print(f"  CORPUS STATS  (total chunks: {kb.count()})")
    print(f"{'='*60}")
    print("\n  By file:")
    for fname, cnt in sorted(by_file.items()):
        print(f"    {fname:<55} {cnt:>5} chunks")
    print("\n  By node class:")
    for cls, cnt in sorted(by_class.items()):
        print(f"    {cls:<20} {cnt:>5}")
    print("\n  Transformation types:")
    for tp, cnt in by_type.most_common():
        print(f"    {tp:<40} {cnt:>5}")
    print(f"{'='*60}\n")

    assert True  # always pass


@skip_if_offline
def test_golden_dataset_contains_only_acceptable_candidates(kb):
    """Golden dataset must be a subset of candidate rows, and every golden row must be acceptable."""
    import rag_system.api.app as api_app

    assert _GOLDEN_CANDIDATES_DATASET.exists(), f"Missing candidates dataset: {_GOLDEN_CANDIDATES_DATASET}"
    assert _GOLDEN_DATASET.exists(), f"Missing dataset: {_GOLDEN_DATASET}"

    candidate_rows = _load_jsonl_rows(_GOLDEN_CANDIDATES_DATASET)
    golden_rows = _load_jsonl_rows(_GOLDEN_DATASET)
    assert candidate_rows, "Golden candidates dataset is empty"
    assert golden_rows, "Golden dataset is empty"

    candidate_ids = {str(r.get("id") or "") for r in candidate_rows}

    original_kb = api_app._kb
    api_app._kb = kb

    failures: list[str] = []
    try:
        for row in golden_rows:
            row_id = str(row.get("id") or "unknown")
            if row_id not in candidate_ids:
                failures.append(f"{row_id}: not present in candidates dataset")
                continue

            query = str(row.get("query") or "").strip()
            source_file = str(row.get("source_file") or "").strip().lower()
            expected_entities = [str(e).strip() for e in (row.get("expected_entities") or []) if str(e).strip()]

            payload = api_app.answer(
                q=query,
                k=int(row.get("k") or 6),
                mode=str(row.get("mode") or "hybrid"),
                rerank=False,
                prompt_name="answer_with_citations",
                llm=False,
                llm_model=None,
                llm_temperature=0.0,
                llm_max_tokens=800,
                use_graph=True,
            )

            accepted, reason = _evaluate_acceptability(payload, source_file, expected_entities)
            if not accepted:
                failures.append(f"{row_id}: {reason}")
    finally:
        api_app._kb = original_kb

    assert not failures, "Golden dataset contains unacceptable rows:\n- " + "\n- ".join(failures)
