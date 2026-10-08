"""PowerCenter XML parser.

Parses an Informatica PowerCenter export into canonical node dictionaries that the
agents consume. The XML traversal logic is reused from the Phase 2 parser, but the
output is plain dicts (message payloads) rather than ETL dataclasses, so the agents
stay decoupled from any compiler.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional


def _attr(el: ET.Element, *names: str, default: str = "") -> str:
    for n in names:
        v = el.get(n)
        if v is not None:
            return v
    return default


def _parse_source(src: ET.Element) -> Dict[str, Any]:
    fields = [
        {
            "name": _attr(f, "NAME"),
            "datatype": _attr(f, "DATATYPE"),
            "precision": _attr(f, "PRECISION"),
            "scale": _attr(f, "SCALE"),
        }
        for f in src.findall("SOURCEFIELD")
    ]
    return {
        "name": _attr(src, "NAME"),
        "dbd": _attr(src, "DATABASETYPE"),
        "owner": _attr(src, "OWNERNAME"),
        "fields": fields,
    }


def _parse_target(tgt: ET.Element) -> Dict[str, Any]:
    fields = [
        {
            "name": _attr(f, "NAME"),
            "datatype": _attr(f, "DATATYPE"),
            "precision": _attr(f, "PRECISION"),
            "scale": _attr(f, "SCALE"),
            "key_type": _attr(f, "KEYTYPE"),
        }
        for f in tgt.findall("TARGETFIELD")
    ]
    keys = [f["name"] for f in fields if "PRIMARY" in f["key_type"].upper()]
    return {
        "name": _attr(tgt, "NAME"),
        "fields": fields,
        "primary_keys": keys,
    }


def _parse_transformation(tx: ET.Element) -> Dict[str, Any]:
    tx_type = _attr(tx, "TYPE")
    ports: List[Dict[str, Any]] = []
    for fld in tx.findall("TRANSFORMFIELD"):
        ports.append(
            {
                "name": _attr(fld, "NAME"),
                "datatype": _attr(fld, "DATATYPE"),
                "precision": _attr(fld, "PRECISION"),
                "scale": _attr(fld, "SCALE"),
                "porttype": _attr(fld, "PORTTYPE"),
                "expression": _attr(fld, "EXPRESSION"),
            }
        )

    attrs: Dict[str, str] = {}
    for ta in tx.findall("TABLEATTRIBUTE"):
        attrs[_attr(ta, "NAME")] = _attr(ta, "VALUE")

    return {
        "name": _attr(tx, "NAME"),
        "type": tx_type,
        "ports": ports,
        "attributes": attrs,
        "sql_override": attrs.get("Sql Query", ""),
        "filter_condition": attrs.get("Filter Condition", ""),
        "join_condition": attrs.get("Join Condition", ""),
        "group_by": [p["name"] for p in ports if p["porttype"].upper().find("GROUPBY") >= 0],
    }


def parse_mapping(mapping_el: ET.Element) -> Dict[str, Any]:
    transformations = [
        _parse_transformation(tx) for tx in mapping_el.findall("TRANSFORMATION")
    ]
    connectors = [
        {
            "from_instance": _attr(c, "FROMINSTANCE"),
            "from_field": _attr(c, "FROMFIELD"),
            "to_instance": _attr(c, "TOINSTANCE"),
            "to_field": _attr(c, "TOFIELD"),
        }
        for c in mapping_el.findall("CONNECTOR")
    ]
    return {
        "name": _attr(mapping_el, "NAME"),
        "transformations": transformations,
        "connectors": connectors,
    }


def parse_powercenter_xml(
    xml_path: str, focus_mapping: Optional[str] = None
) -> Dict[str, Any]:
    """Parse a PowerCenter export file into a canonical dict.

    Returns: {repository, folder, sources, targets, mappings:[...]}.
    If focus_mapping is provided, only that mapping is returned.
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    repo = root.find(".//REPOSITORY")
    # A PowerCenter export can contain multiple FOLDER elements (e.g. a shared
    # source/target folder plus the application folder that owns the mappings).
    # Aggregate sources, targets, and mappings across every folder.
    folders = root.findall(".//FOLDER") or [root]

    sources: List[Dict[str, Any]] = []
    targets: List[Dict[str, Any]] = []
    mappings: List[Dict[str, Any]] = []
    folder_names: List[str] = []

    for folder in folders:
        folder_names.append(_attr(folder, "NAME"))
        sources.extend(_parse_source(s) for s in folder.findall("SOURCE"))
        targets.extend(_parse_target(t) for t in folder.findall("TARGET"))
        for m in folder.findall("MAPPING"):
            if focus_mapping and _attr(m, "NAME") != focus_mapping:
                continue
            mappings.append(parse_mapping(m))

    return {
        "repository": _attr(repo, "NAME") if repo is not None else "",
        "folder": ",".join(n for n in folder_names if n),
        "sources": sources,
        "targets": targets,
        "mappings": mappings,
    }
