"""PowerCenter XML parser — standalone version.

Parses an Informatica PowerCenter export into canonical node dicts.
Identical logic to the e2e_infa_to_pyspark parser but self-contained
(no dependency on the app.utils package).
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
        "node_class": "SOURCE",
        "name": _attr(src, "NAME"),
        "dbd": _attr(src, "DATABASETYPE"),
        "owner": _attr(src, "OWNERNAME"),
        "fields": fields,
        "mapping": "",
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
        "node_class": "TARGET",
        "name": _attr(tgt, "NAME"),
        "fields": fields,
        "primary_keys": keys,
        "mapping": "",
    }


def _parse_transformation(tx: ET.Element, mapping_name: str = "") -> Dict[str, Any]:
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
        "node_class": "TRANSFORMATION",
        "name": _attr(tx, "NAME"),
        "type": tx_type,
        "ports": ports,
        "attributes": attrs,
        "sql_override": attrs.get("Sql Query", ""),
        "filter_condition": attrs.get("Filter Condition", ""),
        "join_condition": attrs.get("Join Condition", ""),
        "group_by": [p["name"] for p in ports if "GROUPBY" in p["porttype"].upper()],
        "mapping": mapping_name,
    }


def _parse_mapping_connectors(mapping_el: ET.Element) -> List[Dict[str, str]]:
    return [
        {
            "from_instance": _attr(c, "FROMINSTANCE"),
            "from_field": _attr(c, "FROMFIELD"),
            "to_instance": _attr(c, "TOINSTANCE"),
            "to_field": _attr(c, "TOFIELD"),
        }
        for c in mapping_el.findall("CONNECTOR")
    ]


def parse_powercenter_xml(
    xml_path: str, focus_mapping: Optional[str] = None
) -> Dict[str, Any]:
    """Parse a PowerCenter export file into a canonical dict.

    Returns:
        {
            repository: str,
            folder: str,
            sources: [SOURCE dicts],
            targets: [TARGET dicts],
            mappings: [{name, transformations, connectors}],
        }

    If focus_mapping is given, only that mapping's transformations are returned;
    sources and targets are always aggregated across all FOLDER elements.
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    repository = root.find("REPOSITORY")
    repo_name = repository.get("NAME", "") if repository is not None else ""

    sources: List[Dict[str, Any]] = []
    targets: List[Dict[str, Any]] = []
    mappings: List[Dict[str, Any]] = []
    folder_name = ""

    for folder in root.findall(".//FOLDER"):
        folder_name = folder_name or folder.get("NAME", "")
        for src in folder.findall("SOURCE"):
            sources.append(_parse_source(src))
        for tgt in folder.findall("TARGET"):
            targets.append(_parse_target(tgt))
        for m in folder.findall("MAPPING"):
            mname = _attr(m, "NAME")
            if focus_mapping and mname != focus_mapping:
                continue
            mappings.append(
                {
                    "name": mname,
                    "transformations": [
                        _parse_transformation(tx, mname)
                        for tx in m.findall("TRANSFORMATION")
                    ],
                    "connectors": _parse_mapping_connectors(m),
                }
            )

    return {
        "repository": repo_name,
        "folder": folder_name,
        "sources": sources,
        "targets": targets,
        "mappings": mappings,
    }
