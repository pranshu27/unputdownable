"""Structure-aware chunker for Informatica PowerCenter nodes.

Strategy
--------
One canonical node = one chunk (structure-aware boundary). For nodes that exceed
the token budget, a secondary line-aware split with ~100-token overlap is applied
so no embedding call sees a window that blurs too many ideas together.

Token budget
------------
The tracker spec is 500-800 tokens. We use a default max of 700 with a 100-token
overlap on splits — sitting in the middle of the range while keeping individual
chunks semantically coherent.

Metadata enrichment
-------------------
Each chunk carries filterable metadata beyond what the e2e version tracked:
    mapping, type (transformation type), has_sql_override, has_join, has_filter,
    field_count, port_count, source_db (dbd), owner, folder, primary_key_count.
This lets the retrieval API support structured pre-filters:
    /retrieve?q=...&filter_type=Source+Qualifier&filter_has_sql=true
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

_CHARS_PER_TOKEN = 4
DEFAULT_MAX_TOKENS = 700    # tracker spec: 500-800 → use midpoint
DEFAULT_OVERLAP_TOKENS = 100  # tracker spec: ~100


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


@dataclass
class Chunk:
    """One retrievable, embeddable unit of Informatica knowledge."""

    chunk_id: str
    source_file: str       # XML filename (basename)
    node_class: str        # SOURCE | TRANSFORMATION | TARGET
    name: str
    text: str
    token_estimate: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


def render_node(node: Dict[str, Any], source_file: str) -> str:
    """Render a canonical node into a self-describing, label-prefixed text block.

    Labels (FILE:, NODE_CLASS:, FIELDS:, SQL_OVERRIDE:, …) serve dual purpose:
    they give the embedding model structural signal and let the downstream LLM
    extract a field-level STTM directly from retrieved text.
    """
    lines: List[str] = []
    node_class = node.get("node_class", "")
    name = node.get("name", "")

    lines.append(f"FILE: {source_file}")
    lines.append(f"NODE_CLASS: {node_class}")
    lines.append(f"NAME: {name}")
    if node.get("type"):
        lines.append(f"TYPE: {node['type']}")
    if node.get("mapping"):
        lines.append(f"MAPPING: {node['mapping']}")
    if node.get("folder"):
        lines.append(f"FOLDER: {node['folder']}")
    if node.get("dbd") or node.get("owner"):
        lines.append(f"DATABASE: {node.get('dbd', '')}  OWNER: {node.get('owner', '')}")

    fields = node.get("fields", [])
    if fields:
        lines.append(f"FIELDS: ({len(fields)} total)")
        for f in fields:
            dt = f.get("datatype", "")
            prec = f.get("precision", "")
            key = f.get("key_type", "")
            suffix = f"  key={key}" if key else ""
            lines.append(f"  - {f.get('name','')}: {dt}({prec}){suffix}")

    ports = node.get("ports", [])
    if ports:
        lines.append(f"PORTS: ({len(ports)} total)")
        for p in ports:
            expr = p.get("expression", "")
            expr_txt = f" = {expr}" if expr else ""
            lines.append(
                f"  - {p.get('name','')} [{p.get('porttype','')}] {p.get('datatype','')}{expr_txt}"
            )

    if node.get("sql_override"):
        lines.append(f"SQL_OVERRIDE: {node['sql_override']}")
    if node.get("join_condition"):
        lines.append(f"JOIN_CONDITION: {node['join_condition']}")
    if node.get("filter_condition"):
        lines.append(f"FILTER_CONDITION: {node['filter_condition']}")
    if node.get("group_by"):
        lines.append(f"GROUP_BY: {', '.join(node['group_by'])}")
    if node.get("primary_keys"):
        lines.append(f"PRIMARY_KEYS: {', '.join(node['primary_keys'])}")

    return "\n".join(lines)


def _split_with_overlap(text: str, max_tokens: int, overlap_tokens: int) -> List[str]:
    """Line-aware split with overlap for nodes that exceed the token budget."""
    max_chars = max_tokens * _CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * _CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return [text]

    lines = text.splitlines(keepends=True)
    chunks: List[str] = []
    buf = ""
    for line in lines:
        if len(buf) + len(line) > max_chars and buf:
            chunks.append(buf)
            buf = buf[-overlap_chars:] if overlap_chars else ""
        buf += line
    if buf.strip():
        chunks.append(buf)
    return chunks or [text]


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", text or "")[:60]


def _content_hash(text: str) -> str:
    """8-char MD5 prefix — makes chunk_id unique even when name collides across folders."""
    return hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()[:8]


def chunk_node(
    node: Dict[str, Any],
    source_file: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> List[Chunk]:
    """Chunk one canonical node into one or more Chunk objects."""
    text = render_node(node, source_file)
    if not text.strip():
        return []

    node_class = node.get("node_class", "")
    name = node.get("name", "")
    fields = node.get("fields", [])
    ports = node.get("ports", [])

    # Richer metadata for structured retrieval filters
    base_meta: Dict[str, Any] = {
        "mapping": node.get("mapping", ""),
        "folder": node.get("folder", ""),
        "type": node.get("type", ""),
        "source_db": node.get("dbd", ""),
        "owner": node.get("owner", ""),
        "field_count": len(fields),
        "port_count": len(ports),
        "primary_key_count": len(node.get("primary_keys", [])),
        "has_sql_override": bool(node.get("sql_override")),
        "has_join": bool(node.get("join_condition")),
        "has_filter": bool(node.get("filter_condition")),
        "field_names": [f.get("name", "") for f in fields],
        "port_names": [p.get("name", "") for p in ports],
    }

    parts = _split_with_overlap(text, max_tokens, overlap_tokens)
    chunks: List[Chunk] = []
    for i, part in enumerate(parts):
        suffix = f"#{i}" if len(parts) > 1 else ""
        # Include a content hash so that the same node name appearing in multiple
        # FOLDER elements (or files) always produces a unique, stable chunk_id.
        chunks.append(
            Chunk(
                chunk_id=f"{source_file}:{node_class}:{_slug(name)}:{_content_hash(part)}{suffix}",
                source_file=source_file,
                node_class=node_class,
                name=name,
                text=part,
                token_estimate=estimate_tokens(part),
                metadata={**base_meta, "part": i, "total_parts": len(parts)},
            )
        )
    return chunks


def chunk_nodes(
    nodes: List[Dict[str, Any]],
    source_file: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> List[Chunk]:
    out: List[Chunk] = []
    for node in nodes:
        out.extend(chunk_node(node, source_file, max_tokens, overlap_tokens))
    return out


# ---------------------------------------------------------------------------
# Lineage chain rendering + chunking
# ---------------------------------------------------------------------------

def render_lineage_chain(chain: Dict[str, Any]) -> str:
    """Render a resolved lineage chain as a self-describing text block.

    The text is designed for semantic retrieval:
        "where does TARGET_NODE.field come from?"
    The answer is the full hop path from target back to source.

    Example output:
        FILE: wf_4201_calculate_interaction_facts.XML
        NODE_CLASS: LINEAGE
        MAPPING: m_4201_wk_interactionevent
        TARGET: DT_WK_InteractionEvent.InteractionEvent_Id
        SOURCE: InteractionEvent.InteractionEvent_Id
        HOP_COUNT: 2
        PATH:
          [TARGET]        DT_WK_InteractionEvent.InteractionEvent_Id
          [TRANSFORMATION] Exp_Default_and_NoMatchAttributes.InteractionEvent_Id
          [SOURCE]         InteractionEvent.InteractionEvent_Id
    """
    lines: List[str] = [
        f"FILE: {chain['source_file']}",
        "NODE_CLASS: LINEAGE",
        f"MAPPING: {chain['mapping']}",
        f"FOLDER: {chain.get('folder', '')}",
        f"TARGET: {chain['target_instance']}.{chain['target_field']}",
    ]
    if chain.get("source_instance"):
        lines.append(f"SOURCE: {chain['source_instance']}.{chain['source_field']}")
    lines.append(f"HOP_COUNT: {chain['hop_count']}")
    lines.append(f"RESOLVED: {'yes' if chain.get('resolved') else 'partial'}")
    lines.append("PATH:")
    for hop in chain.get("hops", []):
        nc = hop.get("node_class", "TRANSFORMATION")
        lines.append(f"  [{nc:<14}] {hop['instance']}.{hop['field']}")
    return "\n".join(lines)


def chunk_lineage_chains(
    chains: List[Dict[str, Any]],
    source_file: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> List[Chunk]:
    """Convert resolved lineage chains into retrievable Chunk objects.

    One chain = one chunk (lineage paths are compact — rarely exceed 700 tokens).
    Chunk ID encodes target+field+source so identical paths produce stable IDs.
    """
    out: List[Chunk] = []
    for chain in chains:
        if not chain.get("resolved"):
            continue  # skip unresolved partial paths to keep index clean
        text = render_lineage_chain(chain)
        cid = (
            f"{source_file}:LINEAGE"
            f":{_slug(chain['target_instance'])}"
            f":{_slug(chain['target_field'])}"
            f":{_content_hash(text)}"
        )
        out.append(
            Chunk(
                chunk_id=cid,
                source_file=source_file,
                node_class="LINEAGE",
                name=f"{chain['target_instance']}.{chain['target_field']}",
                text=text,
                token_estimate=estimate_tokens(text),
                metadata={
                    "mapping":          chain["mapping"],
                    "folder":           chain.get("folder", ""),
                    "target_instance":  chain["target_instance"],
                    "target_field":     chain["target_field"],
                    "source_instance":  chain["source_instance"],
                    "source_field":     chain["source_field"],
                    "hop_count":        chain["hop_count"],
                    "resolved":         chain.get("resolved", False),
                },
            )
        )
    return out
