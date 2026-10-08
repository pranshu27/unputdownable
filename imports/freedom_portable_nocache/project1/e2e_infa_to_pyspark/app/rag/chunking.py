"""Chunking strategies for the Informatica RAG corpus.

Why chunking matters
--------------------
An embedding model maps a *bounded* span of text to one vector. If a chunk is too large it
blurs many ideas into a single averaged vector (poor recall); too small and it loses the
context needed to be meaningful (poor precision). The chunk is also the unit that gets
returned to the LLM, so its boundaries decide how coherent the retrieved context is.

Chunking strategies considered
------------------------------
1. Fixed-size (character/token) windows
   - Split every N characters/tokens. Simple, fast, but cuts through the middle of a field
     list or an expression, splitting a single idea across two vectors.
2. Sliding window with overlap
   - Fixed-size + an overlap (e.g. 15%) so an idea straddling a boundary survives in at
     least one chunk. Mitigates (1) but duplicates text and inflates the index.
3. Sentence / recursive-separator splitting (LangChain-style)
   - Split on a separator hierarchy (paragraph -> line -> sentence -> word). Good for prose
     and source code, but Informatica XML is not prose — there are no sentences.
4. Semantic chunking
   - Embed sentences, start a new chunk when cosine distance to the running centroid spikes.
     Highest quality for narrative text, but expensive (an embedding call per sentence) and
     overkill for already-structured metadata.
5. Structure-aware (schema/element) chunking  <-- CHOSEN
   - Use the document's own structure as the boundary. A PowerCenter export is a tree of
     discrete, self-describing elements: each SOURCE, TARGET, and TRANSFORMATION is a
     complete unit with its own fields, datatypes, SQL override, and join/filter logic.
   - One element == one chunk gives semantically clean, self-contained vectors at exactly
     the grain a data modeller queries ("which source feeds RLTInteractionAgreement?",
     "what is the SQL override on this Source Qualifier?").

Chosen strategy and why
-----------------------
**Structure-aware chunking with a size-bounded fallback.** Because the corpus is already
parsed into canonical nodes (`flatten_mapping_to_nodes`), the natural and most accurate
boundary is one node = one chunk. For the rare oversized node (a source/target with very
many fields), we apply a secondary fixed-size split *with overlap* so no chunk exceeds the
embedding model's effective window, while still keeping field groups together.

This module renders each node into a normalized, retrieval-friendly text block and emits
`Chunk` records ready to embed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

# Rough token estimate: ~4 chars/token for English+code. Good enough for budgeting.
_CHARS_PER_TOKEN = 4
# Embedding models comfortably handle 256–512 token chunks; keep nodes well under that.
DEFAULT_MAX_TOKENS = 350
DEFAULT_OVERLAP_TOKENS = 40


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


@dataclass
class Chunk:
    """One retrievable, embeddable unit of Informatica knowledge."""

    chunk_id: str
    source_file: str
    node_class: str
    name: str
    text: str
    token_estimate: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


def render_node(node: Dict[str, Any], source_file: str) -> str:
    """Render a canonical node into a normalized, self-describing text block.

    The rendering is deliberately label-prefixed ("FIELDS:", "SQL_OVERRIDE:") so both the
    embedding model and the downstream LLM can read structure, and so a data modeller can
    extract a field-level source-to-target mapping from the retrieved text.
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
    if node.get("dbd") or node.get("owner"):
        lines.append(f"DATABASE: {node.get('dbd', '')} OWNER: {node.get('owner', '')}")

    fields = node.get("fields", [])
    if fields:
        lines.append("FIELDS:")
        for f in fields:
            dt = f.get("datatype", "")
            prec = f.get("precision", "")
            key = f.get("key_type", "")
            suffix = f" key={key}" if key else ""
            lines.append(f"  - {f.get('name','')}: {dt}({prec}){suffix}")

    ports = node.get("ports", [])
    if ports:
        lines.append("PORTS:")
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


def _split_with_overlap(
    text: str, max_tokens: int, overlap_tokens: int
) -> List[str]:
    """Line-aware fixed-size split with overlap, used only for oversized nodes."""
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
            # carry an overlap tail into the next chunk to preserve context
            buf = buf[-overlap_chars:] if overlap_chars else ""
        buf += line
    if buf.strip():
        chunks.append(buf)
    return chunks


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", text or "")[:60]


def chunk_node(
    node: Dict[str, Any],
    source_file: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> List[Chunk]:
    """Structure-aware chunking of one canonical node (with size-bounded fallback)."""
    text = render_node(node, source_file)
    if not text.strip():
        return []

    node_class = node.get("node_class", "")
    name = node.get("name", "")
    base_meta = {
        "type": node.get("type", ""),
        "mapping": node.get("mapping", ""),
        "owner": node.get("owner", ""),
        "dbd": node.get("dbd", ""),
        "has_sql_override": bool(node.get("sql_override")),
        "field_names": [f.get("name", "") for f in node.get("fields", [])],
        "port_names": [p.get("name", "") for p in node.get("ports", [])],
    }

    parts = _split_with_overlap(text, max_tokens, overlap_tokens)
    chunks: List[Chunk] = []
    for i, part in enumerate(parts):
        suffix = f"#{i}" if len(parts) > 1 else ""
        chunks.append(
            Chunk(
                chunk_id=f"{source_file}:{node_class}:{_slug(name)}{suffix}",
                source_file=source_file,
                node_class=node_class,
                name=name,
                text=part,
                token_estimate=estimate_tokens(part),
                metadata={**base_meta, "part": i, "parts": len(parts)},
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
