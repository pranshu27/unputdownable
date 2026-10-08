"""
fe_semantic_validator.py
========================
Validates a target PBIP SemanticModel folder against an Enriched (FE) JSON file.

Direction : Enriched JSON  →  PBIP  (JSON is source of truth, PBIP is validated)
Checks    : S1 – S18  (61 sub-checks)

Usage
-----
python fe_semantic_validator.py \
    --json  path/to/enriched_semantic.json \
    --pbip  path/to/MyReport.SemanticModel \
    --out   ./output

Outputs (written to --out folder)
---------
  fe_semantic_<timestamp>_full.csv      All check results
  fe_semantic_<timestamp>_summary.json  Score + per-group counts
  fe_semantic_<timestamp>_gaps.json     FAIL / MISSING / MISMATCH only, sorted CRITICAL first
  fe_semantic_<timestamp>_deploy.json   Deployment flags (Power Automate, Dynamic RLS, etc.)
"""

import argparse, csv, json, os, re, sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    check_id:   str
    sub_id:     str
    status:     str          # PASS | FAIL | MISSING | MISMATCH | SKIP | INFO
    severity:   str          # CRITICAL | HIGH | MEDIUM | LOW | INFO
    src_value:  Optional[str]
    tgt_value:  Optional[str]
    note:       str
    deploy_flag: bool = False


SEV_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}

CHECK_LABELS = {
    "S1":  "Tables",
    "S2":  "Columns",
    "S3":  "Calculated Columns",
    "S4":  "Measures & KPI",
    "S5":  "Hierarchies",
    "S6":  "Relationships & USERELATIONSHIP",
    "S7":  "M Expressions",
    "S8":  "DAX Calculated Tables",
    "S9":  "RLS Roles",
    "S10": "Model Metadata",
    "S11": "Shared Expressions",
    "S12": "OLS Column Permissions",
    "S13": "What-If Parameters",
    "S14": "Field Parameter Tables",
    "S15": "Incremental Refresh",
    "S16": "Dynamic RLS Detection",
    "S17": "Perspectives",
    "S18": "Cultures & Translations",
}
ALL_CHECKS = [f"S{i}" for i in range(1, 19)]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _norm(expr: Optional[str]) -> str:
    """Normalise a DAX / M expression for comparison."""
    if not expr:
        return ""
    s = str(expr)
    s = re.sub(r"\s+", " ", s).strip().lower()
    s = s.replace('"', "'")
    return s

_DTYPE_MAP = {
    "int64": "integer", "int32": "integer", "int16": "integer",
    "double": "decimal", "float": "decimal", "single": "decimal",
    "datetime": "datetime", "date": "datetime",
    "boolean": "boolean", "bool": "boolean",
    "string": "string", "text": "string",
    "binary": "binary",
}

def _norm_dtype(dt: Optional[str]) -> str:
    if not dt:
        return ""
    return _DTYPE_MAP.get(dt.lower().strip(), dt.lower().strip())



def _sval(v) -> str:
    if v is None:
        return "None"
    if isinstance(v, list):
        return "; ".join(str(x) for x in v)
    return str(v)


def _read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _read_tmdl(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# PBIP SemanticModel extractor
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Auto-generated Power BI system tables — never in source JSON, always in PBIP
# Skip these in all checks to avoid false-positive MISSING / MISMATCH noise
# ─────────────────────────────────────────────────────────────────────────────
_AUTO_TABLE_PATTERNS = (
    "datetabletemplate",   # Auto date/time hidden template table
    "localdatetable",      # Auto date/time per-column local date table
    "dateautotable",       # Older auto date table variant
)

def _is_auto_table(name: str) -> bool:
    """Returns True if the table is a Power BI auto-generated system table."""
    n = name.lower()
    return any(n.startswith(p) for p in _AUTO_TABLE_PATTERNS)


class PbipSemanticExtractor:
    """Reads a PBIP SemanticModel folder and exposes structured data."""

    def __init__(self, pbip_root: str):
        self.root = Path(pbip_root)
        # Try both with and without .SemanticModel suffix
        defn = self.root / "definition"
        if not defn.exists():
            defn = self.root / (self.root.name + ".SemanticModel") / "definition"
        self.defn = defn
        self._tables_dir = self.defn / "tables"
        self._rels_file  = self.defn / "relationships.tmdl"
        self._roles_file = self.defn / "roles.tmdl"
        self._expr_file  = self.defn / "expressions.tmdl"
        self._persp_file = self.defn / "perspectives.tmdl"
        self._cult_file  = self.defn / "cultures.tmdl"
        self._model_file = self.defn / "model.tmdl"
        self._pbism_file = self.root / "definition.pbism"

    # ── Tables ────────────────────────────────────────────────────
    def table_names(self) -> list:
        if not self._tables_dir.exists():
            return []
        return [f.stem for f in self._tables_dir.glob("*.tmdl")]

    def _table_raw(self, name: str) -> str:
        p = self._tables_dir / f"{name}.tmdl"
        if not p.exists():
            # try URL-encoded name
            safe = name.replace(" ", "%20")
            p = self._tables_dir / f"{safe}.tmdl"
        return _read_tmdl(p)

    def table_meta(self, name: str) -> dict:
        raw = self._table_raw(name)
        meta = {"storage_mode": "import", "isHidden": False, "description": None}
        for line in raw.splitlines():
            s = line.strip()
            if s.startswith("storageMode:"):
                meta["storage_mode"] = s.split(":", 1)[1].strip()
            elif "= m" in s and s.strip().startswith("partition"):
                # partition 'Name' = m  — explicit import mode
                meta["storage_mode"] = "import"
            if s == "isHidden" or s == "isHidden: true":
                meta["isHidden"] = True
            if s.startswith("description:"):
                meta["description"] = s.split(":", 1)[1].strip().strip("'\"")
        return meta

    def columns(self, table_name: str) -> dict:
        """Returns {col_name: {dataType, isHidden, summarizeBy, sortByColumn, displayFolder}}"""
        raw = self._table_raw(table_name)
        cols = {}
        current = None
        for line in raw.splitlines():
            s = line.strip()
            indent = len(line) - len(line.lstrip("\t"))
            if s.startswith("column ") and not s.startswith("column '"):
                current = s[7:].strip().strip("'\"")
                cols[current] = {"dataType": None, "isHidden": False,
                                 "summarizeBy": None, "sortByColumn": None,
                                 "displayFolder": None, "calculated": False}
            elif s.startswith("column '"):
                current = s[8:].split("'")[0]
                cols[current] = {"dataType": None, "isHidden": False,
                                 "summarizeBy": None, "sortByColumn": None,
                                 "displayFolder": None, "calculated": False}
            elif s.startswith("calculatedColumn") or (current and s.startswith("expression =")):
                if current:
                    cols[current]["calculated"] = True
            elif current:
                if s.startswith("dataType:"):
                    cols[current]["dataType"] = s.split(":", 1)[1].strip()
                elif s in ("isHidden", "isHidden: true"):
                    cols[current]["isHidden"] = True
                elif s.startswith("summarizeBy:"):
                    cols[current]["summarizeBy"] = s.split(":", 1)[1].strip()
                elif s.startswith("sortByColumn:"):
                    cols[current]["sortByColumn"] = s.split(":", 1)[1].strip().strip("'\"")
                elif s.startswith("displayFolder:"):
                    cols[current]["displayFolder"] = s.split(":", 1)[1].strip().strip("'\"")
        return cols

    def calc_columns(self, table_name: str) -> dict:
        """Returns {col_name: {expression, dataType}}"""
        raw = self._table_raw(table_name)
        cols = {}
        current = None
        in_expr = False
        expr_lines = []
        for line in raw.splitlines():
            s = line.strip()
            if s.startswith("calculatedTableColumn ") or s.startswith("calculatedColumn "):
                kw = "calculatedTableColumn " if s.startswith("calculatedTableColumn ") else "calculatedColumn "
                current = s[len(kw):].strip().strip("'\"")
                cols[current] = {"expression": None, "dataType": None}
                in_expr = False
                expr_lines = []
            elif current:
                if s.startswith("expression:") or s.startswith("expression ="):
                    in_expr = True
                    rest = s.split("=", 1)[1].strip() if "=" in s else s.split(":", 1)[1].strip()
                    if rest:
                        expr_lines.append(rest)
                elif in_expr and s.startswith("'"):
                    expr_lines.append(s)
                elif in_expr and not s.startswith("'") and s:
                    cols[current]["expression"] = " ".join(expr_lines)
                    in_expr = False
                    expr_lines = []
                if s.startswith("dataType:"):
                    cols[current]["dataType"] = s.split(":", 1)[1].strip()
        return cols

    def measures(self, table_name: str) -> dict:
        """Returns {measure_name: {expression, formatString, isHidden, displayFolder, description, kpi}}"""
        raw = self._table_raw(table_name)
        measures = {}
        current = None
        expr_lines = []
        in_expr = False
        for line in raw.splitlines():
            s = line.strip()
            if s.startswith("measure "):
                if current and expr_lines:
                    measures[current]["expression"] = " ".join(expr_lines)
                name_part = s[8:].strip()
                if "=" in name_part:
                    current = name_part.split("=")[0].strip().strip("'\"")
                    expr_lines = [name_part.split("=", 1)[1].strip()]
                else:
                    current = name_part.strip().strip("'\"")
                    expr_lines = []
                in_expr = True
                measures[current] = {"expression": None, "formatString": None,
                                     "isHidden": False, "displayFolder": None,
                                     "description": None, "kpi": {}}
            elif current:
                if in_expr and (s.startswith("'") or s.startswith("=") or
                                (not s.startswith(("formatString", "isHidden", "displayFolder",
                                                   "description", "kpi", "annotation", "changedProperty")))):
                    if s.startswith("formatString:") or s.startswith("isHidden") or \
                       s.startswith("displayFolder:") or s.startswith("description:") or \
                       s.startswith("kpi"):
                        in_expr = False
                        measures[current]["expression"] = " ".join(expr_lines)
                    else:
                        expr_lines.append(s)
                if s.startswith("formatString:"):
                    measures[current]["formatString"] = s.split(":", 1)[1].strip().strip("'\"")
                    in_expr = False
                elif s in ("isHidden", "isHidden: true"):
                    measures[current]["isHidden"] = True
                elif s.startswith("displayFolder:"):
                    measures[current]["displayFolder"] = s.split(":", 1)[1].strip().strip("'\"")
                elif s.startswith("description:"):
                    measures[current]["description"] = s.split(":", 1)[1].strip().strip("'\"")
                elif s.startswith("kpi"):
                    kpi = measures[current]["kpi"]
                    if "statusExpression" in s:
                        kpi["statusExpression"] = s.split("=", 1)[-1].strip()
                    if "targetExpression" in s:
                        kpi["targetExpression"] = s.split("=", 1)[-1].strip()
                    if "trendExpression" in s:
                        kpi["trendExpression"] = s.split("=", 1)[-1].strip()
        if current and expr_lines and not measures[current]["expression"]:
            measures[current]["expression"] = " ".join(expr_lines)
        return measures

    def hierarchies(self, table_name: str) -> dict:
        raw = self._table_raw(table_name)
        hierarchies = {}
        current = None
        for line in raw.splitlines():
            s = line.strip()
            if s.startswith("hierarchy "):
                current = s[10:].strip().strip("'\"")
                hierarchies[current] = {"isHidden": False, "levels": []}
            elif current:
                if s in ("isHidden", "isHidden: true"):
                    hierarchies[current]["isHidden"] = True
                elif s.startswith("level "):
                    lvl_name = s[6:].strip().strip("'\"")
                    hierarchies[current]["levels"].append({"name": lvl_name, "column": None})
                elif s.startswith("column:") and hierarchies[current]["levels"]:
                    hierarchies[current]["levels"][-1]["column"] = s.split(":", 1)[1].strip().strip("'\"")
        return hierarchies

    def partitions(self, table_name: str) -> dict:
        """Returns {partition_name: {mode, expression, type}}"""
        raw = self._table_raw(table_name)
        parts = {}
        current = None
        expr_lines = []
        in_expr = False
        for line in raw.splitlines():
            s = line.strip()
            if s.startswith("partition "):
                if current and expr_lines:
                    parts[current]["expression"] = " ".join(expr_lines)
                current = s[10:].strip().strip("'\"")
                parts[current] = {"mode": None, "expression": None, "type": "m"}
                expr_lines = []
                in_expr = False
            elif current:
                if s.startswith("mode:"):
                    parts[current]["mode"] = s.split(":", 1)[1].strip()
                elif s == "calculatedTable" or s == "type: calculatedTable":
                    parts[current]["type"] = "calculatedTable"
                elif s.startswith("expression =") or s.startswith("expression:") or s.startswith("source =") or s.startswith("source="):
                    in_expr = True
                    rest = s.split("=", 1)[1].strip() if "=" in s else s.split(":", 1)[1].strip()
                    if rest:
                        expr_lines.append(rest)
                elif in_expr:
                    if s and not s.startswith(("mode:", "annotation", "changedProperty", "lineageTag")):
                        expr_lines.append(s)
                    else:
                        parts[current]["expression"] = " ".join(expr_lines)
                        in_expr = False
                        expr_lines = []
        if current and expr_lines and not parts.get(current, {}).get("expression"):
            parts[current]["expression"] = " ".join(expr_lines)
        return parts

    def relationships(self) -> list:
        raw = _read_tmdl(self._rels_file)
        rels = []
        current = None
        for line in raw.splitlines():
            s = line.strip()
            if s.startswith("relationship"):
                current = {"from_table": None, "from_column": None,
                           "to_table": None, "to_column": None,
                           "cardinality": None, "crossFilter": "single",
                           "isActive": True}
                rels.append(current)
                # Handle inline TMDL format:
                # relationship 'Table1'.'Col1' to 'Table2'.'Col2'
                rest = s[len("relationship"):].strip()
                import re as _re2
                m = _re2.match(
                    r"['\"]?([^\'\".\s]+)['\"]?\.['\"]?([^\'\".\s]+)['\"]?"
                    r"\s+to\s+"
                    r"['\"]?([^\'\".\s]+)['\"]?\.['\"]?([^\'\".\s]+)['\"]?",
                    rest, _re2.IGNORECASE
                )
                if m:
                    current["from_table"]  = m.group(1).strip("\'\"")
                    current["from_column"] = m.group(2).strip("\'\"")
                    current["to_table"]    = m.group(3).strip("\'\"")
                    current["to_column"]   = m.group(4).strip("\'\"")
            elif current:
                if s.startswith("fromTable:"):
                    current["from_table"] = s.split(":", 1)[1].strip().strip("'\"")
                elif s.startswith("fromColumn:"):
                    # Format A: fromColumn: 'Table'.'Column'  (table+col combined)
                    # Format B: fromColumn: ColumnName        (col only, table from fromTable)
                    val = s.split(":", 1)[1].strip()
                    m_tc = re.match(r"['\"]?([^\'\"]+)['\"]?\.['\"]?([^\'\"]+)['\"]?$", val)
                    if m_tc and "." in val:
                        parts = val.split(".")
                        # 'Table Name'.'Column Name' — may have spaces inside quotes
                        tc_m = re.findall(r"'([^']+)'", val)
                        if len(tc_m) == 2:
                            current["from_table"]  = tc_m[0]
                            current["from_column"] = tc_m[1]
                        elif len(parts) >= 2:
                            current["from_table"]  = parts[0].strip().strip("'\"")
                            current["from_column"] = parts[-1].strip().strip("'\"")
                    else:
                        current["from_column"] = val.strip().strip("'\"")
                elif s.startswith("toTable:"):
                    current["to_table"] = s.split(":", 1)[1].strip().strip("'\"")
                elif s.startswith("toColumn:"):
                    val = s.split(":", 1)[1].strip()
                    if "." in val:
                        tc_m = re.findall(r"'([^']+)'", val)
                        if len(tc_m) == 2:
                            current["to_table"]  = tc_m[0]
                            current["to_column"] = tc_m[1]
                        else:
                            parts = val.split(".")
                            current["to_table"]  = parts[0].strip().strip("'\"")
                            current["to_column"] = parts[-1].strip().strip("'\"")
                    else:
                        current["to_column"] = val.strip().strip("'\"")
                elif s.startswith("cardinality:"):
                    current["cardinality"] = s.split(":", 1)[1].strip()
                elif s.startswith("type:") and "relationship" not in s:
                    pass  # skip type lines
                elif s.startswith("crossFilteringBehavior:"):
                    current["crossFilter"] = s.split(":", 1)[1].strip()
                elif s in ("isActive: false", "isActive:false"):
                    current["isActive"] = False
        # Drop entries where from/to could not be parsed — avoids NoneType errors
        complete = []
        for r in rels:
            if all(r.get(k) for k in ("from_table", "from_column", "to_table", "to_column")):
                # TMDL default cardinality when line is absent = manyToOne
                if not r.get("cardinality"):
                    r["cardinality"] = "manyToOne"
                complete.append(r)
            else:
                print(f"  [S6 WARNING] Skipping unparseable relationship: {r}")
        return complete

    def roles(self) -> dict:
        raw = _read_tmdl(self._roles_file)
        roles = {}
        current = None
        current_table = None
        for line in raw.splitlines():
            s = line.strip()
            if s.startswith("role "):
                current = s[5:].strip().strip("'\"")
                roles[current] = {"modelPermission": None,
                                  "tableFilters": {},
                                  "columnPermissions": {}}
            elif current:
                if s.startswith("modelPermission:"):
                    roles[current]["modelPermission"] = s.split(":", 1)[1].strip()
                elif s.startswith("tablePermission "):
                    current_table = s[16:].strip().strip("'\"")
                    roles[current]["tableFilters"][current_table] = None
                elif s.startswith("filterExpression:") and current_table:
                    roles[current]["tableFilters"][current_table] = s.split(":", 1)[1].strip()
                elif s.startswith("columnPermission ") and current_table:
                    col = s[17:].strip().strip("'\"")
                    roles[current]["columnPermissions"].setdefault(current_table, {})[col] = None
                elif s.startswith("permission:") and current_table:
                    tbl_cols = roles[current]["columnPermissions"].get(current_table, {})
                    if tbl_cols:
                        last_col = list(tbl_cols.keys())[-1]
                        tbl_cols[last_col] = s.split(":", 1)[1].strip()
        return roles

    def shared_expressions(self) -> dict:
        raw = _read_tmdl(self._expr_file)
        exprs = {}
        current = None
        expr_lines = []
        kind = None
        for line in raw.splitlines():
            s = line.strip()
            if s.startswith("expression "):
                if current and expr_lines:
                    exprs[current]["expression"] = " ".join(expr_lines)
                current = s[11:].strip().strip("'\"").rstrip("=").strip()
                exprs[current] = {"expression": None, "kind": None}
                expr_lines = []
                kind = None
            elif current:
                if s.startswith("kind:"):
                    exprs[current]["kind"] = s.split(":", 1)[1].strip()
                elif s.startswith("expression =") or s.startswith("expression:"):
                    rest = s.split("=", 1)[1].strip() if "=" in s else ""
                    if rest:
                        expr_lines.append(rest)
                elif s.startswith("'") or (expr_lines and s):
                    expr_lines.append(s)
        if current and expr_lines and not exprs[current]["expression"]:
            exprs[current]["expression"] = " ".join(expr_lines)
        return exprs

    def perspectives(self) -> dict:
        raw = _read_tmdl(self._persp_file)
        persp = {}
        current = None
        for line in raw.splitlines():
            s = line.strip()
            if s.startswith("perspective "):
                current = s[12:].strip().strip("'\"")
                persp[current] = {"tables": [], "columns": [], "measures": []}
            elif current:
                if s.startswith("perspectiveTable "):
                    persp[current]["tables"].append(s[17:].strip().strip("'\""))
                elif s.startswith("perspectiveColumn "):
                    persp[current]["columns"].append(s[18:].strip().strip("'\""))
                elif s.startswith("perspectiveMeasure "):
                    persp[current]["measures"].append(s[19:].strip().strip("'\""))
        return persp

    def cultures(self) -> dict:
        raw = _read_tmdl(self._cult_file)
        cultures = {}
        current = None
        for line in raw.splitlines():
            s = line.strip()
            if s.startswith("culture "):
                current = s[8:].strip().strip("'\"")
                cultures[current] = {"translations": []}
            elif current and s.startswith("translatedCaption:"):
                cultures[current]["translations"].append(s.split(":", 1)[1].strip())
        return cultures

    def compatibility_level(self) -> Optional[str]:
        raw = _read_tmdl(self._pbism_file) if self._pbism_file.exists() else ""
        for line in raw.splitlines():
            s = line.strip()
            if "compatibilityLevel" in s:
                return s.split(":", 1)[-1].strip()
        return None

    def model_name(self) -> Optional[str]:
        raw = _read_tmdl(self._model_file)
        for line in raw.splitlines():
            s = line.strip()
            if s.startswith("model "):
                return s[6:].strip().strip("'\"")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# JSON extractor — reads enriched semantic JSON
# ─────────────────────────────────────────────────────────────────────────────

class EnrichedJsonExtractor:
    """
    Adapts the actual RE/FE JSON schema to the field names the validator expects.

    Actual JSON top-level structure:
      d['result']['tables']        — list of table objects
      d['result']['relationships'] — list of relationship objects
      d['result']['calculations']  — list of measure/calc objects (NOT nested inside tables)

    Key field mappings resolved here:
      table.hidden          -> is_hidden
      table.table_type      -> storage_mode (calculated, dimension, fact)
      column.data_type      -> data_type  (already matching)
      column.hidden         -> is_hidden
      relationship.left_table_id  -> from_table  (slug -> resolved to real name)
      relationship.left_column    -> from_column
      relationship.active         -> is_active
      relationship.filter_direction bidirectional -> cross_filter_direction both
      calculation.expressions.dax -> expression
      calculation.display.hidden  -> is_hidden
      calculation.display.folder  -> display_folder
    """

    def __init__(self, data: dict):
        # Support both wrapped (d['result']) and flat structures
        if 'result' in data:
            self.r = data['result']
        elif 'tables' in data:
            self.r = data
        else:
            self.r = data.get('data_model', data)

        # Build slug -> actual table name map for resolving relationship table IDs
        self._slug_to_name = {}
        # Build lowercase name -> actual name map for Tableau UUID resolution (Fix 2)
        self._name_to_name = {}
        for t in self.r.get('tables', []):
            name = t.get('name', '')
            slug = 'tbl_' + re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
            self._slug_to_name[slug] = name
            self._name_to_name[name.lower()] = name

        # Build measure lookup by home_table for S4 checks
        # calculations is a flat list at result level, not nested inside tables
        self._measures_by_table: dict = {}
        for c in self.r.get('calculations', []):
            ht = c.get('home_table', '')
            self._measures_by_table.setdefault(ht, []).append(c)

    def _resolve_table_id(self, tid: str) -> str:
        """Resolve a slugified table ID back to the real table name.

        Supports two ID formats:
          - Power BI style : plain slug, e.g. 'tbl_sales'
          - Tableau UUID   : compound path ending with $(tablename)(table)$(uuid)
                             e.g. '...$tbl_sales(table)$cbeaa8cb63b5(uuid)'
        """
        if not tid:
            return ''
        # 1. Direct slug match (Power BI style: 'tbl_sales')
        if tid in self._slug_to_name:
            return self._slug_to_name[tid]
        # 2. Tableau compound UUID: extract table name from '$(name)(table)$' segment.
        #    Only fires when literal '(table)' is present — Power BI IDs never contain
        #    this segment, so they fall through unchanged to step 3.
        m = re.search(r'\$([^$]+)\(table\)\$', tid)
        if m:
            extracted = m.group(1)
            # Prefer exact name match (case-insensitive) over slug lookup
            if extracted.lower() in self._name_to_name:
                return self._name_to_name[extracted.lower()]
            return extracted  # return the clean name even if not in the table list
        # 3. Fallback: normalised alphanum match (original logic — covers edge cases)
        tid_norm = re.sub(r'[^a-z0-9]', '', tid.lower())
        for slug, name in self._slug_to_name.items():
            slug_norm = re.sub(r'[^a-z0-9]', '', slug.lower())
            if tid_norm == slug_norm or tid_norm in slug_norm or slug_norm in tid_norm:
                return name
        return tid  # return as-is if no match

    def tables(self) -> list:
        """Return tables in the normalised format the validator expects."""
        result = []
        for t in self.r.get('tables', []):
            name = t.get('name', '')
            ttype = t.get('table_type', '')
            # Columns — use 'hidden' field, map to is_hidden
            cols = []
            for c in t.get('columns', []):
                cols.append({
                    'name':           c.get('name', ''),
                    'data_type':      c.get('data_type', ''),
                    'is_hidden':      c.get('hidden', False) or False,
                    'isHidden':       c.get('hidden', False) or False,
                    'summarize_by':   c.get('summarize_by', c.get('summarizeBy')),
                    'sort_by_column': c.get('sort_by_column', c.get('sortByColumn')),
                    'display_folder': c.get('display_folder', c.get('displayFolder')),
                    'description':    c.get('description'),
                })
            # Hierarchies — already in correct format {name, levels:[{name,column,ordinal}]}
            hierarchies = []
            for h in t.get('hierarchies', []):
                hierarchies.append({
                    'name':     h.get('name', ''),
                    'is_hidden': h.get('hidden', False) or False,
                    'levels':   [{'name': l.get('name',''), 'column': l.get('column','')}
                                 for l in sorted(h.get('levels', []), key=lambda x: x.get('ordinal', 0))],
                })
            # M expression from ingestion steps
            m_expr = None
            for step in t.get('ingestion', {}).get('steps', []):
                ne = step.get('native_expressions', {})
                if ne and ne.get('powerquery'):
                    m_expr = ne['powerquery']
                    break

            # Measures come from the flat calculations list, not from the table object
            measures = []
            for c in self._measures_by_table.get(name, []):
                measures.append({
                    'name':           c.get('name', ''),
                    'expression':     c.get('expressions', {}).get('dax', ''),
                    'dax_expression': c.get('expressions', {}).get('dax', ''),
                    'format_string':  c.get('format_string'),
                    'is_hidden':      c.get('display', {}).get('hidden', False) or False,
                    'isHidden':       c.get('display', {}).get('hidden', False) or False,
                    'display_folder': c.get('display', {}).get('folder'),
                    'description':    c.get('description'),
                    'kpi':            c.get('kpi', {}),
                })

            result.append({
                'name':         name,
                'storage_mode': ttype,
                'is_hidden':    t.get('hidden', False) or False,
                'isHidden':     t.get('hidden', False) or False,
                'description':  t.get('description'),
                'columns':      cols,
                'hierarchies':  hierarchies,
                'measures':     measures,
                'm_expression': m_expr,
                # calculated tables: table_type == 'calculated'
                'dax_expression': None,  # populated below if calculated
                'calculated_columns': [],  # columns of calculated type not split out in this schema
            })
        return result

    def table_names(self) -> list:
        return [t.get('name', '') for t in self.r.get('tables', [])]

    def relationships(self) -> list:
        """Map JSON relationship schema to validator's expected keys."""
        result = []
        for r in self.r.get('relationships', []):
            fd = r.get('filter_direction', '')
            cross = 'both' if 'bidirectional' in fd.lower() else 'single'
            result.append({
                'from_table':             self._resolve_table_id(r.get('left_table_id', '')),
                'from_column':            r.get('left_column', ''),
                'to_table':               self._resolve_table_id(r.get('right_table_id', '')),
                'to_column':              r.get('right_column', ''),
                'cardinality':            r.get('cardinality', ''),
                'cross_filter_direction': cross,
                'is_active':              r.get('active', True),
                'isActive':               r.get('active', True),
            })
        return result

    def roles(self) -> list:
        return self.r.get('roles', self.r.get('rls_roles', []))

    def shared_expressions(self) -> list:
        return self.r.get('shared_expressions', self.r.get('parameters', []))

    def perspectives(self) -> list:
        return self.r.get('perspectives', [])

    def cultures(self) -> list:
        return self.r.get('cultures', [])

    def metadata(self) -> dict:
        return {
            'name':                self.r.get('name'),
            'compatibility_level': self.r.get('compatibility_level', self.r.get('compatibilityLevel')),
            'default_date_table':  self.r.get('default_date_table'),
            'sensitivity_label':   self.r.get('sensitivity_label'),
        }


class FESemanticValidator:
    def __init__(self, json_path: str, pbip_path: str):
        raw = _read_json(json_path)
        self.src = EnrichedJsonExtractor(raw)
        self.tgt = PbipSemanticExtractor(pbip_path)
        self.results: list[CheckResult] = []
        self.deploy_flags: list[dict] = []

    def _log(self, check_id: str, sub_id: str, status: str, severity: str,
             src_val, tgt_val, note: str, deploy_flag: bool = False):
        r = CheckResult(check_id=check_id, sub_id=sub_id, status=status,
                        severity=severity, src_value=_sval(src_val),
                        tgt_value=_sval(tgt_val), note=note,
                        deploy_flag=deploy_flag)
        self.results.append(r)
        if deploy_flag:
            self.deploy_flags.append({
                "check": f"{check_id}.{sub_id}", "severity": severity,
                "note": note, "src": _sval(src_val)
            })

    def _pass(self, cid, sid, sev, src, tgt, note=""):
        self._log(cid, sid, "PASS", sev, src, tgt, note or "OK")

    def _fail(self, cid, sid, sev, src, tgt, note, deploy=False):
        self._log(cid, sid, "FAIL", sev, src, tgt, note, deploy)

    def _missing(self, cid, sid, sev, src, note, deploy=False):
        self._log(cid, sid, "MISSING", sev, src, None, note, deploy)

    def _mismatch(self, cid, sid, sev, src, tgt, note):
        self._log(cid, sid, "MISMATCH", sev, src, tgt, note)

    def _info(self, cid, sid, src, note):
        self._log(cid, sid, "INFO", "INFO", src, None, note)

    # ══════════════════════════════════════════════════════════════
    # S1 — Tables
    # ══════════════════════════════════════════════════════════════
    def check_s1_tables(self):
        print("[S1] Tables...")
        j_names = self.src.table_names()
        p_names = self.tgt.table_names()
        p_lower = {n.lower(): n for n in p_names}

        # S1.1 existence
        for jn in j_names:
            if _is_auto_table(jn):
                continue
            if jn.lower() in p_lower:
                self._pass("S1", f"table.exists[{jn}]", "CRITICAL", jn, p_lower[jn.lower()])
            else:
                self._missing("S1", f"table.exists[{jn}]", "CRITICAL", jn,
                              f"Table '{jn}' not found in PBIP tables/. All downstream columns, measures, relationships break.")

        # S1.2 count — exclude auto-generated system tables from both sides
        src_c = sum(1 for n in j_names if not _is_auto_table(n))
        tgt_c = sum(1 for n in p_names if not _is_auto_table(n))
        if src_c == tgt_c:
            self._pass("S1", "table.count", "HIGH", src_c, tgt_c)
        else:
            self._mismatch("S1", "table.count", "HIGH", src_c, tgt_c,
                           f"Table count mismatch. JSON={src_c}, PBIP={tgt_c}. "
                           "Extra PBIP tables may be FE-generated artefacts or stale tables.")

        # S1.3-S1.5 per table metadata
        for jt in self.src.tables():
            jn = jt.get("name", "")
            if _is_auto_table(jn):
                continue
            if jn.lower() not in p_lower:
                continue
            meta = self.tgt.table_meta(p_lower[jn.lower()])

            # S1.3 storage mode
            # JSON uses table_type (dimension/fact/calculated), PBIP uses storageMode (import/calculated/directQuery)
            # Mapping: calculated->calculated, dimension/fact->import (default in PBIP)
            jsm_raw = jt.get("storage_mode", None)
            if jsm_raw:
                _SM_MAP = {"dimension": "import", "fact": "import", "calculated": "calculated",
                           "import": "import", "directquery": "directquery", "dual": "dual"}
                jsm = _SM_MAP.get(_norm(jsm_raw), _norm(jsm_raw))
                psm = _norm(meta.get("storage_mode") or "import")
                if jsm == psm:
                    self._pass("S1", f"table.storageMode[{jn}]", "HIGH", jsm_raw, meta.get("storage_mode"))
                else:
                    self._mismatch("S1", f"table.storageMode[{jn}]", "HIGH", jsm_raw,
                                   meta.get("storage_mode"),
                                   f"Storage mode mismatch for table '{jn}'. JSON type='{jsm_raw}' maps to '{jsm}', PBIP='{psm}'.")

            # S1.4 isHidden
            j_hidden = jt.get("is_hidden", jt.get("isHidden", False))
            p_hidden = meta.get("isHidden", False)
            if bool(j_hidden) == bool(p_hidden):
                self._pass("S1", f"table.isHidden[{jn}]", "MEDIUM", j_hidden, p_hidden)
            else:
                self._mismatch("S1", f"table.isHidden[{jn}]", "MEDIUM", j_hidden, p_hidden,
                               f"isHidden mismatch for table '{jn}'.")

            # S1.5 description
            j_desc = jt.get("description", None)
            if j_desc:
                p_desc = meta.get("description")
                if _norm(j_desc) == _norm(p_desc):
                    self._pass("S1", f"table.description[{jn}]", "LOW", j_desc, p_desc)
                else:
                    self._mismatch("S1", f"table.description[{jn}]", "LOW", j_desc, p_desc,
                                   f"Description mismatch for '{jn}'. Affects Q&A / Copilot experience.")

    # ══════════════════════════════════════════════════════════════
    # S2 — Columns
    # ══════════════════════════════════════════════════════════════
    def check_s2_columns(self):
        print("[S2] Columns...")
        p_table_map = {n.lower(): n for n in self.tgt.table_names() if not _is_auto_table(n)}
        for jt in self.src.tables():
            tbl = jt.get("name", "")
            if _is_auto_table(tbl):
                continue
            if tbl.lower() not in p_table_map:
                continue
            p_tbl = p_table_map[tbl.lower()]
            p_cols = self.tgt.columns(p_tbl)
            p_lower = {k.lower(): k for k in p_cols}

            j_cols = jt.get("columns", [])
            for jc in j_cols:
                cname = jc.get("name", jc) if isinstance(jc, dict) else str(jc)
                cdata = jc if isinstance(jc, dict) else {}

                # S2.1 existence
                if cname.lower() not in p_lower:
                    self._missing("S2", f"col.exists[{tbl}.{cname}]", "CRITICAL", f"{tbl}.{cname}",
                                  f"Column '{cname}' missing from table '{tbl}' in PBIP.")
                    continue
                pc = p_cols[p_lower[cname.lower()]]
                self._pass("S2", f"col.exists[{tbl}.{cname}]", "CRITICAL", f"{tbl}.{cname}", cname)

                # S2.2 dataType
                jdt = _norm_dtype(cdata.get("data_type", cdata.get("dataType", None)))
                pdt = _norm_dtype(pc.get("dataType"))
                if jdt and jdt != pdt:
                    self._mismatch("S2", f"col.dataType[{tbl}.{cname}]", "HIGH", jdt, pdt,
                                   f"Data type mismatch for '{tbl}.{cname}'.")
                elif jdt:
                    self._pass("S2", f"col.dataType[{tbl}.{cname}]", "HIGH", jdt, pdt)

                # S2.3 isHidden
                jh = cdata.get("is_hidden", cdata.get("isHidden", False))
                ph = pc.get("isHidden", False)
                if bool(jh) != bool(ph):
                    self._mismatch("S2", f"col.isHidden[{tbl}.{cname}]", "HIGH", jh, ph,
                                   f"isHidden mismatch for '{tbl}.{cname}'.")
                else:
                    self._pass("S2", f"col.isHidden[{tbl}.{cname}]", "HIGH", jh, ph)

                # S2.4 summarizeBy
                jsb = cdata.get("summarize_by", cdata.get("summarizeBy", None))
                if jsb:
                    psb = pc.get("summarizeBy")
                    if _norm(jsb) != _norm(psb):
                        self._mismatch("S2", f"col.summarizeBy[{tbl}.{cname}]", "MEDIUM",
                                       jsb, psb, f"summarizeBy mismatch for '{tbl}.{cname}'.")
                    else:
                        self._pass("S2", f"col.summarizeBy[{tbl}.{cname}]", "MEDIUM", jsb, psb)

                # S2.5 sortByColumn
                jsort = cdata.get("sort_by_column", cdata.get("sortByColumn", None))
                if jsort:
                    psort = pc.get("sortByColumn")
                    if _norm(jsort) != _norm(psort):
                        self._mismatch("S2", f"col.sortByColumn[{tbl}.{cname}]", "MEDIUM",
                                       jsort, psort, f"sortByColumn mismatch for '{tbl}.{cname}'.")
                    else:
                        self._pass("S2", f"col.sortByColumn[{tbl}.{cname}]", "MEDIUM", jsort, psort)

                # S2.6 displayFolder
                jdf = cdata.get("display_folder", cdata.get("displayFolder", None))
                if jdf:
                    pdf = pc.get("displayFolder")
                    if _norm(jdf) != _norm(pdf):
                        self._mismatch("S2", f"col.displayFolder[{tbl}.{cname}]", "LOW",
                                       jdf, pdf, f"displayFolder mismatch for '{tbl}.{cname}'.")
                    else:
                        self._pass("S2", f"col.displayFolder[{tbl}.{cname}]", "LOW", jdf, pdf)

    # ══════════════════════════════════════════════════════════════
    # S3 — Calculated columns
    # ══════════════════════════════════════════════════════════════
    def check_s3_calculated_columns(self):
        print("[S3] Calculated columns...")
        p_table_map = {n.lower(): n for n in self.tgt.table_names() if not _is_auto_table(n)}
        for jt in self.src.tables():
            tbl = jt.get("name", "")
            if _is_auto_table(tbl):
                continue
            if tbl.lower() not in p_table_map:
                continue
            p_tbl = p_table_map[tbl.lower()]
            p_calcs = self.tgt.calc_columns(p_tbl)
            p_lower = {k.lower(): k for k in p_calcs}

            j_calcs = jt.get("calculated_columns", [])
            for jc in j_calcs:
                cname = jc.get("name", "") if isinstance(jc, dict) else str(jc)
                cdata = jc if isinstance(jc, dict) else {}

                # S3.1 existence
                if cname.lower() not in p_lower:
                    self._missing("S3", f"calc_col.exists[{tbl}.{cname}]", "CRITICAL",
                                  f"{tbl}.{cname}",
                                  f"Calculated column '{cname}' missing from '{tbl}' in PBIP.")
                    continue
                pc = p_calcs[p_lower[cname.lower()]]
                self._pass("S3", f"calc_col.exists[{tbl}.{cname}]", "CRITICAL",
                           f"{tbl}.{cname}", cname)

                # S3.2 expression
                jexpr = _norm(cdata.get("expression", cdata.get("dax_expression", None)))
                pexpr = _norm(pc.get("expression"))
                if jexpr and jexpr != pexpr:
                    self._mismatch("S3", f"calc_col.expression[{tbl}.{cname}]", "HIGH",
                                   jexpr[:120], pexpr[:120] if pexpr else None,
                                   f"DAX expression mismatch for calculated column '{tbl}.{cname}'.")
                elif jexpr:
                    self._pass("S3", f"calc_col.expression[{tbl}.{cname}]", "HIGH",
                               jexpr[:80], pexpr[:80])

                # S3.3 dataType
                jdt = _norm_dtype(cdata.get("data_type", cdata.get("dataType", None)))
                pdt = _norm_dtype(pc.get("dataType"))
                if jdt and jdt != pdt:
                    self._mismatch("S3", f"calc_col.dataType[{tbl}.{cname}]", "HIGH",
                                   jdt, pdt, f"Data type mismatch for calculated column '{tbl}.{cname}'.")
                elif jdt:
                    self._pass("S3", f"calc_col.dataType[{tbl}.{cname}]", "HIGH", jdt, pdt)

    # ══════════════════════════════════════════════════════════════
    # S4 — Measures & KPIs
    # ══════════════════════════════════════════════════════════════
    def check_s4_measures(self):
        print("[S4] Measures...")
        p_table_map = {n.lower(): n for n in self.tgt.table_names() if not _is_auto_table(n)}
        for jt in self.src.tables():
            tbl = jt.get("name", "")
            if _is_auto_table(tbl):
                continue
            if tbl.lower() not in p_table_map:
                continue
            p_tbl = p_table_map[tbl.lower()]
            p_meas = self.tgt.measures(p_tbl)
            p_lower = {k.lower(): k for k in p_meas}

            j_meas = jt.get("measures", [])
            for jm in j_meas:
                mname = jm.get("name", "") if isinstance(jm, dict) else str(jm)
                mdata = jm if isinstance(jm, dict) else {}

                # S4.1 existence
                if mname.lower() not in p_lower:
                    self._missing("S4", f"measure.exists[{tbl}.{mname}]", "CRITICAL",
                                  f"{tbl}.{mname}",
                                  f"Measure '{mname}' missing from table '{tbl}' in PBIP.")
                    continue
                pm = p_meas[p_lower[mname.lower()]]
                self._pass("S4", f"measure.exists[{tbl}.{mname}]", "CRITICAL",
                           f"{tbl}.{mname}", mname)

                # S4.2 expression
                jexpr = _norm(mdata.get("expression", mdata.get("dax_expression", None)))
                pexpr = _norm(pm.get("expression"))
                if jexpr and jexpr != pexpr:
                    self._mismatch("S4", f"measure.expression[{tbl}.{mname}]", "CRITICAL",
                                   jexpr[:120], pexpr[:120] if pexpr else None,
                                   f"DAX expression mismatch for measure '{tbl}.{mname}'.")
                elif jexpr:
                    self._pass("S4", f"measure.expression[{tbl}.{mname}]", "CRITICAL",
                               jexpr[:80], pexpr[:80])

                # S4.3 formatString
                jfs = mdata.get("format_string", mdata.get("formatString", None))
                if jfs:
                    pfs = pm.get("formatString")
                    if _norm(jfs) != _norm(pfs):
                        self._mismatch("S4", f"measure.formatString[{tbl}.{mname}]", "HIGH",
                                       jfs, pfs, f"Format string mismatch for '{tbl}.{mname}'.")
                    else:
                        self._pass("S4", f"measure.formatString[{tbl}.{mname}]", "HIGH", jfs, pfs)

                # S4.4 isHidden
                jh = mdata.get("is_hidden", mdata.get("isHidden", False))
                ph = pm.get("isHidden", False)
                if bool(jh) != bool(ph):
                    self._mismatch("S4", f"measure.isHidden[{tbl}.{mname}]", "HIGH", jh, ph,
                                   f"isHidden mismatch for measure '{tbl}.{mname}'.")
                else:
                    self._pass("S4", f"measure.isHidden[{tbl}.{mname}]", "HIGH", jh, ph)

                # S4.5 displayFolder
                jdf = mdata.get("display_folder", mdata.get("displayFolder", None))
                if jdf:
                    pdf = pm.get("displayFolder")
                    if _norm(jdf) != _norm(pdf):
                        self._mismatch("S4", f"measure.displayFolder[{tbl}.{mname}]", "MEDIUM",
                                       jdf, pdf, f"displayFolder mismatch for '{tbl}.{mname}'.")
                    else:
                        self._pass("S4", f"measure.displayFolder[{tbl}.{mname}]", "MEDIUM", jdf, pdf)

                # S4.6 description
                jdesc = mdata.get("description", None)
                if jdesc:
                    pdesc = pm.get("description")
                    if _norm(jdesc) != _norm(pdesc):
                        self._mismatch("S4", f"measure.description[{tbl}.{mname}]", "LOW",
                                       jdesc, pdesc,
                                       f"Description mismatch for '{tbl}.{mname}'. Affects Copilot/Q&A.")
                    else:
                        self._pass("S4", f"measure.description[{tbl}.{mname}]", "LOW", jdesc, pdesc)

                # S4.7 KPI
                jkpi = mdata.get("kpi", {})
                if jkpi:
                    pkpi = pm.get("kpi", {})
                    for kpi_attr in ("statusExpression", "targetExpression", "trendExpression"):
                        jkv = _norm(jkpi.get(kpi_attr))
                        pkv = _norm(pkpi.get(kpi_attr))
                        if jkv and jkv != pkv:
                            self._mismatch("S4", f"measure.kpi.{kpi_attr}[{tbl}.{mname}]", "HIGH",
                                           jkv[:80], pkv[:80] if pkv else None,
                                           f"KPI {kpi_attr} mismatch for '{tbl}.{mname}'.")
                        elif jkv:
                            self._pass("S4", f"measure.kpi.{kpi_attr}[{tbl}.{mname}]", "HIGH", jkv[:60], pkv[:60])

    # ══════════════════════════════════════════════════════════════
    # S5 — Hierarchies
    # ══════════════════════════════════════════════════════════════
    def check_s5_hierarchies(self):
        print("[S5] Hierarchies...")
        p_table_map = {n.lower(): n for n in self.tgt.table_names() if not _is_auto_table(n)}
        for jt in self.src.tables():
            tbl = jt.get("name", "")
            if _is_auto_table(tbl):
                continue
            if tbl.lower() not in p_table_map:
                continue
            p_tbl = p_table_map[tbl.lower()]
            p_hier = self.tgt.hierarchies(p_tbl)
            p_lower = {k.lower(): k for k in p_hier}

            for jh in jt.get("hierarchies", []):
                hname = jh.get("name", "") if isinstance(jh, dict) else str(jh)
                hdata = jh if isinstance(jh, dict) else {}

                # S5.1 existence
                if hname.lower() not in p_lower:
                    self._missing("S5", f"hierarchy.exists[{tbl}.{hname}]", "HIGH",
                                  f"{tbl}.{hname}",
                                  f"Hierarchy '{hname}' missing from table '{tbl}' in PBIP.")
                    continue
                ph = p_hier[p_lower[hname.lower()]]
                self._pass("S5", f"hierarchy.exists[{tbl}.{hname}]", "HIGH",
                           f"{tbl}.{hname}", hname)

                # S5.2 levels
                j_levels = hdata.get("levels", [])
                p_levels = ph.get("levels", [])
                for i, jl in enumerate(j_levels):
                    jlname = jl.get("name", jl) if isinstance(jl, dict) else str(jl)
                    jlcol  = jl.get("column", None) if isinstance(jl, dict) else None
                    if i < len(p_levels):
                        pl = p_levels[i]
                        plname = pl.get("name", "")
                        if _norm(jlname) != _norm(plname):
                            self._mismatch("S5", f"hierarchy.level[{tbl}.{hname}.{i}]", "HIGH",
                                           jlname, plname,
                                           f"Level name mismatch at ordinal {i} for hierarchy '{hname}'.")
                        else:
                            self._pass("S5", f"hierarchy.level[{tbl}.{hname}.{i}]", "HIGH",
                                       jlname, plname)
                        if jlcol:
                            plcol = pl.get("column", "")
                            if _norm(jlcol) != _norm(plcol):
                                self._mismatch("S5", f"hierarchy.levelCol[{tbl}.{hname}.{i}]", "HIGH",
                                               jlcol, plcol,
                                               f"Level column mismatch at ordinal {i} for hierarchy '{hname}'.")
                            else:
                                self._pass("S5", f"hierarchy.levelCol[{tbl}.{hname}.{i}]", "HIGH",
                                           jlcol, plcol)
                    else:
                        self._missing("S5", f"hierarchy.level[{tbl}.{hname}.{i}]", "HIGH",
                                      f"{hname}[{i}]={jlname}",
                                      f"Level {i} '{jlname}' missing from hierarchy '{hname}' in PBIP.")

                # S5.3 isHidden
                jh_hidden = hdata.get("is_hidden", hdata.get("isHidden", False))
                ph_hidden = ph.get("isHidden", False)
                if bool(jh_hidden) != bool(ph_hidden):
                    self._mismatch("S5", f"hierarchy.isHidden[{tbl}.{hname}]", "MEDIUM",
                                   jh_hidden, ph_hidden, f"isHidden mismatch for hierarchy '{hname}'.")
                else:
                    self._pass("S5", f"hierarchy.isHidden[{tbl}.{hname}]", "MEDIUM",
                               jh_hidden, ph_hidden)

    # ══════════════════════════════════════════════════════════════
    # S6 — Relationships & USERELATIONSHIP
    # ══════════════════════════════════════════════════════════════
    def check_s6_relationships(self):
        print("[S6] Relationships...")
        j_rels = self.src.relationships()
        p_rels = self.tgt.relationships()

        # S6.1 count
        if len(j_rels) == len(p_rels):
            self._pass("S6", "rel.count", "CRITICAL", len(j_rels), len(p_rels))
        else:
            self._mismatch("S6", "rel.count", "CRITICAL", len(j_rels), len(p_rels),
                           f"Relationship count mismatch. JSON={len(j_rels)}, PBIP={len(p_rels)}.")

        def _rel_key(r):
            ft = r.get("from_table", r.get("fromTable")) or ""
            fc = r.get("from_column", r.get("fromColumn")) or ""
            tt = r.get("to_table", r.get("toTable")) or ""
            tc = r.get("to_column", r.get("toColumn")) or ""
            return (ft.lower(), fc.lower(), tt.lower(), tc.lower())

        p_rel_map = {_rel_key(r): r for r in p_rels}

        for i, jr in enumerate(j_rels):
            key = _rel_key(jr)
            ft, fc, tt, tc = key
            label = f"{ft}.{fc}->{tt}.{tc}"

            # S6.2 existence by from/to
            if key not in p_rel_map:
                self._missing("S6", f"rel.exists[{label}]", "CRITICAL", label,
                              f"Relationship '{label}' not found in PBIP relationships.tmdl.")
                continue
            pr = p_rel_map[key]
            self._pass("S6", f"rel.exists[{label}]", "CRITICAL", label, label)

            # S6.3 cardinality
            # JSON uses snake_case (many_to_one), PBIP TMDL uses camelCase (manyToOne)
            # Normalise both to lowercase-no-separator for comparison
            def _norm_card(c):
                return re.sub(r'[_\s-]', '', (c or '').lower())
            jcard = jr.get("cardinality", None)
            pcard = pr.get("cardinality")
            if jcard and _norm_card(jcard) != _norm_card(pcard):
                self._mismatch("S6", f"rel.cardinality[{label}]", "HIGH", jcard, pcard,
                               f"Cardinality mismatch for relationship '{label}'. "
                               f"JSON={jcard}, PBIP={pcard}.")
            elif jcard:
                self._pass("S6", f"rel.cardinality[{label}]", "HIGH", jcard, pcard)

            # S6.4 crossFilter
            # JSON: 'both' / 'single', PBIP TMDL: 'bothDirections' / 'single'
            def _norm_cf(c):
                c = (c or '').lower()
                if 'both' in c or 'bi' in c: return 'both'
                return 'single'
            jcf = jr.get("cross_filter_direction", jr.get("crossFilteringBehavior", "single"))
            pcf = pr.get("crossFilter", "single")
            if _norm_cf(jcf) != _norm_cf(pcf):
                self._mismatch("S6", f"rel.crossFilter[{label}]", "HIGH", jcf, pcf,
                               f"Cross-filter direction mismatch for '{label}'.")
            else:
                self._pass("S6", f"rel.crossFilter[{label}]", "HIGH", jcf, pcf)

            # S6.5 isActive
            j_active = jr.get("is_active", jr.get("isActive", True))
            p_active = pr.get("isActive", True)
            if bool(j_active) != bool(p_active):
                self._mismatch("S6", f"rel.isActive[{label}]", "HIGH", j_active, p_active,
                               f"isActive mismatch for '{label}'. Inactive relationships used with USERELATIONSHIP().")
            else:
                self._pass("S6", f"rel.isActive[{label}]", "HIGH", j_active, p_active)

        # S6.6 USERELATIONSHIP cross-check
        inactive_rels = {_rel_key(r) for r in j_rels
                         if not r.get("is_active", r.get("isActive", True))}
        for jt in self.src.tables():
            tbl = jt.get("name", "")
            for jm in jt.get("measures", []):
                mname = jm.get("name", "") if isinstance(jm, dict) else ""
                expr  = ((jm.get("expression") or "") if isinstance(jm, dict) else "").lower()
                if "userelationship" in expr:
                    # Extract USERELATIONSHIP args for existence check
                    matches = re.findall(r"userelationship\s*\(([^,]+),([^)]+)\)", expr)
                    for m in matches:
                        parts_a = m[0].strip().strip("'\"[]").split("[")
                        parts_b = m[1].strip().strip("'\"[]").split("[")
                        if len(parts_a) >= 2 and len(parts_b) >= 2:
                            ta = parts_a[0].strip("'\"").lower()
                            ca = parts_a[1].strip("']\"").lower()
                            tb = parts_b[0].strip("'\"").lower()
                            cb = parts_b[1].strip("']\"").lower()
                            key = (ta, ca, tb, cb)
                            rev = (tb, cb, ta, ca)
                            if key not in inactive_rels and rev not in inactive_rels:
                                self._fail("S6", f"rel.userelationship[{tbl}.{mname}]", "HIGH",
                                           f"{ta}.{ca}->{tb}.{cb}", "not found as inactive",
                                           f"USERELATIONSHIP in measure '{tbl}.{mname}' references a relationship "
                                           f"not captured as inactive in JSON. Ensure the relationship exists and is inactive.")
                            else:
                                self._pass("S6", f"rel.userelationship[{tbl}.{mname}]", "HIGH",
                                           f"{ta}.{ca}->{tb}.{cb}", "inactive rel found")

    # ══════════════════════════════════════════════════════════════
    # S7 — M / Power Query expressions
    # ══════════════════════════════════════════════════════════════
    def check_s7_m_expressions(self):
        print("[S7] M expressions...")
        p_table_map = {n.lower(): n for n in self.tgt.table_names() if not _is_auto_table(n)}
        for jt in self.src.tables():
            tbl = jt.get("name", "")
            if _is_auto_table(tbl):
                continue
            mexpr = jt.get("m_expression", jt.get("power_query", jt.get("query", None)))
            if not mexpr:
                continue
            if tbl.lower() not in p_table_map:
                continue
            p_tbl = p_table_map[tbl.lower()]
            p_parts = self.tgt.partitions(p_tbl)

            if not p_parts:
                self._missing("S7", f"m.partition[{tbl}]", "HIGH", tbl,
                              f"No partition found in PBIP for table '{tbl}' that has M expression in JSON.")
                continue

            # Find first non-calculated partition
            m_part = next(
                (p for p in p_parts.values() if p.get("type", "m") == "m"), None
            ) or next(iter(p_parts.values()))

            # S7.1 expression match
            # Strip local file paths (File.Contents("C:\...")) before comparing —
            # paths change per environment and are not a migration defect.
            # Also strip leading /* comment blocks that some RE tools inject.
            def _norm_m(expr):
                if not expr:
                    return ""
                # Remove block comments /* ... */
                e = re.sub(r"/\*.*?\*/", "", str(expr), flags=re.DOTALL)
                # Replace File.Contents("any path") with a placeholder
                e = re.sub(r'file\.contents\s*\([^)]+\)', 'file.contents(__path__)', e, flags=re.IGNORECASE)
                # Normalise whitespace and case
                return re.sub(r"\s+", " ", e).strip().lower()

            je = _norm_m(mexpr)
            pe = _norm_m(m_part.get("expression"))
            if je and je != pe:
                # Find first differing token after path normalisation to show what actually differs
                je_words = je.split()
                pe_words = pe.split() if pe else []
                first_diff = next(
                    ((a, b) for a, b in zip(je_words, pe_words) if a != b),
                    (je_words[len(pe_words)] if len(je_words) > len(pe_words) else "—",
                     pe_words[len(je_words)] if len(pe_words) > len(je_words) else "—")
                )
                self._mismatch("S7", f"m.expression[{tbl}]", "HIGH",
                               _norm(mexpr)[:200], _norm(m_part.get("expression"))[:200] if m_part.get("expression") else None,
                               f"M expression mismatch for table '{tbl}'. "
                               f"File paths normalised — remaining difference is in query logic/steps/encoding. "
                               f"First differing token: JSON='{first_diff[0][:40]}' vs PBIP='{first_diff[1][:40]}'.")
            elif je:
                self._pass("S7", f"m.expression[{tbl}]", "HIGH",
                           _norm(mexpr)[:80], _norm(m_part.get("expression"))[:80] if m_part.get("expression") else None)

            # S7.2 mode
            # JSON uses semantic table_type (dimension/fact), PBIP uses engine mode (import/directQuery)
            # dimension and fact both map to 'import'; calculated stays 'calculated'
            _MODE_MAP = {"dimension": "import", "fact": "import", "import": "import",
                         "calculated": "calculated", "directquery": "directquery", "dual": "dual"}
            jmode_raw = jt.get("partition_mode", jt.get("storage_mode", None))
            if jmode_raw:
                jmode_norm = _MODE_MAP.get(_norm(jmode_raw), _norm(jmode_raw))
                pmode_norm = _norm(m_part.get("mode") or "import")
                if jmode_norm == pmode_norm:
                    self._pass("S7", f"m.mode[{tbl}]", "MEDIUM", jmode_raw, m_part.get("mode"))
                else:
                    self._mismatch("S7", f"m.mode[{tbl}]", "MEDIUM", jmode_raw, m_part.get("mode"),
                                   f"Partition mode mismatch for table '{tbl}'. "
                                   f"JSON semantic type '{jmode_raw}' maps to '{jmode_norm}', PBIP mode='{pmode_norm}'.")

    # ══════════════════════════════════════════════════════════════
    # S8 — DAX calculated tables
    # ══════════════════════════════════════════════════════════════
    def check_s8_dax_tables(self):
        print("[S8] DAX calculated tables...")
        p_table_map = {n.lower(): n for n in self.tgt.table_names() if not _is_auto_table(n)}
        for jt in self.src.tables():
            tbl = jt.get("name", "")
            if _is_auto_table(tbl):
                continue
            dax_expr = jt.get("dax_expression", jt.get("calculated_table_expression", None))
            if not dax_expr:
                continue
            if tbl.lower() not in p_table_map:
                continue  # S1 already covers missing table
            p_tbl = p_table_map[tbl.lower()]
            p_parts = self.tgt.partitions(p_tbl)

            # S8.1 calculatedTable partition exists
            calc_parts = [p for p in p_parts.values() if p.get("type") == "calculatedTable"]
            if not calc_parts:
                self._missing("S8", f"calcTable.partition[{tbl}]", "HIGH", tbl,
                              f"Table '{tbl}' is a DAX calculated table in JSON but no calculatedTable partition found in PBIP.")
                continue
            self._pass("S8", f"calcTable.partition[{tbl}]", "HIGH", tbl, "calculatedTable partition found")

            # S8.2 expression
            je = _norm(dax_expr)
            pe = _norm(calc_parts[0].get("expression"))
            if je and je != pe:
                self._mismatch("S8", f"calcTable.expression[{tbl}]", "HIGH",
                               je[:120], pe[:120] if pe else None,
                               f"DAX expression mismatch for calculated table '{tbl}'.")
            elif je:
                self._pass("S8", f"calcTable.expression[{tbl}]", "HIGH", je[:80], pe[:80] if pe else None)

    # ══════════════════════════════════════════════════════════════
    # S9 — RLS roles
    # ══════════════════════════════════════════════════════════════
    def check_s9_rls_roles(self):
        print("[S9] RLS roles...")
        j_roles = self.src.roles()
        if not j_roles:
            self._info("S9", "roles.present", "none", "No RLS roles in JSON — N/A")
            return
        p_roles = self.tgt.roles()
        p_lower = {k.lower(): k for k in p_roles}

        for jr in j_roles:
            rname = jr.get("name", jr.get("role_name", "")) if isinstance(jr, dict) else str(jr)
            rdata = jr if isinstance(jr, dict) else {}

            # S9.1 existence
            if rname.lower() not in p_lower:
                self._missing("S9", f"role.exists[{rname}]", "CRITICAL", rname,
                              f"RLS role '{rname}' not found in PBIP roles.tmdl.")
                continue
            pr = p_roles[p_lower[rname.lower()]]
            self._pass("S9", f"role.exists[{rname}]", "CRITICAL", rname, rname)

            # S9.2 filter expressions
            j_filters = rdata.get("table_filters", rdata.get("filters", {}))
            if isinstance(j_filters, list):
                j_filters = {f.get("table", ""): f.get("expression", "") for f in j_filters if isinstance(f, dict)}
            p_filters = pr.get("tableFilters", {})
            for tbl_name, jexpr in j_filters.items():
                pexpr = p_filters.get(tbl_name, p_filters.get(tbl_name.lower()))
                if _norm(jexpr) == _norm(pexpr):
                    self._pass("S9", f"role.filter[{rname}.{tbl_name}]", "CRITICAL",
                               _norm(jexpr)[:60], _norm(pexpr)[:60])
                else:
                    self._mismatch("S9", f"role.filter[{rname}.{tbl_name}]", "CRITICAL",
                                   jexpr, pexpr,
                                   f"RLS filter expression mismatch for role '{rname}' table '{tbl_name}'.")

            # S9.3 modelPermission
            jperm = rdata.get("model_permission", rdata.get("modelPermission", None))
            if jperm:
                pperm = pr.get("modelPermission")
                if _norm(jperm) != _norm(pperm):
                    self._mismatch("S9", f"role.modelPermission[{rname}]", "HIGH", jperm, pperm,
                                   f"modelPermission mismatch for role '{rname}'.")
                else:
                    self._pass("S9", f"role.modelPermission[{rname}]", "HIGH", jperm, pperm)

            # S9.4 dynamic RLS flag
            all_filters = " ".join(str(v) for v in j_filters.values()).lower()
            if "username()" in all_filters or "userprincipalname()" in all_filters:
                self._log("S9", f"role.dynamicRLS[{rname}]", "INFO", "HIGH",
                          "username()/userprincipalname() detected", "deployment team action required",
                          f"Role '{rname}' uses dynamic RLS. User principal mapping must be verified "
                          f"in the target Fabric workspace after deployment.",
                          deploy_flag=True)

    # ══════════════════════════════════════════════════════════════
    # S10 — Model metadata
    # ══════════════════════════════════════════════════════════════
    def check_s10_metadata(self):
        print("[S10] Model metadata...")
        jmeta = self.src.metadata()

        # S10.1 model name
        jname = jmeta.get("name")
        pname = self.tgt.model_name()
        if jname:
            # Skip name comparison when the JSON name is a source file name (e.g.
            # Tableau .twbx/.twb, Qlik .qvf, or a .pbix path). In these cases the
            # JSON holds the origin filename, not a semantic model name, so a
            # mismatch against the PBIP 'model Model' heading is always expected and
            # has no migration consequence.  Power BI JSON names never carry an
            # extension, so this guard never fires for Power BI files.
            _SOURCE_EXTS = ('.twbx', '.twb', '.qvf', '.pbix', '.xlsx', '.hyper')
            if any(jname.lower().endswith(ext) for ext in _SOURCE_EXTS):
                self._info("S10", "model.name", jname,
                           "JSON name is a source filename — model name comparison skipped.")
            elif _norm(jname) == _norm(pname):
                self._pass("S10", "model.name", "MEDIUM", jname, pname)
            else:
                self._mismatch("S10", "model.name", "MEDIUM", jname, pname,
                               "Model name mismatch.")

        # S10.2 compatibility level
        jcl = jmeta.get("compatibility_level")
        pcl = self.tgt.compatibility_level()
        if jcl:
            if str(jcl) == str(pcl):
                self._pass("S10", "model.compatibilityLevel", "HIGH", jcl, pcl)
            else:
                self._mismatch("S10", "model.compatibilityLevel", "HIGH", jcl, pcl,
                               "Compatibility level mismatch. Affects available Fabric features.")

        # S10.3 sensitivity label — deployment flag
        slabel = jmeta.get("sensitivity_label")
        if slabel:
            self._log("S10", "model.sensitivityLabel", "INFO", "LOW",
                      slabel, "manual reapplication required",
                      "Sensitivity label does not transfer automatically on migration. "
                      "Deployment team must reapply in target workspace.",
                      deploy_flag=True)

    # ══════════════════════════════════════════════════════════════
    # S11 — Shared expressions / parameters
    # ══════════════════════════════════════════════════════════════
    def check_s11_shared_expressions(self):
        print("[S11] Shared expressions...")
        j_exprs = self.src.shared_expressions()
        if not j_exprs:
            self._info("S11", "shared_expr.present", "none", "No shared expressions in JSON — N/A")
            return
        if isinstance(j_exprs, dict):
            j_exprs = [{"name": k, "expression": v} for k, v in j_exprs.items()]
        p_exprs = self.tgt.shared_expressions()
        p_lower = {k.lower(): k for k in p_exprs}

        for je in j_exprs:
            ename = je.get("name", "") if isinstance(je, dict) else str(je)
            edata = je if isinstance(je, dict) else {}

            # S11.1 existence
            if ename.lower() not in p_lower:
                self._missing("S11", f"shared_expr.exists[{ename}]", "HIGH", ename,
                              f"Shared expression/parameter '{ename}' not found in PBIP expressions.tmdl.")
                continue
            pe = p_exprs[p_lower[ename.lower()]]
            self._pass("S11", f"shared_expr.exists[{ename}]", "HIGH", ename, ename)

            # S11.2 expression
            jexpr = _norm(edata.get("expression", edata.get("value", None)))
            pexpr = _norm(pe.get("expression"))
            if jexpr and jexpr != pexpr:
                self._mismatch("S11", f"shared_expr.expression[{ename}]", "HIGH",
                               jexpr[:100], pexpr[:100] if pexpr else None,
                               f"Expression mismatch for shared expression '{ename}'.")
            elif jexpr:
                self._pass("S11", f"shared_expr.expression[{ename}]", "HIGH",
                           jexpr[:60], pexpr[:60] if pexpr else None)

            # S11.3 kind
            jkind = edata.get("kind", None)
            if jkind:
                pkind = pe.get("kind")
                if _norm(jkind) != _norm(pkind):
                    self._mismatch("S11", f"shared_expr.kind[{ename}]", "MEDIUM",
                                   jkind, pkind, f"Kind mismatch for shared expression '{ename}'.")
                else:
                    self._pass("S11", f"shared_expr.kind[{ename}]", "MEDIUM", jkind, pkind)

    # ══════════════════════════════════════════════════════════════
    # S12 — OLS column permissions
    # ══════════════════════════════════════════════════════════════
    def check_s12_ols(self):
        print("[S12] OLS column permissions...")
        j_roles = self.src.roles()
        if not j_roles:
            self._info("S12", "ols.present", "none", "No roles/OLS in JSON — N/A")
            return
        p_roles = self.tgt.roles()
        p_lower = {k.lower(): k for k in p_roles}

        for jr in j_roles:
            rname = jr.get("name", jr.get("role_name", "")) if isinstance(jr, dict) else str(jr)
            rdata = jr if isinstance(jr, dict) else {}
            j_ols = rdata.get("column_permissions", rdata.get("ols", {}))
            if not j_ols:
                continue
            if rname.lower() not in p_lower:
                continue  # already flagged in S9
            pr = p_roles[p_lower[rname.lower()]]
            p_col_perms = pr.get("columnPermissions", {})

            for tbl_name, cols in j_ols.items():
                if isinstance(cols, list):
                    cols = {c: None for c in cols}
                for col_name, jperm in cols.items():
                    p_tbl_perms = p_col_perms.get(tbl_name, {})
                    pperm = p_tbl_perms.get(col_name)

                    # S12.1 existence
                    if col_name not in p_tbl_perms:
                        self._missing("S12", f"ols.col[{rname}.{tbl_name}.{col_name}]", "HIGH",
                                      f"{rname}.{tbl_name}.{col_name}",
                                      f"OLS column permission for '{tbl_name}.{col_name}' in role '{rname}' missing from PBIP.")
                        continue
                    self._pass("S12", f"ols.col[{rname}.{tbl_name}.{col_name}]", "HIGH",
                               f"{rname}.{tbl_name}.{col_name}", "found")

                    # S12.2 permission level
                    if jperm and _norm(jperm) != _norm(pperm):
                        self._mismatch("S12", f"ols.perm[{rname}.{tbl_name}.{col_name}]", "HIGH",
                                       jperm, pperm,
                                       f"OLS permission level mismatch for '{tbl_name}.{col_name}' in role '{rname}'. "
                                       f"Expected: {jperm}, got: {pperm}. (None=hidden, Read, Default)")
                    elif jperm:
                        self._pass("S12", f"ols.perm[{rname}.{tbl_name}.{col_name}]", "HIGH",
                                   jperm, pperm)

    # ══════════════════════════════════════════════════════════════
    # S13 — What-If parameters
    # ══════════════════════════════════════════════════════════════
    def check_s13_whatif(self):
        print("[S13] What-If parameters...")
        found = False
        p_table_map = {n.lower(): n for n in self.tgt.table_names()}
        for jt in self.src.tables():
            tbl = jt.get("name", "")
            whatif = jt.get("what_if", jt.get("whatif_parameter", None))
            if not whatif:
                continue
            found = True
            if tbl.lower() not in p_table_map:
                continue
            p_tbl = p_table_map[tbl.lower()]
            p_parts = self.tgt.partitions(p_tbl)
            calc_parts = [p for p in p_parts.values() if p.get("type") == "calculatedTable"]

            # S13.1 GENERATESERIES partition
            gs_parts = [p for p in calc_parts if "generateseries" in _norm(p.get("expression", ""))]
            if not gs_parts:
                self._missing("S13", f"whatif.partition[{tbl}]", "MEDIUM", tbl,
                              f"What-If parameter table '{tbl}' has no GENERATESERIES calculated table in PBIP.")
                continue
            self._pass("S13", f"whatif.partition[{tbl}]", "MEDIUM", tbl, "GENERATESERIES found")

            # S13.2 min/max/increment
            jmin = whatif.get("min") if isinstance(whatif, dict) else None
            jmax = whatif.get("max") if isinstance(whatif, dict) else None
            jinc = whatif.get("increment") if isinstance(whatif, dict) else None
            pexpr = gs_parts[0].get("expression", "")
            # Extract numbers from GENERATESERIES
            gs_nums = re.findall(r"generateseries\s*\(([^)]+)\)", pexpr.lower())
            if gs_nums and (jmin is not None or jmax is not None):
                nums = [n.strip() for n in gs_nums[0].split(",")]
                pmin = nums[0] if len(nums) > 0 else None
                pmax = nums[1] if len(nums) > 1 else None
                pinc = nums[2] if len(nums) > 2 else None
                for attr, jv, pv in [("min", jmin, pmin), ("max", jmax, pmax), ("increment", jinc, pinc)]:
                    if jv is not None:
                        if _norm(str(jv)) == _norm(str(pv) if pv else ""):
                            self._pass("S13", f"whatif.{attr}[{tbl}]", "MEDIUM", jv, pv)
                        else:
                            self._mismatch("S13", f"whatif.{attr}[{tbl}]", "MEDIUM", jv, pv,
                                           f"What-If {attr} value mismatch for '{tbl}'.")
        if not found:
            self._info("S13", "whatif.present", "none", "No What-If parameters in JSON — N/A")

    # ══════════════════════════════════════════════════════════════
    # S14 — Field parameters
    # ══════════════════════════════════════════════════════════════
    def check_s14_field_parameters(self):
        print("[S14] Field parameters...")
        found = False
        p_table_map = {n.lower(): n for n in self.tgt.table_names()}
        for jt in self.src.tables():
            tbl = jt.get("name", "")
            fp = jt.get("field_parameter", jt.get("is_field_parameter", False))
            if not fp:
                continue
            found = True
            if tbl.lower() not in p_table_map:
                continue
            p_tbl = p_table_map[tbl.lower()]
            p_parts = self.tgt.partitions(p_tbl)
            calc_parts = [p for p in p_parts.values() if p.get("type") == "calculatedTable"]

            # S14.1 NAMEOF pattern
            nameof_parts = [p for p in calc_parts if "nameof" in _norm(p.get("expression", ""))]
            if not nameof_parts:
                self._missing("S14", f"fieldparam.nameof[{tbl}]", "MEDIUM", tbl,
                              f"Field parameter table '{tbl}' has no NAMEOF() pattern in PBIP.")
                continue
            self._pass("S14", f"fieldparam.nameof[{tbl}]", "MEDIUM", tbl, "NAMEOF() found")

            # S14.2 placeholder check
            pexpr = nameof_parts[0].get("expression", "")
            if re.search(r"value\d+", pexpr.lower()):
                self._fail("S14", f"fieldparam.placeholder[{tbl}]", "HIGH",
                           tbl, "Value1/Value2 placeholders detected",
                           f"Field parameter table '{tbl}' still contains placeholder field names "
                           f"(Value1, Value2 etc.). FE agent did not substitute enriched field names.")
            else:
                self._pass("S14", f"fieldparam.placeholder[{tbl}]", "HIGH", tbl, "No placeholders")
        if not found:
            self._info("S14", "fieldparam.present", "none", "No field parameters in JSON — N/A")

    # ══════════════════════════════════════════════════════════════
    # S15 — Incremental refresh
    # ══════════════════════════════════════════════════════════════
    def check_s15_incremental_refresh(self):
        print("[S15] Incremental refresh...")
        found = False
        p_table_map = {n.lower(): n for n in self.tgt.table_names()}
        for jt in self.src.tables():
            tbl = jt.get("name", "")
            irp = jt.get("incremental_refresh", jt.get("refresh_policy", None))
            if not irp:
                continue
            found = True
            if tbl.lower() not in p_table_map:
                continue
            p_tbl = p_table_map[tbl.lower()]
            raw = self.tgt._table_raw(p_tbl)

            # S15.1 refreshPolicy block
            if "refreshPolicy" not in raw and "incrementGranularity" not in raw:
                self._missing("S15", f"ir.policy[{tbl}]", "HIGH", tbl,
                              f"Table '{tbl}' has incremental refresh in JSON but no refreshPolicy in PBIP.")
                continue
            self._pass("S15", f"ir.policy[{tbl}]", "HIGH", tbl, "refreshPolicy found")

            # S15.2 granularities
            for attr, keys in [("incrementGranularity", ["increment_granularity", "incrementGranularity"]),
                                ("rangeGranularity",     ["range_granularity",     "rangeGranularity"])]:
                jval = next((irp.get(k) for k in keys if irp.get(k)), None) if isinstance(irp, dict) else None
                m = re.search(rf"{attr}\s*:\s*(\w+)", raw)
                pval = m.group(1) if m else None
                if jval:
                    if _norm(jval) == _norm(pval):
                        self._pass("S15", f"ir.{attr}[{tbl}]", "HIGH", jval, pval)
                    else:
                        self._mismatch("S15", f"ir.{attr}[{tbl}]", "HIGH", jval, pval,
                                       f"{attr} mismatch for table '{tbl}'.")

            # S15.3 pollingExpression
            jpoll = irp.get("polling_expression", irp.get("pollingExpression", None)) if isinstance(irp, dict) else None
            if jpoll:
                m = re.search(r"pollingExpression\s*=\s*(.+)", raw)
                ppoll = m.group(1).strip() if m else None
                if _norm(jpoll) == _norm(ppoll):
                    self._pass("S15", f"ir.pollingExpression[{tbl}]", "MEDIUM", jpoll[:60], ppoll[:60] if ppoll else None)
                else:
                    self._mismatch("S15", f"ir.pollingExpression[{tbl}]", "MEDIUM",
                                   jpoll[:60], ppoll[:60] if ppoll else None,
                                   f"pollingExpression mismatch for table '{tbl}'.")
        if not found:
            self._info("S15", "ir.present", "none", "No incremental refresh in JSON — N/A")

    # ══════════════════════════════════════════════════════════════
    # S16 — Dynamic RLS detection
    # ══════════════════════════════════════════════════════════════
    def check_s16_dynamic_rls(self):
        print("[S16] Dynamic RLS detection...")
        found = False
        p_table_map = {n.lower(): n for n in self.tgt.table_names()}
        for jt in self.src.tables():
            tbl = jt.get("name", "")
            if tbl.lower() not in p_table_map:
                continue
            p_tbl = p_table_map[tbl.lower()]
            p_meas = self.tgt.measures(p_tbl)

            for jm in jt.get("measures", []):
                mname = jm.get("name", "") if isinstance(jm, dict) else ""
                jexpr = ((jm.get("expression") or "") if isinstance(jm, dict) else "").lower()
                if "username()" not in jexpr and "userprincipalname()" not in jexpr:
                    continue
                found = True
                # S16.1 check preserved in PBIP
                pm_data = p_meas.get(mname, {})
                pexpr = _norm(pm_data.get("expression", ""))
                if "username()" in pexpr or "userprincipalname()" in pexpr:
                    self._pass("S16", f"dynrls.measure[{tbl}.{mname}]", "HIGH",
                               "username()/userprincipalname() present", "preserved in PBIP")
                else:
                    self._mismatch("S16", f"dynrls.measure[{tbl}.{mname}]", "HIGH",
                                   "username()/userprincipalname() in JSON",
                                   pexpr[:80] if pexpr else "not found",
                                   f"Dynamic RLS function lost in PBIP measure '{tbl}.{mname}'.")

                # S16.2 deployment flag
                self._log("S16", f"dynrls.deploy[{tbl}.{mname}]", "INFO", "MEDIUM",
                          f"{tbl}.{mname}", "deployment team action required",
                          f"Dynamic RLS measure '{tbl}.{mname}' uses username/UPN. "
                          f"User principal mapping must be verified in target Fabric workspace.",
                          deploy_flag=True)
        if not found:
            self._info("S16", "dynrls.present", "none", "No dynamic RLS functions in JSON measures — N/A")

    # ══════════════════════════════════════════════════════════════
    # S17 — Perspectives
    # ══════════════════════════════════════════════════════════════
    def check_s17_perspectives(self):
        print("[S17] Perspectives...")
        j_persps = self.src.perspectives()
        if not j_persps:
            self._info("S17", "persp.present", "none", "No perspectives in JSON — N/A")
            return
        p_persps = self.tgt.perspectives()
        p_lower = {k.lower(): k for k in p_persps}

        for jp in j_persps:
            pname = jp.get("name", "") if isinstance(jp, dict) else str(jp)
            pdata = jp if isinstance(jp, dict) else {}

            # S17.1 existence
            if pname.lower() not in p_lower:
                self._missing("S17", f"persp.exists[{pname}]", "MEDIUM", pname,
                              f"Perspective '{pname}' missing from PBIP perspectives.tmdl.")
                continue
            pp = p_persps[p_lower[pname.lower()]]
            self._pass("S17", f"persp.exists[{pname}]", "MEDIUM", pname, pname)

            # S17.2 contents
            for entity_type in ("tables", "columns", "measures"):
                j_items = set(i.lower() for i in pdata.get(entity_type, []))
                p_items = set(i.lower() for i in pp.get(entity_type, []))
                missing = j_items - p_items
                for m in missing:
                    self._missing("S17", f"persp.{entity_type}[{pname}.{m}]", "MEDIUM", m,
                                  f"Perspective '{pname}' is missing {entity_type[:-1]} '{m}' from PBIP.")
                if not missing:
                    self._pass("S17", f"persp.{entity_type}[{pname}]", "MEDIUM",
                               len(j_items), len(p_items))

    # ══════════════════════════════════════════════════════════════
    # S18 — Cultures / translations
    # ══════════════════════════════════════════════════════════════
    def check_s18_cultures(self):
        print("[S18] Cultures / translations...")
        j_cultures = self.src.cultures()
        if not j_cultures:
            self._info("S18", "cultures.present", "none", "No cultures in JSON — N/A")
            return
        p_cultures = self.tgt.cultures()
        p_lower = {k.lower(): k for k in p_cultures}

        if isinstance(j_cultures, list):
            j_cultures = {c.get("name", str(c)) if isinstance(c, dict) else str(c):
                          c for c in j_cultures}

        for cname, cdata in j_cultures.items():
            # S18.1 existence
            if cname.lower() not in p_lower:
                self._missing("S18", f"culture.exists[{cname}]", "HIGH", cname,
                              f"Culture '{cname}' missing from PBIP cultures.tmdl. "
                              f"Broken non-English report experience.")
                continue
            pc = p_cultures[p_lower[cname.lower()]]
            self._pass("S18", f"culture.exists[{cname}]", "HIGH", cname, cname)

            # S18.2 translation count
            j_trans = cdata.get("translations", []) if isinstance(cdata, dict) else []
            p_trans = pc.get("translations", [])
            if len(j_trans) > 0 and len(j_trans) != len(p_trans):
                self._mismatch("S18", f"culture.translations[{cname}]", "HIGH",
                               len(j_trans), len(p_trans),
                               f"Translation count mismatch for culture '{cname}'.")
            elif len(j_trans) > 0:
                self._pass("S18", f"culture.translations[{cname}]", "HIGH",
                           len(j_trans), len(p_trans))

    # ══════════════════════════════════════════════════════════════
    # Run all
    # ══════════════════════════════════════════════════════════════
    def run_all(self):
        self.check_s1_tables()
        self.check_s2_columns()
        self.check_s3_calculated_columns()
        self.check_s4_measures()
        self.check_s5_hierarchies()
        self.check_s6_relationships()
        self.check_s7_m_expressions()
        self.check_s8_dax_tables()
        self.check_s9_rls_roles()
        self.check_s10_metadata()
        self.check_s11_shared_expressions()
        self.check_s12_ols()
        self.check_s13_whatif()
        self.check_s14_field_parameters()
        self.check_s15_incremental_refresh()
        self.check_s16_dynamic_rls()
        self.check_s17_perspectives()
        self.check_s18_cultures()


# ─────────────────────────────────────────────────────────────────────────────
# Output writers
# ─────────────────────────────────────────────────────────────────────────────

# Severity weights matching target output format
SEV_WEIGHTS = {"CRITICAL": 5, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "PASS": 0.5, "INFO": 0.5}
PASS_THRESHOLD = 80.0

SEMANTIC_DESCRIPTIONS = {
    "S1":  "Table existence, storage mode, hidden flag, description",
    "S2":  "Column names, data types, hidden flag, summarizeBy, sortByColumn, displayFolder",
    "S3":  "Calculated column existence, DAX expression, data type",
    "S4":  "Measure existence, DAX expression, format string, hidden flag, displayFolder, description, KPI",
    "S5":  "Hierarchy existence, level names and columns, hidden flag",
    "S6":  "Relationship from/to table-column, cardinality, cross-filter direction, isActive, USERELATIONSHIP",
    "S7":  "M / Power Query partition expressions and partition mode",
    "S8":  "DAX calculated table existence and expression",
    "S9":  "RLS role existence, filter expressions, modelPermission, dynamic RLS",
    "S10": "Model name, compatibility level, default date table, sensitivity label",
    "S11": "Shared expression / parameter existence, expression, kind",
    "S12": "OLS column permission existence and permission level per role",
    "S13": "What-If parameter GENERATESERIES expression, min/max/increment",
    "S14": "Field parameter NAMEOF() pattern and placeholder detection",
    "S15": "Incremental refresh policy, granularities, pollingExpression",
    "S16": "Dynamic RLS USERNAME()/USERPRINCIPALNAME() preservation and deployment flag",
    "S17": "Perspective existence and included tables/columns/measures",
    "S18": "Culture existence and translation count",
}


def _weighted_score(results):
    earned = total = 0.0
    for r in results:
        if r.status == "INFO":
            continue
        w = SEV_WEIGHTS.get(r.severity, 1)
        total += w
        if r.status == "PASS":
            earned += w
    score = round(earned / total * 100, 2) if total else 100.0
    return score, round(earned, 2), round(total, 2)


def _verdict(score):
    return "PASS" if score >= PASS_THRESHOLD else "FAIL"


def write_outputs(results, deploy_flags, out_dir, json_path="", pbip_path=""):
    os.makedirs(out_dir, exist_ok=True)
    ts   = datetime.now().isoformat()
    ts_f = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = os.path.join(out_dir, f"fe_semantic_{ts_f}")

    overall_score, overall_earned, overall_total = _weighted_score(results)
    overall_verdict = _verdict(overall_score)

    # Per-check summary
    check_summary = []
    for cid in ALL_CHECKS:
        grp      = [r for r in results if r.check_id == cid]
        non_info = [r for r in grp if r.status != "INFO"]
        passed   = sum(1 for r in non_info if r.status == "PASS")
        failed   = sum(1 for r in non_info if r.status in ("FAIL", "MISMATCH"))
        missing  = sum(1 for r in non_info if r.status == "MISSING")
        total    = len(non_info)
        we = sum(SEV_WEIGHTS.get(r.severity, 1) for r in non_info if r.status == "PASS")
        wt = sum(SEV_WEIGHTS.get(r.severity, 1) for r in non_info)
        grp_score = round(we / wt * 100, 2) if wt else None
        check_summary.append({
            "check":         cid,
            "label":         CHECK_LABELS.get(cid, cid),
            "description":   SEMANTIC_DESCRIPTIONS.get(cid, ""),
            "scope":         "semantic",
            "score":         grp_score,
            "verdict":       _verdict(grp_score) if grp_score is not None else "N/A",
            "passed":        passed,
            "failed":        failed,
            "missing":       missing,
            "total":         total,
            "weight_earned": round(we, 2),
            "weight_total":  round(wt, 2),
        })

    # all_results
    all_results_out = [{
        "check_id":     r.check_id,
        "attribute":    r.sub_id,
        "status":       r.status,
        "source_value": r.src_value,
        "json_value":   r.tgt_value,
        "note":         r.note,
        "severity":     r.severity if r.status != "PASS" else "PASS",
    } for r in results]

    # gap_report
    gaps = [r for r in results if r.status in ("FAIL", "MISSING", "MISMATCH")]
    sev_summary = {}
    for r in gaps:
        sev_summary[r.severity] = sev_summary.get(r.severity, 0) + 1
    gap_list = sorted([{
        "check_id":     r.check_id,
        "attribute":    r.sub_id,
        "status":       r.status,
        "source_value": r.src_value,
        "json_value":   r.tgt_value,
        "note":         r.note,
        "severity":     r.severity,
    } for r in gaps], key=lambda x: (SEV_ORDER.get(x["severity"], 9), x["check_id"]))

    workbook_id = os.path.splitext(os.path.basename(pbip_path or ""))[0][:24] or "unknown"
    file_name   = os.path.basename(json_path or "")

    output = {
        "workbook_id":      workbook_id,
        "file_name":        file_name,
        "tool_name":        "fe_semantic_validator",
        "score":            overall_score,
        "verdict":          overall_verdict,
        "semantic_score":   overall_score,
        "semantic_verdict": overall_verdict,
        "score_breakdown": {
            "overall": {
                "score":     overall_score,
                "verdict":   overall_verdict,
                "formula":   "severity-weighted: CRITICAL=5, HIGH=3, MEDIUM=2, LOW=1, INFO/PASS=0.5",
                "threshold": "PASS if score >= 80%",
            },
            "semantic": {
                "scope":         "semantic",
                "score":         overall_score,
                "verdict":       overall_verdict,
                "weight_earned": overall_earned,
                "weight_total":  overall_total,
                "checks":        check_summary,
            },
        },
        "total_checks":  len([r for r in results if r.status != "INFO"]),
        "gaps_count":    len(gaps),
        "timestamp":     ts,
        "check_summary": check_summary,
        "report": {
            "workbook_id":      workbook_id,
            "pbip_path":        pbip_path or "",
            "json_path":        json_path or "",
            "timestamp":        ts,
            "overall_score":    overall_score,
            "overall_verdict":  overall_verdict,
            "semantic_score":   overall_score,
            "semantic_verdict": overall_verdict,
            "check_summary":    check_summary,
            "all_results":      all_results_out,
        },
        "gap_report": {
            "workbook_id":      workbook_id,
            "timestamp":        ts,
            "total_gaps":       len(gaps),
            "severity_summary": sev_summary,
            "gaps":             gap_list,
        },
        "deploy_report": {
            "workbook_id": workbook_id,
            "timestamp":   ts,
            "count":       len(deploy_flags),
            "items":       deploy_flags,
        },
    }

    json_out = base + "_output.json"
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    csv_path = base + "_full.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["check_id","attribute","status","severity","source_value","json_value","note","deploy_flag"])
        for r in results:
            w.writerow([r.check_id, r.sub_id, r.status, r.severity,
                        r.src_value, r.tgt_value, r.note, r.deploy_flag])

    return json_out, csv_path, overall_score, len(gaps), len(deploy_flags)


def print_summary(results, score, passed, total, deploy_flags):
    non_info = [r for r in results if r.status != "INFO"]
    n_pass   = sum(1 for r in non_info if r.status == "PASS")
    gaps     = sum(1 for r in non_info if r.status in ("FAIL", "MISSING", "MISMATCH"))
    print(f"\n{'='*65}")
    print(f"  FE SEMANTIC VALIDATOR — SUMMARY")
    print(f"  Score        : {score}%   (threshold: {PASS_THRESHOLD}%)")
    print(f"  Deploy flags : {len(deploy_flags)}")
    print("="*65)
    for cid in ALL_CHECKS:
        grp      = [r for r in results if r.check_id == cid]
        non_info = [r for r in grp if r.status != "INFO"]
        gp = sum(1 for r in non_info if r.status == "PASS")
        gt = len(non_info)
        if gt == 0:
            print(f"  ➖  {cid:<4} {CHECK_LABELS.get(cid,''):<38} {'0/0':>9}   N/A")
        else:
            we  = sum(SEV_WEIGHTS.get(r.severity, 1) for r in non_info if r.status == "PASS")
            wt  = sum(SEV_WEIGHTS.get(r.severity, 1) for r in non_info)
            pct = round(we / wt * 100, 1) if wt else 0
            icon = "✅" if pct >= 100 else "❌"
            print(f"  {icon}  {cid:<4} {CHECK_LABELS.get(cid,''):<38} {gp:>4}/{gt:<4} {pct:>6.1f}%")
    n_all  = [r for r in results if r.status != "INFO"]
    n_pass = sum(1 for r in n_all if r.status == "PASS")
    print(f"\n  {'─'*63}")
    print(f"  Total checks : {len(n_all)}  |  Passed : {n_pass}  |  Gaps : {gaps}")
    print(f"  Score        : {score}%")
    if deploy_flags:
        print(f"\n  ⚠️  {len(deploy_flags)} deployment action items — see deploy_report in output JSON")
    print(f"{'='*65}\n")


def main():
    ap = argparse.ArgumentParser(description="FE Semantic Validator — Enriched JSON vs PBIP SemanticModel")
    ap.add_argument("--json",  required=True, help="Path to enriched semantic JSON file")
    ap.add_argument("--pbip",  required=True, help="Path to target PBIP SemanticModel folder")
    ap.add_argument("--out",   default="./output", help="Output folder (default: ./output)")
    args = ap.parse_args()

    if not os.path.isfile(args.json):
        sys.exit(f"ERROR: JSON file not found: {args.json}")
    if not os.path.isdir(args.pbip):
        sys.exit(f"ERROR: PBIP folder not found: {args.pbip}")

    print(f"\nFE Semantic Validator")
    print(f"  JSON : {args.json}")
    print(f"  PBIP : {args.pbip}")
    print(f"  Out  : {args.out}\n")

    v = FESemanticValidator(args.json, args.pbip)
    v.run_all()

    json_out, csv_p, score, n_gaps, n_deploy = write_outputs(
        v.results, v.deploy_flags, args.out,
        json_path=args.json, pbip_path=args.pbip
    )
    print_summary(v.results, score, None, None, v.deploy_flags)
    print(f"  Output JSON : {json_out}")
    print(f"  Full CSV    : {csv_p}\n")


if __name__ == "__main__":
    main()
