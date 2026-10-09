"""NetworkX lineage engine for workflow-scoped and cross-workflow tracing."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import networkx as nx
except Exception:  # pragma: no cover - optional dependency at runtime
    nx = None


def build_workflow_lineage_graph(
    *,
    parsed: Dict[str, Any],
    source_file: str,
    max_depth: int = 20,
) -> Dict[str, Any]:
    """Build a workflow graph from connectors and derive deterministic lineage chains.

    Returns a dict with:
    - chains: List[dict] lineage chains (target -> source hop order)
    - graph_meta: deterministic metadata including graph hash and node/edge counts
    """
    connectors_payload: List[Dict[str, str]] = []
    mapping_by_target: Dict[str, str] = {}

    for mapping in parsed.get("mappings", []):
        mapping_name = str(mapping.get("name") or "").strip()
        for tx in mapping.get("transformations", []):
            tx_name = str(tx.get("name") or "").strip()
            if tx_name:
                mapping_by_target[tx_name] = mapping_name

        for connector in mapping.get("connectors", []):
            from_instance = str(connector.get("from_instance") or "").strip()
            from_field = str(connector.get("from_field") or "").strip()
            to_instance = str(connector.get("to_instance") or "").strip()
            to_field = str(connector.get("to_field") or "").strip()
            if not from_instance or not from_field or not to_instance or not to_field:
                continue
            connectors_payload.append(
                {
                    "mapping": mapping_name,
                    "from_instance": from_instance,
                    "from_field": from_field,
                    "to_instance": to_instance,
                    "to_field": to_field,
                }
            )

    target_fields: List[Tuple[str, str]] = []
    for target in parsed.get("targets", []):
        target_name = str(target.get("name") or "").strip()
        if not target_name:
            continue
        mapping_by_target.setdefault(target_name, next((
            str(m.get("name") or "").strip() for m in parsed.get("mappings", [])
        ), ""))
        for field in target.get("fields", []):
            field_name = str(field.get("name") or "").strip()
            if field_name:
                target_fields.append((target_name, field_name))

    graph_hash_payload = {
        "source_file": str(source_file or "").strip(),
        "connectors": sorted(
            connectors_payload,
            key=lambda row: (
                row.get("mapping", ""),
                row.get("from_instance", ""),
                row.get("from_field", ""),
                row.get("to_instance", ""),
                row.get("to_field", ""),
            ),
        ),
        "targets": sorted(target_fields),
    }
    graph_hash = hashlib.sha256(
        json.dumps(graph_hash_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]

    if nx is None:
        from rag_system.ingestion.lineage_parser import build_lineage_chains

        chains = build_lineage_chains(parsed, source_file=source_file, max_depth=max_depth)
        resolved_chain_count = sum(1 for row in chains if row.get("resolved"))
        return {
            "chains": chains,
            "graph_meta": {
                "engine": "fallback_no_networkx",
                "graph_hash": graph_hash,
                "graph_node_count": 0,
                "graph_edge_count": 0,
                "chain_count": len(chains),
                "resolved_chain_count": resolved_chain_count,
                "unresolved_chain_count": len(chains) - resolved_chain_count,
            },
        }

    def _node_id(instance: str, field: str) -> str:
        return f"{instance.strip().lower()}::{field.strip().lower()}"

    node_lookup: Dict[str, str] = {}
    for src in parsed.get("sources", []):
        src_name = str(src.get("name") or "").strip()
        if src_name:
            node_lookup[src_name] = "SOURCE"
    for target in parsed.get("targets", []):
        target_name = str(target.get("name") or "").strip()
        if target_name:
            node_lookup[target_name] = "TARGET"
    for mapping in parsed.get("mappings", []):
        for tx in mapping.get("transformations", []):
            tx_name = str(tx.get("name") or "").strip()
            if tx_name:
                node_lookup[tx_name] = "TRANSFORMATION"

    graph = nx.DiGraph()
    for connector in connectors_payload:
        from_instance = connector["from_instance"]
        from_field = connector["from_field"]
        to_instance = connector["to_instance"]
        to_field = connector["to_field"]

        src_id = _node_id(from_instance, from_field)
        dst_id = _node_id(to_instance, to_field)

        graph.add_node(
            src_id,
            instance=from_instance,
            field=from_field,
            node_class=node_lookup.get(from_instance, "TRANSFORMATION"),
        )
        graph.add_node(
            dst_id,
            instance=to_instance,
            field=to_field,
            node_class=node_lookup.get(to_instance, "TRANSFORMATION"),
        )
        graph.add_edge(src_id, dst_id, mapping=connector.get("mapping", ""))

    chains: List[Dict[str, Any]] = []
    folder = str(parsed.get("folder") or "").strip()
    for target_instance, target_field in sorted(target_fields):
        start_id = _node_id(target_instance, target_field)
        if not graph.has_node(start_id):
            graph.add_node(
                start_id,
                instance=target_instance,
                field=target_field,
                node_class=node_lookup.get(target_instance, "TARGET"),
            )

        queue: deque[List[str]] = deque([[start_id]])
        completed_paths: List[List[str]] = []
        while queue:
            node_path = queue.popleft()
            if len(node_path) > max_depth + 1:
                completed_paths.append(node_path)
                continue

            tail = node_path[-1]
            parents = sorted(graph.predecessors(tail))
            if not parents:
                completed_paths.append(node_path)
                continue

            expanded = False
            for parent in parents:
                if parent in node_path:
                    continue
                queue.append(node_path + [parent])
                expanded = True
            if not expanded:
                completed_paths.append(node_path)

        for node_path in completed_paths:
            hops: List[Dict[str, str]] = []
            mapping_name = mapping_by_target.get(target_instance, "")
            for idx, node_id in enumerate(node_path):
                attrs = graph.nodes.get(node_id, {})
                hops.append(
                    {
                        "instance": str(attrs.get("instance") or "").strip(),
                        "field": str(attrs.get("field") or "").strip(),
                        "node_class": str(attrs.get("node_class") or "TRANSFORMATION").strip() or "TRANSFORMATION",
                    }
                )
                if idx < len(node_path) - 1 and not mapping_name:
                    edge = graph.get_edge_data(node_path[idx + 1], node_path[idx]) or {}
                    mapping_name = str(edge.get("mapping") or "").strip()

            last_hop = hops[-1] if hops else {"instance": "", "field": "", "node_class": "TRANSFORMATION"}
            is_source = str(last_hop.get("node_class") or "").strip().upper() == "SOURCE"
            chains.append(
                {
                    "node_class": "LINEAGE",
                    "source_file": source_file,
                    "mapping": mapping_name,
                    "folder": folder,
                    "target_instance": target_instance,
                    "target_field": target_field,
                    "source_instance": str(last_hop.get("instance") or "").strip() if is_source else "",
                    "source_field": str(last_hop.get("field") or "").strip() if is_source else "",
                    "hop_count": max(0, len(hops) - 1),
                    "resolved": is_source,
                    "hops": hops,
                }
            )

    chains.sort(
        key=lambda row: (
            str(row.get("target_instance") or ""),
            str(row.get("target_field") or ""),
            0 if bool(row.get("resolved")) else 1,
            int(row.get("hop_count") or 0),
            " -> ".join(
                f"{str(h.get('instance') or '')}.{str(h.get('field') or '')}"
                for h in row.get("hops") or []
            ),
        )
    )

    resolved_chain_count = sum(1 for row in chains if row.get("resolved"))
    return {
        "chains": chains,
        "graph_meta": {
            "engine": "networkx",
            "graph_hash": graph_hash,
            "graph_node_count": int(graph.number_of_nodes()),
            "graph_edge_count": int(graph.number_of_edges()),
            "chain_count": len(chains),
            "resolved_chain_count": resolved_chain_count,
            "unresolved_chain_count": len(chains) - resolved_chain_count,
        },
    }


class LineageNetworkXEngine:
    """Graph-backed lineage and impact query helper.

    The graph is built from semantic lineage paths and supports:
    - workflow-scoped lineage/impact traversal
    - cross-workflow field identity discovery (same canonical field name)
    """

    def __init__(self, semantic_workflows: Dict[str, Dict[str, Any]]) -> None:
        """Initialize graph state and optional indices from semantic workflow models."""
        self._available = nx is not None
        self._semantic_workflows = semantic_workflows or {}

        self._graph = nx.DiGraph() if self._available else None
        self._workflow_graphs: Dict[str, Any] = {}
        self._workflow_to_source_file: Dict[str, str] = {}
        self._workflow_keys: Set[str] = set()

        self._field_nodes: Dict[str, Set[str]] = defaultdict(set)
        self._workflow_field_nodes: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))
        self._source_nodes_by_workflow: Dict[str, Set[str]] = defaultdict(set)

        self._path_index: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
        self._path_catalog: Dict[str, Dict[str, Any]] = {}

        if self._available:
            self._build()

    @staticmethod
    def _norm(value: Any) -> str:
        """Return a stripped string value for nullable inputs."""
        return str(value or "").strip()

    @classmethod
    def _norm_lower(cls, value: Any) -> str:
        """Normalize input text to a lowercase token for keying and matching."""
        return cls._norm(value).lower()

    @staticmethod
    def _path_sort_key(path: Dict[str, Any]) -> Tuple[int, int, str, str, str]:
        """Provide deterministic ordering for lineage paths in query responses."""
        return (
            0 if bool(path.get("resolved")) else 1,
            int(path.get("hop_count") or 0),
            str(path.get("workflow") or ""),
            str(path.get("target_instance") or ""),
            str(path.get("target_field") or ""),
        )

    @classmethod
    def _step_node_id(cls, workflow_key: str, instance: str, field: str, node_class: str) -> str:
        """Create a stable node id for one workflow-specific field occurrence."""
        return (
            f"step:{workflow_key}:"
            f"{cls._norm_lower(instance)}:{cls._norm_lower(field)}:{cls._norm_lower(node_class)}"
        )

    @classmethod
    def _canonical_field_node_id(cls, field: str) -> str:
        """Create the canonical cross-workflow identity node id for a field name."""
        return f"field::{cls._norm_lower(field)}"

    def _build(self) -> None:
        """Build graph nodes, edges, and path indexes from semantic lineage documents."""
        for workflow_key, model in self._semantic_workflows.items():
            wf = model.get("workflow") or {}
            source_file = self._norm(wf.get("source_file") or workflow_key)
            self._workflow_to_source_file[workflow_key] = source_file
            self._workflow_keys.add(workflow_key)

            for path in list(model.get("lineage_paths") or []):
                self._ingest_path(workflow_key=workflow_key, source_file=source_file, raw_path=path)

        # Keep query output stable and deterministic.
        for workflow_key in list(self._path_index.keys()):
            for field_norm in list(self._path_index[workflow_key].keys()):
                self._path_index[workflow_key][field_norm].sort(key=self._path_sort_key)

    def _ensure_workflow_graph(self, workflow_key: str) -> Any:
        """Return (or lazily create) the workflow-scoped directed graph."""
        g = self._workflow_graphs.get(workflow_key)
        if g is None:
            g = nx.DiGraph()
            self._workflow_graphs[workflow_key] = g
        return g

    def _ingest_path(self, *, workflow_key: str, source_file: str, raw_path: Dict[str, Any]) -> None:
        """Normalize and ingest one lineage path into graph structures and lookup indexes."""
        hops = list(raw_path.get("hops") or [])
        normalized_hops: List[Dict[str, Any]] = []
        for hop in hops:
            instance = self._norm(hop.get("instance"))
            field = self._norm(hop.get("field"))
            if not instance or not field:
                continue
            node_class = self._norm(hop.get("node_class")) or "TRANSFORMATION"
            normalized_hops.append(
                {"instance": instance, "field": field, "node_class": node_class}
            )

        if not normalized_hops:
            target_instance = self._norm(raw_path.get("target_instance"))
            target_field = self._norm(raw_path.get("target_field"))
            source_instance = self._norm(raw_path.get("source_instance"))
            source_field = self._norm(raw_path.get("source_field"))
            if target_instance and target_field:
                normalized_hops.append(
                    {
                        "instance": target_instance,
                        "field": target_field,
                        "node_class": "TARGET",
                    }
                )
            if source_instance and source_field:
                normalized_hops.append(
                    {
                        "instance": source_instance,
                        "field": source_field,
                        "node_class": "SOURCE",
                    }
                )

        if not normalized_hops:
            return

        workflow_graph = self._ensure_workflow_graph(workflow_key)
        node_ids: List[str] = []
        for hop in normalized_hops:
            step_id = self._step_node_id(
                workflow_key,
                hop["instance"],
                hop["field"],
                hop.get("node_class") or "TRANSFORMATION",
            )
            field_norm = self._norm_lower(hop["field"])

            node_attrs = {
                "node_type": "workflow_field",
                "workflow_key": workflow_key,
                "workflow": source_file,
                "instance": hop["instance"],
                "field": hop["field"],
                "field_norm": field_norm,
                "node_class": hop.get("node_class") or "TRANSFORMATION",
            }
            self._graph.add_node(step_id, **node_attrs)
            workflow_graph.add_node(step_id, **node_attrs)

            canonical_field_id = self._canonical_field_node_id(hop["field"])
            self._graph.add_node(
                canonical_field_id,
                node_type="field_identity",
                field=hop["field"],
                field_norm=field_norm,
            )
            self._graph.add_edge(step_id, canonical_field_id, edge_kind="field_identity")
            self._graph.add_edge(canonical_field_id, step_id, edge_kind="field_identity")

            self._field_nodes[field_norm].add(step_id)
            self._workflow_field_nodes[workflow_key][field_norm].add(step_id)
            if self._norm_lower(hop.get("node_class")) == "source":
                self._source_nodes_by_workflow[workflow_key].add(step_id)

            node_ids.append(step_id)

        mapping_name = self._norm(raw_path.get("mapping"))
        evidence_id = self._norm(raw_path.get("evidence_id"))
        path_id = self._norm(raw_path.get("path_id"))
        for idx in range(len(node_ids) - 1):
            src_id = node_ids[idx]
            dst_id = node_ids[idx + 1]
            edge_attrs = {
                "edge_kind": "lineage",
                "workflow_key": workflow_key,
                "workflow": source_file,
                "mapping": mapping_name,
                "evidence_id": evidence_id,
                "path_id": path_id,
            }
            self._graph.add_edge(src_id, dst_id, **edge_attrs)
            workflow_graph.add_edge(src_id, dst_id, **edge_attrs)

        target_hop = normalized_hops[0]
        source_hop = normalized_hops[-1]
        normalized_path = {
            "path_id": path_id or f"{workflow_key}|nx|{len(self._path_catalog) + 1}",
            "evidence_id": evidence_id
            or f"semantic:lineage:nx:{hashlib.md5('|'.join(node_ids).encode('utf-8')).hexdigest()[:16]}",
            "workflow": source_file,
            "workflow_key": workflow_key,
            "mapping": mapping_name,
            "target_instance": self._norm(raw_path.get("target_instance")) or target_hop["instance"],
            "target_field": self._norm(raw_path.get("target_field")) or target_hop["field"],
            "source_instance": self._norm(raw_path.get("source_instance")) or source_hop["instance"],
            "source_field": self._norm(raw_path.get("source_field")) or source_hop["field"],
            "hop_count": int(raw_path.get("hop_count") or max(0, len(normalized_hops) - 1)),
            "resolved": bool(raw_path.get("resolved", self._norm_lower(source_hop.get("node_class")) == "source")),
            "hops": normalized_hops,
        }

        unique_fields = {
            self._norm_lower(normalized_path.get("target_field")),
            self._norm_lower(normalized_path.get("source_field")),
            *[self._norm_lower(h.get("field")) for h in normalized_hops],
        }
        for field_norm in unique_fields:
            if not field_norm:
                continue
            self._path_index[workflow_key][field_norm].append(normalized_path)

        self._path_catalog[normalized_path["evidence_id"]] = normalized_path

    def _resolve_workflow_key(self, workflow_hint: str) -> Optional[str]:
        """Resolve user workflow hints to canonical workflow keys with extension tolerance."""
        hint = self._norm_lower(workflow_hint)
        if not hint:
            return None
        if hint in self._workflow_keys:
            return hint

        hint_no_ext = hint[:-4] if hint.endswith(".xml") else hint
        for key in self._workflow_keys:
            key_no_ext = key[:-4] if key.endswith(".xml") else key
            if key_no_ext == hint_no_ext:
                return key
        return None

    def _trace_paths_from_anchor_nodes(
        self,
        *,
        workflow_key: str,
        anchor_nodes: Set[str],
        max_paths: int,
        max_depth: int = 20,
    ) -> List[Dict[str, Any]]:
        """BFS-trace candidate lineage paths from anchor nodes toward source nodes."""
        graph = self._workflow_graphs.get(workflow_key)
        if graph is None or not anchor_nodes:
            return []

        out: List[Dict[str, Any]] = []
        seen: Set[Tuple[str, ...]] = set()
        source_file = self._workflow_to_source_file.get(workflow_key, workflow_key)

        for anchor in sorted(anchor_nodes):
            queue: deque[List[str]] = deque([[anchor]])
            while queue and len(out) < max_paths:
                node_path = queue.popleft()
                tail = node_path[-1]
                tail_attrs = graph.nodes.get(tail, {})
                if len(node_path) > 1 and self._norm_lower(tail_attrs.get("node_class")) == "source":
                    signature = tuple(node_path)
                    if signature not in seen:
                        seen.add(signature)
                        out.append(
                            self._render_path_from_nodes(
                                workflow_key=workflow_key,
                                workflow=source_file,
                                node_path=node_path,
                            )
                        )
                    continue

                if len(node_path) >= max_depth:
                    continue

                for nxt in graph.successors(tail):
                    if nxt in node_path:
                        continue
                    queue.append(node_path + [nxt])

        out.sort(key=self._path_sort_key)
        return out

    def _render_path_from_nodes(self, *, workflow_key: str, workflow: str, node_path: List[str]) -> Dict[str, Any]:
        """Render traversal node ids into API lineage-path shape with evidence metadata."""
        hops: List[Dict[str, Any]] = []
        mapping = ""
        for idx, node_id in enumerate(node_path):
            attrs = self._workflow_graphs[workflow_key].nodes.get(node_id, {})
            hops.append(
                {
                    "instance": self._norm(attrs.get("instance")),
                    "field": self._norm(attrs.get("field")),
                    "node_class": self._norm(attrs.get("node_class")) or "TRANSFORMATION",
                }
            )
            if idx < len(node_path) - 1:
                edge = self._workflow_graphs[workflow_key].get_edge_data(node_id, node_path[idx + 1]) or {}
                if not mapping:
                    mapping = self._norm(edge.get("mapping"))

        target = hops[0] if hops else {"instance": "", "field": ""}
        source = hops[-1] if hops else {"instance": "", "field": ""}
        key = "|".join(f"{h.get('instance')}.{h.get('field')}" for h in hops)
        evidence_id = "semantic:lineage:nx:" + hashlib.md5(key.encode("utf-8")).hexdigest()[:16]

        return {
            "path_id": f"{workflow_key}|nx|{evidence_id[-8:]}",
            "evidence_id": evidence_id,
            "workflow": workflow,
            "workflow_key": workflow_key,
            "mapping": mapping,
            "target_instance": self._norm(target.get("instance")),
            "target_field": self._norm(target.get("field")),
            "source_instance": self._norm(source.get("instance")),
            "source_field": self._norm(source.get("field")),
            "hop_count": max(0, len(hops) - 1),
            "resolved": self._norm_lower(source.get("node_class")) == "source",
            "hops": hops,
        }

    @staticmethod
    def _dedupe_paths(paths: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Drop duplicate lineage-path records while preserving original order."""
        out: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        for path in paths:
            token = str(path.get("evidence_id") or "")
            if not token:
                token = "|".join(
                    [
                        str(path.get("workflow") or ""),
                        str(path.get("target_instance") or ""),
                        str(path.get("target_field") or ""),
                        str(path.get("source_instance") or ""),
                        str(path.get("source_field") or ""),
                        str(path.get("hop_count") or 0),
                    ]
                )
            if token in seen:
                continue
            seen.add(token)
            out.append(path)
        return out

    def query_lineage(
        self,
        *,
        workflow_hint: str,
        field_name: str,
        limit: int = 20,
        allow_cross_workflow: bool = False,
    ) -> Dict[str, Any]:
        """Return lineage paths for a field in one workflow or across workflows."""
        if not self._available or self._graph is None:
            return {
                "status": "graph_unavailable",
                "workflow_hint": workflow_hint,
                "field": field_name,
                "paths": [],
            }

        field_token = self._norm(field_name)
        field_norm = self._norm_lower(field_token)
        cap = max(1, int(limit))

        if workflow_hint:
            workflow_key = self._resolve_workflow_key(workflow_hint)
            if not workflow_key:
                return {
                    "status": "workflow_not_indexed",
                    "workflow_hint": workflow_hint,
                    "field": field_token,
                    "paths": [],
                }

            indexed_paths = list(self._path_index.get(workflow_key, {}).get(field_norm, []))
            anchor_nodes = set(self._workflow_field_nodes.get(workflow_key, {}).get(field_norm, set()))
            traced_paths: List[Dict[str, Any]] = []
            if not indexed_paths:
                traced_paths = self._trace_paths_from_anchor_nodes(
                    workflow_key=workflow_key,
                    anchor_nodes=anchor_nodes,
                    max_paths=max(cap, 12),
                )

            merged_paths = self._dedupe_paths(indexed_paths + traced_paths)
            if not indexed_paths:
                merged_paths.sort(key=self._path_sort_key)
            if not merged_paths:
                return {
                    "status": "field_not_found",
                    "workflow": self._workflow_to_source_file.get(workflow_key, workflow_hint),
                    "field": field_token,
                    "paths": [],
                    "graph": {
                        "engine": "networkx",
                        "anchor_count": len(anchor_nodes),
                        "workflow_node_count": self._workflow_graphs.get(workflow_key).number_of_nodes()
                        if self._workflow_graphs.get(workflow_key)
                        else 0,
                    },
                }

            limited = merged_paths[:cap]
            resolved_count = sum(1 for p in limited if p.get("resolved"))
            return {
                "status": "ok",
                "workflow": self._workflow_to_source_file.get(workflow_key, workflow_hint),
                "field": field_token,
                "total_path_count": len(merged_paths),
                "resolved_path_count": resolved_count,
                "unresolved_path_count": max(0, len(limited) - resolved_count),
                "paths": limited,
                "graph": {
                    "engine": "networkx",
                    "anchor_count": len(anchor_nodes),
                    "workflow_node_count": self._workflow_graphs.get(workflow_key).number_of_nodes()
                    if self._workflow_graphs.get(workflow_key)
                    else 0,
                },
            }

        if not allow_cross_workflow:
            return {
                "status": "workflow_not_indexed",
                "workflow_hint": workflow_hint,
                "field": field_token,
                "paths": [],
            }

        identity_node = self._canonical_field_node_id(field_token)
        if not self._graph.has_node(identity_node):
            return {
                "status": "field_not_found",
                "workflow": "*",
                "field": field_token,
                "paths": [],
                "cross_workflow": True,
                "workflows": [],
                "workflow_count": 0,
            }

        occurrence_nodes = [
            n for n in self._graph.successors(identity_node) if str(n).startswith("step:")
        ]
        workflow_keys = sorted(
            {
                str(self._graph.nodes.get(n, {}).get("workflow_key") or "")
                for n in occurrence_nodes
                if str(self._graph.nodes.get(n, {}).get("workflow_key") or "")
            }
        )

        merged: List[Dict[str, Any]] = []
        for workflow_key in workflow_keys:
            merged.extend(self._path_index.get(workflow_key, {}).get(field_norm, []))

        merged = self._dedupe_paths(merged)
        merged.sort(key=self._path_sort_key)
        if not merged:
            return {
                "status": "field_not_found",
                "workflow": "*",
                "field": field_token,
                "paths": [],
                "cross_workflow": True,
                "workflows": [self._workflow_to_source_file.get(k, k) for k in workflow_keys],
                "workflow_count": len(workflow_keys),
            }

        limited = merged[:cap]
        resolved_count = sum(1 for p in limited if p.get("resolved"))
        return {
            "status": "ok",
            "workflow": "*",
            "field": field_token,
            "cross_workflow": True,
            "workflow_count": len(workflow_keys),
            "workflows": [self._workflow_to_source_file.get(k, k) for k in workflow_keys],
            "total_path_count": len(merged),
            "resolved_path_count": resolved_count,
            "unresolved_path_count": max(0, len(limited) - resolved_count),
            "paths": limited,
            "graph": {
                "engine": "networkx",
                "identity_node": identity_node,
                "occurrence_count": len(occurrence_nodes),
            },
        }

    def query_impact(
        self,
        *,
        workflow_hint: str,
        field_name: str,
        limit: int = 25,
        allow_cross_workflow: bool = False,
    ) -> Dict[str, Any]:
        """Return impacted targets and mappings for the requested lineage field."""
        lineage = self.query_lineage(
            workflow_hint=workflow_hint,
            field_name=field_name,
            limit=limit,
            allow_cross_workflow=allow_cross_workflow,
        )
        if lineage.get("status") != "ok":
            lineage["impacted_targets"] = []
            lineage["impacted_target_count"] = 0
            lineage.setdefault("impacted_mappings", [])
            return lineage

        paths = list(lineage.get("paths") or [])
        impacted_targets_set = {
            f"{self._norm(p.get('target_instance'))}.{self._norm(p.get('target_field'))}"
            for p in paths
            if self._norm(p.get("target_instance")) and self._norm(p.get("target_field"))
        }
        impacted_mappings = sorted(
            {
                self._norm(p.get("mapping"))
                for p in paths
                if self._norm(p.get("mapping"))
            }
        )

        lineage["impacted_target_count"] = len(impacted_targets_set)
        lineage["impacted_targets"] = sorted(impacted_targets_set)
        lineage["impacted_mappings"] = impacted_mappings
        return lineage

    def stats(self) -> Dict[str, Any]:
        """Return availability and high-level graph cardinality statistics."""
        if not self._available or self._graph is None:
            return {
                "available": False,
                "engine": "networkx",
                "reason": "networkx_not_installed",
            }
        return {
            "available": True,
            "engine": "networkx",
            "workflow_count": len(self._workflow_keys),
            "node_count": int(self._graph.number_of_nodes()),
            "edge_count": int(self._graph.number_of_edges()),
            "field_identity_count": len(self._field_nodes),
        }