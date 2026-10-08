"""Field-level lineage resolver for Informatica PowerCenter mappings.

Takes parsed mapping dicts (from xml_parser.py) which already include
``connectors`` — the 13,237 CONNECTOR edges across the 7 XMLs — and resolves
them into complete lineage chains from TARGET field back to SOURCE field.

A lineage chain is:
    TARGET.field_N  ← TransformN.port_N  ← … ← SOURCE.field_0

Each chain becomes a LINEAGE chunk in the RAG, enabling queries like:
    "Where does InteractionEvent_Id in wf_4201 come from?"
    "What source table feeds the DM facts InteractionGroup_Id column?"
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

# --------------------------------------------------------------------------- #
# Types                                                                         #
# --------------------------------------------------------------------------- #
Edge = Dict[str, str]   # {from_instance, from_field, to_instance, to_field}
Hop  = Dict[str, str]   # {instance, field, instance_type}
Chain = Dict[str, Any]  # a complete lineage path + metadata


# --------------------------------------------------------------------------- #
# Build reverse adjacency (target → source direction)                          #
# --------------------------------------------------------------------------- #
def _build_reverse_adj(
    connectors: List[Edge],
) -> Dict[Tuple[str, str], List[Tuple[str, str]]]:
    """Map (to_instance, to_field) → [(from_instance, from_field), ...]."""
    reverse: Dict[Tuple[str, str], List[Tuple[str, str]]] = defaultdict(list)
    for c in connectors:
        key = (c["to_instance"], c["to_field"])
        reverse[key].append((c["from_instance"], c["from_field"]))
    return reverse


def _classify_instance(instance: str, node_lookup: Dict[str, str]) -> str:
    """Return SOURCE | TARGET | TRANSFORMATION for an instance name."""
    return node_lookup.get(instance, "TRANSFORMATION")


# --------------------------------------------------------------------------- #
# BFS backward from a target field                                             #
# --------------------------------------------------------------------------- #
def _trace_back(
    start_instance: str,
    start_field: str,
    reverse_adj: Dict[Tuple[str, str], List[Tuple[str, str]]],
    node_lookup: Dict[str, str],
    max_depth: int = 20,
) -> List[List[Hop]]:
    """Return all lineage paths from (start_instance, start_field) back to sources.

    Uses BFS with path tracking. Returns a list of complete paths, where each
    path is a list of Hop dicts ordered from target → source.
    """
    # Each queue item: (current_path_so_far,)
    queue: List[List[Hop]] = [
        [{"instance": start_instance, "field": start_field,
          "node_class": node_lookup.get(start_instance, "TRANSFORMATION")}]
    ]
    completed_paths: List[List[Hop]] = []
    seen_states: set = set()

    while queue:
        path = queue.pop(0)
        if len(path) > max_depth:
            completed_paths.append(path)
            continue

        last = path[-1]
        key = (last["instance"], last["field"])
        parents = reverse_adj.get(key, [])

        if not parents:
            # No upstream — this is either a SOURCE or a dead end
            completed_paths.append(path)
            continue

        for from_inst, from_field in parents:
            state = (from_inst, from_field, len(path))
            if state in seen_states:
                continue
            seen_states.add(state)
            nclass = node_lookup.get(from_inst, "TRANSFORMATION")
            new_hop: Hop = {"instance": from_inst, "field": from_field,
                            "node_class": nclass}
            new_path = path + [new_hop]

            # If we've reached a SOURCE node, record as complete
            if nclass == "SOURCE":
                completed_paths.append(new_path)
            else:
                queue.append(new_path)

    return completed_paths if completed_paths else [path]


# --------------------------------------------------------------------------- #
# Build node lookup from parsed mapping                                        #
# --------------------------------------------------------------------------- #
def _build_node_lookup(parsed: Dict[str, Any]) -> Dict[str, str]:
    """Map instance name → node_class for all nodes in the parsed file."""
    lookup: Dict[str, str] = {}
    for s in parsed.get("sources", []):
        lookup[s["name"]] = "SOURCE"
    for t in parsed.get("targets", []):
        lookup[t["name"]] = "TARGET"
    for m in parsed.get("mappings", []):
        for tx in m.get("transformations", []):
            lookup[tx["name"]] = "TRANSFORMATION"
    return lookup


def _get_target_fields(parsed: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Return (target_name, field_name) for every TARGET field in the file."""
    pairs = []
    for t in parsed.get("targets", []):
        for f in t.get("fields", []):
            pairs.append((t["name"], f["name"]))
    return pairs


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #
def build_lineage_chains(
    parsed: Dict[str, Any],
    source_file: str,
    max_depth: int = 20,
) -> List[Chain]:
    """Resolve all TARGET-to-SOURCE lineage chains for one parsed XML file.

    Args:
        parsed:       Output of xml_parser.parse_powercenter_xml().
        source_file:  XML filename (for chunk metadata).
        max_depth:    Maximum hops before giving up (prevents infinite loops
                      in cyclic or very deep mappings).

    Returns:
        List of chain dicts, each representing one field lineage path.
        Each chain has:
            node_class       = "LINEAGE"
            source_file      = str
            mapping          = str
            folder           = str
            target_instance  = str
            target_field     = str
            source_instance  = str (first source found, or "" if unresolved)
            source_field     = str
            hop_count        = int
            hops             = [{"instance", "field", "node_class"}, ...]
                               ordered TARGET → SOURCE
    """
    node_lookup = _build_node_lookup(parsed)
    folder = parsed.get("folder", "")

    # Aggregate all connectors across all mappings in this file
    all_connectors: List[Edge] = []
    mapping_by_target: Dict[str, str] = {}

    for m in parsed.get("mappings", []):
        mname = m["name"]
        all_connectors.extend(m.get("connectors", []))
        # Record which mapping each target instance belongs to
        for tx in m.get("transformations", []):
            mapping_by_target[tx["name"]] = mname
    for t in parsed.get("targets", []):
        mapping_by_target[t["name"]] = next(
            (m["name"] for m in parsed.get("mappings", [])), ""
        )

    reverse_adj = _build_reverse_adj(all_connectors)
    target_fields = _get_target_fields(parsed)

    chains: List[Chain] = []
    for target_inst, target_field in target_fields:
        paths = _trace_back(
            target_inst, target_field, reverse_adj, node_lookup, max_depth
        )
        for path in paths:
            last_hop = path[-1]
            is_source = last_hop["node_class"] == "SOURCE"
            chain: Chain = {
                "node_class":       "LINEAGE",
                "source_file":      source_file,
                "mapping":          mapping_by_target.get(target_inst, ""),
                "folder":           folder,
                "target_instance":  target_inst,
                "target_field":     target_field,
                "source_instance":  last_hop["instance"] if is_source else "",
                "source_field":     last_hop["field"]    if is_source else "",
                "hop_count":        len(path) - 1,
                "resolved":         is_source,
                "hops":             path,   # list of {instance, field, node_class}
            }
            chains.append(chain)

    return chains


def summarise(chains: List[Chain]) -> Dict[str, Any]:
    """Return quick stats for logging / testing."""
    resolved   = sum(1 for c in chains if c["resolved"])
    unresolved = len(chains) - resolved
    max_depth  = max((c["hop_count"] for c in chains), default=0)
    sources    = len({c["source_instance"] for c in chains if c["source_instance"]})
    targets    = len({c["target_instance"] for c in chains})
    return {
        "total":       len(chains),
        "resolved":    resolved,
        "unresolved":  unresolved,
        "max_depth":   max_depth,
        "unique_sources": sources,
        "unique_targets": targets,
    }
