"""Smoke tests — fully offline, no Azure, no Postgres, no XML files needed.

Tests exercise the full pipeline with synthetic canonical nodes using the
HashingEmbedding + InMemoryVectorStore backends.
"""

from __future__ import annotations

import importlib.util
import pytest
from fastapi.testclient import TestClient

from rag_system.chunking import Chunk, chunk_node, chunk_nodes, estimate_tokens
from rag_system.embeddings import HashingEmbedding
from rag_system.knowledge_base import InformaticaKnowledgeBase
from rag_system.store import InMemoryVectorStore


# ---------------------------------------------------------------------------
# Sample nodes (synthetic — mirrors what xml_parser produces)
# ---------------------------------------------------------------------------

SOURCE_NODE = {
    "node_class": "SOURCE",
    "name": "DT_FND_EINTR",
    "dbd": "Teradata",
    "owner": "FND_EINTR_DB",
    "fields": [
        {"name": "INTERACTION_ID", "datatype": "INTEGER", "precision": "10", "scale": "0"},
        {"name": "PARTY_ID", "datatype": "INTEGER", "precision": "10", "scale": "0"},
        {"name": "CHANNEL_CODE", "datatype": "VARCHAR", "precision": "10", "scale": "0"},
    ],
    "mapping": "",
    "folder": "APP_CALCULATE_EINTERACTION",
}

SQ_NODE = {
    "node_class": "TRANSFORMATION",
    "name": "SQ_DT_FND_EINTR",
    "type": "Source Qualifier",
    "ports": [
        {"name": "INTERACTION_ID", "datatype": "INTEGER", "porttype": "OUTPUT", "expression": "", "precision": "10", "scale": "0"},
        {"name": "PARTY_ID", "datatype": "INTEGER", "porttype": "OUTPUT", "expression": "", "precision": "10", "scale": "0"},
    ],
    "sql_override": "SELECT INTERACTION_ID, PARTY_ID FROM FND_EINTR_DB.DT_FND_EINTR WHERE EFFECTIVE_DATE <= CURRENT_DATE",
    "filter_condition": "",
    "join_condition": "",
    "group_by": [],
    "attributes": {},
    "mapping": "m_4202_dt_chn_rltinteractionagreement",
    "folder": "APP_CALCULATE_EINTERACTION",
}

TARGET_NODE = {
    "node_class": "TARGET",
    "name": "DT_CHN_RLTINTERACTIONAGREEMENT",
    "fields": [
        {"name": "INTERACTION_ID", "datatype": "INTEGER", "precision": "10", "scale": "0", "key_type": "PRIMARY KEY"},
        {"name": "AGREEMENT_CODE", "datatype": "VARCHAR", "precision": "20", "scale": "0", "key_type": ""},
    ],
    "primary_keys": ["INTERACTION_ID"],
    "mapping": "",
    "folder": "APP_CALCULATE_EINTERACTION",
}

NODES = [SOURCE_NODE, SQ_NODE, TARGET_NODE]


# ---------------------------------------------------------------------------
# Chunker
# ---------------------------------------------------------------------------

def test_chunk_source_node():
    chunks = chunk_node(SOURCE_NODE, source_file="wf_4202.XML")
    assert len(chunks) >= 1
    c = chunks[0]
    assert c.node_class == "SOURCE"
    assert c.name == "DT_FND_EINTR"
    assert "INTERACTION_ID" in c.text
    assert "Teradata" in c.text
    assert c.metadata["source_db"] == "Teradata"
    assert c.metadata["field_count"] == 3


def test_chunk_transformation_has_sql_flag():
    chunks = chunk_node(SQ_NODE, source_file="wf_4202.XML")
    assert chunks[0].metadata["has_sql_override"] is True
    assert "SQL_OVERRIDE" in chunks[0].text


def test_chunk_target_primary_key():
    chunks = chunk_node(TARGET_NODE, source_file="wf_4202.XML")
    assert "INTERACTION_ID" in chunks[0].text
    assert "PRIMARY_KEYS" in chunks[0].text


def test_token_estimate():
    assert estimate_tokens("hello world foo bar") > 0


def test_chunk_nodes_returns_all():
    chunks = chunk_nodes(NODES, source_file="wf_4202.XML")
    assert len(chunks) == 3  # one per node (all fit in 700 tokens)


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

def test_hashing_embed_shape():
    emb = HashingEmbedding(dim=64)
    vecs = emb.embed(["hello", "world"])
    assert len(vecs) == 2
    assert len(vecs[0]) == 64


def test_hashing_l2_normalized():
    import math
    emb = HashingEmbedding(dim=128)
    vec = emb.embed_one("test embedding normalization")
    norm = math.sqrt(sum(v * v for v in vec))
    assert abs(norm - 1.0) < 1e-5


def test_hashing_deterministic():
    emb = HashingEmbedding()
    a = emb.embed_one("SELECT * FROM foo")
    b = emb.embed_one("SELECT * FROM foo")
    assert a == b


# ---------------------------------------------------------------------------
# Vector store
# ---------------------------------------------------------------------------

def test_in_memory_store_upsert_and_search():
    emb = HashingEmbedding(dim=64)
    store = InMemoryVectorStore(dim=64)

    chunks = chunk_nodes(NODES, source_file="wf_4202.XML")
    vectors = emb.embed([c.text for c in chunks])
    store.upsert(chunks, vectors)

    assert store.count() == 3

    hits = store.search(emb.embed_one("Teradata source SQL SELECT"), k=2)
    assert len(hits) <= 2
    assert all("score" in h for h in hits)
    assert all("text" in h for h in hits)


# ---------------------------------------------------------------------------
# Knowledge base (offline — no XML files, inject nodes directly)
# ---------------------------------------------------------------------------

class _SyntheticKB(InformaticaKnowledgeBase):
    """Subclass that bypasses XML parsing for offline testing."""

    def build_from_nodes(self, nodes, source_file="wf_4202_fnd_rltinteraction.XML"):
        from rag_system.chunking import chunk_nodes as _cn
        self.chunks = _cn(nodes, source_file=source_file)
        self._store = self._make_store()
        vectors = self._embedder.embed([c.text for c in self.chunks])
        self._store.upsert(self.chunks, vectors)
        workflow_key = source_file.lower()
        self._semantic_workflows = {
            workflow_key: {
                "workflow": {
                    "workflow_id": source_file,
                    "source_file": source_file,
                    "repository": "repo_test",
                    "folder": "APP_CALCULATE_EINTERACTION",
                },
                "mappings": [{"mapping_id": f"{source_file}|m_4202_dt_chn_rltinteractionagreement", "workflow": source_file, "name": "m_4202_dt_chn_rltinteractionagreement"}],
                "nodes": [],
                "ports": [],
                "connectors": [],
                "lineage_paths": [
                    {
                        "path_id": f"{source_file}|lineage|1",
                        "evidence_id": "semantic:lineage:test4202",
                        "workflow": source_file,
                        "mapping": "m_4202_dt_chn_rltinteractionagreement",
                        "target_instance": "DT_CHN_RLTINTERACTIONAGREEMENT",
                        "target_field": "INTERACTION_ID",
                        "source_instance": "DT_FND_EINTR",
                        "source_field": "INTERACTION_ID",
                        "hop_count": 2,
                        "resolved": True,
                        "hops": [
                            {
                                "instance": "DT_CHN_RLTINTERACTIONAGREEMENT",
                                "field": "INTERACTION_ID",
                                "node_class": "TARGET",
                            },
                            {
                                "instance": "SQ_DT_FND_EINTR",
                                "field": "INTERACTION_ID",
                                "node_class": "TRANSFORMATION",
                            },
                            {
                                "instance": "DT_FND_EINTR",
                                "field": "INTERACTION_ID",
                                "node_class": "SOURCE",
                            },
                        ],
                    }
                ],
            }
        }
        self._built = True
        return self


def test_kb_search_returns_hits():
    kb = _SyntheticKB(backend="memory", embedding_provider=HashingEmbedding(dim=64))
    kb.build_from_nodes(NODES)
    assert kb.count() == 3

    hits = kb.search("SQL override source qualifier", k=2)
    assert len(hits) >= 1
    assert hits[0]["node_class"] in {"SOURCE", "TRANSFORMATION", "TARGET"}


def test_kb_filter_by_node_class():
    kb = _SyntheticKB(backend="memory", embedding_provider=HashingEmbedding(dim=64))
    kb.build_from_nodes(NODES)
    hits = kb.search("interaction", k=5, filter_node_class="SOURCE")
    assert all(h["node_class"] == "SOURCE" for h in hits)


def test_kb_semantic_lineage_query_exact_match():
    kb = _SyntheticKB(backend="memory", embedding_provider=HashingEmbedding(dim=64))
    kb.build_from_nodes(NODES)

    result = kb.query_semantic_lineage(
        workflow_hint="wf_4202_fnd_rltinteraction.XML",
        field_name="INTERACTION_ID",
        limit=10,
    )
    assert result["status"] == "ok"
    assert result["workflow"] == "wf_4202_fnd_rltinteraction.XML"
    assert result["total_path_count"] >= 1
    assert result["paths"][0]["evidence_id"] == "semantic:lineage:test4202"


def test_kb_semantic_impact_query_exact_match():
    kb = _SyntheticKB(backend="memory", embedding_provider=HashingEmbedding(dim=64))
    kb.build_from_nodes(NODES)

    result = kb.query_semantic_impact(
        workflow_hint="wf_4202_fnd_rltinteraction.XML",
        field_name="INTERACTION_ID",
        limit=10,
    )
    assert result["status"] == "ok"
    assert result["impacted_target_count"] >= 1
    assert "DT_CHN_RLTINTERACTIONAGREEMENT.INTERACTION_ID" in result["impacted_targets"]


def test_kb_semantic_cross_workflow_lineage_query():
    kb = _SyntheticKB(backend="memory", embedding_provider=HashingEmbedding(dim=64))
    kb.build_from_nodes(NODES)

    second_workflow = "wf_4205_calculate_dm_facts.XML"
    kb._semantic_workflows[second_workflow.lower()] = {
        "workflow": {
            "workflow_id": second_workflow,
            "source_file": second_workflow,
            "repository": "repo_test",
            "folder": "APP_CALCULATE_EINTERACTION",
        },
        "mappings": [{"mapping_id": f"{second_workflow}|m_4205", "workflow": second_workflow, "name": "m_4205"}],
        "nodes": [],
        "ports": [],
        "connectors": [],
        "lineage_paths": [
            {
                "path_id": f"{second_workflow}|lineage|1",
                "evidence_id": "semantic:lineage:test4205",
                "workflow": second_workflow,
                "mapping": "m_4205",
                "target_instance": "FACT_DM",
                "target_field": "INTERACTION_ID",
                "source_instance": "SRC_DM",
                "source_field": "INTERACTION_ID",
                "hop_count": 1,
                "resolved": True,
                "hops": [
                    {"instance": "FACT_DM", "field": "INTERACTION_ID", "node_class": "TARGET"},
                    {"instance": "SRC_DM", "field": "INTERACTION_ID", "node_class": "SOURCE"},
                ],
            }
        ],
    }
    kb._rebuild_lineage_graph(source="memory")

    result = kb.query_semantic_lineage(
        workflow_hint="",
        field_name="INTERACTION_ID",
        limit=10,
        allow_cross_workflow=True,
    )
    assert result["status"] == "ok"
    assert result.get("cross_workflow") is True
    assert result.get("workflow_count", 0) >= 2
    assert len(result.get("paths") or []) >= 2


# ---------------------------------------------------------------------------
# FastAPI endpoint (in-process, no network)
# ---------------------------------------------------------------------------

@pytest.fixture
def api_client_with_kb():
    from rag_system.api import app as _app_module
    import rag_system.api.app as api_app

    kb = _SyntheticKB(backend="memory", embedding_provider=HashingEmbedding(dim=64))
    kb.build_from_nodes(NODES)
    api_app._kb = kb
    api_app._ingest_status = {"state": "done", "chunks": kb.count(), "error": None}

    with TestClient(api_app.app) as client:
        yield client

    api_app._kb = None
    api_app._ingest_status = {"state": "idle", "chunks": 0, "error": None}


def test_health_endpoint(api_client_with_kb):
    r = api_client_with_kb.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["kb_built"] is True
    assert data["chunk_count"] == 3


def test_retrieve_endpoint(api_client_with_kb):
    r = api_client_with_kb.get("/retrieve", params={"q": "SQL override Teradata", "k": 2})
    assert r.status_code == 200
    data = r.json()
    assert "hits" in data
    assert len(data["hits"]) <= 2
    assert "trace" in data and data["trace"]["endpoint"] == "/retrieve"
    assert "telemetry" in data and "timing_ms" in data["telemetry"]
    assert data["telemetry"]["timing_ms"]["total_ms"] >= 0


def test_answer_lineage_routes_semantic_primary(api_client_with_kb):
    r = api_client_with_kb.get(
        "/answer",
        params={
            "q": "Show lineage for INTERACTION_ID in wf_4202_fnd_rltinteraction.XML",
            "k": 4,
            "llm": False,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["orchestration_mode"] == "semantic_primary"
    assert data["refused"] is False
    assert data["answer_strategy"] in {"semantic_deterministic", "semantic_llm_copilot"}
    assert data["evidence"]
    assert data["evidence"][0]["evidence_source"] == "semantic_layer"
    assert "trace" in data and data["trace"]["endpoint"] == "/answer"
    assert "telemetry" in data and "timing_ms" in data["telemetry"]
    assert data["telemetry"]["timing_ms"]["total_ms"] >= 0


def test_answer_impact_routes_semantic_primary(api_client_with_kb):
    r = api_client_with_kb.get(
        "/answer",
        params={
            "q": "What is the impact of INTERACTION_ID in wf_4202_fnd_rltinteraction.XML",
            "k": 4,
            "llm": False,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["orchestration_mode"] == "semantic_primary"
    assert data["refused"] is False
    assert data["answer_strategy"] in {"semantic_deterministic", "semantic_llm_copilot"}
    assert "impacted" in (data.get("answer_text") or "").lower()


def test_answer_lineage_without_workflow_hint_uses_cross_workflow_graph(api_client_with_kb):
    r = api_client_with_kb.get(
        "/answer",
        params={
            "q": "Show lineage for INTERACTION_ID",
            "k": 4,
            "llm": False,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["orchestration_mode"] == "semantic_primary"
    assert data["refused"] is False
    assert data.get("semantic_result", {}).get("cross_workflow") is True


def test_retrieve_without_kb_returns_503():
    from rag_system.api import app as api_app_module
    import rag_system.api.app as api_app

    original = api_app._kb
    api_app._kb = None
    with TestClient(api_app.app) as client:
        r = client.get("/retrieve", params={"q": "test"})
    api_app._kb = original
    assert r.status_code == 503


def test_answer_empty_llm_uses_extractive_fallback(api_client_with_kb, monkeypatch):
    import rag_system.api.app as api_app

    def _fake_generate(*args, **kwargs):
        return None, False, "gpt-test", "OpenAI returned an empty response"

    monkeypatch.setattr(api_app, "_generate_answer_openai", _fake_generate)

    r = api_client_with_kb.get(
        "/answer",
        params={"q": "Explain SQL override in wf_4202.XML", "k": 3, "llm": True},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["refused"] is False
    assert isinstance(data.get("answer_text"), str)
    assert "Based on retrieved Informatica evidence" in data["answer_text"]
    assert data["llm_used"] is False
    assert "fallback_extractive" in (data.get("llm_error") or "")


def test_answer_includes_relevancy_boost_fields(api_client_with_kb):
    r = api_client_with_kb.get(
        "/answer",
        params={"q": "Find SQL override in wf_4202.XML", "k": 3, "llm": False, "relevancy_boost": True},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["refused"] is False
    assert data["relevancy_boost_requested"] is True
    assert "answer_strategy" in data
    assert "[" in (data.get("answer_text") or "") and "]" in (data.get("answer_text") or "")


def test_answer_relevancy_boost_can_be_disabled(api_client_with_kb):
    r = api_client_with_kb.get(
        "/answer",
        params={"q": "Find SQL override in wf_4202.XML", "k": 3, "llm": False, "relevancy_boost": False},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["refused"] is False
    assert data["relevancy_boost_requested"] is False
    assert data["relevancy_boost_applied"] is False


def test_needs_relevancy_boost_when_answer_misses_source_hint():
    import rag_system.api.app as api_app

    query = "What logic exists in wf_4202_fnd_rltinteraction.XML?"
    answer = "The workflow contains Source Qualifier logic and joins [chunk_1]."
    assert api_app._needs_relevancy_boost(answer, query) is True


def test_grounded_fallback_mentions_usage_entity_in_answer():
    import rag_system.api.app as api_app

    query = "Where is BeginInteractionGroup_Id used?"
    evidence = [
        {
            "chunk_id": "wf_4205:LINEAGE:begin:1",
            "source_file": "wf_4205_calculate_dm_facts.XML",
            "node_class": "LINEAGE",
            "name": "Fact.BaseInteractionGroup_Id",
            "cited_text": (
                "FILE: wf_4205_calculate_dm_facts.XML\n"
                "NODE_CLASS: LINEAGE\n"
                "TARGET: Fact.BaseInteractionGroup_Id\n"
                "SOURCE: BeginInteractionGroup.BeginInteractionGroup_Id\n"
                "PATH: BeginInteractionGroup_Id -> Fact.BaseInteractionGroup_Id"
            ),
        }
    ]

    answer = api_app._build_grounded_relevance_answer(query, evidence)
    assert "BeginInteractionGroup_Id" in answer
    assert "wf_4205_calculate_dm_facts.XML" in answer
    assert "[wf_4205:LINEAGE:begin:1]" in answer


def test_source_file_hints_extract_and_filter_helpers():
    import rag_system.api.app as api_app

    hints = api_app._extract_source_file_hints("Show logic from wf_4202_fnd_rltinteraction.XML")
    assert hints == ["wf_4202_fnd_rltinteraction.xml"]

    hits = [
        {"chunk_id": "a", "source_file": "wf_4201_calculate_interaction_facts.xml"},
        {"chunk_id": "b", "source_file": "wf_4202_fnd_rltinteraction.xml"},
    ]
    scoped = api_app._prefer_source_file_hits(hits, hints)
    assert len(scoped) == 1
    assert scoped[0]["chunk_id"] == "b"


def test_source_file_hints_strict_mode_returns_empty_when_no_match():
    import rag_system.api.app as api_app

    hints = ["wf_9999_missing.xml"]
    hits = [
        {"chunk_id": "a", "source_file": "wf_4201_calculate_interaction_facts.xml"},
        {"chunk_id": "b", "source_file": "wf_4202_fnd_rltinteraction.xml"},
    ]

    scoped = api_app._prefer_source_file_hits(hits, hints, strict=True)
    assert scoped == []


def test_lineage_guardrail_refuses_when_lineage_hits_missing():
    import rag_system.api.app as api_app

    payload = api_app._build_answer_payload_from_retrieval(
        q="Show lineage for InteractionEvent_Id in wf_4202_fnd_rltinteraction.XML",
        rerank=False,
        prompt_name="answer_with_citations",
        llm=False,
        relevancy_boost=True,
        llm_model=None,
        llm_temperature=0.0,
        llm_max_tokens=700,
        hits=[
            {
                "chunk_id": "wf_4202:TRANSFORMATION:exp_shared:1",
                "source_file": "wf_4202_fnd_rltinteraction.xml",
                "node_class": "TRANSFORMATION",
                "name": "exp_shared_attributes",
                "score": 0.95,
                "text": "Expression with shared attribute defaults",
            }
        ],
        reranked=False,
        rerank_error=None,
        plan={"rewritten_query": "InteractionEvent_Id wf_4202"},
        resolved_mode="hybrid",
        effective_query="InteractionEvent_Id wf_4202_fnd_rltinteraction.XML",
        source_file_hints=["wf_4202_fnd_rltinteraction.xml"],
    )

    assert payload["refused"] is True
    assert payload["reason"] in {"lineage_unavailable", "lineage_not_indexed_for_workflow"}
    assert payload["answer_strategy"] == "lineage_guardrail_refusal"
    assert "LINEAGE" in (payload.get("detail") or "")


def test_retrieve_hits_lineage_applies_source_and_anchor_filters(monkeypatch):
    import rag_system.api.app as api_app

    class _DummyKB:
        _built = True
        _store = None

        def hybrid_search(self, query_text, k=5, filter_node_class=None):
            assert filter_node_class == "LINEAGE"
            return [
                {
                    "chunk_id": "wf_4202:LINEAGE:a",
                    "source_file": "wf_4202_fnd_rltinteraction.xml",
                    "node_class": "LINEAGE",
                    "name": "DT.InteractionEvent_Id",
                    "text": "TARGET: DT.InteractionEvent_Id\\nSOURCE: SRC.InteractionEvent_Id",
                    "score": 0.9,
                },
                {
                    "chunk_id": "wf_4201:LINEAGE:b",
                    "source_file": "wf_4201_calculate_interaction_facts.xml",
                    "node_class": "LINEAGE",
                    "name": "DT.InteractionEvent_Id",
                    "text": "TARGET: DT.InteractionEvent_Id\\nSOURCE: SRC.InteractionEvent_Id",
                    "score": 0.8,
                },
                {
                    "chunk_id": "wf_4202:LINEAGE:c",
                    "source_file": "wf_4202_fnd_rltinteraction.xml",
                    "node_class": "LINEAGE",
                    "name": "DT.Other_Field",
                    "text": "TARGET: DT.Other_Field\\nSOURCE: SRC.Other_Field",
                    "score": 0.7,
                },
            ]

        def search(self, query_text, k=5, filter_node_class=None):
            return self.hybrid_search(query_text, k=k, filter_node_class=filter_node_class)

    monkeypatch.setattr(api_app, "_kb", _DummyKB())

    out = api_app._retrieve_hits(
        q="Show lineage for InteractionEvent_Id in wf_4202_fnd_rltinteraction.XML",
        k=5,
        node_class=None,
        mode="hybrid",
        rerank=False,
        use_planner=False,
        planner_llm_model=None,
    )

    hits = out["hits"]
    assert hits
    assert all(h["node_class"] == "LINEAGE" for h in hits)
    assert all(h["source_file"] == "wf_4202_fnd_rltinteraction.xml" for h in hits)
    assert all("interactionevent_id" in (h.get("text") or "").lower() for h in hits)


def test_lineage_coverage_snapshot_method():
    kb = InformaticaKnowledgeBase(backend="memory", embedding_provider=HashingEmbedding(dim=32))
    kb._lineage_coverage_by_file = {
        "wf_4202_fnd_rltinteraction.XML": {
            "lineage_chunk_count": 3,
            "chain_count": 5,
            "resolved_chain_count": 3,
            "unresolved_chain_count": 2,
            "target_field_count": 4,
            "resolved_target_field_count": 3,
            "unresolved_target_field_count": 1,
            "resolved_target_fields": ["DT.INTERACTION_ID"],
            "unresolved_target_fields": ["DT.UNRELATED_FIELD"],
            "parse_error": None,
        }
    }

    summary = kb.lineage_coverage_snapshot(include_fields=False)
    assert summary["available"] is True
    assert summary["workflow_count"] == 1
    assert summary["totals"]["lineage_chunk_count"] == 3
    assert "resolved_target_fields" not in summary["workflows"][0]

    detailed = kb.lineage_coverage_snapshot(include_fields=True)
    assert detailed["workflows"][0]["resolved_target_fields"] == ["DT.INTERACTION_ID"]


def test_lineage_coverage_endpoint(api_client_with_kb):
    r = api_client_with_kb.get("/lineage/coverage")
    assert r.status_code == 200
    data = r.json()
    assert data["kb_built"] is True
    assert "lineage_coverage" in data


def test_semantic_model_endpoint(api_client_with_kb):
    r = api_client_with_kb.get("/semantic/model")
    assert r.status_code == 200
    data = r.json()
    assert data["kb_built"] is True
    assert data["semantic_layer"]["available"] is True


def test_semantic_lineage_endpoint(api_client_with_kb):
    r = api_client_with_kb.get(
        "/semantic/lineage",
        params={
            "workflow": "wf_4202_fnd_rltinteraction.XML",
            "field": "INTERACTION_ID",
            "limit": 10,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["result"]["status"] == "ok"
    assert data["result"]["paths"]
    assert data["trace"]["endpoint"] == "/semantic/lineage"
    assert data["telemetry"]["timing_ms"]["total_ms"] >= 0


def test_semantic_impact_endpoint(api_client_with_kb):
    r = api_client_with_kb.get(
        "/semantic/impact",
        params={
            "workflow": "wf_4202_fnd_rltinteraction.XML",
            "field": "INTERACTION_ID",
            "limit": 10,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["result"]["status"] == "ok"
    assert data["result"]["impacted_target_count"] >= 1
    assert data["trace"]["endpoint"] == "/semantic/impact"
    assert data["telemetry"]["timing_ms"]["total_ms"] >= 0


def test_answer_graph_mode_explicit_flag(api_client_with_kb):
    if importlib.util.find_spec("langgraph") is None:
        pytest.skip("langgraph is not installed")

    r = api_client_with_kb.get(
        "/answer",
        params={
            "q": "SQL override Teradata",
            "k": 3,
            "llm": False,
            "use_graph": True,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("orchestration_mode") == "graph"
    assert "graph" in data
    assert data["graph"]["validator_decision"] in {"pass", "retry", "fail"}


def test_answer_graph_mode_env_toggle(api_client_with_kb, monkeypatch):
    if importlib.util.find_spec("langgraph") is None:
        pytest.skip("langgraph is not installed")

    monkeypatch.setenv("ANSWER_ORCHESTRATION_MODE", "graph")

    r = api_client_with_kb.get(
        "/answer",
        params={
            "q": "SQL override Teradata",
            "k": 3,
            "llm": False,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("orchestration_mode") == "graph"


def test_chat_session_create_and_transcript(api_client_with_kb):
    import rag_system.api.app as api_app

    # Ensure isolated chat state for repeatable tests
    with api_app._chat_lock:
        api_app._chat_sessions.clear()

    created = api_client_with_kb.post("/chat/sessions")
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    msg = api_client_with_kb.post(
        f"/chat/sessions/{session_id}/messages",
        json={
            "message": "Find SQL override in wf_4202.XML",
            "llm": False,
            "history_turns": 4,
        },
    )
    assert msg.status_code == 200
    payload = msg.json()
    assert payload["session_id"] == session_id
    assert payload["answer"]["refused"] is False
    assert isinstance(payload["answer"].get("answer_text"), str)

    transcript = api_client_with_kb.get(f"/chat/sessions/{session_id}/messages")
    assert transcript.status_code == 200
    data = transcript.json()
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][1]["role"] == "assistant"


def test_chat_followup_uses_contextual_query(api_client_with_kb):
    import rag_system.api.app as api_app

    with api_app._chat_lock:
        api_app._chat_sessions.clear()

    created = api_client_with_kb.post("/chat/sessions")
    session_id = created.json()["session_id"]

    first = api_client_with_kb.post(
        f"/chat/sessions/{session_id}/messages",
        json={
            "message": "Find SQL override in wf_4202.XML",
            "llm": False,
        },
    )
    assert first.status_code == 200

    follow = api_client_with_kb.post(
        f"/chat/sessions/{session_id}/messages",
        json={
            "message": "Where is it used?",
            "llm": False,
            "history_turns": 4,
        },
    )
    assert follow.status_code == 200
    out = follow.json()
    assert out["answer"]["query_original"] == "Where is it used?"
    assert "Follow-up question with chat context" in out["answer"]["query_contextualized"]
    assert out["answer"]["chat_context_message_count"] >= 2


def test_chat_ui_endpoint_serves_html(api_client_with_kb):
    r = api_client_with_kb.get("/chat/ui")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert "RAG Web Chat" in r.text


def test_chat_refusal_has_non_empty_assistant_text(api_client_with_kb, monkeypatch):
    import rag_system.api.app as api_app

    with api_app._chat_lock:
        api_app._chat_sessions.clear()

    created = api_client_with_kb.post("/chat/sessions")
    session_id = created.json()["session_id"]

    def _fake_answer_legacy(**kwargs):
        return {
            "query": kwargs.get("q"),
            "refused": True,
            "reason": "insufficient_evidence",
            "detail": "Not enough evidence for this broad question.",
            "answer_text": None,
            "answer_strategy": "refusal",
            "llm_used": False,
            "llm_error": "skipped_due_to_refusal",
        }

    monkeypatch.setattr(api_app, "_answer_legacy", _fake_answer_legacy)

    resp = api_client_with_kb.post(
        f"/chat/sessions/{session_id}/messages",
        json={
            "message": "what can you help me with?",
            "llm": True,
            "use_graph": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["assistant_message"]["text"], str)
    assert data["assistant_message"]["text"].strip() != ""
    assert "Not enough evidence" in data["assistant_message"]["text"]


def test_chat_summary_update_and_clear(api_client_with_kb):
    import rag_system.api.app as api_app

    with api_app._chat_lock:
        api_app._chat_sessions.clear()

    created = api_client_with_kb.post("/chat/sessions")
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    update = api_client_with_kb.put(
        f"/chat/sessions/{session_id}/summary",
        json={"summary": "user prefers lineage-first explanations"},
    )
    assert update.status_code == 200
    updated = update.json()
    assert updated["summary"] == "user prefers lineage-first explanations"

    meta = api_client_with_kb.get(f"/chat/sessions/{session_id}")
    assert meta.status_code == 200
    assert meta.json()["summary"] == "user prefers lineage-first explanations"

    cleared = api_client_with_kb.delete(f"/chat/sessions/{session_id}/summary")
    assert cleared.status_code == 200
    assert cleared.json()["summary"] == ""


def test_agent_context_endpoint_reports_inventory(api_client_with_kb):
    r = api_client_with_kb.get("/agent/context", params={"query": "what can you do"})
    assert r.status_code == 200
    data = r.json()
    assert data["orchestration_mode"] == "agent_context"
    assert data["answer_strategy"] == "agent_context_capabilities"
    assert data["context_inventory"]["kb_available"] is True
    assert data["context_inventory"]["total_chunks"] >= 3
    assert "Indexed knowledge snapshot" in (data.get("answer_text") or "")


def test_chat_capability_prompt_routes_to_context_agent(api_client_with_kb):
    import rag_system.api.app as api_app

    with api_app._chat_lock:
        api_app._chat_sessions.clear()

    created = api_client_with_kb.post("/chat/sessions")
    session_id = created.json()["session_id"]

    resp = api_client_with_kb.post(
        f"/chat/sessions/{session_id}/messages",
        json={
            "message": "what can you do and what xmls are indexed?",
            "llm": True,
            "use_graph": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"]["answer_strategy"] == "agent_context_capabilities"
    assert data["answer"]["orchestration_mode"] == "agent_context"
    assert data["answer"]["context_inventory"]["kb_available"] is True
    assert "Indexed knowledge snapshot" in (data["assistant_message"].get("text") or "")


def test_chat_capability_prompt_natural_phrase_routes_to_context_agent(api_client_with_kb):
    import rag_system.api.app as api_app

    with api_app._chat_lock:
        api_app._chat_sessions.clear()

    created = api_client_with_kb.post("/chat/sessions")
    session_id = created.json()["session_id"]

    resp = api_client_with_kb.post(
        f"/chat/sessions/{session_id}/messages",
        json={
            "message": "tell me what it can do and what all information it has across indexed xmls",
            "llm": True,
            "use_graph": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"]["answer_strategy"] == "agent_context_capabilities"
    assert data["answer"]["orchestration_mode"] == "agent_context"


def test_chat_session_persists_across_memory_clear(api_client_with_kb):
    import rag_system.api.app as api_app

    with api_app._chat_lock:
        api_app._chat_sessions.clear()

    created = api_client_with_kb.post("/chat/sessions")
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    sent = api_client_with_kb.post(
        f"/chat/sessions/{session_id}/messages",
        json={
            "message": "Find SQL override in wf_4202.XML",
            "llm": False,
            "use_graph": False,
        },
    )
    assert sent.status_code == 200

    with api_app._chat_lock:
        api_app._chat_sessions.clear()

    meta = api_client_with_kb.get(f"/chat/sessions/{session_id}")
    assert meta.status_code == 200
    assert meta.json()["message_count"] >= 2

    transcript = api_client_with_kb.get(f"/chat/sessions/{session_id}/messages")
    assert transcript.status_code == 200
    roles = [m["role"] for m in transcript.json()["messages"]]
    assert roles[:2] == ["user", "assistant"]


# ---------------------------------------------------------------------------
# Lineage parser + chunker (offline — synthetic connector graph)
# ---------------------------------------------------------------------------

SYNTHETIC_PARSED = {
    "repository": "TEST",
    "folder": "TEST_FOLDER",
    "sources": [
        {"node_class": "SOURCE", "name": "SRC_INTERACTION", "dbd": "Teradata",
         "owner": "DB", "fields": [{"name": "INTERACTION_ID", "datatype": "INTEGER",
                                    "precision": "10", "scale": "0"}], "mapping": ""}
    ],
    "targets": [
        {"node_class": "TARGET", "name": "TGT_INTERACTION",
         "fields": [{"name": "INTERACTION_ID", "datatype": "INTEGER",
                     "precision": "10", "scale": "0", "key_type": "PRIMARY KEY"}],
         "primary_keys": ["INTERACTION_ID"], "mapping": ""}
    ],
    "mappings": [
        {
            "name": "m_test_mapping",
            "transformations": [
                {"node_class": "TRANSFORMATION", "name": "EXP_CALC",
                 "type": "Expression", "ports": [], "attributes": {},
                 "sql_override": "", "filter_condition": "", "join_condition": "",
                 "group_by": [], "mapping": "m_test_mapping"}
            ],
            "connectors": [
                # SRC_INTERACTION.INTERACTION_ID → EXP_CALC.INTERACTION_ID
                {"from_instance": "SRC_INTERACTION", "from_field": "INTERACTION_ID",
                 "to_instance": "EXP_CALC", "to_field": "INTERACTION_ID"},
                # EXP_CALC.INTERACTION_ID → TGT_INTERACTION.INTERACTION_ID
                {"from_instance": "EXP_CALC", "from_field": "INTERACTION_ID",
                 "to_instance": "TGT_INTERACTION", "to_field": "INTERACTION_ID"},
            ]
        }
    ]
}


def test_lineage_chains_resolved():
    from rag_system.ingestion.lineage_parser import build_lineage_chains, summarise
    chains = build_lineage_chains(SYNTHETIC_PARSED, source_file="test.XML")
    assert len(chains) >= 1
    resolved = [c for c in chains if c["resolved"]]
    assert len(resolved) >= 1, "At least one chain must trace back to a SOURCE"


def test_lineage_chain_fields():
    from rag_system.ingestion.lineage_parser import build_lineage_chains
    chains = build_lineage_chains(SYNTHETIC_PARSED, source_file="test.XML")
    resolved = [c for c in chains if c["resolved"]]
    chain = resolved[0]
    assert chain["node_class"] == "LINEAGE"
    assert chain["target_instance"] == "TGT_INTERACTION"
    assert chain["target_field"] == "INTERACTION_ID"
    assert chain["source_instance"] == "SRC_INTERACTION"
    assert chain["source_field"] == "INTERACTION_ID"
    assert chain["hop_count"] == 2   # TGT → EXP → SRC


def test_lineage_chain_hops_order():
    """Path should be ordered TARGET → ... → SOURCE."""
    from rag_system.ingestion.lineage_parser import build_lineage_chains
    chains = build_lineage_chains(SYNTHETIC_PARSED, source_file="test.XML")
    resolved = [c for c in chains if c["resolved"]]
    hops = resolved[0]["hops"]
    assert hops[0]["node_class"] == "TARGET"
    assert hops[-1]["node_class"] == "SOURCE"


def test_lineage_chunk_rendered():
    from rag_system.ingestion.lineage_parser import build_lineage_chains
    from rag_system.chunking.chunker import chunk_lineage_chains, render_lineage_chain
    chains = build_lineage_chains(SYNTHETIC_PARSED, source_file="test.XML")
    resolved = [c for c in chains if c["resolved"]]
    text = render_lineage_chain(resolved[0])
    assert "NODE_CLASS: LINEAGE" in text
    assert "TARGET: TGT_INTERACTION.INTERACTION_ID" in text
    assert "SOURCE: SRC_INTERACTION.INTERACTION_ID" in text
    assert "PATH:" in text


def test_lineage_chunk_id_stable():
    """Same chain always produces the same chunk_id (content-hash based)."""
    from rag_system.ingestion.lineage_parser import build_lineage_chains
    from rag_system.chunking.chunker import chunk_lineage_chains
    chains = build_lineage_chains(SYNTHETIC_PARSED, source_file="test.XML")
    c1 = chunk_lineage_chains(chains, source_file="test.XML")
    c2 = chunk_lineage_chains(chains, source_file="test.XML")
    ids1 = {c.chunk_id for c in c1}
    ids2 = {c.chunk_id for c in c2}
    assert ids1 == ids2


def test_lineage_chunk_node_class():
    from rag_system.ingestion.lineage_parser import build_lineage_chains
    from rag_system.chunking.chunker import chunk_lineage_chains
    chains = build_lineage_chains(SYNTHETIC_PARSED, source_file="test.XML")
    chunks = chunk_lineage_chains(chains, source_file="test.XML")
    assert all(c.node_class == "LINEAGE" for c in chunks)
