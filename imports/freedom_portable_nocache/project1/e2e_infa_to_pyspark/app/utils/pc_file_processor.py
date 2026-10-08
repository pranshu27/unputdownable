"""Shared-folder pre-processing for PowerCenter exports.

Mirrors farmers_backend app/utils + orchestrator helpers:
- get_export_type(): detect the ETL export type from a file.
- pre_process_shared_folder(): walk an input folder, parse each PowerCenter XML, and
  flatten every mapping into a list of canonical node payloads ready to publish to the
  extractor topic.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from app.utils.xml_parser import parse_powercenter_xml


def get_export_type(file_path: str) -> str:
    """Detect ETL export type. Only PowerCenter is supported here."""
    lower = file_path.lower()
    if lower.endswith(".xml"):
        with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
            head = fh.read(4096)
        if "POWERMART" in head or "REPOSITORY" in head:
            return "powercenter"
    return "unknown"


def flatten_mapping_to_nodes(parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Turn a parsed PowerCenter dict into ordered canonical node payloads.

    Order: SOURCE -> TRANSFORMATION (file order ~ dependency order) -> TARGET.
    Each payload is the content for one PCMessage published to the extractor topic.
    """
    nodes: List[Dict[str, Any]] = []

    for src in parsed.get("sources", []):
        nodes.append({"node_class": "SOURCE", "mapping": "", **src})

    for mapping in parsed.get("mappings", []):
        mname = mapping["name"]
        for tx in mapping["transformations"]:
            nodes.append({"node_class": "TRANSFORMATION", "mapping": mname, **tx})

    for tgt in parsed.get("targets", []):
        nodes.append({"node_class": "TARGET", "mapping": "", **tgt})

    return nodes


def pre_process_shared_folder(
    folder_path: str, focus_mapping: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Walk a folder of PowerCenter XML exports and return all canonical node payloads."""
    all_nodes: List[Dict[str, Any]] = []
    for root, _dirs, files in os.walk(folder_path):
        for fname in files:
            fpath = os.path.join(root, fname)
            if get_export_type(fpath) != "powercenter":
                continue
            parsed = parse_powercenter_xml(fpath, focus_mapping=focus_mapping)
            all_nodes.extend(flatten_mapping_to_nodes(parsed))
    return all_nodes
