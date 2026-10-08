"""PostgreSQL-backed semantic layer store for deterministic lineage/impact queries."""

from __future__ import annotations

from collections import defaultdict
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PgSemanticStore:
    """Persist and query semantic workflow entities in PostgreSQL.

    This store keeps deterministic lineage/impact truth as relational tables,
    while vector chunks remain in pgvector tables.
    """

    def __init__(self, dsn: str, schema: str = "rag") -> None:
        """Create a PostgreSQL semantic store session and ensure required schema objects."""
        import psycopg

        self.schema = schema
        self._dsn = dsn
        self._psycopg = psycopg
        self._conn = psycopg.connect(dsn, autocommit=True)
        self._ensure_schema()

    def _reconnect(self) -> None:
        """Re-establish the psycopg connection using the configured DSN."""
        self._conn = self._psycopg.connect(self._dsn, autocommit=True)

    def _ensure_connection(self) -> None:
        """Ensure an open database connection before executing SQL."""
        if getattr(self, "_conn", None) is None:
            self._reconnect()
            return
        if self._conn.closed:
            self._reconnect()

    def _execute(self, sql: str, params: Any = None):
        """Execute SQL with one reconnect retry on transient closed-connection errors."""
        for attempt in range(2):
            self._ensure_connection()
            try:
                if params is None:
                    return self._conn.execute(sql)
                return self._conn.execute(sql, params)
            except self._psycopg.OperationalError as exc:
                if attempt == 0 and (self._conn.closed or "connection is closed" in str(exc).lower()):
                    logger.warning("PgSemanticStore connection closed; reconnecting and retrying query")
                    self._reconnect()
                    continue
                raise
        raise RuntimeError("Unexpected execute retry flow")

    def _ensure_schema(self) -> None:
        """Create semantic layer tables and indexes when they do not already exist."""
        self._execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")

        self._execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.schema}.semantic_workflows (
                workflow_key text PRIMARY KEY,
                source_file  text NOT NULL,
                repository   text,
                folder       text,
                graph_hash   text,
                updated_at   timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        self._execute(
            f"ALTER TABLE {self.schema}.semantic_workflows ADD COLUMN IF NOT EXISTS graph_hash text"
        )
        self._execute(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {self.schema}_semantic_workflows_source_file_uq
            ON {self.schema}.semantic_workflows (lower(source_file))
            """
        )

        self._execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.schema}.semantic_mappings (
                workflow_key text NOT NULL REFERENCES {self.schema}.semantic_workflows(workflow_key) ON DELETE CASCADE,
                mapping_id   text NOT NULL,
                name         text NOT NULL,
                PRIMARY KEY (workflow_key, mapping_id)
            )
            """
        )
        self._execute(
            f"""
            CREATE INDEX IF NOT EXISTS {self.schema}_semantic_mappings_name_idx
            ON {self.schema}.semantic_mappings (workflow_key, lower(name))
            """
        )

        self._execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.schema}.semantic_nodes (
                workflow_key text NOT NULL REFERENCES {self.schema}.semantic_workflows(workflow_key) ON DELETE CASCADE,
                node_id      text NOT NULL,
                mapping_name text,
                node_class   text,
                name         text,
                type         text,
                owner        text,
                PRIMARY KEY (workflow_key, node_id)
            )
            """
        )
        self._execute(
            f"""
            CREATE INDEX IF NOT EXISTS {self.schema}_semantic_nodes_lookup_idx
            ON {self.schema}.semantic_nodes (workflow_key, node_class, lower(name))
            """
        )

        self._execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.schema}.semantic_ports (
                workflow_key text NOT NULL REFERENCES {self.schema}.semantic_workflows(workflow_key) ON DELETE CASCADE,
                port_id      text NOT NULL,
                mapping_name text,
                node_class   text,
                node_name    text,
                name         text,
                datatype     text,
                role         text,
                expression   text,
                PRIMARY KEY (workflow_key, port_id)
            )
            """
        )
        self._execute(
            f"""
            CREATE INDEX IF NOT EXISTS {self.schema}_semantic_ports_lookup_idx
            ON {self.schema}.semantic_ports (workflow_key, lower(name), lower(node_name))
            """
        )

        self._execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.schema}.semantic_connectors (
                workflow_key text NOT NULL REFERENCES {self.schema}.semantic_workflows(workflow_key) ON DELETE CASCADE,
                edge_id      text NOT NULL,
                mapping_name text,
                from_node    text,
                from_port    text,
                to_node      text,
                to_port      text,
                PRIMARY KEY (workflow_key, edge_id)
            )
            """
        )
        self._execute(
            f"""
            CREATE INDEX IF NOT EXISTS {self.schema}_semantic_connectors_from_idx
            ON {self.schema}.semantic_connectors (workflow_key, lower(from_node), lower(from_port))
            """
        )
        self._execute(
            f"""
            CREATE INDEX IF NOT EXISTS {self.schema}_semantic_connectors_to_idx
            ON {self.schema}.semantic_connectors (workflow_key, lower(to_node), lower(to_port))
            """
        )

        self._execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.schema}.semantic_lineage_paths (
                workflow_key    text NOT NULL REFERENCES {self.schema}.semantic_workflows(workflow_key) ON DELETE CASCADE,
                path_id         text NOT NULL,
                evidence_id     text NOT NULL,
                mapping_name    text,
                target_instance text,
                target_field    text,
                source_instance text,
                source_field    text,
                hop_count       integer,
                resolved        boolean,
                PRIMARY KEY (workflow_key, path_id)
            )
            """
        )
        self._execute(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {self.schema}_semantic_lineage_evidence_uq
            ON {self.schema}.semantic_lineage_paths (workflow_key, evidence_id)
            """
        )
        self._execute(
            f"""
            CREATE INDEX IF NOT EXISTS {self.schema}_semantic_lineage_target_field_idx
            ON {self.schema}.semantic_lineage_paths (workflow_key, lower(target_field))
            """
        )
        self._execute(
            f"""
            CREATE INDEX IF NOT EXISTS {self.schema}_semantic_lineage_source_field_idx
            ON {self.schema}.semantic_lineage_paths (workflow_key, lower(source_field))
            """
        )

        self._execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.schema}.semantic_lineage_hops (
                workflow_key text NOT NULL,
                path_id      text NOT NULL,
                hop_index    integer NOT NULL,
                instance     text,
                field        text,
                field_norm   text,
                node_class   text,
                PRIMARY KEY (workflow_key, path_id, hop_index),
                FOREIGN KEY (workflow_key, path_id)
                    REFERENCES {self.schema}.semantic_lineage_paths(workflow_key, path_id)
                    ON DELETE CASCADE
            )
            """
        )
        self._execute(
            f"""
            CREATE INDEX IF NOT EXISTS {self.schema}_semantic_lineage_hops_field_idx
            ON {self.schema}.semantic_lineage_hops (workflow_key, field_norm)
            """
        )

    @staticmethod
    def _norm(value: Any) -> str:
        """Return a stripped string value for nullable database fields."""
        return str(value or "").strip()

    @staticmethod
    def _dedupe_rows(rows: List[tuple[Any, ...]], key_indexes: tuple[int, ...]) -> List[tuple[Any, ...]]:
        """Keep the first row for each logical primary-key tuple."""
        if not rows:
            return rows

        seen: set[tuple[Any, ...]] = set()
        unique: List[tuple[Any, ...]] = []
        for row in rows:
            key = tuple(row[idx] for idx in key_indexes)
            if key in seen:
                continue
            seen.add(key)
            unique.append(row)
        return unique

    def _resolve_workflow(self, workflow_hint: str) -> Optional[Dict[str, str]]:
        """Resolve workflow hints to canonical workflow key and source file."""
        hint = self._norm(workflow_hint).lower()
        if not hint:
            return None

        row = self._execute(
            f"""
            SELECT workflow_key, source_file
            FROM {self.schema}.semantic_workflows
            WHERE workflow_key = %s
               OR regexp_replace(workflow_key, '\\.(xml)$', '', 'i') = regexp_replace(%s, '\\.(xml)$', '', 'i')
            ORDER BY CASE WHEN workflow_key = %s THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (hint, hint, hint),
        ).fetchone()
        if not row:
            return None
        return {"workflow_key": str(row[0]), "source_file": str(row[1])}

    def upsert_workflow_model(self, model: Dict[str, Any]) -> None:
        """Atomically replace one workflow's semantic entities and lineage paths."""
        workflow = model.get("workflow") or {}
        source_file = self._norm(workflow.get("source_file"))
        if not source_file:
            raise ValueError("semantic workflow model is missing workflow.source_file")

        workflow_key = source_file.lower()
        repository = self._norm(workflow.get("repository"))
        folder = self._norm(workflow.get("folder"))
        graph_hash = self._norm(workflow.get("graph_hash"))

        mappings = list(model.get("mappings") or [])
        nodes = list(model.get("nodes") or [])
        ports = list(model.get("ports") or [])
        connectors = list(model.get("connectors") or [])
        lineage_paths = list(model.get("lineage_paths") or [])

        with self._conn.transaction():
            self._execute(
                f"""
                INSERT INTO {self.schema}.semantic_workflows (workflow_key, source_file, repository, folder, graph_hash, updated_at)
                VALUES (%s, %s, %s, %s, %s, now())
                ON CONFLICT (workflow_key) DO UPDATE SET
                    source_file = EXCLUDED.source_file,
                    repository = EXCLUDED.repository,
                    folder = EXCLUDED.folder,
                    graph_hash = EXCLUDED.graph_hash,
                    updated_at = now()
                """,
                (workflow_key, source_file, repository, folder, graph_hash),
            )

            # Replace this workflow atomically to avoid stale connectors/paths.
            self._execute(f"DELETE FROM {self.schema}.semantic_ports WHERE workflow_key = %s", (workflow_key,))
            self._execute(f"DELETE FROM {self.schema}.semantic_connectors WHERE workflow_key = %s", (workflow_key,))
            self._execute(f"DELETE FROM {self.schema}.semantic_nodes WHERE workflow_key = %s", (workflow_key,))
            self._execute(f"DELETE FROM {self.schema}.semantic_mappings WHERE workflow_key = %s", (workflow_key,))
            self._execute(f"DELETE FROM {self.schema}.semantic_lineage_paths WHERE workflow_key = %s", (workflow_key,))

            if mappings:
                rows = [
                    (workflow_key, self._norm(r.get("mapping_id")), self._norm(r.get("name")))
                    for r in mappings
                ]
                rows = self._dedupe_rows(rows, (0, 1))
                with self._conn.cursor() as cur:
                    cur.executemany(
                        f"""
                        INSERT INTO {self.schema}.semantic_mappings (workflow_key, mapping_id, name)
                        VALUES (%s, %s, %s)
                        """,
                        rows,
                    )

            if nodes:
                rows = [
                    (
                        workflow_key,
                        self._norm(r.get("node_id")),
                        self._norm(r.get("mapping")),
                        self._norm(r.get("node_class")),
                        self._norm(r.get("name")),
                        self._norm(r.get("type")),
                        self._norm(r.get("owner")),
                    )
                    for r in nodes
                ]
                rows = self._dedupe_rows(rows, (0, 1))
                with self._conn.cursor() as cur:
                    cur.executemany(
                        f"""
                        INSERT INTO {self.schema}.semantic_nodes
                            (workflow_key, node_id, mapping_name, node_class, name, type, owner)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        rows,
                    )

            if ports:
                rows = [
                    (
                        workflow_key,
                        self._norm(r.get("port_id")),
                        self._norm(r.get("mapping")),
                        self._norm(r.get("node_class")),
                        self._norm(r.get("node")),
                        self._norm(r.get("name")),
                        self._norm(r.get("datatype")),
                        self._norm(r.get("role")),
                        self._norm(r.get("expression")),
                    )
                    for r in ports
                ]
                rows = self._dedupe_rows(rows, (0, 1))
                with self._conn.cursor() as cur:
                    cur.executemany(
                        f"""
                        INSERT INTO {self.schema}.semantic_ports
                            (workflow_key, port_id, mapping_name, node_class, node_name, name, datatype, role, expression)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        rows,
                    )

            if connectors:
                rows = [
                    (
                        workflow_key,
                        self._norm(r.get("edge_id")),
                        self._norm(r.get("mapping")),
                        self._norm(r.get("from_node")),
                        self._norm(r.get("from_port")),
                        self._norm(r.get("to_node")),
                        self._norm(r.get("to_port")),
                    )
                    for r in connectors
                ]
                rows = self._dedupe_rows(rows, (0, 1))
                with self._conn.cursor() as cur:
                    cur.executemany(
                        f"""
                        INSERT INTO {self.schema}.semantic_connectors
                            (workflow_key, edge_id, mapping_name, from_node, from_port, to_node, to_port)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        rows,
                    )

            if lineage_paths:
                path_rows = [
                    (
                        workflow_key,
                        self._norm(p.get("path_id")),
                        self._norm(p.get("evidence_id")),
                        self._norm(p.get("mapping")),
                        self._norm(p.get("target_instance")),
                        self._norm(p.get("target_field")),
                        self._norm(p.get("source_instance")),
                        self._norm(p.get("source_field")),
                        int(p.get("hop_count") or 0),
                        bool(p.get("resolved")),
                    )
                    for p in lineage_paths
                ]
                path_rows = self._dedupe_rows(path_rows, (0, 1))
                with self._conn.cursor() as cur:
                    cur.executemany(
                        f"""
                        INSERT INTO {self.schema}.semantic_lineage_paths
                            (workflow_key, path_id, evidence_id, mapping_name, target_instance, target_field,
                             source_instance, source_field, hop_count, resolved)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        path_rows,
                    )

                hop_rows: List[tuple[Any, ...]] = []
                for p in lineage_paths:
                    path_id = self._norm(p.get("path_id"))
                    for idx, hop in enumerate(list(p.get("hops") or [])):
                        field = self._norm(hop.get("field"))
                        hop_rows.append(
                            (
                                workflow_key,
                                path_id,
                                idx,
                                self._norm(hop.get("instance")),
                                field,
                                field.lower(),
                                self._norm(hop.get("node_class")),
                            )
                        )
                if hop_rows:
                    hop_rows = self._dedupe_rows(hop_rows, (0, 1, 2))
                    with self._conn.cursor() as cur:
                        cur.executemany(
                            f"""
                            INSERT INTO {self.schema}.semantic_lineage_hops
                                (workflow_key, path_id, hop_index, instance, field, field_norm, node_class)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            """,
                            hop_rows,
                        )

    def semantic_layer_snapshot(self, *, max_workflows: Optional[int] = None) -> Dict[str, Any]:
        """Return per-workflow semantic entity counts for diagnostics and health checks."""
        limit = int(max_workflows) if max_workflows is not None else 200

        rows = self._execute(
            f"""
            SELECT
                w.source_file,
                w.repository,
                w.folder,
                w.graph_hash,
                COALESCE(m.mapping_count, 0) AS mapping_count,
                COALESCE(n.node_count, 0) AS node_count,
                COALESCE(p.port_count, 0) AS port_count,
                COALESCE(c.connector_count, 0) AS connector_count,
                COALESCE(lp.lineage_path_count, 0) AS lineage_path_count
            FROM {self.schema}.semantic_workflows w
            LEFT JOIN (
                SELECT workflow_key, COUNT(*)::int AS mapping_count
                FROM {self.schema}.semantic_mappings
                GROUP BY workflow_key
            ) m ON m.workflow_key = w.workflow_key
            LEFT JOIN (
                SELECT workflow_key, COUNT(*)::int AS node_count
                FROM {self.schema}.semantic_nodes
                GROUP BY workflow_key
            ) n ON n.workflow_key = w.workflow_key
            LEFT JOIN (
                SELECT workflow_key, COUNT(*)::int AS port_count
                FROM {self.schema}.semantic_ports
                GROUP BY workflow_key
            ) p ON p.workflow_key = w.workflow_key
            LEFT JOIN (
                SELECT workflow_key, COUNT(*)::int AS connector_count
                FROM {self.schema}.semantic_connectors
                GROUP BY workflow_key
            ) c ON c.workflow_key = w.workflow_key
            LEFT JOIN (
                SELECT workflow_key, COUNT(*)::int AS lineage_path_count
                FROM {self.schema}.semantic_lineage_paths
                GROUP BY workflow_key
            ) lp ON lp.workflow_key = w.workflow_key
            ORDER BY lower(w.source_file)
            LIMIT %s
            """,
            (max(1, limit),),
        ).fetchall()

        workflow_count_row = self._execute(
            f"SELECT COUNT(*)::int FROM {self.schema}.semantic_workflows"
        ).fetchone()
        workflow_count = int(workflow_count_row[0] or 0) if workflow_count_row else 0

        workflows = [
            {
                "source_file": str(r[0] or ""),
                "repository": str(r[1] or ""),
                "folder": str(r[2] or ""),
                "graph_hash": str(r[3] or ""),
                "mapping_count": int(r[4] or 0),
                "node_count": int(r[5] or 0),
                "port_count": int(r[6] or 0),
                "connector_count": int(r[7] or 0),
                "lineage_path_count": int(r[8] or 0),
            }
            for r in rows
        ]

        return {
            "available": workflow_count > 0,
            "workflow_count": workflow_count,
            "workflows": workflows,
        }

    def load_workflow_lineage_models(self, *, max_workflows: Optional[int] = None) -> Dict[str, Dict[str, Any]]:
        """Load workflow + lineage-path models for graph hydration.

        This is used when the API is attached via /connect and semantic entities
        live in PostgreSQL while in-memory workflow models are empty.
        """
        limit = int(max_workflows) if max_workflows is not None else 500

        wf_rows = self._execute(
            f"""
            SELECT workflow_key, source_file, repository, folder, graph_hash
            FROM {self.schema}.semantic_workflows
            ORDER BY lower(source_file)
            LIMIT %s
            """,
            (max(1, limit),),
        ).fetchall()

        if not wf_rows:
            return {}

        workflow_meta: Dict[str, Dict[str, Any]] = {}
        workflow_keys: List[str] = []
        for row in wf_rows:
            workflow_key = str(row[0] or "")
            if not workflow_key:
                continue
            workflow_keys.append(workflow_key)
            workflow_meta[workflow_key] = {
                "workflow": {
                    "workflow_id": str(row[1] or workflow_key),
                    "source_file": str(row[1] or workflow_key),
                    "repository": str(row[2] or ""),
                    "folder": str(row[3] or ""),
                    "graph_hash": str(row[4] or ""),
                },
                "mappings": [],
                "nodes": [],
                "ports": [],
                "connectors": [],
                "lineage_paths": [],
            }

        if not workflow_keys:
            return {}

        path_rows = self._execute(
            f"""
            SELECT
                p.workflow_key,
                p.path_id,
                p.evidence_id,
                p.mapping_name,
                p.target_instance,
                p.target_field,
                p.source_instance,
                p.source_field,
                p.hop_count,
                p.resolved,
                COALESCE(
                    (
                        SELECT jsonb_agg(
                            jsonb_build_object(
                                'instance', h.instance,
                                'field', h.field,
                                'node_class', h.node_class
                            )
                            ORDER BY h.hop_index
                        )
                        FROM {self.schema}.semantic_lineage_hops h
                        WHERE h.workflow_key = p.workflow_key
                          AND h.path_id = p.path_id
                    ),
                    '[]'::jsonb
                ) AS hops
            FROM {self.schema}.semantic_lineage_paths p
            WHERE p.workflow_key = ANY(%s)
            ORDER BY p.workflow_key, p.path_id
            """,
            (workflow_keys,),
        ).fetchall()

        mapping_names: Dict[str, set[str]] = defaultdict(set)
        for row in path_rows:
            workflow_key = str(row[0] or "")
            if workflow_key not in workflow_meta:
                continue

            hops = row[10] if row[10] is not None else []
            if isinstance(hops, str):
                try:
                    hops = json.loads(hops)
                except Exception:
                    hops = []

            mapping_name = str(row[3] or "")
            if mapping_name:
                mapping_names[workflow_key].add(mapping_name)

            workflow_meta[workflow_key]["lineage_paths"].append(
                {
                    "path_id": str(row[1] or ""),
                    "evidence_id": str(row[2] or ""),
                    "workflow": workflow_meta[workflow_key]["workflow"]["source_file"],
                    "mapping": mapping_name,
                    "target_instance": str(row[4] or ""),
                    "target_field": str(row[5] or ""),
                    "source_instance": str(row[6] or ""),
                    "source_field": str(row[7] or ""),
                    "hop_count": int(row[8] or 0),
                    "resolved": bool(row[9]),
                    "hops": list(hops or []),
                }
            )

        for workflow_key, names in mapping_names.items():
            workflow_meta[workflow_key]["mappings"] = [
                {
                    "mapping_id": f"{workflow_meta[workflow_key]['workflow']['source_file']}|{name}",
                    "workflow": workflow_meta[workflow_key]["workflow"]["source_file"],
                    "name": name,
                }
                for name in sorted(names)
            ]

        return workflow_meta

    def _query_lineage_rows(self, *, workflow_key: str, field_token: str, limit: int) -> List[Dict[str, Any]]:
        """Fetch lineage path rows plus ordered hop payloads for one workflow field token."""
        rows = self._execute(
            f"""
            SELECT
                p.path_id,
                p.evidence_id,
                p.mapping_name,
                p.target_instance,
                p.target_field,
                p.source_instance,
                p.source_field,
                p.hop_count,
                p.resolved,
                COALESCE(
                    (
                        SELECT jsonb_agg(
                            jsonb_build_object(
                                'instance', h.instance,
                                'field', h.field,
                                'node_class', h.node_class
                            )
                            ORDER BY h.hop_index
                        )
                        FROM {self.schema}.semantic_lineage_hops h
                        WHERE h.workflow_key = p.workflow_key
                          AND h.path_id = p.path_id
                    ),
                    '[]'::jsonb
                ) AS hops
            FROM {self.schema}.semantic_lineage_paths p
            WHERE p.workflow_key = %s
              AND (
                    lower(p.target_field) = %s
                    OR lower(p.source_field) = %s
                    OR EXISTS (
                        SELECT 1
                        FROM {self.schema}.semantic_lineage_hops h2
                        WHERE h2.workflow_key = p.workflow_key
                          AND h2.path_id = p.path_id
                          AND h2.field_norm = %s
                    )
              )
            ORDER BY p.resolved DESC, p.hop_count ASC, lower(p.target_instance), lower(p.target_field)
            LIMIT %s
            """,
            (workflow_key, field_token, field_token, field_token, max(1, int(limit))),
        ).fetchall()

        out: List[Dict[str, Any]] = []
        for r in rows:
            hops = r[9] if r[9] is not None else []
            if isinstance(hops, str):
                try:
                    hops = json.loads(hops)
                except Exception:
                    hops = []
            out.append(
                {
                    "path_id": str(r[0] or ""),
                    "evidence_id": str(r[1] or ""),
                    "mapping": str(r[2] or ""),
                    "target_instance": str(r[3] or ""),
                    "target_field": str(r[4] or ""),
                    "source_instance": str(r[5] or ""),
                    "source_field": str(r[6] or ""),
                    "hop_count": int(r[7] or 0),
                    "resolved": bool(r[8]),
                    "hops": list(hops or []),
                }
            )
        return out

    def query_semantic_lineage(self, *, workflow_hint: str, field_name: str, limit: int = 20) -> Dict[str, Any]:
        """Return deterministic lineage matches for a field within a resolved workflow."""
        resolved = self._resolve_workflow(workflow_hint)
        if not resolved:
            return {
                "status": "workflow_not_indexed",
                "workflow_hint": workflow_hint,
                "field": field_name,
                "paths": [],
            }

        workflow_key = resolved["workflow_key"]
        source_file = resolved["source_file"]
        field_token = self._norm(field_name).lower()

        count_row = self._execute(
            f"""
            SELECT COUNT(*)::int
            FROM {self.schema}.semantic_lineage_paths p
            WHERE p.workflow_key = %s
              AND (
                    lower(p.target_field) = %s
                    OR lower(p.source_field) = %s
                    OR EXISTS (
                        SELECT 1
                        FROM {self.schema}.semantic_lineage_hops h2
                        WHERE h2.workflow_key = p.workflow_key
                          AND h2.path_id = p.path_id
                          AND h2.field_norm = %s
                    )
              )
            """,
            (workflow_key, field_token, field_token, field_token),
        ).fetchone()
        total_matches = int(count_row[0] or 0) if count_row else 0
        if total_matches == 0:
            return {
                "status": "field_not_found",
                "workflow": source_file,
                "field": self._norm(field_name),
                "paths": [],
            }

        paths = self._query_lineage_rows(workflow_key=workflow_key, field_token=field_token, limit=limit)
        resolved_count = sum(1 for p in paths if p.get("resolved"))

        return {
            "status": "ok",
            "workflow": source_file,
            "field": self._norm(field_name),
            "total_path_count": total_matches,
            "resolved_path_count": resolved_count,
            "unresolved_path_count": max(0, len(paths) - resolved_count),
            "paths": paths,
        }

    def query_semantic_impact(self, *, workflow_hint: str, field_name: str, limit: int = 25) -> Dict[str, Any]:
        """Return impacted targets, mappings, and supporting lineage paths for a field."""
        resolved = self._resolve_workflow(workflow_hint)
        if not resolved:
            return {
                "status": "workflow_not_indexed",
                "workflow_hint": workflow_hint,
                "field": field_name,
                "paths": [],
                "impacted_targets": [],
            }

        workflow_key = resolved["workflow_key"]
        source_file = resolved["source_file"]
        field_token = self._norm(field_name).lower()

        count_row = self._execute(
            f"""
            SELECT COUNT(*)::int
            FROM {self.schema}.semantic_lineage_paths p
            WHERE p.workflow_key = %s
              AND (
                    lower(p.target_field) = %s
                    OR lower(p.source_field) = %s
                    OR EXISTS (
                        SELECT 1
                        FROM {self.schema}.semantic_lineage_hops h2
                        WHERE h2.workflow_key = p.workflow_key
                          AND h2.path_id = p.path_id
                          AND h2.field_norm = %s
                    )
              )
            """,
            (workflow_key, field_token, field_token, field_token),
        ).fetchone()
        total_matches = int(count_row[0] or 0) if count_row else 0
        if total_matches == 0:
            return {
                "status": "field_not_found",
                "workflow": source_file,
                "field": self._norm(field_name),
                "paths": [],
                "impacted_targets": [],
            }

        impacted_target_rows = self._execute(
            f"""
            SELECT DISTINCT p.target_instance, p.target_field
            FROM {self.schema}.semantic_lineage_paths p
            WHERE p.workflow_key = %s
              AND (
                    lower(p.target_field) = %s
                    OR lower(p.source_field) = %s
                    OR EXISTS (
                        SELECT 1
                        FROM {self.schema}.semantic_lineage_hops h2
                        WHERE h2.workflow_key = p.workflow_key
                          AND h2.path_id = p.path_id
                          AND h2.field_norm = %s
                    )
              )
                        ORDER BY p.target_instance, p.target_field
            """,
            (workflow_key, field_token, field_token, field_token),
        ).fetchall()
        impacted_targets = [
            f"{self._norm(r[0])}.{self._norm(r[1])}"
            for r in impacted_target_rows
            if self._norm(r[0]) and self._norm(r[1])
        ]

        impacted_mapping_rows = self._execute(
            f"""
            SELECT DISTINCT p.mapping_name
            FROM {self.schema}.semantic_lineage_paths p
            WHERE p.workflow_key = %s
              AND (
                    lower(p.target_field) = %s
                    OR lower(p.source_field) = %s
                    OR EXISTS (
                        SELECT 1
                        FROM {self.schema}.semantic_lineage_hops h2
                        WHERE h2.workflow_key = p.workflow_key
                          AND h2.path_id = p.path_id
                          AND h2.field_norm = %s
                    )
              )
              AND COALESCE(p.mapping_name, '') <> ''
                ORDER BY p.mapping_name
            """,
            (workflow_key, field_token, field_token, field_token),
        ).fetchall()
        impacted_mappings = [self._norm(r[0]) for r in impacted_mapping_rows if self._norm(r[0])]

        paths = self._query_lineage_rows(workflow_key=workflow_key, field_token=field_token, limit=limit)

        return {
            "status": "ok",
            "workflow": source_file,
            "field": self._norm(field_name),
            "total_path_count": total_matches,
            "impacted_target_count": len(impacted_targets),
            "impacted_targets": impacted_targets,
            "impacted_mappings": impacted_mappings,
            "paths": paths,
        }
