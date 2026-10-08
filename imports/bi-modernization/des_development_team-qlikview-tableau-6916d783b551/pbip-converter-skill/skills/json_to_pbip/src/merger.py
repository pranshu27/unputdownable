"""
merger.py — Combine the two common-model JSONs produced for a thin /
live-connected Power BI report into a single unified JSON the existing
parser pipeline can consume.

Live-connect reports have their data model published as a separate dataset
on the service; the .pbix on the user's machine carries only the visual
definitions plus (optionally) report-level measures. The RE extracts each
side independently, producing two JSON files:

  * **data JSON** — semantic model: tables[], relationships[], calculations[],
                    data_sources[], plus an empty/placeholder visualizations.
  * **report JSON** — visualizations.pages[] with the real visuals; tables /
                      relationships / data_sources are empty; calculations[]
                      may carry report-level measures the report author
                      added inside the .pbix.

`merge_thin_live(a, b)` accepts the two top-level JSON dicts in either
order, auto-detects which is which (the side with 0 tables is the report),
and returns a single dict that looks identical to a regular single-extraction
common-model JSON. Calculations are unioned (semantic wins on name
collision). The merged dict can be fed straight into the existing
parse_common_model -> map_intermediate -> write_pbip pipeline.
"""
from __future__ import annotations

from typing import Any, Iterable


def _unwrap(d: dict) -> dict:
    """Return the inner common-model dict, peeling the `{ "result": {...} }`
    envelope the upstream extractor wraps around its output."""
    if isinstance(d.get("result"), dict) and "schema_version" in d["result"]:
        inner = d["result"]
        # Preserve the extractor's tool_type hint if the inner dict omits it.
        if d.get("tool_type") and not inner.get("tool_type"):
            inner["tool_type"] = d["tool_type"]
        return inner
    return d


def _classify(a_inner: dict, b_inner: dict) -> tuple[dict, dict]:
    """Auto-detect which side is the semantic-data JSON and which is the
    report JSON, returning (data, report). The report side has no tables /
    relationships / data_sources but carries the populated visualizations;
    the data side carries the model.

    Raises ValueError if neither (or both) look like the report side, so
    callers know the inputs are not a valid thin/live-connect pair.
    """
    def is_report(d: dict) -> bool:
        # A live-connect report's data-model arrays are all empty; only its
        # visualizations are populated.
        if d.get("tables") or d.get("relationships") or d.get("data_sources"):
            return False
        vz = d.get("visualizations") or {}
        pages = vz.get("pages") if isinstance(vz, dict) else None
        return bool(pages)

    a_is_rep = is_report(a_inner)
    b_is_rep = is_report(b_inner)
    if a_is_rep and not b_is_rep:
        return b_inner, a_inner
    if b_is_rep and not a_is_rep:
        return a_inner, b_inner
    if a_is_rep and b_is_rep:
        raise ValueError(
            "Both inputs look like report JSONs (no tables / relationships). "
            "One of them must be the semantic-data JSON."
        )
    raise ValueError(
        "Neither input looks like a live-connect report JSON (both carry "
        "tables / relationships). For a single-file extraction use the "
        "regular single-input invocation."
    )


def _union_calculations(semantic: list, report: list) -> list:
    """Return semantic.calculations[] with any report-level measures appended.
    Dedupe by name (case-insensitive) — semantic wins on collision because
    the semantic model is the system of record and any same-name entry on
    the report side is by definition redundant."""
    seen = {(c.get("name") or "").lower() for c in (semantic or []) if c.get("name")}
    merged = list(semantic or [])
    for c in (report or []):
        name = (c.get("name") or "").lower()
        if not name or name in seen:
            continue
        merged.append(c)
        seen.add(name)
    return merged


def merge_thin_live(a: dict, b: dict) -> dict:
    """Merge a thin live-connect pair (data JSON + report JSON, in either
    order) into a single unified common-model JSON. The returned dict is
    wrapped in the same `{ "result": ... }` envelope the upstream emits so
    downstream code that unwraps `result` keeps working unchanged.
    """
    a_inner = _unwrap(a)
    b_inner = _unwrap(b)
    data, report = _classify(a_inner, b_inner)

    # Start from the semantic model as the base — it owns everything except
    # the visualizations.
    merged_inner: dict[str, Any] = dict(data)

    # Identity (name / model_id / file_name) comes from the REPORT side, not
    # the data side. In a thin / live-connect setup the data side is the
    # upstream published semantic model on the service (its name is the
    # dataset's identifier — incidental metadata to the user); the report
    # side is what the user actually opens in Power BI Desktop. Carrying
    # over the dataset name turned the output folder name into
    # `<Dataset Name>` instead of `<Report Name>`, which both misrepresents
    # the artifact and inflates the folder path length.
    for _id_key in ("name", "model_id", "file_name"):
        rv = report.get(_id_key)
        if rv:
            merged_inner[_id_key] = rv

    # Swap in the report's visualizations. The semantic side's
    # `visualizations` is a placeholder (empty pages) and would otherwise
    # mask the report's real ones.
    merged_inner["visualizations"] = report.get("visualizations") or {}

    # Union calculations (semantic + any report-level measures).
    merged_inner["calculations"] = _union_calculations(
        data.get("calculations") or [],
        report.get("calculations") or [],
    )

    # Preserve a hint that this came from a thin/live-connect merge — useful
    # for telemetry and downstream debugging. Not consumed by the pipeline.
    merged_inner["_merged_from"] = {
        "data":   {"file_name": a.get("file_name") if data is a_inner else b.get("file_name")},
        "report": {"file_name": b.get("file_name") if report is b_inner else a.get("file_name")},
    }

    # Re-wrap in the `result` envelope so local_runner's existing unwrap
    # logic keeps working. Use the REPORT side's top-level envelope so the
    # outer `file_name` / `report_id` also align with the user-visible
    # artifact rather than the upstream dataset.
    envelope_src = a if report is a_inner else b
    envelope: dict[str, Any] = {
        k: v for k, v in envelope_src.items()
        if k != "result"
    }
    envelope["result"] = merged_inner
    return envelope


# ── Binding-resolution check (diagnostic only) ────────────────────────────────

def check_visual_bindings(merged_inner: dict) -> list[str]:
    """Walk every visual field reference in merged_inner.visualizations and
    return a list of `<table>.<column>` strings that don't resolve to either
    a table column or a measure name in the merged model. Used by the CLI
    to print a one-line "Unresolved bindings: N" summary so users can spot
    report-level measures the merge missed (or naming-mismatch typos).
    """
    table_cols = {
        (t.get("name"), c.get("name"))
        for t in (merged_inner.get("tables") or [])
        for c in (t.get("columns") or [])
    }
    table_measures = {
        (t.get("name"), m.get("name"))
        for t in (merged_inner.get("tables") or [])
        for m in (t.get("measures") or [])
    }
    # Calculations can be home-tabled or floating. Match by measure name only
    # since visuals address measures as <table>.<MeasureName> but the
    # measure's home table is resolved downstream.
    measure_names = {
        c.get("name") for c in (merged_inner.get("calculations") or [])
        if c.get("name")
    }

    broken: list[str] = []
    vz = merged_inner.get("visualizations") or {}
    for page in (vz.get("pages") or []):
        for vis in (page.get("visuals") or []):
            for field in (vis.get("fields") or []):
                tbl = field.get("table")
                col = field.get("column")
                if not tbl or not col:
                    continue
                # Hierarchy paths like "MM.Variation.Date Hierarchy.Year" —
                # the first segment is the base column on `tbl`.
                first = col.split(".", 1)[0]
                if (tbl, first) in table_cols:
                    continue
                if (tbl, first) in table_measures:
                    continue
                if first in measure_names:
                    continue
                broken.append(f"{tbl}.{col}")
    return broken
