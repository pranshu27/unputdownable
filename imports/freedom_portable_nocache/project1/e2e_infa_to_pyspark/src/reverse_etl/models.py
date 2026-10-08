from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SourceField:
    name: str
    datatype: str
    precision: Optional[str] = None
    scale: Optional[str] = None


@dataclass
class SourceDef:
    name: str
    database: str
    fields: List[SourceField] = field(default_factory=list)


@dataclass
class TargetField:
    name: str
    datatype: str
    key_type: str
    precision: Optional[str] = None
    scale: Optional[str] = None


@dataclass
class TargetDef:
    name: str
    database: str
    fields: List[TargetField] = field(default_factory=list)


@dataclass
class Transformation:
    name: str
    type_name: str
    table_attributes: Dict[str, str] = field(default_factory=dict)
    fields: List[str] = field(default_factory=list)


@dataclass
class MappingDef:
    name: str
    transformations: List[Transformation] = field(default_factory=list)


@dataclass
class WorkflowSpec:
    xml_path: str
    sources: List[SourceDef] = field(default_factory=list)
    targets: List[TargetDef] = field(default_factory=list)
    mappings: List[MappingDef] = field(default_factory=list)

    def mapping_by_name(self, mapping_name: str) -> MappingDef:
        for mapping in self.mappings:
            if mapping.name == mapping_name:
                return mapping
        raise ValueError(f"Mapping not found: {mapping_name}")
