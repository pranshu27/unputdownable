"""Informatica RAG Knowledge Base.

Orchestrates the full ingest pipeline:
    parse_powercenter_xml → flatten_mapping_to_nodes → chunk_nodes → embed → upsert

Then serves semantic retrieval over the indexed corpus.

Backends (RAG_BACKEND env):
    memory   — InMemoryVectorStore (default; offline/tests)
    pgvector — PgVectorStore (production; requires POSTGRES_URL)

Usage
-----
    from rag_system.knowledge_base import InformaticaKnowledgeBase

    kb = InformaticaKnowledgeBase()
    kb.build_from_folder("path/to/app_CALCULATE_EINTERACTION")

    hits = kb.search("Source Qualifier SQL override for RLTInteraction", k=5)
    for h in hits:
        print(h["score"], h["name"], h["text"][:120])
"""

from __future__ import annotations

import json
import hashlib
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from rag_system.chunking import Chunk, chunk_nodes
from rag_system.embeddings import EmbeddingProvider, get_embedding_provider
from rag_system.ingestion.pc_processor import walk_xml_folder
from rag_system.ingestion.xml_parser import parse_powercenter_xml
from rag_system.chunking.chunker import chunk_lineage_chains
from rag_system.lineage import LineageNetworkXEngine, build_workflow_lineage_graph
from rag_system.store import InMemoryVectorStore, PgSemanticStore, PgVectorStore, VectorStore

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=_PROJECT_ROOT / ".env")
logger = logging.getLogger(__name__)


class InformaticaKnowledgeBase:
    """Chunk + embed + index every canonical node from an Informatica XML dump folder."""

    def __init__(
        self,
        backend: Optional[str] = None,
        embedding_provider: Optional[EmbeddingProvider] = None,
    ) -> None:
        """Initialize KB runtime state, store adapters, and semantic graph cache handles."""
        self._embedder = embedding_provider or get_embedding_provider()
        self.backend = (backend or os.getenv("RAG_BACKEND", "memory")).lower()
        self.chunks: List[Chunk] = []
        self._store: Optional[VectorStore] = None
        self._semantic_store: Optional[PgSemanticStore] = None
        self._built = False
        self._lineage_coverage_by_file: Dict[str, Dict[str, Any]] = {}
        self._semantic_workflows: Dict[str, Dict[str, Any]] = {}
        self._lineage_graph: Optional[LineageNetworkXEngine] = None
        self._lineage_graph_source = "none"

    @staticmethod
    def _norm_text(value: Any) -> str:
        """Return a trimmed string representation for nullable values."""
        return str(value or "").strip()

    @classmethod
    def _semantic_port_record(
        cls,
        *,
        source_file: str,
        node_class: str,
        node_name: str,
        mapping: str,
        port_name: str,
        datatype: str,
        role: str,
        expression: str = "",
    ) -> Dict[str, Any]:
        """Build a normalized semantic-port record for persistence and querying."""
        return {
            "port_id": f"{source_file}|{node_class}|{node_name}|{port_name}",
            "workflow": source_file,
            "mapping": mapping,
            "node_class": node_class,
            "node": node_name,
            "name": port_name,
            "datatype": datatype,
            "role": role,
            "expression": expression,
        }

    @classmethod
    def _build_semantic_workflow_model(
        cls,
        *,
        parsed: Dict[str, Any],
        source_file: str,
        chains: List[Dict[str, Any]],
        graph_meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Convert parsed XML and lineage chains into one semantic workflow document."""
        graph_meta = graph_meta or {}
        workflow_entity = {
            "workflow_id": source_file,
            "source_file": source_file,
            "repository": cls._norm_text(parsed.get("repository")),
            "folder": cls._norm_text(parsed.get("folder")),
            "graph_hash": cls._norm_text(graph_meta.get("graph_hash")),
            "graph_engine": cls._norm_text(graph_meta.get("engine")),
        }

        mappings: List[Dict[str, Any]] = []
        nodes: List[Dict[str, Any]] = []
        ports: List[Dict[str, Any]] = []
        connectors: List[Dict[str, Any]] = []
        lineage_paths: List[Dict[str, Any]] = []

        for src in parsed.get("sources", []):
            src_name = cls._norm_text(src.get("name"))
            nodes.append(
                {
                    "node_id": f"{source_file}|SOURCE|{src_name}",
                    "workflow": source_file,
                    "mapping": "",
                    "node_class": "SOURCE",
                    "name": src_name,
                    "type": cls._norm_text(src.get("dbd")),
                    "owner": cls._norm_text(src.get("owner")),
                }
            )
            for field in src.get("fields", []):
                ports.append(
                    cls._semantic_port_record(
                        source_file=source_file,
                        node_class="SOURCE",
                        node_name=src_name,
                        mapping="",
                        port_name=cls._norm_text(field.get("name")),
                        datatype=cls._norm_text(field.get("datatype")),
                        role="FIELD",
                    )
                )

        for tgt in parsed.get("targets", []):
            tgt_name = cls._norm_text(tgt.get("name"))
            nodes.append(
                {
                    "node_id": f"{source_file}|TARGET|{tgt_name}",
                    "workflow": source_file,
                    "mapping": "",
                    "node_class": "TARGET",
                    "name": tgt_name,
                    "type": "TARGET",
                    "owner": "",
                }
            )
            for field in tgt.get("fields", []):
                ports.append(
                    cls._semantic_port_record(
                        source_file=source_file,
                        node_class="TARGET",
                        node_name=tgt_name,
                        mapping="",
                        port_name=cls._norm_text(field.get("name")),
                        datatype=cls._norm_text(field.get("datatype")),
                        role=cls._norm_text(field.get("key_type")) or "FIELD",
                    )
                )

        for mapping in parsed.get("mappings", []):
            mapping_name = cls._norm_text(mapping.get("name"))
            mappings.append(
                {
                    "mapping_id": f"{source_file}|{mapping_name}",
                    "workflow": source_file,
                    "name": mapping_name,
                }
            )

            for tx in mapping.get("transformations", []):
                tx_name = cls._norm_text(tx.get("name"))
                tx_type = cls._norm_text(tx.get("type"))
                nodes.append(
                    {
                        "node_id": f"{source_file}|TRANSFORMATION|{tx_name}",
                        "workflow": source_file,
                        "mapping": mapping_name,
                        "node_class": "TRANSFORMATION",
                        "name": tx_name,
                        "type": tx_type,
                        "owner": "",
                    }
                )
                for port in tx.get("ports", []):
                    ports.append(
                        cls._semantic_port_record(
                            source_file=source_file,
                            node_class="TRANSFORMATION",
                            node_name=tx_name,
                            mapping=mapping_name,
                            port_name=cls._norm_text(port.get("name")),
                            datatype=cls._norm_text(port.get("datatype")),
                            role=cls._norm_text(port.get("porttype")) or "PORT",
                            expression=cls._norm_text(port.get("expression")),
                        )
                    )

            for connector in mapping.get("connectors", []):
                from_instance = cls._norm_text(connector.get("from_instance"))
                from_field = cls._norm_text(connector.get("from_field"))
                to_instance = cls._norm_text(connector.get("to_instance"))
                to_field = cls._norm_text(connector.get("to_field"))
                edge_key = f"{source_file}|{mapping_name}|{from_instance}.{from_field}|{to_instance}.{to_field}"
                edge_id = hashlib.md5(edge_key.encode("utf-8")).hexdigest()[:12]
                connectors.append(
                    {
                        "edge_id": edge_id,
                        "workflow": source_file,
                        "mapping": mapping_name,
                        "from_node": from_instance,
                        "from_port": from_field,
                        "to_node": to_instance,
                        "to_port": to_field,
                    }
                )

        for idx, chain in enumerate(chains, start=1):
            target_instance = cls._norm_text(chain.get("target_instance"))
            target_field = cls._norm_text(chain.get("target_field"))
            source_instance = cls._norm_text(chain.get("source_instance"))
            source_field = cls._norm_text(chain.get("source_field"))
            path_text = " -> ".join(
                f"{cls._norm_text(h.get('instance'))}.{cls._norm_text(h.get('field'))}"
                for h in chain.get("hops", [])
            )
            lineage_key = (
                f"{source_file}|{target_instance}.{target_field}|{source_instance}.{source_field}|"
                f"{cls._norm_text(chain.get('mapping'))}|{path_text}"
            )
            evidence_id = "semantic:lineage:" + hashlib.md5(lineage_key.encode("utf-8")).hexdigest()[:16]
            lineage_paths.append(
                {
                    "path_id": f"{source_file}|lineage|{idx}",
                    "evidence_id": evidence_id,
                    "workflow": source_file,
                    "mapping": cls._norm_text(chain.get("mapping")),
                    "target_instance": target_instance,
                    "target_field": target_field,
                    "source_instance": source_instance,
                    "source_field": source_field,
                    "hop_count": int(chain.get("hop_count") or 0),
                    "resolved": bool(chain.get("resolved")),
                    "hops": [
                        {
                            "instance": cls._norm_text(h.get("instance")),
                            "field": cls._norm_text(h.get("field")),
                            "node_class": cls._norm_text(h.get("node_class")) or "TRANSFORMATION",
                        }
                        for h in chain.get("hops", [])
                    ],
                }
            )

        return {
            "workflow": workflow_entity,
            "mappings": mappings,
            "nodes": nodes,
            "ports": ports,
            "connectors": connectors,
            "lineage_paths": lineage_paths,
        }

    def _resolve_semantic_workflow_key(self, workflow_hint: str) -> Optional[str]:
        """Resolve workflow hints to canonical workflow keys with extension-tolerant matching."""
        if not workflow_hint:
            return None

        hint = self._norm_text(workflow_hint).lower()
        if hint in self._semantic_workflows:
            return hint

        hint_no_ext = hint[:-4] if hint.endswith(".xml") else hint
        for key in self._semantic_workflows.keys():
            key_no_ext = key[:-4] if key.endswith(".xml") else key
            if key_no_ext == hint_no_ext:
                return key
        return None

    @staticmethod
    def _path_mentions_field(path: Dict[str, Any], field_name: str) -> bool:
        """Return True when a lineage path references the requested field token."""
        token = str(field_name or "").strip().lower()
        if not token:
            return False
        if str(path.get("target_field") or "").strip().lower() == token:
            return True
        if str(path.get("source_field") or "").strip().lower() == token:
            return True
        for hop in path.get("hops", []):
            if str(hop.get("field") or "").strip().lower() == token:
                return True
        return False

    def _hydrate_semantic_workflows_from_store(self) -> bool:
        """Load semantic workflows from PostgreSQL when in-memory models are empty."""
        if self._semantic_store is None:
            return False
        if self._semantic_workflows:
            return True

        try:
            models = self._semantic_store.load_workflow_lineage_models(max_workflows=1000)
        except Exception as exc:
            logger.warning("Failed to hydrate semantic workflows from postgres store: %s", exc)
            return False

        if not models:
            return False

        self._semantic_workflows = models
        return True

    def _rebuild_lineage_graph(self, *, source: str) -> None:
        """Recreate the NetworkX lineage graph from current semantic workflow models."""
        if not self._semantic_workflows:
            self._lineage_graph = None
            self._lineage_graph_source = "none"
            return

        self._lineage_graph = LineageNetworkXEngine(self._semantic_workflows)
        self._lineage_graph_source = source

    def _ensure_lineage_graph(self) -> Optional[LineageNetworkXEngine]:
        """Return an initialized lineage graph, hydrating workflow models when necessary."""
        if self._lineage_graph is not None:
            return self._lineage_graph

        if self._semantic_workflows:
            self._rebuild_lineage_graph(source="memory")
            return self._lineage_graph

        hydrated = self._hydrate_semantic_workflows_from_store()
        if hydrated:
            self._rebuild_lineage_graph(source="postgres")
            return self._lineage_graph

        return None

    def lineage_graph_snapshot(self) -> Dict[str, Any]:
        """Return runtime lineage-graph availability and structural stats."""
        graph = self._ensure_lineage_graph()
        if graph is None:
            return {
                "available": False,
                "engine": "networkx",
                "source": self._lineage_graph_source,
            }
        stats = graph.stats()
        stats["source"] = self._lineage_graph_source
        return stats

    def semantic_layer_snapshot(self, *, max_workflows: Optional[int] = None) -> Dict[str, Any]:
        """Return semantic layer counts by workflow from PostgreSQL or in-memory fallback."""
        if self._semantic_store is not None:
            try:
                return self._semantic_store.semantic_layer_snapshot(max_workflows=max_workflows)
            except Exception as exc:
                logger.warning("Semantic snapshot from postgres failed; falling back to in-memory model: %s", exc)

        items = list(self._semantic_workflows.items())
        items.sort(key=lambda kv: kv[0])
        if max_workflows is not None:
            items = items[: max(0, int(max_workflows))]

        workflows: List[Dict[str, Any]] = []
        for _, wf in items:
            workflows.append(
                {
                    "source_file": wf.get("workflow", {}).get("source_file"),
                    "repository": wf.get("workflow", {}).get("repository"),
                    "folder": wf.get("workflow", {}).get("folder"),
                    "graph_hash": wf.get("workflow", {}).get("graph_hash"),
                    "mapping_count": len(wf.get("mappings", [])),
                    "node_count": len(wf.get("nodes", [])),
                    "port_count": len(wf.get("ports", [])),
                    "connector_count": len(wf.get("connectors", [])),
                    "lineage_path_count": len(wf.get("lineage_paths", [])),
                }
            )

        return {
            "available": bool(self._semantic_workflows),
            "workflow_count": len(self._semantic_workflows),
            "workflows": workflows,
        }

    def query_semantic_lineage(
        self,
        *,
        workflow_hint: str,
        field_name: str,
        limit: int = 20,
        allow_cross_workflow: bool = False,
    ) -> Dict[str, Any]:
        """Resolve deterministic lineage paths for a field within one workflow or across workflows."""
        graph = self._ensure_lineage_graph()
        if graph is not None:
            try:
                graph_result = graph.query_lineage(
                    workflow_hint=workflow_hint,
                    field_name=field_name,
                    limit=limit,
                    allow_cross_workflow=allow_cross_workflow,
                )
                if graph_result.get("status") != "graph_unavailable":
                    return graph_result
            except Exception as exc:
                logger.warning("NetworkX lineage query failed; falling back to semantic store: %s", exc)

        if self._semantic_store is not None:
            try:
                return self._semantic_store.query_semantic_lineage(
                    workflow_hint=workflow_hint,
                    field_name=field_name,
                    limit=limit,
                )
            except Exception as exc:
                logger.warning("Semantic lineage query from postgres failed; falling back to in-memory model: %s", exc)

        resolved_key = self._resolve_semantic_workflow_key(workflow_hint)
        if not resolved_key:
            return {
                "status": "workflow_not_indexed",
                "workflow_hint": workflow_hint,
                "field": field_name,
                "paths": [],
            }

        wf = self._semantic_workflows[resolved_key]
        field_token = self._norm_text(field_name)
        matches = [
            path
            for path in wf.get("lineage_paths", [])
            if self._path_mentions_field(path, field_token)
        ]

        if not matches:
            return {
                "status": "field_not_found",
                "workflow": wf.get("workflow", {}).get("source_file", workflow_hint),
                "field": field_token,
                "paths": [],
            }

        matches.sort(
            key=lambda p: (
                0 if bool(p.get("resolved")) else 1,
                int(p.get("hop_count") or 0),
                str(p.get("target_instance") or ""),
                str(p.get("target_field") or ""),
            )
        )
        limited = matches[: max(1, int(limit))]

        resolved_count = sum(1 for p in limited if p.get("resolved"))
        unresolved_count = len(limited) - resolved_count

        return {
            "status": "ok",
            "workflow": wf.get("workflow", {}).get("source_file", workflow_hint),
            "field": field_token,
            "total_path_count": len(matches),
            "resolved_path_count": resolved_count,
            "unresolved_path_count": unresolved_count,
            "paths": limited,
        }

    def query_semantic_impact(
        self,
        *,
        workflow_hint: str,
        field_name: str,
        limit: int = 25,
        allow_cross_workflow: bool = False,
    ) -> Dict[str, Any]:
        """Resolve deterministic impact targets for a field using semantic lineage evidence."""
        graph = self._ensure_lineage_graph()
        if graph is not None:
            try:
                graph_result = graph.query_impact(
                    workflow_hint=workflow_hint,
                    field_name=field_name,
                    limit=limit,
                    allow_cross_workflow=allow_cross_workflow,
                )
                if graph_result.get("status") != "graph_unavailable":
                    return graph_result
            except Exception as exc:
                logger.warning("NetworkX impact query failed; falling back to semantic store: %s", exc)

        if self._semantic_store is not None:
            try:
                return self._semantic_store.query_semantic_impact(
                    workflow_hint=workflow_hint,
                    field_name=field_name,
                    limit=limit,
                )
            except Exception as exc:
                logger.warning("Semantic impact query from postgres failed; falling back to in-memory model: %s", exc)

        resolved_key = self._resolve_semantic_workflow_key(workflow_hint)
        if not resolved_key:
            return {
                "status": "workflow_not_indexed",
                "workflow_hint": workflow_hint,
                "field": field_name,
                "paths": [],
                "impacted_targets": [],
            }

        wf = self._semantic_workflows[resolved_key]
        field_token = self._norm_text(field_name)
        matches = [
            path
            for path in wf.get("lineage_paths", [])
            if self._path_mentions_field(path, field_token)
        ]

        if not matches:
            return {
                "status": "field_not_found",
                "workflow": wf.get("workflow", {}).get("source_file", workflow_hint),
                "field": field_token,
                "paths": [],
                "impacted_targets": [],
            }

        impacted_targets_set = {
            f"{self._norm_text(path.get('target_instance'))}.{self._norm_text(path.get('target_field'))}"
            for path in matches
            if self._norm_text(path.get("target_instance")) and self._norm_text(path.get("target_field"))
        }
        impacted_mappings = sorted(
            {
                self._norm_text(path.get("mapping"))
                for path in matches
                if self._norm_text(path.get("mapping"))
            }
        )

        matches.sort(
            key=lambda p: (
                int(p.get("hop_count") or 0),
                str(p.get("target_instance") or ""),
                str(p.get("target_field") or ""),
            )
        )
        limited = matches[: max(1, int(limit))]

        return {
            "status": "ok",
            "workflow": wf.get("workflow", {}).get("source_file", workflow_hint),
            "field": field_token,
            "total_path_count": len(matches),
            "impacted_target_count": len(impacted_targets_set),
            "impacted_targets": sorted(impacted_targets_set),
            "impacted_mappings": impacted_mappings,
            "paths": limited,
        }

    @staticmethod
    def _lineage_target_key(chain: Dict[str, Any]) -> str:
        """Create a stable target_instance.target_field key for a lineage chain."""
        return f"{chain.get('target_instance', '')}.{chain.get('target_field', '')}"

    @classmethod
    def _build_lineage_file_coverage(
        cls,
        chains: List[Dict[str, Any]],
        lineage_chunk_count: int,
        parse_error: Optional[str] = None,
        graph_meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Aggregate lineage resolution coverage metrics for one source workflow file."""
        graph_meta = graph_meta or {}
        target_fields = {
            cls._lineage_target_key(c)
            for c in chains
            if c.get("target_instance") and c.get("target_field")
        }
        resolved_target_fields = {
            cls._lineage_target_key(c)
            for c in chains
            if c.get("resolved") and c.get("target_instance") and c.get("target_field")
        }
        unresolved_target_fields = sorted(target_fields - resolved_target_fields)
        resolved_target_fields_sorted = sorted(resolved_target_fields)

        resolved_chain_count = sum(1 for c in chains if c.get("resolved"))
        unresolved_chain_count = len(chains) - resolved_chain_count

        return {
            "lineage_chunk_count": int(lineage_chunk_count),
            "chain_count": int(len(chains)),
            "resolved_chain_count": int(resolved_chain_count),
            "unresolved_chain_count": int(unresolved_chain_count),
            "target_field_count": int(len(target_fields)),
            "resolved_target_field_count": int(len(resolved_target_fields_sorted)),
            "unresolved_target_field_count": int(len(unresolved_target_fields)),
            "resolved_target_fields": resolved_target_fields_sorted,
            "unresolved_target_fields": unresolved_target_fields,
            "parse_error": parse_error,
            "graph_hash": cls._norm_text(graph_meta.get("graph_hash")),
            "graph_engine": cls._norm_text(graph_meta.get("engine")),
            "graph_node_count": int(graph_meta.get("graph_node_count") or 0),
            "graph_edge_count": int(graph_meta.get("graph_edge_count") or 0),
        }

    @staticmethod
    def _slug_for_chunk_id(value: str) -> str:
        """Convert free text to a compact chunk-id-safe slug."""
        return re.sub(r"[^A-Za-z0-9_]+", "_", str(value or ""))[:60]

    @staticmethod
    def _short_hash(value: str) -> str:
        """Return a short stable hash token for deterministic chunk ids."""
        return hashlib.md5(str(value or "").encode("utf-8", errors="replace")).hexdigest()[:10]

    @staticmethod
    def _semantic_definition_use_llm() -> bool:
        """Return whether semantic explanation artifacts should call an LLM."""
        return os.getenv("SEMANTIC_DEFINITIONS_USE_LLM", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _resolve_semantic_definition_runtime() -> Dict[str, Any]:
        """Resolve provider/runtime settings for LLM-backed semantic explanation generation."""
        if not InformaticaKnowledgeBase._semantic_definition_use_llm():
            return {"enabled": False, "reason": "llm_disabled"}

        openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        azure_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
        azure_base = (
            os.getenv("AZURE_OPENAI_API_BASE", "").strip()
            or os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
        )
        model_name = (
            os.getenv("SEMANTIC_DEFINITION_MODEL", "").strip()
            or os.getenv("OPENAI_MODEL", "").strip()
            or os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "").strip()
        )

        if azure_key and azure_base and model_name:
            return {
                "enabled": True,
                "provider": "azure",
                "api_key": azure_key,
                "base_url": azure_base,
                "api_version": os.getenv("AZURE_API_VERSION", "2024-08-01-preview").strip(),
                "model_name": model_name,
            }

        if openai_key and model_name:
            return {
                "enabled": True,
                "provider": "openai",
                "api_key": openai_key,
                "model_name": model_name,
            }

        return {"enabled": False, "reason": "credentials_or_model_missing"}

    @staticmethod
    def _make_semantic_definition_client(runtime: Dict[str, Any]) -> Any:
        """Create an OpenAI/Azure OpenAI client for semantic explanation generation."""
        if not runtime.get("enabled"):
            return None

        from openai import AzureOpenAI, OpenAI

        if runtime.get("provider") == "azure":
            return AzureOpenAI(
                api_key=runtime.get("api_key"),
                azure_endpoint=runtime.get("base_url"),
                api_version=runtime.get("api_version", "2024-08-01-preview"),
            )
        return OpenAI(api_key=runtime.get("api_key"))

    @classmethod
    def _render_semantic_explanation_template(cls, *, artifact_kind: str, facts: Dict[str, Any]) -> str:
        """Render deterministic fallback explanation text from structured semantic facts."""
        if artifact_kind == "node_definition":
            return (
                f"Workflow {cls._norm_text(facts.get('workflow'))} contains "
                f"{cls._norm_text(facts.get('node_class'))} node {cls._norm_text(facts.get('name'))}. "
                f"Mapping: {cls._norm_text(facts.get('mapping')) or 'N/A'}. "
                f"Type: {cls._norm_text(facts.get('type')) or 'N/A'}. "
                f"This node exposes {int(facts.get('port_count') or 0)} ports and "
                f"{int(facts.get('field_count') or 0)} source/target fields."
            )

        hops = list(facts.get("hops") or [])
        hop_render = " -> ".join(
            f"{cls._norm_text(h.get('instance'))}.{cls._norm_text(h.get('field'))}"
            for h in hops
            if cls._norm_text(h.get("instance")) and cls._norm_text(h.get("field"))
        )
        return (
            f"Deterministic lineage path in workflow {cls._norm_text(facts.get('workflow'))}: "
            f"target {cls._norm_text(facts.get('target_instance'))}.{cls._norm_text(facts.get('target_field'))} "
            f"maps from source {cls._norm_text(facts.get('source_instance'))}.{cls._norm_text(facts.get('source_field'))}. "
            f"Mapping: {cls._norm_text(facts.get('mapping')) or 'N/A'}. "
            f"Hop count: {int(facts.get('hop_count') or 0)}. "
            f"Path: {hop_render}."
        )

    @classmethod
    def _generate_semantic_explanation_text(
        cls,
        *,
        artifact_kind: str,
        facts: Dict[str, Any],
        runtime: Dict[str, Any],
        client: Any,
    ) -> str:
        """Generate a human-readable explanation using LLM when configured, otherwise template text."""
        fallback_text = cls._render_semantic_explanation_template(
            artifact_kind=artifact_kind,
            facts=facts,
        )
        if not runtime.get("enabled") or client is None:
            return fallback_text

        system_prompt = (
            "You explain Informatica semantic entities and lineage paths. "
            "Use only provided facts. Do not invent fields, mappings, or sources. "
            "Return 2-4 concise sentences."
        )
        user_prompt = (
            f"artifact_kind={artifact_kind}\n"
            f"facts_json={json.dumps(facts, sort_keys=True)}\n"
            "Write a concise deterministic explanation."
        )

        try:
            max_tokens = int(os.getenv("SEMANTIC_DEFINITION_MAX_TOKENS", "220") or 220)
        except ValueError:
            max_tokens = 220

        try:
            response = client.chat.completions.create(
                model=runtime.get("model_name"),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                max_tokens=min(max(max_tokens, 120), 500),
            )
            text = ((response.choices or [None])[0].message.content if response.choices else None) or ""
            text = str(text).strip()
            return text or fallback_text
        except Exception as exc:
            logger.warning("Semantic definition LLM generation failed; using fallback text: %s", exc)
            return fallback_text

    def _build_semantic_explanation_chunks(
        self,
        *,
        workflow_model: Dict[str, Any],
        graph_meta: Optional[Dict[str, Any]] = None,
    ) -> List[Chunk]:
        """Build vector-store explanation artifacts from deterministic semantic entities."""
        graph_meta = graph_meta or {}
        workflow = workflow_model.get("workflow") or {}
        source_file = self._norm_text(workflow.get("source_file"))
        graph_hash = self._norm_text(graph_meta.get("graph_hash") or workflow.get("graph_hash"))
        generated_at = datetime.now(timezone.utc).isoformat()

        runtime = self._resolve_semantic_definition_runtime()
        try:
            client = self._make_semantic_definition_client(runtime)
        except Exception as exc:
            logger.warning("Semantic definition client init failed; using template explanations: %s", exc)
            runtime = {"enabled": False, "reason": "client_init_failed"}
            client = None

        try:
            max_items_env = int(os.getenv("SEMANTIC_DEFINITIONS_MAX_ITEMS", "0") or 0)
        except ValueError:
            max_items_env = 0
        max_items = max(0, max_items_env)

        out: List[Chunk] = []
        nodes = list(workflow_model.get("nodes") or [])
        lineage_paths = list(workflow_model.get("lineage_paths") or [])

        for node in nodes:
            facts = {
                "workflow": source_file,
                "node_id": self._norm_text(node.get("node_id")),
                "node_class": self._norm_text(node.get("node_class")),
                "name": self._norm_text(node.get("name")),
                "type": self._norm_text(node.get("type")),
                "mapping": self._norm_text(node.get("mapping")),
                "field_count": 0,
                "port_count": sum(
                    1
                    for p in workflow_model.get("ports", [])
                    if self._norm_text(p.get("node")) == self._norm_text(node.get("name"))
                ),
            }
            text = self._generate_semantic_explanation_text(
                artifact_kind="node_definition",
                facts=facts,
                runtime=runtime,
                client=client,
            )
            chunk_id = (
                f"{source_file}:SEMANTIC_DEF_NODE:{self._slug_for_chunk_id(facts['name'])}:"
                f"{self._short_hash(text + facts['node_id'])}"
            )
            out.append(
                Chunk(
                    chunk_id=chunk_id,
                    source_file=source_file,
                    node_class="SEMANTIC_DEFINITION",
                    name=facts["name"],
                    text=text,
                    metadata={
                        "artifact_kind": "node_definition",
                        "workflow": source_file,
                        "workflow_key": source_file.lower(),
                        "node_id": facts["node_id"],
                        "mapping": facts["mapping"],
                        "graph_hash": graph_hash,
                        "generated_at": generated_at,
                        "authoritative": False,
                        "evidence_source": "vector_secondary",
                    },
                )
            )
            if max_items and len(out) >= max_items:
                return out

        for path in lineage_paths:
            facts = {
                "workflow": source_file,
                "path_id": self._norm_text(path.get("path_id")),
                "evidence_id": self._norm_text(path.get("evidence_id")),
                "mapping": self._norm_text(path.get("mapping")),
                "target_instance": self._norm_text(path.get("target_instance")),
                "target_field": self._norm_text(path.get("target_field")),
                "source_instance": self._norm_text(path.get("source_instance")),
                "source_field": self._norm_text(path.get("source_field")),
                "hop_count": int(path.get("hop_count") or 0),
                "resolved": bool(path.get("resolved")),
                "hops": list(path.get("hops") or []),
            }
            text = self._generate_semantic_explanation_text(
                artifact_kind="lineage_definition",
                facts=facts,
                runtime=runtime,
                client=client,
            )
            chunk_id = (
                f"{source_file}:SEMANTIC_DEF_PATH:{self._slug_for_chunk_id(facts['target_field'])}:"
                f"{self._short_hash(text + facts['evidence_id'])}"
            )
            out.append(
                Chunk(
                    chunk_id=chunk_id,
                    source_file=source_file,
                    node_class="SEMANTIC_DEFINITION",
                    name=(f"{facts['target_instance']}.{facts['target_field']}"),
                    text=text,
                    metadata={
                        "artifact_kind": "lineage_definition",
                        "workflow": source_file,
                        "workflow_key": source_file.lower(),
                        "path_id": facts["path_id"],
                        "path_evidence_id": facts["evidence_id"],
                        "target_instance": facts["target_instance"],
                        "target_field": facts["target_field"],
                        "mapping": facts["mapping"],
                        "graph_hash": graph_hash,
                        "generated_at": generated_at,
                        "authoritative": False,
                        "evidence_source": "vector_secondary",
                    },
                )
            )
            if max_items and len(out) >= max_items:
                return out

        return out

    def search_semantic_explanations(
        self,
        *,
        query: str,
        evidence_ids: List[str],
        workflow_hint: str = "",
        k: int = 3,
    ) -> List[Dict[str, Any]]:
        """Retrieve vector-ranked explanation artifacts linked to semantic lineage evidence ids."""
        if not self._built or self._store is None:
            return []

        query_vec = self._embedder.embed_one(query)
        fetch_k = max(int(k) * 12, 40)
        hits = self._store.search(query_vec, k=fetch_k)

        evidence_set = {self._norm_text(x) for x in evidence_ids if self._norm_text(x)}
        workflow_norm = self._norm_text(workflow_hint).lower()

        out: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for hit in hits:
            chunk_id = self._norm_text(hit.get("chunk_id"))
            if not chunk_id or chunk_id in seen:
                continue

            metadata = hit.get("metadata") or {}
            artifact_kind = self._norm_text(metadata.get("artifact_kind"))
            if artifact_kind not in {"lineage_definition", "node_definition"}:
                continue

            if workflow_norm:
                hit_workflow = self._norm_text(metadata.get("workflow")).lower()
                hit_workflow_key = self._norm_text(metadata.get("workflow_key")).lower()
                if hit_workflow and hit_workflow != workflow_norm and hit_workflow_key != workflow_norm:
                    continue

            if artifact_kind == "lineage_definition" and evidence_set:
                path_evidence = self._norm_text(metadata.get("path_evidence_id"))
                if path_evidence not in evidence_set:
                    continue

            seen.add(chunk_id)
            out.append(hit)
            if len(out) >= max(1, int(k)):
                break

        return out

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _make_store(self) -> VectorStore:
        """Create the configured vector store backend with safe fallback to memory."""
        if self.backend == "pgvector":
            dsn = os.getenv("POSTGRES_URL", "")
            if dsn:
                try:
                    store = PgVectorStore(dsn, dim=self._embedder.dim)
                    logger.info("RAG store: pgvector (dim=%s)", self._embedder.dim)
                    return store
                except Exception as exc:
                    logger.warning("pgvector unavailable (%s); falling back to memory", exc)
        logger.info("RAG store: in-memory (dim=%s)", self._embedder.dim)
        return InMemoryVectorStore(dim=self._embedder.dim)

    def _make_semantic_store(self) -> Optional[PgSemanticStore]:
        """Create PostgreSQL semantic-store adapter when pgvector mode is enabled."""
        if self.backend != "pgvector":
            return None

        dsn = os.getenv("POSTGRES_URL", "")
        if not dsn:
            return None

        try:
            store = PgSemanticStore(dsn, schema="rag")
            logger.info("Semantic store: postgres schema rag")
            return store
        except Exception as exc:
            logger.warning("Semantic postgres store unavailable (%s); using in-memory semantic model", exc)
            return None

    def build_from_folder(
        self,
        folder_path: str,
        focus_mapping: Optional[str] = None,
        batch_size: int = 64,
    ) -> "InformaticaKnowledgeBase":
        """Parse, chunk, embed, and index every PowerCenter XML in folder_path.

        Args:
            folder_path:    Directory containing wf_*.XML exports.
            focus_mapping:  If set, only this mapping's transformations are chunked
                            (sources and targets are still indexed from all files).
            batch_size:     Embedding batch size (reduce if hitting API limits).
        """
        logger.info("Building RAG KB from: %s", folder_path)
        nodes = walk_xml_folder(folder_path, focus_mapping=focus_mapping)
        logger.info("Parsed %d canonical nodes from XML folder", len(nodes))

        # Group nodes by source file so chunk_id stays namespaced per file.
        nodes_by_file = {}
        for node in nodes:
            sf = node.get("_source_file", "unknown.xml")
            nodes_by_file.setdefault(sf, []).append(node)

        all_chunks: List[Chunk] = []
        for sf, file_nodes in nodes_by_file.items():
            all_chunks.extend(chunk_nodes(file_nodes, source_file=sf))

        # Build lineage chunks from CONNECTOR elements in each XML
        seen_paths: set[str] = set()
        lineage_chunks_total = 0
        explanation_chunks_total = 0
        lineage_coverage_by_file: Dict[str, Dict[str, Any]] = {}
        semantic_workflows: Dict[str, Dict[str, Any]] = {}
        for sf, file_nodes in nodes_by_file.items():
            xml_path = file_nodes[0].get("_xml_path", "") if file_nodes else ""
            if not xml_path or xml_path in seen_paths:
                continue
            seen_paths.add(xml_path)
            try:
                parsed = parse_powercenter_xml(xml_path)
                graph_bundle = build_workflow_lineage_graph(parsed=parsed, source_file=sf)
                chains = list(graph_bundle.get("chains") or [])
                graph_meta = dict(graph_bundle.get("graph_meta") or {})
                lineage_chunks = chunk_lineage_chains(chains, source_file=sf)
                all_chunks.extend(lineage_chunks)
                lineage_chunks_total += len(lineage_chunks)
                semantic_model = self._build_semantic_workflow_model(
                    parsed=parsed,
                    source_file=sf,
                    chains=chains,
                    graph_meta=graph_meta,
                )
                semantic_workflows[sf.lower()] = semantic_model

                explanation_chunks = self._build_semantic_explanation_chunks(
                    workflow_model=semantic_model,
                    graph_meta=graph_meta,
                )
                explanation_chunks_total += len(explanation_chunks)
                all_chunks.extend(explanation_chunks)

                lineage_coverage_by_file[sf] = self._build_lineage_file_coverage(
                    chains=chains,
                    lineage_chunk_count=len(lineage_chunks),
                    graph_meta=graph_meta,
                )
            except Exception as exc:
                lineage_coverage_by_file[sf] = self._build_lineage_file_coverage(
                    chains=[],
                    lineage_chunk_count=0,
                    parse_error=str(exc),
                )
                logger.warning("Lineage parsing failed for %s: %s", sf, exc)
        if lineage_chunks_total:
            logger.info("Generated %d lineage chunks", lineage_chunks_total)
        if explanation_chunks_total:
            logger.info("Generated %d semantic explanation artifact chunks", explanation_chunks_total)
        self._lineage_coverage_by_file = lineage_coverage_by_file
        self._semantic_workflows = semantic_workflows
        self._rebuild_lineage_graph(source="memory")

        # Deduplicate: same source table/target can appear in multiple FOLDER elements
        # within one XML; identical chunk_id means identical content — keep first.
        seen: set[str] = set()
        unique: list[Chunk] = []
        for c in all_chunks:
            if c.chunk_id not in seen:
                seen.add(c.chunk_id)
                unique.append(c)
        dropped = len(all_chunks) - len(unique)
        if dropped:
            logger.info("Deduplication removed %d identical chunks", dropped)
        all_chunks = unique

        logger.info("Generated %d chunks", len(all_chunks))
        self.chunks = all_chunks
        self._store = self._make_store()
        self._semantic_store = self._make_semantic_store()

        if self._semantic_store and semantic_workflows:
            persisted = 0
            for workflow_model in semantic_workflows.values():
                self._semantic_store.upsert_workflow_model(workflow_model)
                persisted += 1
            logger.info("Persisted semantic workflows into postgres: %d", persisted)

        # Embed in batches and upsert
        for i in range(0, len(all_chunks), batch_size):
            batch = all_chunks[i : i + batch_size]
            texts = [c.text for c in batch]
            vectors = self._embedder.embed(texts)
            self._store.upsert(batch, vectors)

        logger.info(
            "Indexed %d chunks into %s store", self._store.count(), self.backend
        )
        self._built = True
        return self

    # ------------------------------------------------------------------
    # Retrieve
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        k: int = 5,
        filter_node_class: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Semantic search over the indexed corpus.

        Args:
            query:            Natural-language or keyword query.
            k:                Number of top hits to return.
            filter_node_class: Optional post-filter: SOURCE | TRANSFORMATION | TARGET.
        """
        if not self._built or self._store is None:
            raise RuntimeError("Call build_from_folder() before search().")

        qvec = self._embedder.embed_one(query)
        # Fetch extra so post-filter doesn't leave us short
        fetch_k = k * 3 if filter_node_class else k
        hits = self._store.search(qvec, k=fetch_k)

        if filter_node_class:
            hits = [h for h in hits if h.get("node_class") == filter_node_class]

        return hits[:k]

    def hybrid_search(
        self,
        query: str,
        k: int = 5,
        filter_node_class: Optional[str] = None,
        rrf_k: int = 60,
    ) -> List[Dict[str, Any]]:
        """Hybrid retrieval: BM25 + vector cosine fused with RRF.

        Falls back to vector-only search if the store does not support BM25
        (e.g. InMemoryVectorStore in tests).
        """
        if not self._built or self._store is None:
            raise RuntimeError("Call build_from_folder() before hybrid_search().")

        from rag_system.store.vector_store import PgVectorStore

        if not isinstance(self._store, PgVectorStore):
            # Offline / test path: vector-only
            return self.search(query, k=k, filter_node_class=filter_node_class)

        qvec = self._embedder.embed_one(query)
        fetch_k = k * 4 if filter_node_class else k * 2
        hits = self._store.search_hybrid(qvec, query_text=query, k=fetch_k, rrf_k=rrf_k)

        if filter_node_class:
            hits = [h for h in hits if h.get("node_class") == filter_node_class]

        return hits[:k]

    def count(self) -> int:
        """Return indexed chunk count from the active vector store."""
        return self._store.count() if self._store else 0

    def lineage_coverage_snapshot(
        self,
        *,
        include_fields: bool = False,
        max_files: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Return lineage-resolution telemetry aggregated across indexed workflow files."""
        if not self._lineage_coverage_by_file:
            return {
                "available": False,
                "workflow_count": 0,
                "totals": {
                    "lineage_chunk_count": 0,
                    "resolved_target_field_count": 0,
                    "unresolved_target_field_count": 0,
                },
                "workflows": [],
            }

        items = sorted(
            self._lineage_coverage_by_file.items(),
            key=lambda kv: (
                -int(kv[1].get("unresolved_target_field_count") or 0),
                kv[0].lower(),
            ),
        )
        if max_files is not None:
            items = items[: max(0, int(max_files))]

        workflows: List[Dict[str, Any]] = []
        total_lineage_chunks = 0
        total_resolved_target_fields = 0
        total_unresolved_target_fields = 0

        for source_file, row in items:
            total_lineage_chunks += int(row.get("lineage_chunk_count") or 0)
            total_resolved_target_fields += int(row.get("resolved_target_field_count") or 0)
            total_unresolved_target_fields += int(row.get("unresolved_target_field_count") or 0)

            entry: Dict[str, Any] = {
                "source_file": source_file,
                "lineage_chunk_count": int(row.get("lineage_chunk_count") or 0),
                "chain_count": int(row.get("chain_count") or 0),
                "resolved_chain_count": int(row.get("resolved_chain_count") or 0),
                "unresolved_chain_count": int(row.get("unresolved_chain_count") or 0),
                "target_field_count": int(row.get("target_field_count") or 0),
                "resolved_target_field_count": int(row.get("resolved_target_field_count") or 0),
                "unresolved_target_field_count": int(row.get("unresolved_target_field_count") or 0),
                "graph_hash": row.get("graph_hash"),
                "graph_engine": row.get("graph_engine"),
                "graph_node_count": int(row.get("graph_node_count") or 0),
                "graph_edge_count": int(row.get("graph_edge_count") or 0),
                "parse_error": row.get("parse_error"),
            }
            if include_fields:
                entry["resolved_target_fields"] = list(row.get("resolved_target_fields") or [])
                entry["unresolved_target_fields"] = list(row.get("unresolved_target_fields") or [])

            workflows.append(entry)

        return {
            "available": True,
            "workflow_count": int(len(self._lineage_coverage_by_file)),
            "totals": {
                "lineage_chunk_count": int(total_lineage_chunks),
                "resolved_target_field_count": int(total_resolved_target_fields),
                "unresolved_target_field_count": int(total_unresolved_target_fields),
            },
            "workflows": workflows,
        }
