"""PC file processor — flatten parsed PowerCenter dicts into ordered node lists.

Order: SOURCE → TRANSFORMATION (file order ≈ dependency order) → TARGET.
Walks an entire folder of XML exports and merges them into one node list.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from rag_system.ingestion.xml_parser import parse_powercenter_xml


def get_export_type(file_path: str) -> str:
    lower = file_path.lower()
    if lower.endswith(".xml"):
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
                head = fh.read(4096)
            if "POWERMART" in head or "REPOSITORY" in head:
                return "powercenter"
        except OSError:
            return "unknown"
    return "unknown"


def flatten_mapping_to_nodes(parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Turn a parsed PowerCenter dict into an ordered list of canonical node payloads."""
    nodes: List[Dict[str, Any]] = []
    for src in parsed.get("sources", []):
        nodes.append({**src, "folder": parsed.get("folder", "")})
    for mapping in parsed.get("mappings", []):
        for tx in mapping["transformations"]:
            nodes.append({**tx, "folder": parsed.get("folder", "")})
    for tgt in parsed.get("targets", []):
        nodes.append({**tgt, "folder": parsed.get("folder", "")})
    return nodes


def walk_xml_folder(
    folder_path: str,
    focus_mapping: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Walk a folder of PowerCenter XML exports and return all canonical node payloads.

    Each node dict gets two extra keys:
        ``_source_file``: the originating XML filename (basename)
        ``_xml_path``:    the full resolved path (for the knowledge base builder)
    """
    all_nodes: List[Dict[str, Any]] = []
    for root, _dirs, files in os.walk(folder_path):
        for fname in sorted(files):
            fpath = os.path.join(root, fname)
            if get_export_type(fpath) != "powercenter":
                continue
            try:
                parsed = parse_powercenter_xml(fpath, focus_mapping=focus_mapping)
            except Exception:
                continue
            nodes = flatten_mapping_to_nodes(parsed)
            for node in nodes:
                node["_source_file"] = fname
                node["_xml_path"] = fpath
            all_nodes.extend(nodes)
    return all_nodes
