"""
validation_runner.py — Run the FE semantic + report validators against a
generated PBIP and assemble a single result JSON.

The two validator scripts live at the package root and are used AS-IS:
  scemanticvalidator.py  → FESemanticValidator (JSON tables  vs  .SemanticModel)
  reportvalidator.py     → FEReportValidator   (JSON visuals vs  .Report)

Routing
-------
Each input JSON is classified by what it carries:
  * tables present (`result.tables`)                → semantic validation
  * pages present  (`result.visualizations.pages`)  → report validation
A single full extraction carries both  → both validators run.
A thin / live-connect pair carries one of each.

File-path handling
------------------
The validators take a JSON *file path* and a PBIP *folder path*. The endpoint
receives uploaded JSON bytes + zip archives, so this module:
  * writes each JSON to a real temp file (the validators call open() on it),
  * extracts the zip(s) — including a nested-zip bundle — to a temp tree,
  * locates the `.SemanticModel` / `.Report` folders inside,
  * passes absolute paths to the validators.
That removes any dependence on the caller's working directory.

Output
------
A dict shaped like `testoutput.json` — score_breakdown / check_summary /
all_results / gap_report / report.
"""
import json
import os
import sys
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import scemanticvalidator as _sem
import reportvalidator as _rep


# ── Scoring ────────────────────────────────────────────────────────────────────
# severity-weighted: a PASS earns 0.5; a gap costs its severity weight.
_SEV_WEIGHT = {"CRITICAL": 5, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0.5}
_PASS_WEIGHT = 0.5
_THRESHOLD = 80.0
_FORMULA = ("severity-weighted: a PASS earns 0.5; a gap costs CRITICAL=5, "
            "HIGH=3, MEDIUM=2, LOW=1. INFO rows are informational and excluded.")

# Short descriptions for the check groups (S = semantic, R = report/visual).
_DESC = {
    "S1":  "Table existence, count, storage mode, hidden flag",
    "S2":  "Column names, data types, summarize-by, sort-by",
    "S3":  "DAX calculated columns and their expressions",
    "S4":  "Measures, KPI definitions and format strings",
    "S5":  "Hierarchies and their levels",
    "S6":  "Relationships, cardinality, USERELATIONSHIP",
    "S7":  "Power Query (M) partition expressions",
    "S8":  "DAX calculated tables",
    "S9":  "Row-level-security roles",
    "S10": "Model-level metadata",
    "S11": "Shared / parameter expressions",
    "S12": "Object-level-security column permissions",
    "S13": "What-if parameters",
    "S14": "Field-parameter tables",
    "S15": "Incremental-refresh policies",
    "S16": "Dynamic RLS detection",
    "S17": "Perspectives",
    "S18": "Cultures and translations",
    "R1":  "Report pages — existence, size, visibility",
    "R2":  "Visuals — type, count, position",
    "R3":  "Visual field bindings (roles, columns, aggregations)",
    "R4":  "Visual-level filters",
    "R5":  "Page-level filters",
    "R6":  "Report-level filters",
    "R7":  "Bookmarks",
    "R8":  "Theme and page backgrounds",
    "R9":  "Visual formatting objects",
    "R10": "Custom visuals (AppSource)",
    "R11": "Button actions and navigation",
    "R12": "Conditional formatting",
    "R13": "Tooltips",
    "R14": "Drillthrough",
    "R15": "Images and logos",
    "R16": "HTML and embedded custom visuals",
    "R17": "Visual interactions (edit interactions)",
    "R18": "Sync slicers (cross-page)",
}


# ── JSON classification ─────────────────────────────────────────────────────────
def _unwrap(data: dict) -> dict:
    """Return the model/report payload regardless of whether the JSON is wrapped
    in a `result` envelope or stored flat."""
    if not isinstance(data, dict):
        return {}
    if isinstance(data.get("result"), dict):
        return data["result"]
    return data


def classify(data: dict) -> tuple[bool, bool]:
    """Return (has_tables, has_pages) for one extraction JSON."""
    r = _unwrap(data)
    has_tables = bool(r.get("tables"))
    pages = (r.get("visualizations") or {}).get("pages") or []
    return has_tables, bool(pages)


def extract_meta(jsons: list[dict]) -> dict:
    """Pull workbook id / file name / tool name from whichever JSON carries
    them. Falls back to sensible defaults."""
    workbook_id = file_name = tool_name = None
    for d in jsons:
        r = _unwrap(d)
        workbook_id = workbook_id or d.get("report_id") or d.get("workbook_id") or r.get("model_id")
        file_name = file_name or d.get("file_name") or r.get("name")
        tool_name = tool_name or d.get("tool_type") or d.get("tool_name") or r.get("tool_type")
    return {
        "workbook_id": str(workbook_id) if workbook_id else uuid.uuid4().hex[:8],
        "file_name": file_name or "extraction.pbix",
        "tool_name": tool_name or "powerbi",
    }


# ── Zip / folder discovery ──────────────────────────────────────────────────────
def extract_zip(src: str, dest: str) -> None:
    """Extract `src` into `dest`, then recursively extract any nested .zip files
    (the /generate_pbip/ bundle nests <Name>_dataset.zip + <Name>_report.zip)."""
    os.makedirs(dest, exist_ok=True)
    with zipfile.ZipFile(src) as zf:
        zf.extractall(dest)
    for root, _, files in os.walk(dest):
        for fn in files:
            if fn.lower().endswith(".zip"):
                inner = os.path.join(root, fn)
                sub = os.path.join(root, fn[:-4] + "__unzipped")
                try:
                    extract_zip(inner, sub)
                except zipfile.BadZipFile:
                    pass


def find_dirs(root: str, suffix: str) -> list[str]:
    """All folders under `root` whose name ends with `suffix` (e.g. '.Report')."""
    hits = []
    for dirpath, dirnames, _ in os.walk(root):
        for d in dirnames:
            if d.endswith(suffix):
                hits.append(os.path.join(dirpath, d))
    return hits


def _file_count(path: str) -> int:
    return sum(len(files) for _, _, files in os.walk(path))


def pick_pbip_folder(root: str, suffix: str) -> str | None:
    """Pick the best `.SemanticModel` / `.Report` folder under `root`. When a
    bundle carries both a real report and an empty-shell report (the dataset
    deliverable), the richer folder — more files — wins."""
    hits = find_dirs(root, suffix)
    if not hits:
        return None
    return max(hits, key=_file_count)


# ── Result assembly ─────────────────────────────────────────────────────────────
def _cid_sort(cid: str):
    """Sort S1,S2,…,S18 / R1,…,R18 numerically rather than lexically."""
    try:
        return (cid[0], int(cid[1:]))
    except (ValueError, IndexError):
        return (cid, 0)


def _verdict(score) -> str:
    if score is None:
        return "N/A"
    return "PASS" if score >= _THRESHOLD else "FAIL"


def _summarize(results: list, labels: dict, scope: str):
    """Group CheckResults by check_id into testoutput-style check entries.
    Returns (check_entries, scope_weight_earned, scope_weight_total)."""
    by_cid: dict[str, list] = {}
    for r in results:
        by_cid.setdefault(r.check_id, []).append(r)

    checks = []
    scope_earned = scope_total = 0.0
    for cid in sorted(by_cid, key=_cid_sort):
        grp = [r for r in by_cid[cid] if r.status != "INFO"]
        if not grp:
            continue
        n_pass = sum(1 for r in grp if r.status == "PASS")
        n_miss = sum(1 for r in grp if r.status == "MISSING")
        n_fail = sum(1 for r in grp if r.status in ("FAIL", "MISMATCH"))
        earned = total = 0.0
        for r in grp:
            if r.status == "PASS":
                earned += _PASS_WEIGHT
                total += _PASS_WEIGHT
            else:
                total += _SEV_WEIGHT.get(r.severity, 1)
        score = round(earned / total * 100, 2) if total else 100.0
        checks.append({
            "check": cid,
            "label": labels.get(cid, cid),
            "description": _DESC.get(cid, labels.get(cid, cid)),
            "scope": scope,
            "score": score,
            "verdict": _verdict(score),
            "passed": n_pass,
            "failed": n_fail,
            "missing": n_miss,
            "total": n_pass + n_fail + n_miss,
            "weight_earned": round(earned, 2),
            "weight_total": round(total, 2),
        })
        scope_earned += earned
        scope_total += total
    return checks, scope_earned, scope_total


def _result_row(r, scope: str) -> dict:
    """One CheckResult → a testoutput `all_results` / `gaps` row.
    `source_value` = the JSON (source of truth); `json_value` = the PBIP value."""
    return {
        "check_id": r.check_id,
        "attribute": r.sub_id,
        "status": r.status,
        "source_value": r.src_value,
        "json_value": r.tgt_value,
        "note": r.note,
        "severity": r.severity,
    }


def run_validation(jsons: list[dict],
                    semantic_model_dir: str | None,
                    report_dir: str | None,
                    tmp_dir: str):
    """Route each JSON to the right validator, run it, and assemble the
    testoutput.json-shaped result(s).

    jsons              : 1 or 2 parsed extraction JSONs.
    semantic_model_dir : path to the `<Name>.SemanticModel` folder (or None).
    report_dir         : path to the `<Name>.Report` folder (or None).
    tmp_dir            : a scratch folder for per-JSON temp files.

    Return value
    ------------
    * 1 input JSON  → a single result dict (a full single extraction is
                      validated against both folders and reported as one).
    * 2 input JSONs → a LIST of two result dicts — ONE PER INPUT JSON. The
                      tables JSON gets its own semantic result, the report
                      JSON gets its own report result; they are NOT merged.
    Every result dict is in the testoutput.json shape.
    """
    if not jsons:
        raise ValueError("No input JSON provided.")
    if len(jsons) > 2:
        raise ValueError(f"Expected 1 or 2 JSONs, got {len(jsons)}.")

    # Decide which validator(s) each JSON feeds.
    #   * 2 JSONs (thin / live-connect pair) — strict split: the JSON WITH
    #     tables is the semantic model, the JSON WITHOUT tables is the report.
    #     A dataset extraction often still carries one vestigial blank page;
    #     it must NOT be report-validated against the real multi-page report.
    #   * 1 JSON — a full single extraction: run whichever validators its
    #     content supports (semantic if it has tables, report if it has pages).
    routes: list[tuple[int, dict, bool, bool]] = []   # (idx, data, do_sem, do_rep)
    if len(jsons) == 2:
        for idx, data in enumerate(jsons, start=1):
            has_tables, _ = classify(data)
            routes.append((idx, data, has_tables, not has_tables))
    else:
        for idx, data in enumerate(jsons, start=1):
            has_tables, has_pages = classify(data)
            routes.append((idx, data, has_tables, has_pages))

    # Validate each JSON independently, keeping its results separate.
    per_json: list[tuple[dict, list, list, list, list]] = []
    for idx, data, do_sem, do_rep in routes:
        json_path = os.path.join(tmp_dir, f"input_{idx}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        s_res: list = []
        r_res: list = []
        ran: list[str] = []
        skipped: list[str] = []

        # tables  → semantic validator (vs .SemanticModel)
        if do_sem:
            if not semantic_model_dir or not os.path.isdir(semantic_model_dir):
                skipped.append(f"JSON #{idx}: routed to semantic but no .SemanticModel folder in the zip(s).")
            else:
                v = _sem.FESemanticValidator(json_path, semantic_model_dir)
                v.run_all()
                s_res.extend(v.results)
                ran.append("semantic")

        # no tables → report validator (vs .Report)
        if do_rep:
            if not report_dir or not os.path.isdir(report_dir):
                skipped.append(f"JSON #{idx}: routed to report but no .Report folder in the zip(s).")
            else:
                v = _rep.FEReportValidator(json_path, report_dir)
                v.run_all()
                r_res.extend(v.results)
                ran.append("report")

        if not do_sem and not do_rep:
            skipped.append(f"JSON #{idx}: no tables and no visuals — nothing to validate.")

        per_json.append((data, s_res, r_res, ran, skipped))

    if not any(s or r for _, s, r, _, _ in per_json):
        all_skipped = [m for _, _, _, _, sk in per_json for m in sk]
        raise ValueError(
            "Nothing was validated. " + (" ".join(all_skipped) or
            "Check that the JSON carries tables/visuals and the matching "
            "PBIP folder is present in the uploaded zip(s)."))

    # 1 input → one combined result; 2 inputs → one result per input JSON.
    if len(per_json) == 1:
        data, s_res, r_res, ran, skipped = per_json[0]
        return _assemble(extract_meta([data]), s_res, r_res, ran, skipped)

    return [_assemble(extract_meta([data]), s_res, r_res, ran, skipped)
            for data, s_res, r_res, ran, skipped in per_json]


def _assemble(meta: dict, sem_results: list, rep_results: list,
              ran: list, skipped: list) -> dict:
    """Fold the raw CheckResults into the testoutput.json shape."""
    ts = datetime.now().isoformat()

    sem_checks, sem_e, sem_t = _summarize(sem_results, _sem.CHECK_LABELS, "semantic")
    rep_checks, rep_e, rep_t = _summarize(rep_results, _rep.CHECK_LABELS, "visual")

    sem_score = round(sem_e / sem_t * 100, 2) if sem_t else None
    vis_score = round(rep_e / rep_t * 100, 2) if rep_t else None
    overall_e, overall_t = sem_e + rep_e, sem_t + rep_t
    overall_score = round(overall_e / overall_t * 100, 2) if overall_t else None

    check_summary = sem_checks + rep_checks

    # all_results (every row) + gaps (FAIL / MISSING / MISMATCH only).
    all_results, gaps = [], []
    for r in sem_results:
        row = _result_row(r, "semantic")
        all_results.append(row)
        if r.status in ("FAIL", "MISSING", "MISMATCH"):
            gaps.append(row)
    for r in rep_results:
        row = _result_row(r, "visual")
        all_results.append(row)
        if r.status in ("FAIL", "MISSING", "MISMATCH"):
            gaps.append(row)
    gaps.sort(key=lambda g: (_sem.SEV_ORDER.get(g["severity"], 9), g["check_id"]))

    severity_summary: dict[str, int] = {}
    for g in gaps:
        severity_summary[g["severity"]] = severity_summary.get(g["severity"], 0) + 1

    score_breakdown = {
        "overall": {
            "score": overall_score,
            "verdict": _verdict(overall_score),
            "formula": _FORMULA,
            "threshold": f"PASS if score >= {int(_THRESHOLD)}%",
        },
        "semantic": {
            "scope": "semantic",
            "score": sem_score,
            "verdict": _verdict(sem_score),
            "weight_earned": round(sem_e, 2),
            "weight_total": round(sem_t, 2),
            "checks": sem_checks,
        },
        "visual": {
            "scope": "visual",
            "score": vis_score,
            "verdict": _verdict(vis_score),
            "weight_earned": round(rep_e, 2),
            "weight_total": round(rep_t, 2),
            "checks": rep_checks,
        },
    }

    out = {
        "workbook_id": meta["workbook_id"],
        "file_name": meta["file_name"],
        "tool_name": meta["tool_name"],
        "score": overall_score,
        "verdict": _verdict(overall_score),
        "semantic_score": sem_score,
        "semantic_verdict": _verdict(sem_score),
        "visual_score": vis_score,
        "visual_verdict": _verdict(vis_score),
        "score_breakdown": score_breakdown,
        "total_checks": len(all_results),
        "gaps_count": len(gaps),
        "timestamp": ts,
        "validators_run": ran,
        "validators_skipped": skipped,
        "check_summary": check_summary,
        "report": {
            "workbook_id": meta["workbook_id"],
            "pbix_path": "",
            "json_path": "",
            "timestamp": ts,
            "overall_score": overall_score,
            "overall_verdict": _verdict(overall_score),
            "semantic_score": sem_score,
            "semantic_verdict": _verdict(sem_score),
            "visual_score": vis_score,
            "visual_verdict": _verdict(vis_score),
            "check_summary": check_summary,
            "all_results": all_results,
        },
        "gap_report": {
            "workbook_id": meta["workbook_id"],
            "timestamp": ts,
            "total_gaps": len(gaps),
            "severity_summary": severity_summary,
            "gaps": gaps,
        },
        "excel_base64": "",
    }
    return out
