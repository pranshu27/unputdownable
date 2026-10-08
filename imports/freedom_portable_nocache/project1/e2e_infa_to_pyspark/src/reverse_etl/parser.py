from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List

from .models import (
    MappingDef,
    SourceDef,
    SourceField,
    TargetDef,
    TargetField,
    Transformation,
    WorkflowSpec,
)


def _safe_attr(node: ET.Element, key: str, default: str = "") -> str:
    return (node.attrib.get(key) or default).strip()


def parse_informatica_xml(xml_path: str) -> WorkflowSpec:
    path = Path(xml_path)
    tree = ET.parse(path)
    root = tree.getroot()

    sources = _parse_sources(root)
    targets = _parse_targets(root)
    mappings = _parse_mappings(root)

    return WorkflowSpec(
        xml_path=str(path),
        sources=sources,
        targets=targets,
        mappings=mappings,
    )


def _parse_sources(root: ET.Element) -> List[SourceDef]:
    source_defs: List[SourceDef] = []
    for source_node in root.findall(".//SOURCE"):
        fields: List[SourceField] = []
        for field_node in source_node.findall("SOURCEFIELD"):
            fields.append(
                SourceField(
                    name=_safe_attr(field_node, "NAME"),
                    datatype=_safe_attr(field_node, "DATATYPE"),
                    precision=_safe_attr(field_node, "PRECISION") or None,
                    scale=_safe_attr(field_node, "SCALE") or None,
                )
            )
        source_defs.append(
            SourceDef(
                name=_safe_attr(source_node, "NAME"),
                database=_safe_attr(source_node, "DBDNAME"),
                fields=fields,
            )
        )
    return source_defs


def _parse_targets(root: ET.Element) -> List[TargetDef]:
    target_defs: List[TargetDef] = []
    for target_node in root.findall(".//TARGET"):
        fields: List[TargetField] = []
        for field_node in target_node.findall("TARGETFIELD"):
            fields.append(
                TargetField(
                    name=_safe_attr(field_node, "NAME"),
                    datatype=_safe_attr(field_node, "DATATYPE"),
                    key_type=_safe_attr(field_node, "KEYTYPE"),
                    precision=_safe_attr(field_node, "PRECISION") or None,
                    scale=_safe_attr(field_node, "SCALE") or None,
                )
            )
        target_defs.append(
            TargetDef(
                name=_safe_attr(target_node, "NAME"),
                database=_safe_attr(target_node, "DATABASETYPE"),
                fields=fields,
            )
        )
    return target_defs


def _parse_mappings(root: ET.Element) -> List[MappingDef]:
    mappings: List[MappingDef] = []
    for mapping_node in root.findall(".//MAPPING"):
        transformations: List[Transformation] = []
        for tf_node in mapping_node.findall("TRANSFORMATION"):
            table_attributes = {
                _safe_attr(attr_node, "NAME"): _safe_attr(attr_node, "VALUE")
                for attr_node in tf_node.findall("TABLEATTRIBUTE")
            }
            field_names = [
                _safe_attr(field_node, "NAME")
                for field_node in tf_node.findall("TRANSFORMFIELD")
                if _safe_attr(field_node, "NAME")
            ]
            transformations.append(
                Transformation(
                    name=_safe_attr(tf_node, "NAME"),
                    type_name=_safe_attr(tf_node, "TYPE"),
                    table_attributes=table_attributes,
                    fields=field_names,
                )
            )

        mappings.append(
            MappingDef(
                name=_safe_attr(mapping_node, "NAME"),
                transformations=transformations,
            )
        )
    return mappings
