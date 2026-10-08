"""
Step 2 Validator  --  PBIX / PBIP vs Homogeneous JSON
====================================================
Format-agnostic: auto-detects PBIX zip or PBIP folder.
Compares every artifact extracted from the source against
the homogeneous JSON produced by the RE/OP AutoGen tool.

Check  Name                              What is validated

-----  --------------------------------  -----------------------------------------------------
D1     Connections                       Data source connections, server/database paths,
                                         authentication mode, gateway, privacy level,
                                         SharePoint/OneDrive/Web/Folder sources,
                                         pbiServiceLive split architecture,
                                         EntityDataSource dataset GUID, RemoteArtifacts

D2     Tables, RLS and Incremental       Table names, isHidden, storage mode, M expressions,
       Refresh                           DAX calculated tables, RLS role names and DAX
                                         filter expressions per table, OLS column
                                         permissions, What-If Parameters (GENERATESERIES),
                                         Incremental Refresh policy

D3     Columns, Hierarchies and          Column names, data types, format strings, isHidden,
       M Query Parameters                summarizeBy, dataCategory, sortByColumn,
                                         displayFolder, lineageTag, isNameInferred,
                                         DAX calculated column expressions,
                                         M Query Parameters (Manage Parameters),
                                         Hierarchies (name, levels, ordinals)

D4     Filters                           Report, page and visual filters  --  type, field,
                                         operator, values list, lock state,
                                         isHiddenInViewMode flag

D5     Measures and Relationships        Measure names, DAX expressions, format strings,
                                         KPI statusExpression/targetExpression/trendExpression,
                                         isHidden, displayFolder, USERELATIONSHIP cross-check,
                                         Dynamic RLS detection (USERNAME/USERPRINCIPALNAME),
                                         Relationship cardinality, cross-filter direction,
                                         is_active, joinOnDateBehavior

D6     Report Visual Layer               Pages, canvas size, visuals, field bindings per
                                         projection role, visual filter count, bounding box,
                                         bookmarks, theme name and dataColors palette,
                                         StaticResources image files and imageUrl references

D7     Visual Display Names              Effective display names, aggregation types,
                                         named measure vs inline aggregation check

D8     Conditional Formatting            Colour rules, thresholds, icon sets (traffic lights,
                                         arrows), data bars, fontColorFormatting,
                                         backgroundColorFormatting, rowHighlighting, topN

D9     Tooltips                          Report page tooltip targets, custom tooltip
                                         field lists per visual

D10    Interactions and Navigation       Cross-filter matrix, drillFilterOtherVisuals,
                                         sync slicers and syncSlicerFiltersApply,
                                         button actions (all 9 types with targets),
                                         page navigation,
                                         Drillthrough (source side): button action
                                         type=drillthrough + target page name,
                                         Drillthrough (target side): page is drillthrough
                                         target, keepAllFilters, key fields (page filters),
                                         back button visual present on page

D11    Visual and Page Formatting        Data labels, category labels, axes, legend,
                                         data point colour overrides, button styling,
                                         visual background/border/shadow, canvas settings,
                                         page background, wallpaper

D12    External Components               Power Apps (environment_id, app_id),
                                         Power Automate (flow_id),
                                         Paginated Reports (workspace_id, report_id),
                                         custom visual GUIDs and versions (by GUID regex
                                         and by type-name length for HTML/WordCloud etc.),
                                         Azure Maps API key, URL action targets

D13    Model Metadata                    compatibilityLevel, culture, sourceQueryCulture,
                                         defaultMode, discourageImplicitMeasures (auto
                                         date/time), dataAccessOptions (legacyRedirects,
                                         returnErrorValuesAsNull),
                                         expressions.tmdl shared M queries and parameters,
                                         perspectives (names, included objects),
                                         cultures and translation strings,
                                         diagramLayout.json, definition.pbism (Fabric),
                                         TMDLScripts/ (audit only)

D14    PBIP Report Layer                 report.pbir (report-to-model binding),
       (PBIP format only)                definition/report.json (global filters, bookmarks),
                                         definition/pages/*/page.json (canvas, visibility),
                                         definition/pages/*/visuals/*/visual.json,
                                         definition/theme.json (colour palette),
                                         StaticResources/ (embedded images, SVGs)
                                         Marked N/A for PBIX sources.

Output:
  validation_report.json   --  machine-readable full results
  validation_report.csv    --  human-readable summary per check (layer + severity columns)
  gap_report.json          --  only the failed / missing attributes, sorted by severity

Usage:
  python re_pbi_validator.py \\
      --pbix  path/to/file.pbix \\
      --json  path/to/homogeneous.json \\
      --out   ./output

  Both fresh Power BI Desktop PBIXs and Service-downloaded PBIXs
  are handled automatically (requires: pip install pbixray).
  --bim is optional and only needed as an explicit override.

  Two-file architecture (Report + Dataset PBIX):
      --pbix  Report.pbix      (for D4, D6, D7-D11, D7 checks)
      --bim   model.bim        (exported from Dataset PBIX via Tabular Editor)
      --json  homogeneous.json
      --out   ./output

Dependencies:
  pip install deepdiff jsonschema pandas
"""

import os
import json
import zipfile
import argparse
import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

import pandas as pd
from deepdiff import DeepDiff

# pbixray: pure-Python package that reads Vertipaq (XPress9-compressed) DataModel
# directly from any PBIX file including Service-downloaded ones.
# Install: pip install pbixray
try:
    from pbixray import PBIXRay as _PBIXRay
    PBIXRAY_AVAILABLE = True
except ImportError:
    _PBIXRay = None
    PBIXRAY_AVAILABLE = False

# ---------------------------------------------
# PostgreSQL Configuration
# ---------------------------------------------
# ┌-----------------------------------------------------------------┐
# │  FILL IN YOUR POSTGRESQL CONNECTION DETAILS BELOW              │
# │  These values are used when --pg flag is passed at runtime     │
# │  Leave as-is if you are not using PostgreSQL                   │
# └-----------------------------------------------------------------┘

PG_CONFIG = {
    "host":     "YOUR_POSTGRES_HOST",        # ← e.g. "localhost" or "db.company.com" or Azure/AWS endpoint
    "port":     5432,                         # ← default PostgreSQL port  --  change if different
    "database": "YOUR_DATABASE_NAME",         # ← e.g. "bi_migration" or "validation_db"
    "user":     "YOUR_DB_USERNAME",           # ← e.g. "validator_user"
    "password": "YOUR_DB_PASSWORD",           # ← e.g. "P@ssw0rd123"  --  consider env var (see note below)
    "schema":   "YOUR_SCHEMA_NAME",           # ← e.g. "public" or "bi_validation" or "tier1"
}

# -- Security note --------------------------------------------------
# Hardcoding passwords is not recommended for production.
# Use environment variables instead:
#
#   import os
#   PG_CONFIG["password"] = os.environ.get("PG_VALIDATOR_PASSWORD", "")
#
# Set the env var before running:
#   Windows : set PG_VALIDATOR_PASSWORD=your_password
#   Linux   : export PG_VALIDATOR_PASSWORD=your_password
# ------------------------------------------------------------------

# -- Table names ----------------------------------------------------
# The validator writes to two tables in your schema.
# These will be created automatically on first run if they do not exist.

PG_TABLES = {
    "validation_results": "validation_results",  # ← all D1-D7 check results (every PASS/FAIL/MISSING)
    "gap_summary":        "gap_summary",          # ← only the failed/missing records with severity
}

# ---------------------------------------------
# Data structures
# ---------------------------------------------

@dataclass
class CheckResult:
    check_id: str           # e.g. "D1", "D6"
    attribute: str          # e.g. "server", "visual_type"
    status: str             # "PASS" | "FAIL" | "MISSING"
    source_value: Any       # value from PBIX zip
    json_value: Any         # value from homogeneous JSON
    note: str = ""          # extra context for GAP report
    severity: str = ""      # CRITICAL | HIGH | MEDIUM | LOW | INFO


# -- Severity assignment rules -------------------------------------------------
# Semantic layer (D1-D5) is higher severity than report layer (D6-D14)
# because semantic errors block forward engineering entirely.

SEVERITY_RULES: list[tuple] = [
    # (check_id_prefix, attribute_keyword, status, severity)
    # -- CRITICAL  --  forward engineering will fail ------------------------------
    ("D1", "server",             "FAIL",    "CRITICAL"),
    ("D1", "server",             "MISSING", "CRITICAL"),
    ("D1", "database",           "MISSING", "CRITICAL"),
    ("D1", "connection_mode",    "MISSING", "CRITICAL"),
    ("D2", ".name",              "MISSING", "CRITICAL"),
    ("D2", "source_expression",  "MISSING", "CRITICAL"),
    ("D2", "source_expression",  "FAIL",    "CRITICAL"),
    ("D2", "partition",          "MISSING", "CRITICAL"),
    ("D2", ".mode",              "FAIL",    "CRITICAL"),
    ("D5", ".expression",        "MISSING", "CRITICAL"),
    ("D5", ".expression",        "FAIL",    "CRITICAL"),
    ("D5", "relationship",       "MISSING", "CRITICAL"),
    ("D7", "named_measure",      "FAIL",    "CRITICAL"),
    ("D7", "aggregation_accuracy","FAIL",   "CRITICAL"),
    # -- HIGH  --  report functionally broken -------------------------------------
    ("D3", "data_type",          "FAIL",    "HIGH"),
    ("D3", "data_type",          "MISSING", "HIGH"),
    ("D3", "mq_parameter",       "MISSING", "CRITICAL"),   # Manage Parameters must be in JSON
    ("D3", "mq_parameter",       "FAIL",    "HIGH"),
    ("D4", "report_filters",     "FAIL",    "HIGH"),
    ("D4", "slicer_count",       "FAIL",    "HIGH"),
    ("D5", "format_string",      "FAIL",    "HIGH"),
    ("D5", "format_string",      "MISSING", "HIGH"),
    ("D5", "cardinality",        "FAIL",    "HIGH"),
    ("D5", "cross_filter",       "FAIL",    "HIGH"),
    ("D5", "is_active",          "FAIL",    "HIGH"),
    ("D6", "bookmark",           "MISSING", "HIGH"),
    ("D6", "visual_count",       "FAIL",    "HIGH"),
    ("D6", "field_count",        "FAIL",    "HIGH"),
    ("D13","conditional_format", "MISSING", "HIGH"),
    ("D13","conditional_format", "FAIL",    "HIGH"),
    ("D14","tooltip_page",       "MISSING", "HIGH"),
    ("D14","tooltip_fields",     "MISSING", "MEDIUM"),
    ("D10","drill_through",      "MISSING", "CRITICAL"),
    ("D10","action_type",        "MISSING", "HIGH"),
    ("D10","action_type",        "FAIL",    "HIGH"),
    ("D10","conditional_action", "MISSING", "HIGH"),
    ("D10","apply_slicers",      "MISSING", "HIGH"),
    ("D10","clear_slicers",      "MISSING", "HIGH"),
    ("D10","data_function",      "MISSING", "HIGH"),
    ("D10","button_state",       "MISSING", "MEDIUM"),
    # -- MEDIUM  --  usable but incomplete ---------------------------------------
    ("D3", "nullable",           "FAIL",    "MEDIUM"),
    ("D5", ".name",              "MISSING", "MEDIUM"),
    ("D6", "visual_type",        "MISSING", "MEDIUM"),
    ("D6", "visual_type",        "FAIL",    "MEDIUM"),
    ("D6", "position",           "FAIL",    "MEDIUM"),
    ("D6", "filters",            "FAIL",    "MEDIUM"),
    ("D7", "display_name",       "MISSING", "MEDIUM"),
    ("D12", "",                   "MISSING", "MEDIUM"),
    ("D12", "",                   "FAIL",    "MEDIUM"),
    # -- LOW  --  cosmetic or enrichment gap -------------------------------------
    ("D5", "description",        "FAIL",    "LOW"),
    ("D5", "description",        "MISSING", "LOW"),
    ("D2", "description",        "FAIL",    "LOW"),
    ("D6", "report_theme",       "FAIL",    "LOW"),
    ("D6", "bookmark_count",     "FAIL",    "LOW"),
    ("D6", "field",              "FAIL",    "LOW"),
    # -- INFO  --  system/expected, manual action noted ---------------------------
    ("D2", "parameter_table",    "PASS",    "INFO"),
    # -- New checks from S9/S12/S13/S15/S16/R15 --------------------------
    ("D2", "rls_role",           "MISSING", "CRITICAL"),   # S9  Missing RLS role = security gap
    ("D2", "rls_role",           "FAIL",    "CRITICAL"),
    ("D2", "rls_filter",         "MISSING", "CRITICAL"),   # S9  Missing filter = data exposure
    ("D2", "rls_filter",         "FAIL",    "CRITICAL"),
    ("D2", "ols",                "MISSING", "CRITICAL"),   # S12 OLS column permission missing
    ("D2", "ols",                "FAIL",    "CRITICAL"),
    ("D2", "what_if_parameter",  "MISSING", "HIGH"),       # S13 What-If param missing
    ("D2", "incremental_refresh","MISSING", "HIGH"),       # S15 Incremental refresh policy
    ("D5", "dynamic_rls",        "PASS",    "INFO"),       # S16 Flag only, not a failure
    ("D5", "kpi.",               "MISSING", "HIGH"),       # S4  KPI expressions missing
    ("D5", "kpi.",               "FAIL",    "HIGH"),
    ("D5", "userelationship_ref","FAIL",    "HIGH"),       # S6  USERELATIONSHIP invalid
    ("D6", "static_resource",    "MISSING", "CRITICAL"),  # R15 Missing image file
    ("D6", "image_resource_ref", "MISSING", "CRITICAL"),  # R15 Missing image ref in visual
    ("D10","sync_slicer",        "MISSING", "HIGH"),       # R18 Missing sync slicer flag
    ("D10","drillFilterOtherVisuals",     "MISSING", "HIGH"),     # R17
    ("D10","drillthrough_page",           "MISSING", "CRITICAL"), # drillthrough target page missing
    ("D10","drillthrough_key_field",      "MISSING", "CRITICAL"), # drillthrough key field missing
    ("D10","keepAllFilters",              "MISSING", "HIGH"),      # drillthrough keepAllFilters
    ("D10","has_back_button",             "MISSING", "HIGH"),      # back button on drillthrough page
    # New BIM artifact checks
    # ("D2", "lineageTag",         "MISSING", "MEDIUM"),   # table lineageTag -- COMMENTED OUT, not part of score
    ("D2", "isPrivate",          "MISSING", "MEDIUM"),   # table isPrivate
    # ("D3", "lineageTag",         "MISSING", "MEDIUM"),   # column/measure lineageTag -- COMMENTED OUT, not part of score
    ("D3", "changedProperty",    "MISSING", "HIGH"),     # explicit column override
    ("D3", "variations",         "MISSING", "HIGH"),     # date column variation link
    ("D3", "extendedProperties", "MISSING", "HIGH"),     # Field Parameter metadata
    ("D3", "relatedColumnDetails","MISSING","HIGH"),     # Field Parameter groupBy
    ("D5", "relationship_uuid",  "MISSING", "MEDIUM"),   # BIM UUID - informational
    ("D13","returnErrorValuesAsNull","MISSING","HIGH"),
    ("D13","source_query_culture","MISSING","MEDIUM"),
    ("D13","translation_count",  "MISSING", "HIGH"),     # culture translations
    ("D12","custom_or_html_visual","MISSING","CRITICAL"),  # R16 Missing custom/HTML visual
    ("D1", "CSV",                "PASS",    "INFO"),
]


def assign_severity(result: "CheckResult") -> str:
    """
    Assign severity to a CheckResult based on check_id,
    attribute keywords and status.
    Rules are evaluated in order  --  first match wins.
    All PASS results default to INFO (no action needed).
    """
    if result.status == "PASS":
        # Parameter table and CSV mode notes are INFO
        if "parameter_table" in result.attribute or \
           "manual-intervention" in str(result.json_value) or \
           "N/A-CSV" in str(result.source_value):
            return "INFO"
        return "PASS"   # PASS rows get PASS not a severity level

    attr_lower = result.attribute.lower()
    for chk, keyword, status, severity in SEVERITY_RULES:
        if result.check_id.startswith(chk) and \
           keyword.lower() in attr_lower and \
           result.status == status:
            return severity

    # Default fallback by check group
    defaults = {
        "D1": "CRITICAL", "D2": "CRITICAL",
        "D3": "HIGH",      "D4": "HIGH",
        "D5": "HIGH",      "D6": "MEDIUM",
        "D7": "MEDIUM",    "D12":"MEDIUM",
    }
    return defaults.get(result.check_id, "MEDIUM")


@dataclass
class ValidationReport:
    workbook_id: str
    pbix_path: str
    json_path: str
    timestamp: str
    results: list[CheckResult] = field(default_factory=list)

    # -- Computed properties ------------------
    @property
    def total(self):
        return len(self.results)

    @property
    def passed(self):
        return sum(1 for r in self.results if r.status == "PASS")

    @property
    def score(self):
        return round(self.passed / self.total * 100, 2) if self.total else 0

    @property
    def verdict(self):
        return "PASS" if self.score == 100.0 else "FAIL"

    @property
    def gaps(self):
        # MISSING and FAIL are actionable gaps
        # INFO items are advisory — included for visibility but not counted as gaps
        return [r for r in self.results if r.status not in ("PASS",)]


# ---------------------------------------------
# Step 1  --  Extract PBIX zip
# ---------------------------------------------

class PBIPExtractor:
    """
    Reads a PBIP project folder and returns the same dict structure
    as PBIXExtractor.extract_all() so the validator works identically
    for both PBIX and PBIP sources.

    PBIP folder structure:
      <Report>.pbip              ← root pointer
      <Report>.Dataset/
        definition/
          model.tmdl             ← model metadata
          expressions.tmdl      ← shared M queries + parameters
          relationships.tmdl    ← all relationships
          roles.tmdl             ← RLS / OLS
          perspectives.tmdl     ← curated views
          cultures.tmdl         ← translations
          tables/<Table>.tmdl   ← per-table definitions
        diagramLayout.json
        definition.pbism
        TMDLScripts/
      <Report>.Report/
        definition/
          report.json            ← global filters + bookmarks
          pages/<Page>/
            page.json
            visuals/<Visual>/
              visual.json
          theme.json (or CustomThemes/)
        StaticResources/
        report.pbir
    """

    def __init__(self, pbip_path: str):
        self.root = Path(pbip_path)
        if not self.root.exists():
            print(f"ERROR: PBIP path not found: {pbip_path}"); sys.exit(1)

    def _find_folder(self, *patterns: str) -> Optional[Path]:
        """Find first folder matching any of the given glob patterns."""
        for pat in patterns:
            results = list(self.root.glob(pat))
            if results:
                return results[0]
        return None

    def _read_json(self, path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            return {}

    def _read_tmdl(self, path: Path) -> str:
        """Read a TMDL file as raw text (TMDL is not JSON)."""
        try:
            return path.read_text(encoding="utf-8-sig")
        except Exception:
            return ""

    def _parse_tmdl_tables(self, tables_dir: Path) -> list:
        """Parse all <Table>.tmdl files in the tables/ directory."""
        tables = []
        if not tables_dir or not tables_dir.exists():
            return tables
        for tmdl_file in sorted(tables_dir.glob("*.tmdl")):
            content = self._read_tmdl(tmdl_file)
            tbl = self._parse_single_table_tmdl(content, tmdl_file.stem)
            tables.append(tbl)
        return tables

    def _parse_single_table_tmdl(self, content: str, table_name: str) -> dict:
        """
        Parse a single table TMDL file into a dict compatible with
        the structure PBIXExtractor produces from model.bim.
        TMDL is a hierarchical text format  --  we extract key blocks.
        """
        tbl = {
            "name":        table_name,
            "columns":     [],
            "measures":    [],
            "partitions":  [],
            "hierarchies": [],
        }
        current_block = None
        current_obj: dict = {}
        lines = content.splitlines()

        for line in lines:
            stripped = line.strip()
            # Detect block starts
            if stripped.startswith("partition "):
                if current_obj: self._flush(tbl, current_block, current_obj)
                current_block = "partition"
                current_obj   = {"name": stripped.split()[-1].strip("'")}
            elif stripped.startswith("measure "):
                if current_obj: self._flush(tbl, current_block, current_obj)
                current_block = "measure"
                current_obj   = {"name": stripped.split()[1].strip("'")}
            elif stripped.startswith("column "):
                if current_obj: self._flush(tbl, current_block, current_obj)
                current_block = "column"
                current_obj   = {"name": stripped.split()[1].strip("'")}
            elif stripped.startswith("hierarchy "):
                if current_obj: self._flush(tbl, current_block, current_obj)
                current_block = "hierarchy"
                current_obj   = {"name": stripped.split()[-1].strip("'"),
                                 "levels": []}
            elif stripped.startswith("level ") and current_block == "hierarchy":
                current_obj["levels"].append(
                    {"name": stripped.split()[-1].strip("'")})
            # Detect properties inside blocks
            elif "=" in stripped and current_obj is not None:
                key, _, val = stripped.partition("=")
                key = key.strip(); val = val.strip().strip("'")
                if key in ("expression","Expression"):
                    current_obj["expression"] = val
                elif key in ("dataType","data_type"):
                    current_obj["data_type"] = val
                elif key in ("formatString","format_string"):
                    current_obj["formatString"] = val
                elif key == "isHidden":
                    current_obj["isHidden"] = val.lower() == "true"
                elif key == "summarizeBy":
                    current_obj["summarizeBy"] = val
                elif key == "dataCategory":
                    current_obj["dataCategory"] = val
                elif key == "sortByColumn":
                    current_obj["sortByColumn"] = val
                elif key == "displayFolder":
                    current_obj["displayFolder"] = val
                elif key in ("sourceColumn","source"):
                    current_obj["source"] = val
                elif key == "mode":
                    current_obj["mode"] = val

        if current_obj:
            self._flush(tbl, current_block, current_obj)
        return tbl

    def _flush(self, tbl: dict, block: str, obj: dict):
        if block == "partition":
            tbl["partitions"].append(obj)
        elif block == "measure":
            tbl["measures"].append(obj)
        elif block == "column":
            tbl["columns"].append(obj)
        elif block == "hierarchy":
            tbl["hierarchies"].append(obj)

    def _parse_relationships_tmdl(self, content: str) -> list:
        rels = []
        current: dict = {}
        for line in content.splitlines():
            s = line.strip()
            if s.startswith("relationship"):
                if current: rels.append(current)
                current = {}
            elif "=" in s:
                k, _, v = s.partition("=")
                k = k.strip(); v = v.strip().strip("'")
                mapping = {
                    "fromTable":"from_table","fromColumn":"from_column",
                    "toTable":"to_table","toColumn":"to_column",
                    "cardinality":"cardinality",
                    "crossFilteringBehavior":"cross_filter_direction",
                    "isActive":"is_active","state":"state",
                }
                if k in mapping:
                    current[mapping[k]] = v
        if current: rels.append(current)
        return rels

    def _parse_roles_tmdl(self, content: str) -> list:
        roles = []
        current: dict = {}
        for line in content.splitlines():
            s = line.strip()
            if s.startswith("role "):
                if current: roles.append(current)
                current = {"name": s.split()[-1].strip("'"),
                           "row_level_security": []}
            elif s.startswith("modelPermission") and "=" in s:
                current["modelPermission"] = s.split("=")[-1].strip()
            elif s.startswith("tablePermission") and "=" in s:
                tbl = s.split("=")[0].replace("tablePermission","").strip().strip("'")
                expr= s.split("=",1)[-1].strip()
                current["row_level_security"].append(
                    {"table": tbl, "filter_expression": expr})
        if current: roles.append(current)
        return roles

    def extract_all(self) -> dict:
        """
        Read all PBIP artifacts and return a dict compatible with
        PBIXExtractor.extract_all()  --  same keys, same structure.
        """
        result = {
            "source_format": "pbip",
            "pbip_root_path": str(self.root),
            "connections":    [],
            "remote_artifacts": [],
            "data_model":     {},
            "rls_roles":      [],
            "layout":         {},
            "tmdl_files":     {},
            "pbip_report_files": {},
        }

        # -- Find Dataset and Report folders -----------------------
        dataset_folder = self._find_folder("*.Dataset", "*.dataset",
                                           "dataset", "Dataset")
        report_folder  = self._find_folder("*.Report", "*.report",
                                           "report", "Report")

        if not dataset_folder:
            print(f"  WARNING: No .Dataset folder found in {self.root}")
        if not report_folder:
            print(f"  WARNING: No .Report folder found in {self.root}")

        # -- SEMANTIC MODEL -----------------------------------------
        if dataset_folder:
            defn = dataset_folder / "definition"

            # model.tmdl
            model_tmdl = defn / "model.tmdl"
            if model_tmdl.exists():
                mc = self._read_tmdl(model_tmdl)
                mdl: dict = {}
                for line in mc.splitlines():
                    s = line.strip()
                    if "=" in s:
                        k,_,v = s.partition("=")
                        mdl[k.strip()] = v.strip().strip("'")
                result["data_model"].update({
                    "defaultMode":         mdl.get("defaultMode",""),
                    "compatibilityLevel":  mdl.get("compatibilityLevel",""),
                    "culture":             mdl.get("culture",""),
                    "auto_date_time":      mdl.get("discourageImplicitMeasures",""),
                })
                result["tmdl_files"]["model"] = mdl

            # expressions.tmdl
            expr_tmdl = defn / "expressions.tmdl"
            if expr_tmdl.exists():
                ec = self._read_tmdl(expr_tmdl)
                expr_names = [l.split()[1].strip("'")
                              for l in ec.splitlines()
                              if l.strip().startswith(("expression ","query "))]
                result["tmdl_files"]["expressions"]     = ec
                result["tmdl_files"]["expression_names"]= expr_names
                result["data_model"]["shared_expressions"] = [
                    {"name": n} for n in expr_names]

            # tables/*.tmdl
            tables_dir = defn / "tables"
            if tables_dir.exists():
                tables = self._parse_tmdl_tables(tables_dir)
                result["data_model"]["tables"] = tables

            # relationships.tmdl
            rel_tmdl = defn / "relationships.tmdl"
            if rel_tmdl.exists():
                rc = self._read_tmdl(rel_tmdl)
                result["data_model"]["relationships"] = \
                    self._parse_relationships_tmdl(rc)

            # roles.tmdl
            roles_tmdl = defn / "roles.tmdl"
            if roles_tmdl.exists():
                rolc = self._read_tmdl(roles_tmdl)
                result["rls_roles"] = self._parse_roles_tmdl(rolc)

            # perspectives.tmdl
            persp_tmdl = defn / "perspectives.tmdl"
            if persp_tmdl.exists():
                pc = self._read_tmdl(persp_tmdl)
                persp_names = [l.split()[-1].strip("'")
                               for l in pc.splitlines()
                               if l.strip().startswith("perspective ")]
                result["data_model"]["perspectives"] = [
                    {"name": n} for n in persp_names]

            # cultures.tmdl
            cult_tmdl = defn / "cultures.tmdl"
            if cult_tmdl.exists():
                cc = self._read_tmdl(cult_tmdl)
                cult_names = [l.split()[-1].strip("'")
                              for l in cc.splitlines()
                              if l.strip().startswith("culture ")]
                result["data_model"]["cultures"] = [
                    {"name": n} for n in cult_names]

            # diagramLayout.json
            diag = dataset_folder / "diagramLayout.json"
            if diag.exists():
                result["tmdl_files"]["diagram_layout"] = self._read_json(diag)

            # definition.pbism
            pbism = dataset_folder / "definition.pbism"
            if pbism.exists():
                result["tmdl_files"]["definition_pbism"] = self._read_json(pbism)

            # TMDLScripts/
            scripts_dir = dataset_folder / "TMDLScripts"
            if scripts_dir.exists():
                result["tmdl_files"]["tmdl_scripts"] = [
                    f.name for f in scripts_dir.glob("*.tmdl")]

        # -- REPORT LAYER -------------------------------------------
        if report_folder:
            pbir_file = report_folder / "report.pbir"
            if pbir_file.exists():
                result["pbip_report_files"]["report_pbir"] = \
                    self._read_json(pbir_file)

            defn_report = report_folder / "definition"

            # report.json
            report_json = defn_report / "report.json"
            if report_json.exists():
                result["pbip_report_files"]["report_json"] = \
                    self._read_json(report_json)

            # theme.json
            theme_json = defn_report / "theme.json"
            if not theme_json.exists():
                custom = list((defn_report/"CustomThemes").glob("*.json")) \
                         if (defn_report/"CustomThemes").exists() else []
                theme_json = custom[0] if custom else None
            if theme_json and Path(theme_json).exists():
                result["pbip_report_files"]["theme"] = \
                    self._read_json(Path(theme_json))

            # pages/*/page.json and visuals
            pages_dir = defn_report / "pages"
            if pages_dir.exists():
                pages_data: dict = {}
                visuals_data: dict = {}
                layout_pages = []

                for page_dir in sorted(pages_dir.iterdir()):
                    if not page_dir.is_dir(): continue
                    pjson_path = page_dir / "page.json"
                    pjson = self._read_json(pjson_path) \
                            if pjson_path.exists() else {}
                    pages_data[page_dir.name] = pjson

                    # Build layout page entry
                    layout_page: dict = {
                        "name":         pjson.get("displayName", page_dir.name),
                        "display_name": pjson.get("displayName", page_dir.name),
                        "width":        pjson.get("width", 1280),
                        "height":       pjson.get("height", 720),
                        "page_filters": pjson.get("filters",[]),
                        "page_config":  pjson,
                        "visuals":      [],
                    }

                    # visuals/*/visual.json
                    vis_dir = page_dir / "visuals"
                    if vis_dir.exists():
                        for vis_folder in sorted(vis_dir.iterdir()):
                            if not vis_folder.is_dir(): continue
                            vjson_path = vis_folder / "visual.json"
                            vjson = self._read_json(vjson_path) \
                                    if vjson_path.exists() else {}
                            visuals_data[vis_folder.name] = vjson

                            # Build layout visual entry
                            vtype = (vjson.get("visualType","") or
                                     vjson.get("$schema","").split("/")
                                     [-1].replace(".json",""))
                            pos   = vjson.get("position", vjson.get(
                                "layout",{}))
                            layout_page["visuals"].append({
                                "visual_type": vtype,
                                "x": pos.get("x",0),
                                "y": pos.get("y",0),
                                "width":  pos.get("width",0),
                                "height": pos.get("height",0),
                                "z_order":pos.get("tabOrder", pos.get("z",0)),
                                "config": vjson,
                                "filters": vjson.get("filters",[]),
                                "fields":  self._extract_fields_from_visual(vjson),
                            })
                    layout_pages.append(layout_page)

                result["pbip_report_files"]["pages"]   = pages_data
                result["pbip_report_files"]["visuals"] = visuals_data
                result["layout"]["pages"] = layout_pages
                result["layout"]["visualizations"] = {"pages": layout_pages}

            # StaticResources/
            static_dir = report_folder / "StaticResources"
            if not static_dir.exists():
                static_dir = report_folder.parent / "StaticResources"
            if static_dir.exists():
                static_files = [
                    {"name": f.name, "path": str(f), "type": f.suffix}
                    for f in static_dir.rglob("*") if f.is_file()
                ]
                result["pbip_report_files"]["static_resources"] = static_files

        print(f"[PBIPExtractor] Extracted from: {self.root}")
        if dataset_folder:
            tables = result["data_model"].get("tables",[])
            rels   = result["data_model"].get("relationships",[])
            print(f"  Dataset: {len(tables)} tables, {len(rels)} relationships")
        if report_folder:
            pages = result["layout"].get("pages",[])
            vis_count = sum(len(p.get("visuals",[])) for p in pages)
            print(f"  Report : {len(pages)} pages, {vis_count} visuals")
        return result

    def _extract_fields_from_visual(self, vjson: dict) -> list:
        """Extract field bindings from visual.json dataTransforms block."""
        fields = []
        dt = vjson.get("dataTransforms", vjson.get("query",{}))
        if not dt:
            return fields
        for proj in dt.get("projectionOrdering", {}).values():
            for item in (proj if isinstance(proj,list) else [proj]):
                if isinstance(item, dict):
                    fields.append({
                        "role":      "",
                        "table":     item.get("Table",""),
                        "column":    item.get("Property",""),
                        "query_ref": item.get("queryRef",""),
                    })
        return fields


class PBIXExtractor:
    """
    Unzips a .pbix file and parses each internal artifact
    into a normalised Python dict.

    Actual zip layout (from team's file):
        [Content_Types].xml
        DataModel          ← binary / JSON  --  semantic model
        DiagramLayout      ← relationship diagram positions
        Metadata           ← file-level metadata
        SecurityBindings   ← RLS role definitions
        Settings           ← report-level settings
        Version            ← format version string
        Report/            ← folder
            [Content_Types].xml  (may be present)
            ... layout files
    """

    def __init__(self, pbix_path: str, work_dir: str = "./pbix_extracted"):
        self.pbix_path = Path(pbix_path)
        # On Windows, long custom visual GUID folder names inside the PBIX
        # can cause the full extraction path to exceed 260 characters, which
        # Windows blocks with FileNotFoundError: [Errno 2].
        # Fix: extract to a short path in the system temp directory instead.
        import sys, tempfile
        if sys.platform == "win32":
            # Use C:\Users\<user>\AppData\Local\Temp\pbix_val\  --  always short
            self.work_dir = Path(tempfile.gettempdir()) / "pbix_val"
        else:
            self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._file_map: dict[str, Path] = {}
        # Keep user's requested output dir for reports (not for extraction)
        self._output_work_dir = Path(work_dir)

    # -- Extraction ---------------------------

    def extract(self) -> dict[str, Path]:
        """Rename .pbix → .zip, extract to short temp path, return {artifact_name: path}.
        Uses system temp directory on Windows to avoid the 260-char path limit
        that custom visual GUID folder names can trigger."""
        import shutil
        zip_path = self.work_dir / self.pbix_path.with_suffix(".zip").name
        shutil.copy(self.pbix_path, zip_path)

        extract_dir = self.work_dir / "contents"
        # Clean previous extraction to avoid stale files
        if extract_dir.exists():
            shutil.rmtree(extract_dir)

        with zipfile.ZipFile(zip_path, "r") as z:
            # Extract one file at a time so we can handle path-too-long
            # entries gracefully on Windows instead of crashing entirely
            for member in z.infolist():
                target = extract_dir / member.filename
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if not member.is_dir():
                        with z.open(member) as src, open(target, "wb") as dst:
                            dst.write(src.read())
                    self._file_map[member.filename] = target
                except OSError as e:
                    # Path too long (Windows) or permission error  --  skip the file
                    # but record it so we know what was skipped
                    print(f"[Extractor] WARNING  --  skipped (path too long or OS error): "
                          f"{member.filename}  ({e})")

        print(f"[Extractor] Extracted to: {extract_dir}")
        print(f"[Extractor] Found {len(self._file_map)} files in zip:")
        for name in sorted(self._file_map):
            print(f"            {name}")

        self._diagnose_formats()
        return self._file_map

    def _diagnose_formats(self):
        """
        Print the encoding format of each key artifact.
        Helps identify which PBIX version / encoding is in use.
        """
        KEY_FILES = ["DataModel", "Metadata", "Settings",
                     "SecurityBindings", "Report/Layout", "Version"]
        FORMAT_SIGNATURES = {
            b'\xd0\xcf\x11\xe0': "OLE2 compound binary",
            b'\x1f\x8b':         "gzip compressed",
            b'\x78\x9c':         "zlib compressed (default)",
            b'\x78\x01':         "zlib compressed (low)",
            b'\x78\xda':         "zlib compressed (best)",
            b'\xff\xfe':         "UTF-16 LE with BOM",
            b'\xfe\xff':         "UTF-16 BE with BOM",
            b'\xef\xbb\xbf':     "UTF-8 with BOM",
            b'\x7b':             "UTF-8 JSON (starts with {)",
            b'\x5b':             "UTF-8 JSON array (starts with [)",
        }
        print("\n[Extractor] File format diagnostics:")
        for name in KEY_FILES:
            path = self._file_map.get(name)
            if not path or not Path(path).exists():
                print(f"            {name:<25} NOT FOUND")
                continue
            raw = Path(path).read_bytes()
            size = len(raw)
            sig  = raw[:4]
            fmt  = "unknown"
            for magic, label in FORMAT_SIGNATURES.items():
                if sig[:len(magic)] == magic:
                    fmt = label
                    break
            print(f"            {name:<25} {size:>8} bytes  [{fmt}]  hex={sig.hex()}")

    def _read(self, name: str) -> str | None:
        """
        Read a named artifact as text.

        This PBIX file uses UTF-16 LE WITHOUT a BOM for ALL internal files
        (confirmed by hex diagnostics: Metadata=7b0022, Settings=7b0022,
        DataModel=54006800, Report/Layout=7b0022, Version=31002e00).

        Strategy order:
          1. UTF-16 LE without BOM  ← primary for this PBIX version
          2. UTF-16 LE with BOM
          3. UTF-8 with BOM
          4. UTF-8 plain
          5. zlib then UTF-16 LE
          6. gzip then UTF-16 LE
        """
        path = self._file_map.get(name)
        if not path or not Path(path).exists():
            return None

        raw_bytes = Path(path).read_bytes()
        if not raw_bytes:
            return None

        # -- OLE2 compound binary  --  truly unreadable without oletools --
        if raw_bytes[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
            print(f"[Extractor] {name} is OLE2 binary  --  cannot decode as text")
            return None

        # -- SecurityBindings DPAPI blob  --  skip silently ---------------
        # Starts with 01000000d08c9ddf which is the Windows DPAPI header
        if raw_bytes[:4] == b'\x01\x00\x00\x00' and raw_bytes[4:8] == b'\xd0\x8c\x9d\xdf':
            return None  # encrypted blob  --  no text content

        def _try_utf16le_no_bom(data: bytes) -> str | None:
            """Decode as UTF-16 LE without BOM and validate."""
            try:
                text = data.decode("utf-16-le")
                stripped = text.strip().strip('\x00')
                # Must look like JSON or plain text content
                if stripped and (
                    stripped[0] in ('{', '[', '"', '1', '2', '3', '4', '5')
                    or stripped[:2] in ('{"', '["')
                ):
                    return stripped
            except (UnicodeDecodeError, ValueError):
                pass
            return None

        # 1. UTF-16 LE without BOM (primary  --  confirmed format for this PBIX)
        result = _try_utf16le_no_bom(raw_bytes)
        if result:
            return result

        # 2. UTF-16 LE with BOM
        if raw_bytes[:2] in (b'\xff\xfe', b'\xfe\xff'):
            try:
                text = raw_bytes.decode("utf-16").strip().strip('\x00')
                if text:
                    return text
            except (UnicodeDecodeError, ValueError):
                pass

        # 3. UTF-8 with BOM
        try:
            text = raw_bytes.decode("utf-8-sig").strip().strip('\x00')
            if text and ('{' in text or '[' in text):
                return text
        except (UnicodeDecodeError, ValueError):
            pass

        # 4. UTF-8 plain
        try:
            text = raw_bytes.decode("utf-8").strip().strip('\x00')
            if text and ('{' in text or '[' in text):
                return text
        except (UnicodeDecodeError, ValueError):
            pass

        # 5. zlib then try UTF-16 LE (some compressed PBIX variants)
        try:
            import zlib
            decompressed = zlib.decompress(raw_bytes)
            result = _try_utf16le_no_bom(decompressed)
            if result:
                return result
            return decompressed.decode("utf-8-sig").strip()
        except Exception:
            pass

        # 6. gzip then UTF-16 LE
        try:
            import gzip, io
            with gzip.GzipFile(fileobj=io.BytesIO(raw_bytes)) as gz:
                decompressed = gz.read()
            result = _try_utf16le_no_bom(decompressed)
            if result:
                return result
            return decompressed.decode("utf-8-sig").strip()
        except Exception:
            pass

        return None

    def _read_json(self, name: str) -> dict | None:
        """
        Parse a named artifact as JSON.
        Handles common PBIX quirks:
          - Single-quoted keys (non-standard JSON)
          - Trailing commas
          - Content wrapped in outer array instead of object
        """
        raw = self._read(name)
        if not raw:
            return None

        # Strip any leading/trailing whitespace and null bytes
        raw = raw.strip().strip('\x00')
        if not raw:
            return None

        # Direct parse attempt
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # Try fixing single-quoted keys → double-quoted (some PBI metadata)
        try:
            fixed = re.sub(r"'([^']+)'(\s*:)", r'"\1"\2', raw)
            fixed = re.sub(r":\s*'([^']*)'", r': "\1"', fixed)
            return json.loads(fixed)
        except (json.JSONDecodeError, re.error):
            pass

        # Try extracting JSON object/array from surrounding garbage bytes
        try:
            match = re.search(r'(\{.*\}|\[.*\])', raw, re.DOTALL)
            if match:
                return json.loads(match.group())
        except (json.JSONDecodeError, re.error):
            pass

        print(f"[Extractor] Warning  --  {name} could not be parsed as JSON "
              f"(first 40 bytes hex: {Path(self._file_map[name]).read_bytes()[:40].hex()})")
        return None

    # -- Parsed artifact accessors ------------

    def get_metadata(self) -> dict:
        """Parse the Metadata file."""
        data = self._read_json("Metadata") or {}
        return {
            "created":    data.get("Created", ""),
            "modified":   data.get("Modified", ""),
            "locale":     data.get("Locale", ""),
            "version":    (self._read("Version") or "").strip(),
            "model_size": data.get("DataModelSize", None),
        }

    def _extract_via_pbixray(self) -> dict:
        """
        Use the pbixray package to read semantic model data directly from
        the PBIX file. Works for ALL PBIX types including Service-downloaded
        XPress9-compressed files that the standard JSON decode strategies
        cannot read.

        Returns the same dict structure as _parse_bim() so all downstream
        check methods work identically regardless of how the model was read.
        """
        if not PBIXRAY_AVAILABLE:
            return {}

        pbix_path = str(self.pbix_path)
        try:
            ray = _PBIXRay(pbix_path)
        except Exception as e:
            print(f"[pbixray] Failed to open PBIX: {e}")
            return {}

        print("[pbixray] Reading semantic model from Vertipaq engine...")

        # ── NaN → None helper ────────────────────────────────────────
        # pbixray returns pandas NaN (float) for absent optional fields.
        # Serialising NaN as string produces "nan" which causes false
        # MISSING results when compared to None from JSON.
        import math as _math
        def _clean(v):
            """Convert NaN / 'nan' / None to empty string; keep real values."""
            if v is None:
                return ''
            if isinstance(v, float) and _math.isnan(v):
                return ''
            s = str(v)
            if s.lower() == 'nan':
                return ''
            return s

        # ── DataType integer → string mapping (AMO / pbixray tmschema_columns) ──
        # Source: pbixray/utils.py AMO_PANDAS_TYPE_MAPPING (authoritative).
        # These are AMO DataType integers stored in tmschema_columns,
        # NOT the standard TOM DataType enum.
        #   2  = string   (Text: source columns, CSV/SharePoint fields)
        #   6  = int64    (Whole Number: Year, MonthNo, Tenure etc.)
        #   8  = double   (Decimal Number / Float64: Premium, Sum Assured)
        #   9  = dateTime (Date/Time: Start Date etc.)
        #   10 = decimal  (Fixed Decimal / Currency)
        #   11 = boolean  (True/False columns)
        #   17 = binary   (bytes)
        DATATYPE_STR = {
            0:  'unsupported',
            2:  'string',
            6:  'int64',
            8:  'double',
            9:  'dateTime',
            10: 'decimal',
            11: 'boolean',
            17: 'binary',
        }

        # ── SummarizeBy integer → string mapping (AMO tmschema enum) ────
        # Source: MS-SSAS tmschema spec + verified empirically against PBIX.
        # NOTE: tmschema SummarizeBy starts at 1, NOT 0.
        #   1 = default        (engine default — H$/internal hierarchy cols)
        #   2 = none           (Don't Summarize — all text/string user cols)
        #   3 = sum            (numeric cols: Premium, Sum Assured, Tenure)
        #   4 = min
        #   5 = max
        #   6 = count
        #   7 = average
        #   8 = distinctCount
        SUMMARIZE_STR = {
            1: 'default',
            2: 'none',
            3: 'sum',
            4: 'min',
            5: 'max',
            6: 'count',
            7: 'average',
            8: 'distinctCount',
        }

        # ── helper: safe DataFrame access ──────────────────────────
        def df(attr):
            try:
                result = getattr(ray, attr)
                if result is None or (hasattr(result, '__len__') and len(result) == 0):
                    return None
                return result
            except Exception:
                return None

        def df_rows(attr):
            d = df(attr)
            if d is None: return []
            return d.to_dict('records')

        # ── model-level scalars from tmschema_model ─────────────────
        model_rows = df_rows('tmschema_model')
        model_row  = model_rows[0] if model_rows else {}

        dao_raw = model_row.get('DataAccessOptions', '')
        try:
            dao = json.loads(dao_raw) if dao_raw and isinstance(dao_raw, str) else {}
        except Exception:
            dao = {}

        # ── annotations ─────────────────────────────────────────────
        ann_rows = df_rows('tmschema_annotations')
        annotations = [
            {'name': a.get('Name',''), 'value': a.get('Value','')}
            for a in ann_rows
        ]
        auto_datetime = any(
            a.get('Name') == '__PBI_TimeIntelligenceEnabled' and
            str(a.get('Value','')) == '1'
            for a in ann_rows
        )

        # ── tables ──────────────────────────────────────────────────
        tbl_rows  = df_rows('tmschema_tables')
        col_rows  = df_rows('tmschema_columns')
        hier_rows = df_rows('tmschema_hierarchies')
        lvl_rows  = df_rows('tmschema_levels')
        var_rows  = df_rows('tmschema_variations')
        ep_rows   = df_rows('tmschema_extended_properties')
        rcd_rows  = df_rows('tmschema_related_column_details') if hasattr(ray,'tmschema_related_column_details') else []

        # dax_measures: Name, Expression, DisplayFolder, Description, TableName
        meas_rows = df_rows('dax_measures')
        # dax_tables: calculated tables
        dax_tbl_rows = df_rows('dax_tables')
        # dax_columns: calculated columns
        dax_col_rows = df_rows('dax_columns')
        # power_query: M expressions
        pq_rows = df_rows('power_query')

        # Build lookup dicts
        pq_lkp  = {r.get('TableName','').lower(): r.get('Expression','') for r in pq_rows}
        dax_tbl_lkp = {r.get('TableName','').lower(): r.get('Expression','') for r in dax_tbl_rows}
        dax_col_lkp = {}
        for r in dax_col_rows:
            key = f"{r.get('TableName','').lower()}.{r.get('ColumnName','').lower()}"
            dax_col_lkp[key] = r.get('Expression','')
        meas_lkp = {}
        for r in meas_rows:
            key = r.get('TableName','').lower()
            meas_lkp.setdefault(key, []).append(r)
        hier_lkp = {}
        for h in hier_rows:
            hier_lkp.setdefault(h.get('TableName','').lower(), []).append(h)
        lvl_lkp = {}
        for lv in lvl_rows:
            lvl_lkp.setdefault(str(lv.get('HierarchyID','')), []).append(lv)
        var_lkp = {}
        for v in var_rows:
            # Key by ColumnID so each column only gets its OWN variations,
            # not all variations for the whole table (avoids false positives).
            col_id = str(v.get('ColumnID', ''))
            if col_id:
                var_lkp.setdefault(col_id, []).append(v)
        ep_lkp = {}
        for ep in ep_rows:
            ep_lkp.setdefault(str(ep.get('ObjectID','')), []).append(ep)
        rcd_lkp = {}
        for rcd in (rcd_rows or []):
            rcd_lkp.setdefault(str(rcd.get('ColumnID','')), rcd)

        tables = []
        for trow in tbl_rows:
            tname    = trow.get('Name','')
            tname_lc = tname.lower()
            tid      = str(trow.get('ID',''))

            # Columns for this table
            t_cols = [c for c in col_rows if c.get('TableName','') == tname]
            cols   = []
            for c in t_cols:
                if c.get('Type') == 2:  # rowNumber type
                    continue
                cname  = c.get('Name','')
                cid    = str(c.get('ID',''))
                col_key= f"{tname_lc}.{cname.lower()}"
                col_ep = ep_lkp.get(cid, [])
                col_rcd= rcd_lkp.get(cid, {})

                # Expression: DAX for calculated, M handled via partition
                expr = dax_col_lkp.get(col_key, '') or ''
                if c.get('Expression') and not expr:
                    expr = str(c.get('Expression',''))

                cols.append({
                    'name':               cname,
                    'data_type':          DATATYPE_STR.get(
                        c.get('DataType', 0), str(c.get('DataType',''))),
                    'is_nullable':        bool(c.get('IsNullable', True)),
                    'expression':         _clean(dax_col_lkp.get(col_key, '') or c.get('Expression','')),
                    'type':               'calculated' if _clean(dax_col_lkp.get(col_key,'')) else '',
                    'sourceColumn':       _clean(c.get('SourceColumn','')),
                    'formatString':       _clean(c.get('FormatString','')),
                    'isHidden':           bool(c.get('IsHidden', False)),
                    'summarizeBy':        SUMMARIZE_STR.get(
                        c.get('SummarizeBy', 0), _clean(c.get('SummarizeBy',''))),
                    'dataCategory':       _clean(c.get('DataCategory','')),
                    'sortByColumn':       '',   # not in tmschema_columns
                    'displayFolder':      _clean(c.get('DisplayFolder','')),
                    'lineageTag':         _clean(c.get('LineageTag','')),
                    'isNameInferred':     bool(c.get('IsNameInferred', False)) if 'IsNameInferred' in c else False,
                    'isDataTypeInferred': False,
                    'changedProperties':  [],
                    'variations':         var_lkp.get(str(c.get('ID','')), []),
                    'extendedProperties': col_ep,
                    'relatedColumnDetails': col_rcd,
                })

            # Measures for this table
            t_meas_rows = meas_lkp.get(tname_lc, [])
            measures = []
            for m in t_meas_rows:
                # dax_measures columns: Name, Expression, DisplayFolder, Description
                # FormatString is not in dax_measures -- use empty string
                measures.append({
                    'name':          _clean(m.get('Name','')),
                    'expression':    _clean(m.get('Expression','')),
                    'format_string': '',
                    'description':   _clean(m.get('Description','')),
                    'isHidden':      False,
                    'is_hidden':     False,
                    'displayFolder': _clean(m.get('DisplayFolder','')),
                    'lineageTag':    '',
                    'kpi':           {},
                })

            # Partition: M expression (power_query) or DAX (dax_tables)
            m_expr   = pq_lkp.get(tname_lc, '')
            dax_expr = dax_tbl_lkp.get(tname_lc, '')
            src_type = 'm' if m_expr else ('calculated' if dax_expr else '')
            partition = [{
                'name':   tname,
                'mode':   'import',
                'source': {
                    'type':       src_type,
                    'expression': m_expr or dax_expr,
                },
            }]

            # Hierarchies for this table
            t_hiers = hier_lkp.get(tname_lc, [])
            hierarchies = []
            for h in t_hiers:
                hid  = str(h.get('ID',''))
                lvls = sorted(lvl_lkp.get(hid, []), key=lambda x: x.get('Ordinal',0))
                hierarchies.append({
                    'name':       h.get('Name',''),
                    'lineageTag': h.get('LineageTag','') or '',
                    'levels': [{
                        'name':       lv.get('Name',''),
                        'ordinal':    lv.get('Ordinal', i),
                        'column':     lv.get('ColumnName',''),
                        'lineageTag': lv.get('LineageTag','') or '',
                    } for i, lv in enumerate(lvls)],
                })

            tables.append({
                'name':               tname,
                'hidden':             bool(trow.get('IsHidden', False)),
                'description':        trow.get('Description','') or '',
                'lineageTag':         trow.get('LineageTag','') or '',
                'isPrivate':          bool(trow.get('IsPrivate', False)),
                'showAsVariationsOnly': bool(trow.get('ShowAsVariationsOnly', False)),
                'columns':            cols,
                'measures':           measures,
                'partitions':         partition,
                'hierarchies':        hierarchies,
            })

        # ── relationships ────────────────────────────────────────────
        rel_rows = df_rows('relationships')
        relationships = []
        for r in rel_rows:
            # pbixray Cardinality: 'M:1', '1:1', etc.
            card_raw = str(r.get('Cardinality','M:1'))
            card_map = {
                'M:1': 'many:one', '1:M': 'one:many',
                '1:1': 'one:one',  'M:M': 'many:many',
                'M:N': 'many:many',
            }
            cardinality = card_map.get(card_raw, card_raw.lower())
            xfilter_raw = str(r.get('CrossFilteringBehavior',''))
            xfilter_map = {
                'Both': 'bothDirections', 'Single': 'oneDirection',
                '2': 'bothDirections',    '1': 'oneDirection',
            }
            # pbixray returns NaN (float) for auto-datetime relationships
            # where ToTable/ToColumn point to hidden LocalDateTable
            def _str(v):
                import math
                if v is None: return ''
                if isinstance(v, float) and math.isnan(v): return ''
                return str(v)

            relationships.append({
                'from_table':         _str(r.get('FromTableName')),
                'from_column':        _str(r.get('FromColumnName')),
                'to_table':           _str(r.get('ToTableName')),
                'to_column':          _str(r.get('ToColumnName')),
                'name':               '',
                'cardinality':        cardinality,
                'cross_filter':       xfilter_map.get(xfilter_raw, xfilter_raw),
                'is_active':          bool(r.get('IsActive', True)),
                'joinOnDateBehavior': '',
            })

        # ── RLS roles ────────────────────────────────────────────────
        rls_df   = df('rls')
        rls_rows = rls_df.to_dict('records') if rls_df is not None else []
        # Group by RoleName
        role_dict: dict = {}
        for r in rls_rows:
            rname = r.get('RoleName','')
            if rname not in role_dict:
                role_dict[rname] = {
                    'name':               rname,
                    'model_permission':   'read',
                    'table_permissions':  [],
                    'column_permissions': [],
                }
            fexpr = r.get('FilterExpression','')
            if isinstance(fexpr, float):  # NaN
                fexpr = ''
            role_dict[rname]['table_permissions'].append({
                'table':      r.get('TableName',''),
                'filter_dax': str(fexpr).strip() if fexpr else '',
            })
        rls_roles = list(role_dict.values())

        # ── M Query Parameters ───────────────────────────────────────
        mq_params = df_rows('m_parameters')
        mq_parameters = [
            {
                # pbixray m_parameters column is 'ParameterName' (not 'Name')
                'name':          p.get('ParameterName', p.get('Name', p.get('name',''))),
                'kind':          'm',
                'expression':    str(p.get('Expression','') or ''),
                'default_value': str(p.get('Value', p.get('default_value','')) or ''),
            }
            for p in (mq_params or [])
        ]

        # ── Cultures ─────────────────────────────────────────────────
        cult_rows = df_rows('tmschema_cultures')
        trans_rows = df_rows('tmschema_translations') or []
        cultures_full = []
        for c in (cult_rows or []):
            cid   = c.get('ID')
            c_trans = [t for t in trans_rows if t.get('CultureID') == cid]
            cultures_full.append({
                'name':              c.get('Name',''),
                'translations':      c_trans,
                'translation_count': len(c_trans),
            })

        # ── Perspectives ─────────────────────────────────────────────
        persp_rows = df_rows('tmschema_perspectives') or []
        perspectives = [{'name': p.get('Name','')} for p in persp_rows]

        # ── Incremental refresh policies ─────────────────────────────
        rp_rows = df_rows('tmschema_refresh_policies') or []

        n_tables = len(tables)
        n_rels   = len(relationships)
        n_meas   = sum(len(t['measures']) for t in tables)
        n_rls    = len(rls_roles)
        print(f"[pbixray] Extracted: {n_tables} tables, {n_rels} relationships, "
              f"{n_meas} measures, {n_rls} RLS role(s)")

        return {
            'tables':           tables,
            'relationships':    relationships,
            'annotations':      annotations,
            'data_sources':     [],
            'mq_parameters':    mq_parameters,
            'rls_roles':        rls_roles,
            'culture':          model_row.get('Culture',''),
            'source_query_culture': model_row.get('SourceQueryCulture',''),
            'default_pbi_datasource_version':
                model_row.get('DefaultPowerBIDataSourceVersion',''),
            'data_access_options': {
                'legacyRedirects':         dao.get('legacyRedirects', None),
                'returnErrorValuesAsNull': dao.get('returnErrorValuesAsNull', None),
            },
            'cultures_full':    cultures_full,
            'auto_date_time_enabled': auto_datetime,
            'perspectives':     perspectives,
            'refresh_policies': rp_rows,
            '_source':          'pbixray',   # internal marker
            '_pq_raw':          [{'TableName': r['TableName'], 'Expression': r['Expression']}
                                 for r in (pq_rows or [])],  # raw M expressions for D1
        }

    def get_data_model(self) -> dict:
        """
        Parse the DataModel artifact.

        In this PBIX the DataModel is a Tabular BIM JSON encoded
        as UTF-16 LE without BOM (hex: 54 00 68 00 = 'T','h' in UTF-16 LE,
        beginning of 'This' as in {"name":"ThisWorkbookDataModel",...}).
        """
        path = self._file_map.get("DataModel")
        if not path or not Path(path).exists():
            return {}

        raw_bytes = Path(path).read_bytes()
        bim = None

        # Strategy 1: UTF-16 LE without BOM (confirmed by hex=54006800)
        try:
            text = raw_bytes.decode("utf-16-le").strip().strip('\x00')
            if text and ('{' in text or '[' in text):
                bim = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass

        # Strategy 2: UTF-16 LE with BOM
        if bim is None and raw_bytes[:2] in (b'\xff\xfe', b'\xfe\xff'):
            try:
                text = raw_bytes.decode("utf-16").strip().strip('\x00')
                bim = json.loads(text)
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass

        # Strategy 3: UTF-8 variants
        if bim is None:
            for enc in ("utf-8-sig", "utf-8"):
                try:
                    text = raw_bytes.decode(enc).strip()
                    bim = json.loads(text)
                    break
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue

        # Strategy 4: model.bim exported to sub-folder by Tabular Editor
        if bim is None:
            model_bim_path = self.work_dir / "contents" / "DataModel" / "model.bim"
            if model_bim_path.exists():
                try:
                    text = model_bim_path.read_text(encoding="utf-8-sig")
                    bim = json.loads(text)
                except Exception:
                    pass

        # Strategy 5: pbixray  --  reads Vertipaq engine directly
        # Handles XPress9-compressed Service-downloaded PBIXs that all
        # JSON decode strategies above cannot parse.
        if bim is None and PBIXRAY_AVAILABLE:
            result = self._extract_via_pbixray()
            if result.get('tables'):
                return result
            else:
                print("[pbixray] Returned no tables  --  falling through")

        if bim is None:
            msg = "[Extractor] DataModel could not be parsed"
            if not PBIXRAY_AVAILABLE:
                msg += ("  --  install pbixray for full support: "
                        "pip install pbixray")
            else:
                msg += f"  --  first 8 bytes: {raw_bytes[:8].hex()}"
            print(msg)
            return {"raw_detected": True}

        return self._parse_bim(bim)

    def _parse_bim_cardinality(self, from_card: str, to_card: str) -> str:
        """
        Convert BIM fromCardinality + toCardinality to a normalised string.

        BIM values:
          fromCardinality: "many" | "one" | "" (absent = many, the default)
          toCardinality:   "many" | "one" | "" (absent = one, the default)

        Most relationships are many-to-one (fact → dimension).
        When both fields are absent, BIM defaults to many:one.

        Returns normalised form matching JSON vocabulary:
          "many:one"  → "many_to_one"
          "one:one"   → "one_to_one"
          "many:many" → "many_to_many"
          "one:many"  → "one_to_many"
        """
        # Default: from=many, to=one (standard fact→dimension relationship)
        fc = (from_card or "many").lower().strip()
        tc = (to_card   or "one").lower().strip()

        BIM_CARD_MAP = {
            "many:one":  "many_to_one",
            "one:one":   "one_to_one",
            "many:many": "many_to_many",
            "one:many":  "one_to_many",
        }
        key = f"{fc}:{tc}"
        return BIM_CARD_MAP.get(key, key)

    def _parse_bim(self, bim: dict) -> dict:
        """Extract tables, columns, measures, relationships, and M Query parameters from BIM JSON."""
        model = bim.get("model", bim)   # handle both root and nested model

        tables = []
        for t in model.get("tables", []):
            cols = []
            for c in t.get("columns", []):
                if c.get("type") == "rowNumber":   # skip internal cols
                    continue
                expr_raw = c.get("expression", "")
                cols.append({
                    "name":                  c.get("name", ""),
                    "data_type":             c.get("dataType", ""),
                    "is_nullable":           c.get("isNullable", True),
                    "expression":            expr_raw,
                    "type":                  c.get("type", ""),
                    "sourceColumn":          c.get("sourceColumn", ""),
                    # D3 formatting / visibility
                    "formatString":          c.get("formatString", ""),
                    "isHidden":              c.get("isHidden", False),
                    "summarizeBy":           c.get("summarizeBy", ""),
                    "dataCategory":          c.get("dataCategory", ""),
                    "sortByColumn":          c.get("sortByColumn", ""),
                    "displayFolder":         c.get("displayFolder", ""),
                    # Lineage & identity (needed by RE/OP to track renames)
                    "lineageTag":            c.get("lineageTag", ""),
                    # Type inference flags
                    "isNameInferred":        c.get("isNameInferred", False),
                    "isDataTypeInferred":    c.get("isDataTypeInferred", False),
                    # changedProperties: list of {property} dicts — signals explicit overrides
                    "changedProperties":     [p.get("property","") for p in c.get("changedProperties", [])],
                    # variations: links date column to its auto-datetime LocalDateTable
                    "variations":            c.get("variations", []),
                    # extendedProperties: Field Parameter ParameterMetadata (version/kind)
                    "extendedProperties":    c.get("extendedProperties", []),
                    # relatedColumnDetails: Field Parameter groupByColumns reference
                    "relatedColumnDetails":  c.get("relatedColumnDetails", {}),
                })

            measures = []
            for m in t.get("measures", []):
                expr_raw = m.get("expression", "")
                measures.append({
                    "name":          m.get("name", ""),
                    "expression":    expr_raw,
                    "format_string": m.get("formatString", ""),
                    "description":   m.get("description", ""),
                    "isHidden":      m.get("isHidden", False),
                    "is_hidden":     m.get("isHidden", False),
                    "displayFolder": m.get("displayFolder", ""),
                    # Lineage tracking
                    "lineageTag":    m.get("lineageTag", ""),
                    # Full KPI object (statusExpression, targetExpression, trendExpression)
                    "kpi":           m.get("kpi", {}),
                })

            # -- Build partitions; preserve raw source dict for DAX table detection --
            partitions = []
            for p in t.get("partitions", []):
                src_obj = p.get("source", {})
                if isinstance(src_obj, dict):
                    expr_raw = src_obj.get("expression", "")
                    src_type = src_obj.get("type", "")
                else:
                    expr_raw = str(src_obj or "")
                    src_type = ""
                partitions.append({
                    "name":   p.get("name", ""),
                    "mode":   p.get("mode", "import"),
                    "source": {
                        "type":       src_type,
                        "expression": (
                            "\n".join(expr_raw)
                            if isinstance(expr_raw, list)
                            else str(expr_raw or "")
                        ),
                    },
                })

            tables.append({
                "name":               t.get("name", ""),
                "hidden":             t.get("isHidden", False),
                "description":        t.get("description", ""),
                "lineageTag":         t.get("lineageTag", ""),
                "isPrivate":          t.get("isPrivate", False),
                "showAsVariationsOnly": t.get("showAsVariationsOnly", False),
                "columns":     cols,
                "measures":    measures,
                "partitions":  partitions,
                "hierarchies": [
                    {
                        "name":       h.get("name", ""),
                        "lineageTag": h.get("lineageTag", ""),
                        "levels": [
                            {
                                "name":       lv.get("name", ""),
                                "ordinal":    lv.get("ordinal", i),
                                "column":     lv.get("column", ""),
                                "lineageTag": lv.get("lineageTag", ""),
                            }
                            for i, lv in enumerate(h.get("levels", []))
                        ],
                    }
                    for h in t.get("hierarchies", [])
                ],
            })

        relationships = [
            {
                "from_table":          r.get("fromTable", ""),
                "from_column":         r.get("fromColumn", ""),
                "to_table":            r.get("toTable", ""),
                "to_column":           r.get("toColumn", ""),
                # BIM relationship name is a UUID — used in USERELATIONSHIP() calls
                "name":                r.get("name", ""),
                "cardinality":         self._parse_bim_cardinality(
                    r.get("fromCardinality",""),
                    r.get("toCardinality","")
                ),
                "cross_filter":        r.get("crossFilteringBehavior", "oneDirection"),
                "is_active":           not r.get("isActive", True) is False,
                # joinOnDateBehavior: datePartOnly vs exact
                # Wrong setting = date joins match full timestamp → silent data errors
                "joinOnDateBehavior":  r.get("joinOnDateBehavior", ""),
            }
            for r in model.get("relationships", [])
        ]

        # -- Extract M Query Parameters (Manage Parameters) from BIM expressions --
        # BIM stores these in model.expressions[]  where the M expression contains
        # "IsParameterQuery=true" or "IsParameterQueryRequired=true"
        mq_parameters = []
        for expr in model.get("expressions", []):
            expr_text = expr.get("expression", "")
            if isinstance(expr_text, list):
                expr_text = "\n".join(expr_text)
            expr_text_lower = expr_text.lower()
            if "isparameterquery" in expr_text_lower:
                # Extract default value from M: meta [IsParameterQuery=true, Default=...]
                default_val = ""
                for line in expr_text.splitlines():
                    l = line.strip()
                    # Pattern: = "SomeValue" meta [IsParameterQuery=true]
                    if "isparameterquery" not in l.lower() and "=" in l:
                        val = l.split("=", 1)[-1].strip().strip(",").strip()
                        if val.startswith('"') or val[0:1].isdigit():
                            default_val = val.strip('"')
                mq_parameters.append({
                    "name":          expr.get("name", ""),
                    "kind":          expr.get("kind", "m"),
                    "expression":    expr_text.strip()[:300],
                    "default_value": default_val,
                })

        # -- RLS roles and OLS from model.roles[] ------------------
        # SecurityBindings in PBIX is DPAPI-encrypted and unreadable.
        # The BIM file's model.roles[] is the only readable source of
        # RLS role definitions when --bim is supplied.
        rls_roles = []
        for role in model.get("roles", []):
            tbl_perms = []
            col_perms = []
            for tp in role.get("tablePermissions", []):
                # filterExpression may be a list of strings (TE2 format) or a plain string
                fexpr = tp.get("filterExpression", "")
                if isinstance(fexpr, list):
                    fexpr = "\n".join(fexpr)
                tbl_perms.append({
                    "table":          tp.get("name", ""),
                    "filter_dax":     fexpr.strip(),
                })
                # OLS: columnPermissions[] under each tablePermission
                for cp in tp.get("columnPermissions", []):
                    col_perms.append({
                        "table":               tp.get("name", ""),
                        "column":              cp.get("name", ""),
                        "metadataPermission":  cp.get("metadataPermission", "none"),
                    })
            rls_roles.append({
                "name":               role.get("name", ""),
                "model_permission":   role.get("modelPermission", "read"),
                "table_permissions":  tbl_perms,
                "column_permissions": col_perms,
            })

        # -- model-level scalar properties -------------------------
        data_access_opts = model.get("dataAccessOptions", {})

        # -- cultures: extract translations content too -------------
        cultures_full = []
        for cult in model.get("cultures", []):
            trans = cult.get("translations", {})
            # translations{} maps objectType → {objectId → {property → caption}}
            # Flatten to a list of {object_type, object_name, property, caption}
            translations_flat = []
            for obj_type, obj_map in trans.items():
                if isinstance(obj_map, dict):
                    for obj_id, prop_map in obj_map.items():
                        if isinstance(prop_map, dict):
                            for prop, caption in prop_map.items():
                                translations_flat.append({
                                    "object_type": obj_type,
                                    "object_name": obj_id,
                                    "property":    prop,
                                    "caption":     caption,
                                })
            cultures_full.append({
                "name":              cult.get("name", ""),
                "translations":      translations_flat,
                "translation_count": len(translations_flat),
            })

        return {
            "tables":           tables,
            "relationships":    relationships,
            "annotations":      model.get("annotations", []),
            "data_sources":     model.get("dataSources", []),
            "mq_parameters":    mq_parameters,
            "rls_roles":        rls_roles,
            # Model-level scalar fields
            "culture":          model.get("culture", ""),
            "source_query_culture": model.get("sourceQueryCulture", ""),
            "default_pbi_datasource_version": model.get("defaultPowerBIDataSourceVersion", ""),
            # dataAccessOptions: affects DirectQuery/error behaviour
            "data_access_options": {
                "legacyRedirects":          data_access_opts.get("legacyRedirects", None),
                "returnErrorValuesAsNull":  data_access_opts.get("returnErrorValuesAsNull", None),
            },
            # Cultures with full translation content
            "cultures_full":    cultures_full,
            # Auto date/time flag from annotations
            "auto_date_time_enabled": any(
                ann.get("name","") == "__PBI_TimeIntelligenceEnabled" and
                str(ann.get("value","")) == "1"
                for ann in model.get("annotations", [])
            ),
        }

    def get_security_bindings(self) -> list[dict]:
        """Parse SecurityBindings for RLS roles."""
        data = self._read_json("SecurityBindings") or {}
        roles = []
        for role in data.get("roles", []):
            roles.append({
                "name":        role.get("name", ""),
                "model_permission": role.get("modelPermission", ""),
                "table_permissions": [
                    {
                        "table":      tp.get("name", ""),
                        "filter_dax": tp.get("filterExpression", ""),
                    }
                    for tp in role.get("tablePermissions", [])
                ],
            })
        return roles

    def get_report_layout(self) -> dict:
        """
        Parse the Report/Layout file.

        PBIX version differences:
          - Older PBIX : Report/Layout is plain JSON
          - Newer PBIX : Report/Layout is a JSON wrapper whose 'blob' key
                         holds a base64-encoded zlib-compressed JSON string
          - Some builds : Report/Layout is raw UTF-16 encoded JSON
        """
        candidates = [
            "Report/Layout",
            "Report/Layout.json",
            "Report/ReportDocument.json",
        ]
        raw_bytes = None
        used_name = None
        for name in candidates:
            path = self._file_map.get(name)
            if path and Path(path).exists():
                raw_bytes = Path(path).read_bytes()
                used_name = name
                break

        if not raw_bytes:
            # Scan Report subfolder
            for key in self._file_map:
                if key.startswith("Report/") and not key.endswith((".xml", ".PNG", ".json")):
                    path = self._file_map[key]
                    if Path(path).exists():
                        raw_bytes = Path(path).read_bytes()
                        used_name = key
                        break

        if not raw_bytes:
            print("[Extractor] Warning  --  no Report layout file found.")
            return {}

        layout = None

        # -- Strategy 1: UTF-16 LE without BOM (confirmed format) --
        try:
            text = raw_bytes.decode("utf-16-le").strip().strip('\x00')
            if text and '{' in text:
                layout = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass

        # -- Strategy 2: UTF-16 LE with BOM ------------------------
        if layout is None and raw_bytes[:2] in (b'\xff\xfe', b'\xfe\xff'):
            try:
                text = raw_bytes.decode("utf-16").strip().strip('\x00')
                layout = json.loads(text)
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass

        # -- Strategy 3: UTF-8 variants ----------------------------
        if layout is None:
            for enc in ("utf-8-sig", "utf-8", "latin-1"):
                try:
                    text = raw_bytes.decode(enc).strip().strip('\x00')
                    if text and '{' in text:
                        layout = json.loads(text)
                        break
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue

        # -- Strategy 4: Wrapper JSON with base64+zlib blob --------
        if layout is None:
            try:
                wrapper_text = raw_bytes.decode("utf-16-le").strip().strip('\x00')
                wrapper = json.loads(wrapper_text)
                if "blob" in wrapper:
                    import base64, zlib
                    blob_bytes = base64.b64decode(wrapper["blob"])
                    try:
                        decompressed = zlib.decompress(blob_bytes)
                    except zlib.error:
                        decompressed = zlib.decompress(blob_bytes, -15)
                    inner = decompressed.decode("utf-16-le").strip().strip('\x00')
                    layout = json.loads(inner)
            except Exception:
                pass

        # -- Strategy 5: Raw zlib -----------------------------------
        if layout is None:
            try:
                import zlib
                decompressed = zlib.decompress(raw_bytes)
                text = decompressed.decode("utf-16-le").strip()
                layout = json.loads(text)
            except Exception:
                pass

        if layout is None:
            print(f"[Extractor] Warning  --  {used_name} could not be decoded. "
                  f"First 16 bytes: {raw_bytes[:16].hex()}")
            return {}

        # -- Parse layout into normalised structure -----------------
        pages = []
        for section in layout.get("sections", []):
            visuals = []
            for vc in section.get("visualContainers", []):
                config_raw = vc.get("config", "{}")
                try:
                    config = json.loads(config_raw) if isinstance(config_raw, str) else config_raw
                except json.JSONDecodeError:
                    config = {}

                sv = config.get("singleVisual", {})
                visual_type = sv.get("visualType", "")

                # Field bindings from projections
                fields = []
                for role, items in sv.get("projections", {}).items():
                    for item in (items or []):
                        fields.append({
                            "role":      role,
                            "query_ref": item.get("queryRef", ""),
                        })

                # Enrich fields with table/column/aggregation from prototypeQuery.Select[]
                # projections only carries role+queryRef; the actual Entity (table),
                # Property (column) and Aggregation live in prototypeQuery.Select[].
                # Match by Select[].Name == queryRef.
                #
                # Aggregation Function enum (Power BI Layout spec):
                #   0=Sum  1=Average  2=Min  3=Max  4=Count  5=DistinctCount
                #   6=StandardDeviation  7=Variance  8=Median
                _AGG_MAP = {
                    0: "Sum", 1: "Average", 2: "Min", 3: "Max",
                    4: "Count", 5: "DistinctCount", 6: "StandardDeviation",
                    7: "Variance", 8: "Median",
                }
                proto_select = sv.get("prototypeQuery", {}).get("Select", [])
                proto_lkp = {}
                for sel in proto_select:
                    sel_name = sel.get("Name", "")
                    if not sel_name:
                        continue
                    agg_node  = sel.get("Aggregation") or {}
                    hl_node   = sel.get("HierarchyLevel") or {}
                    col_node  = sel.get("Column") or sel.get("Measure") or {}

                    if agg_node:
                        # Aggregation{Function, Expression{Column{SourceRef,Property}}}
                        inner    = agg_node.get("Expression", {}).get("Column") or {}
                        entity   = inner.get("Expression", {}).get("SourceRef", {}).get("Entity", "")
                        prop     = inner.get("Property", "")
                        agg_func = agg_node.get("Function", "")
                        agg_str  = _AGG_MAP.get(agg_func, str(agg_func)) if isinstance(agg_func, int) else str(agg_func)
                    elif hl_node:
                        # HierarchyLevel — date drill fields: Table.Col.Variation.HierarchyName.Level
                        # Parse directly from queryRef which already encodes the full path
                        qref_raw = sel_name  # e.g. "FCT Table.Start Date.Variation.Date Hierarchy.Year"
                        if ".Variation." in qref_raw:
                            dot      = qref_raw.index(".")
                            entity   = qref_raw[:dot]
                            base_col = qref_raw[dot+1:qref_raw.index(".Variation.")]
                            right    = qref_raw.split(".Variation.", 1)[1]
                            prop     = f"{base_col}.Variation.{right}"
                        else:
                            entity = hl_node.get("Expression", {}).get("Hierarchy", {})                                             .get("Expression", {}).get("SourceRef", {}).get("Entity", "")
                            prop   = hl_node.get("Level", "")
                        agg_str = "none"
                    else:
                        # Plain Column or Measure
                        entity  = col_node.get("Expression", {}).get("SourceRef", {}).get("Entity", "")
                        prop    = col_node.get("Property", "")
                        agg_str = "none"

                    proto_lkp[sel_name] = {"table": entity, "column": prop, "aggregation": agg_str}

                for f in fields:
                    qref_match = proto_lkp.get(f["query_ref"], {})
                    f["table"]       = qref_match.get("table", "")
                    f["column"]      = qref_match.get("column", "")
                    f["aggregation"] = qref_match.get("aggregation", "")

                # Visual-level filters
                flt_raw = vc.get("filters", "[]")
                try:
                    filters = json.loads(flt_raw) if isinstance(flt_raw, str) else flt_raw
                except json.JSONDecodeError:
                    filters = []

                visuals.append({
                    "id":          vc.get("id", ""),
                    "visual_type": visual_type,
                    "x":           vc.get("x", 0),
                    "y":           vc.get("y", 0),
                    "width":       vc.get("width", 0),
                    "height":      vc.get("height", 0),
                    "z_order":     vc.get("z", 0),
                    "fields":      fields,
                    "filters":     filters,
                    "config":      config,
                })

            # Page-level filters
            pflt_raw = section.get("filters", "[]")
            try:
                page_filters = json.loads(pflt_raw) if isinstance(pflt_raw, str) else pflt_raw
            except json.JSONDecodeError:
                page_filters = []

            # Page config (canvas settings, background, wallpaper)
            pcfg_raw = section.get("config", "{}")
            try:
                page_config = json.loads(pcfg_raw) if isinstance(pcfg_raw, str) else pcfg_raw
            except json.JSONDecodeError:
                page_config = {}

            pages.append({
                "name":         section.get("displayName", ""),
                "width":        section.get("width", 0),
                "height":       section.get("height", 0),
                "visual_count": len(visuals),
                "visuals":      visuals,
                "filters":      page_filters,    # kept for backwards compat
                "page_filters": page_filters,    # explicit name used by D4
                "page_config":  page_config,     # canvas settings, background
            })

        # Report-level filters
        rflt_raw = layout.get("filters", "[]")
        try:
            report_filters = json.loads(rflt_raw) if isinstance(rflt_raw, str) else rflt_raw
        except json.JSONDecodeError:
            report_filters = []

        # Bookmarks from report config
        rcfg_raw = layout.get("config", "{}")
        try:
            report_config = json.loads(rcfg_raw) if isinstance(rcfg_raw, str) else rcfg_raw
        except json.JSONDecodeError:
            report_config = {}

        bookmarks = [
            {"name": b.get("displayName", ""), "id": b.get("name", "")}
            for b in report_config.get("bookmarks", [])
        ]

        return {
            "page_count":     len(pages),
            "pages":          pages,
            "report_filters": report_filters,
            "bookmarks":      bookmarks,
            "theme":          report_config.get("theme", {}).get("name", ""),
        }

    def get_settings(self) -> dict:
        """Parse Settings file for connection/refresh config."""
        return self._read_json("Settings") or {}

    def _parse_bim_raw(self) -> dict:
        """Return raw BIM dict for M expression scanning."""
        import json as _json
        # Try external BIM file first (passed via --bim)
        bim_override = getattr(self, "_bim_override", None)
        if bim_override and Path(bim_override).exists():
            try:
                return _json.loads(Path(bim_override).read_text(encoding="utf-8-sig")).get("model",
                       _json.loads(Path(bim_override).read_text(encoding="utf-8-sig")))
            except Exception: pass
        # Try DataModel from extracted zip
        p = self._file_map.get("DataModel")
        if not p or not Path(p).exists(): return {}
        raw = Path(p).read_bytes()
        for enc in ("utf-16-le","utf-16","utf-8-sig","utf-8"):
            try:
                text = raw.decode(enc).strip().strip('\x00')
                if '{' in text:
                    bim = _json.loads(text)
                    return bim.get("model", bim)
            except Exception: pass
        return {}

    def get_connections(self) -> list[dict]:
        """
        Extract connection info from:
          1. Connections file (pbiServiceLive / EntityDataSource for split architecture)
          2. DataModel.dataSources (standard DB connections)
        """
        connections = []

        # -- Connections file  --  split report/dataset architecture --
        conn_file = self._read_json("Connections") or {}
        file_conns = conn_file.get("Connections", [])
        for fc in file_conns:
            conn_str = fc.get("ConnectionString","")
            ctype    = fc.get("ConnectionType","")
            # Parse catalog/database from connection string
            catalog  = ""
            model_id = fc.get("PbiServiceModelId","")
            vserver  = fc.get("PbiModelVirtualServerName","")
            if "Initial Catalog=" in conn_str:
                try:
                    catalog = conn_str.split("Initial Catalog=")[1].split(";")[0].strip()
                except: pass
            connections.append({
                "name":             fc.get("Name","EntityDataSource"),
                "connection_type":  ctype,
                "connection_string":conn_str,
                "server":           "",
                "database":         catalog,
                "PbiServiceModelId":str(model_id) if model_id else "",
                "PbiModelVirtualServerName": vserver,
            })

        # -- RemoteArtifacts  --  dataset PBIX ------------------------
        remote_file = conn_file.get("RemoteArtifacts", [])
        for ra in remote_file:
            connections.append({
                "name":       "RemoteArtifact",
                "DatasetId":  ra.get("DatasetId",""),
                "ReportId":   ra.get("ReportId",""),
                "connection_type": "RemoteArtifact",
            })

        # -- DataModel.dataSources  --  standard DB connections --------
        dm = self.get_data_model()
        raw_sources = dm.get("data_sources", [])
        for ds in raw_sources:
            conn_details = ds.get("connectionDetails", {})
            cred = ds.get("credential", {})
            connections.append({
                "name":            ds.get("name", ""),
                "server":          conn_details.get("server",
                                   conn_details.get("address", "")),
                "database":        conn_details.get("database",
                                   conn_details.get("catalog", "")),
                "connection_type": ds.get("type", ""),
                "auth_method":     cred.get("AuthenticationKind", ""),
                "gateway_id":      ds.get("gatewayId", ""),
            })

        # -- BIM partition M expressions  --  SharePoint / CSV / Web --
        # When dataSources is empty, connections are embedded in partition
        # M expressions. Extract unique Source = X(...) calls.
        if not raw_sources:
            dm_full = self._parse_bim_raw()
            seen_sources: set = set()
            import re as _re
            src_patterns = [
                (_re.compile(r'SharePoint\.Files\s*\(\s*"([^"]+)"', _re.IGNORECASE), "SharePoint"),
                (_re.compile(r'Csv\.Document\s*\(File\.Contents\s*\(\s*"([^"]+)"', _re.IGNORECASE), "CSV"),
                (_re.compile(r'Web\.Contents\s*\(\s*"([^"]+)"', _re.IGNORECASE), "Web"),
                (_re.compile(r'Sql\.Database\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"', _re.IGNORECASE), "SQL"),
                (_re.compile(r'AzureStorage\.[A-Za-z]+\s*\(\s*"([^"]+)"', _re.IGNORECASE), "AzureStorage"),
                (_re.compile(r'Oracle\.Database\s*\(\s*"([^"]+)"', _re.IGNORECASE), "Oracle"),
                (_re.compile(r'OData\.Feed\s*\(\s*"([^"]+)"', _re.IGNORECASE), "OData"),
            ]
            for t in (dm_full.get("tables",[]) if dm_full else []):
                for part in t.get("partitions",[]):
                    src = part.get("source",{})
                    expr = src.get("expression","")
                    if isinstance(expr,list): expr = "\n".join(expr)
                    if not expr: continue
                    for pat, src_type in src_patterns:
                        m = pat.search(expr)
                        if m:
                            path_key = m.group(1)
                            if path_key not in seen_sources:
                                seen_sources.add(path_key)
                                entry = {
                                    "name":            path_key,
                                    "connection_type": src_type,
                                    "source_type":     src_type,
                                    "path":            path_key,
                                    "server":          path_key if src_type in ("SQL","Oracle") else "",
                                    "database":        m.group(2) if src_type=="SQL" else "",
                                    "auth_method":     "",
                                }
                                connections.append(entry)
                            break

        return connections

    def get_remote_artifacts(self) -> list[dict]:
        """Extract RemoteArtifacts from Connections file (dataset PBIX)."""
        conn_file = self._read_json("Connections") or {}
        return conn_file.get("RemoteArtifacts", [])

    def extract_all(self) -> dict:
        """Extract zip and return all parsed artifacts."""
        self.extract()
        return {
            "metadata":         self.get_metadata(),
            "connections":      self.get_connections(),
            "remote_artifacts": self.get_remote_artifacts(),
            "data_model":       self.get_data_model(),
            "rls_roles":        self.get_security_bindings(),
            "layout":           self.get_report_layout(),
            "settings":         self.get_settings(),
        }


# ---------------------------------------------
# Step 2  --  Compare zip artifacts vs JSON
# ---------------------------------------------

class RePBIValidator:
    """
    Runs D1-D7 checks by comparing the normalised PBIX
    artifact dict against the homogeneous JSON dict.
    """

    def __init__(self, pbix_artifacts: dict, homo_json: dict):
        self.pbix = pbix_artifacts
        self.json = homo_json
        self.results: list[CheckResult] = []

    @staticmethod
    def _is_absent(v) -> bool:
        """Return True if v represents a missing/none value."""
        if v is None:
            return True
        if isinstance(v, str) and v.strip().lower() in ("none", "null", ""):
            return True
        if isinstance(v, (list, dict)) and len(v) == 0:
            return True
        return False

    def _log(self, check_id: str, attribute: str,
             src_val: Any, json_val: Any, note: str = "") -> None:
        """Compare src vs json and record the result."""
        src_absent  = self._is_absent(src_val)
        json_absent = self._is_absent(json_val)

        if src_absent and json_absent:
            status = "PASS"   # both absent — not required in this workbook
        elif src_absent:
            status = "PASS"   # not present in source — JSON having it is fine
        elif json_absent:
            status = "MISSING"
        elif isinstance(src_val, str) and isinstance(json_val, str):
            status = "PASS" if src_val.strip().lower() == json_val.strip().lower() else "FAIL"
        elif isinstance(src_val, (int, float)) and isinstance(json_val, (int, float)):
            status = "PASS" if abs(src_val - json_val) < 0.0001 else "FAIL"
        elif isinstance(src_val, bool):
            status = "PASS" if src_val == json_val else "FAIL"
        else:
            status = "PASS" if src_val == json_val else "FAIL"

        self.results.append(CheckResult(
            check_id=check_id,
            attribute=attribute,
            status=status,
            source_value=src_val,
            json_value=json_val,
            note=note,
        ))

    # -- D1  --  Connection check ----------------

    def check_d1_connections(self):
        """
        D1  --  Compare each connection from PBIX DataModel
        against the homogeneous JSON data_sources block.
        JSON uses: data_sources[].{name, source_type, authentication_method,
                                    server, database, path, connection_mode}

        Handles three architectures:
          1. Standard PBIX (semantic + report in one file)
          2. Split architecture: Report PBIX connects to Dataset PBIX
             via pbiServiceLive / EntityDataSource
          3. Dataset PBIX with folder/Excel file parameters
        """
        print("\n[D1] Checking connections...")
        src_conns  = self.pbix.get("connections", [])
        json_conns = self.json.get("data_sources", [])

        # -- Detect split report/dataset architecture --------------
        # Report PBIX: Connections has ConnectionType=pbiServiceLive
        # and EntityDataSource with a dataset GUID catalog
        pbi_live_conns = [
            c for c in src_conns
            if (c.get("connection_type","") or "").lower() in
               ("pbiServiceLive","pbiservicelive","pb iservice") or
            "pbiazure" in (c.get("server","") or "").lower() or
            "pbiazure" in (c.get("connection_string","") or "").lower()
        ]
        if pbi_live_conns:
            print("     Split architecture detected  --  Report PBIX connects "
                  "to Dataset PBIX via Power BI Service (pbiServiceLive)")
            for src in pbi_live_conns:
                name   = src.get("name","EntityDataSource")
                prefix = f"connection[{name}]"
                # Extract dataset GUID from connection string or catalog
                conn_str  = src.get("connection_string","") or src.get("ConnectionString","")
                catalog   = src.get("database","") or src.get("PbiModelDatabaseName","")
                model_id  = src.get("PbiServiceModelId","") or src.get("model_id","")
                vserver   = src.get("PbiModelVirtualServerName","") or \
                            src.get("virtual_server","")

                # Match against JSON data_sources
                jc = next((j for j in json_conns
                            if j.get("source_type","").lower() in
                               ("pbiservicelive","live_connection","dataset_live",
                                "powerbi_service")), {})
                if not jc:
                    jc = next((j for j in json_conns), {})

                self._log("D1", f"{prefix}.connection_type",
                          "pbiServiceLive", jc.get("source_type"),
                          "Split architecture: Report connects to Dataset PBIX "
                          "via pbiServiceLive. JSON must capture source_type="
                          "pbiServiceLive")
                self._log("D1", f"{prefix}.dataset_catalog_guid",
                          catalog, jc.get("database") or jc.get("catalog_guid"),
                          "Dataset GUID (catalog) from Connections file must be "
                          "captured in JSON  --  used to identify the target dataset "
                          "in Power BI Service")
                self._log("D1", f"{prefix}.pbi_model_id",
                          str(model_id) if model_id else None,
                          str(jc.get("pbi_model_id","")) or None,
                          "PbiServiceModelId must be captured  --  identifies the "
                          "semantic model in Power BI Service")
                self._log("D1", f"{prefix}.virtual_server",
                          vserver, jc.get("virtual_server"),
                          "PbiModelVirtualServerName must be captured")
                self._log("D1", f"{prefix}.connection_string",
                          conn_str[:80] if conn_str else None,
                          jc.get("connection_string","")[:80] if
                          jc.get("connection_string") else None,
                          "Full connection string must be captured for re-pointing "
                          "the report to the target dataset after migration")
            return

        # -- Detect folder/Excel parameter-based sources -----------
        # Dataset PBIX may use parameters for file paths (Folder.Files,
        # Excel.Workbook etc.)  --  these appear as RemoteArtifacts + DataModel
        remote_artifacts = self.pbix.get("remote_artifacts", [])
        # Real data source connections (exclude RemoteArtifact metadata entries)
        real_src_conns = [c for c in src_conns
                          if c.get("connection_type","").lower() != "remoteartifact"]
        # RemoteArtifacts check: only applies when this is a Report PBIX that
        # connects to a published Dataset PBIX via pbiServiceLive (split architecture).
        # A Dataset PBIX with local CSV/DB connections also has RemoteArtifacts in
        # its Connections file but those are Power BI Service registration metadata --
        # not relevant for semantic validation.
        # Only check RemoteArtifacts when this is a pure live-connection Report PBIX.
        # Discriminator: a live-connection Report PBIX has RemoteArtifacts AND no BIM tables
        # (the model lives on the Service, not locally).
        # A Dataset PBIX has RemoteArtifacts (Service registration) AND BIM tables (CSV/DB).
        bim_tables = self.pbix.get("data_model", {}).get("tables", [])
        is_live_connection_report = (remote_artifacts and not real_src_conns
                                     and not bim_tables)
        if is_live_connection_report:
            for ra in remote_artifacts:
                ds_id = ra.get("DatasetId","") or ra.get("dataset_id","")
                rpt_id= ra.get("ReportId","")  or ra.get("report_id","")
                jc    = next((j for j in json_conns), {})
                self._log("D1", "remote_artifact.dataset_id",
                          ds_id, jc.get("dataset_id"),
                          "Dataset PBIX: DatasetId from RemoteArtifacts must be "
                          "captured  --  links dataset back to Power BI Service")
                if rpt_id:
                    self._log("D1", "remote_artifact.report_id",
                              rpt_id, jc.get("report_id"),
                              "Dataset PBIX: ReportId from RemoteArtifacts must "
                              "be captured")

        # -- Standard connection path (no live service connection) -
        # -- M-expression source path (SharePoint/CSV/Excel via pbixray) ─
        # When src_conns is empty (Service-downloaded PBIX with RemoteArtifacts)
        # but pbixray has M expressions, validate JSON data_sources against
        # the connection details embedded in the M expressions.
        # This covers SharePoint.Files, Web.Contents, Folder.Files, Sql.Database etc.
        # -- M-expression source path: triggered when no direct DB connections
        # exist but pbixray has M expressions (SharePoint/CSV/Excel sources).
        # real_src_conns excludes RemoteArtifact entries so this fires correctly
        # for Service-downloaded PBIXs that only have RemoteArtifacts in Connections.
        if not real_src_conns and json_conns:
            pq_data = self.pbix.get("data_model", {}).get("_pq_raw", [])
            # _pq_raw is populated by _extract_via_pbixray; fallback: use tables partitions
            if not pq_data:
                tables = self.pbix.get("data_model", {}).get("tables", [])
                for t in tables:
                    if self._is_system_table(t.get("name","")): continue
                    for p in t.get("partitions", []):
                        src = p.get("source", {})
                        expr = src.get("expression","") if isinstance(src,dict) else str(src or "")
                        if expr:
                            pq_data.append({"TableName": t.get("name",""), "Expression": expr})

            if pq_data and json_conns:
                print(f"     M-expression source validation  --  "
                      f"{len(pq_data)} table(s), {len(json_conns)} JSON data_source(s)")

                import re as _re_d1
                from urllib.parse import urlparse as _urlparse

                # Build JSON lookup by filename (name field, lowercase, underscores normalised)
                json_ds_lkp = {}
                for jds in json_conns:
                    nm = jds.get("name","").lower()
                    json_ds_lkp[nm] = jds
                    # also index without extension
                    json_ds_lkp[nm.replace(".csv","").replace(".xlsx","").replace(".txt","")] = jds

                def _extract_m_connection(expr_str):
                    """Extract (server_domain, filename, source_type) from M expression."""
                    sp_url  = (_re_d1.findall(r'SharePoint\.Files\("([^"]+)"', expr_str) or
                               _re_d1.findall(r'SharePoint\.Tables\("([^"]+)"', expr_str))
                    web_url = _re_d1.findall(r'Web\.Contents\("([^"]+)"', expr_str)
                    sql_srv = _re_d1.findall(r'Sql\.Database\("([^"]+)"', expr_str)
                    fold    = _re_d1.findall(r'Folder\.Files\("([^"]+)"', expr_str)
                    file_nm = _re_d1.findall(r'\[Name\]\s*=\s*"([^"]+\.(?:csv|xlsx|txt))"',
                                             expr_str, _re_d1.IGNORECASE)
                    server  = ""
                    stype   = ""
                    if sp_url:
                        parsed = _urlparse(sp_url[0])
                        server = parsed.netloc
                        stype  = "sharepoint"
                    elif web_url:
                        parsed = _urlparse(web_url[0])
                        server = parsed.netloc
                        stype  = "web"
                    elif sql_srv:
                        server = sql_srv[0]
                        stype  = "sql"
                    elif fold:
                        server = fold[0]
                        stype  = "folder"
                    fname = file_nm[0] if file_nm else ""
                    return server, fname, stype

                matched_json_names = set()
                for pq_row in pq_data:
                    tname = pq_row.get("TableName","")
                    expr  = pq_row.get("Expression","")
                    if self._is_system_table(tname): continue

                    src_server, src_fname, src_type = _extract_m_connection(str(expr))
                    if not src_server and not src_fname:
                        continue   # No extractable connection info (DAX table etc.)

                    prefix = f"datasource[{tname}]"

                    # Find matching JSON data_source
                    fname_lc = src_fname.lower()
                    jds = (json_ds_lkp.get(fname_lc) or
                           json_ds_lkp.get(fname_lc.replace(".csv","").replace(".xlsx","")) or
                           # Fallback: match by server domain if no filename
                           next((j for j in json_conns
                                 if src_server.lower() in (j.get("server","") or "").lower()
                                 and j.get("name","").lower() not in matched_json_names), None))

                    if jds:
                        matched_json_names.add(jds.get("name","").lower())

                    # 1. data_source entry present in JSON
                    self._log("D1", f"{prefix}.present",
                              src_fname or src_server,
                              jds.get("name") if jds else None,
                              "DATA SOURCE: each table's connection must have a "
                              "corresponding entry in JSON data_sources[]. "
                              "RE/OP must extract the source name from the M expression.")

                    if not jds:
                        continue

                    # 2. server / domain
                    json_server = (jds.get("server","") or "").lower()
                    if src_server:
                        server_ok = (src_server.lower() in json_server or
                                     json_server in src_server.lower())
                        self._log("D1", f"{prefix}.server",
                                  src_server, jds.get("server") or None,
                                  "SERVER: SharePoint/SQL server domain must match. "
                                  "Mismatch = target model points to wrong environment.")

                    # 3. source_type captured
                    self._log("D1", f"{prefix}.source_type",
                              jds.get("source_type") or src_type or "unknown",
                              jds.get("source_type") or None,
                              "SOURCE TYPE: connection type must be captured in JSON "
                              "(e.g. 'CSV (via SharePoint)', 'SQL Server', 'SharePoint'). "
                              "Required so RE/OP knows what connector to use in target.")

                    # 4. connection_mode
                    self._log("D1", f"{prefix}.connection_mode",
                              jds.get("connection_mode","import"),
                              jds.get("connection_mode") or None,
                              "CONNECTION MODE: import/DirectQuery mode must be captured.")

                # Check count match
                m_tables_with_conn = sum(
                    1 for pq_row in pq_data
                    if not self._is_system_table(pq_row.get("TableName",""))
                    and _extract_m_connection(str(pq_row.get("Expression","")))[0]
                )
                # JSON may have one extra generic SharePoint entry — allow +1 tolerance
                count_ok = abs(m_tables_with_conn - len(json_conns)) <= 1
                self._log("D1", "datasource.count",
                          m_tables_with_conn, len(json_conns) if count_ok else len(json_conns),
                          f"DATA SOURCE COUNT: {m_tables_with_conn} table(s) have M "
                          f"expression connections; JSON has {len(json_conns)} data_source(s).")
                return  # M-expression path handled — skip standard path

            # No M expressions found and no direct connections
            if not pq_data:
                self.results.append(CheckResult(
                    check_id="D1", attribute="datasource.present",
                    status="PASS", source_value="no_direct_connections",
                    json_value="no_direct_connections",
                    note="No direct DB connections or M expressions found — "
                         "model may use RemoteArtifacts (live Service connection). "
                         "D1 N/A for this PBIX type."
                ))
            return   # Always return from M-expression path block

        if not src_conns and not remote_artifacts:
            json_sources = self.json.get("data_sources", [])
            csv_sources  = [s for s in json_sources
                            if (s.get("source_type","") or "").upper() in
                            ("CSV","EXCEL","FILE","FOLDER","TEXT","XLSX")]
            folder_sources = [s for s in json_sources
                              if (s.get("source_type","") or "").upper() in
                              ("FOLDER","FOLDERFILES","SHAREPOINT.FOLDER",
                               "FOLDER.FILES")]
            if csv_sources or folder_sources or not json_sources:
                for ds in json_sources:
                    name = ds.get("name","")
                    self._log("D1", f"datasource[{name}].connection_mode",
                              ds.get("connection_mode","import"),
                              ds.get("connection_mode","import"),
                              "File/Folder Import mode  --  connection validated "
                              "via M expression in D2")
                    self._log("D1", f"datasource[{name}].source_type",
                              ds.get("source_type"), ds.get("source_type"),
                              "Source type captured in JSON")
                    # Folder sources  --  check path parameter
                    if (ds.get("source_type","") or "").upper() in \
                       ("FOLDER","FOLDERFILES","FOLDER.FILES","SHAREPOINT.FOLDER"):
                        self._log("D1", f"datasource[{name}].folder_path_parameter",
                                  ds.get("folder_path") or ds.get("path_parameter"),
                                  ds.get("folder_path") or ds.get("path_parameter"),
                                  "Folder source: the M Query parameter name used "
                                  "for the folder path must be captured so it can "
                                  "be re-pointed in the target environment. "
                                  "RE/OP must extract the parameter name from "
                                  "the M expression (e.g. FolderPath parameter)")
                if not json_sources:
                    self._log("D1", "datasource.present",
                              "N/A-File-Import", "N/A-File-Import",
                              "File Import mode  --  no server connection to validate")
                print("     File/Folder Import mode  --  D1 validated via "
                      "data_sources block and M expressions")
            else:
                print("     No connections found in PBIX  --  skipping D1")
            return

        json_lookup = {c.get("name", "").lower(): c for c in json_conns}
        for src in [c for c in src_conns
                    if c.get("connection_type","").lower() != "remoteartifact"]:
            name    = src.get("name", "unknown")
            src_type= src.get("connection_type","") or src.get("source_type","")
            path    = src.get("path","") or src.get("server","") or name

            # Match JSON datasource by name, path, or URL
            jc = (json_lookup.get(name.lower()) or
                  json_lookup.get(path.lower()) or
                  next((j for j in json_conns
                        if path.lower() in (j.get("path","") or
                                            j.get("server","") or
                                            j.get("url","") or
                                            j.get("name","")).lower()), None) or
                  next((j for j in json_conns
                        if (j.get("source_type","") or "").lower() ==
                           src_type.lower()), {}) or
                  {})

            prefix = f"datasource[{src_type}]"
            self._log("D1", f"{prefix}.name",
                      name, jc.get("name") or jc.get("url") or jc.get("path"),
                      f"[D1] {src_type} data source must be captured in JSON data_sources")
            self._log("D1", f"{prefix}.source_type",
                      src_type,
                      jc.get("source_type") or jc.get("connection_type"),
                      f"[D1] Source type (SharePoint/CSV/SQL etc.) must match")
            if path and path != name:
                self._log("D1", f"{prefix}.path",
                          path,
                          jc.get("path") or jc.get("url") or jc.get("server"),
                          f"[D1] Connection URL/path must be captured for environment re-pointing")

    # -- D2  --  Tables, views and joins --------

    SYSTEM_TABLE_PREFIXES = (
        "localdatetable_",
        "datetabletemplate_",
        "localizedtable_",
    )

    PARAMETER_TABLE_INDICATORS = (
        "visual-parameter",
        "row selecting parameter",
        "field parameter",
    )
    # "parameter" alone is too broad -- only flag when expression also starts with {
    PARAMETER_TABLE_NAME_WEAK = (
        "parameter",
    )

    def _is_system_table(self, name: str) -> bool:
        """Return True for Power BI auto-generated system tables."""
        return name.lower().startswith(self.SYSTEM_TABLE_PREFIXES)

    def _is_parameter_table(self, table: dict) -> bool:
        """
        Return True for Power BI Field Parameter tables.
        These have M source starting with { (DAX list literal)
        and are used for dynamic field/measure switching via slicers.
        Two-tier check:
          - Strong name indicators: True without checking expression
          - Weak name indicator ("parameter"): requires expression starting with {
          - No name match but expression starts with {: True
        Note: M Query Parameters (Manage Parameters) are in model.expressions[]
        and are handled separately by _check_d3_mq_parameters, not here.
        """
        name = table.get("name","").lower()
        # Strong name indicators
        if any(p in name for p in self.PARAMETER_TABLE_INDICATORS):
            return True
        # Check M source expression  --  field parameter tables start with {
        has_brace_expr = False
        for p in table.get("partitions", []):
            src = p.get("source","") or ""
            if isinstance(src, dict):
                src = src.get("expression","") or ""
            if isinstance(src, list):
                src = "\n".join(src)
            if src.strip().startswith("{"):
                has_brace_expr = True
                break
        if has_brace_expr:
            return True
        return False

    def check_d2_tables(self):
        """
        D2  --  Compare tables from model.bim against json['tables'].
        Checks:
          - Table names, description, storage mode, M source expressions
          - DAX calculated tables (tables defined by a DAX expression,
            e.g. DateTable = CALENDARAUTO(), bridge tables)
          - RLS filters, OLS rules, Merge, Append, all Transform steps
        """
        print("[D2] Checking tables, views, joins and DAX calculated tables...")
        src_tables  = self.pbix.get("data_model", {}).get("tables", [])
        json_tables = self.json.get("tables", [])

        if not src_tables:
            print("     No tables in PBIX data model  --  skipping D2")
            return

        json_tbl_lookup = {t.get("name","").lower(): t for t in json_tables}

        for st in src_tables:
            tname = st.get("name", "")
            if self._is_system_table(tname):
                continue
            if self._is_parameter_table(st):
                print(f"     Parameter table noted: {tname}")
                self.results.append(CheckResult(
                    check_id="D2",
                    attribute=f"parameter_table[{tname}]",
                    status="PASS",
                    source_value=tname,
                    json_value="manual-intervention-required",
                    note=(
                        f"'{tname}' is a Power BI Field Parameter table. "
                        "Not a data table  --  no data source to capture. "
                        "Requires manual recreation in forward-engineered PBIX "
                        "via Modeling → New Parameter."
                    )
                ))
                continue

            jt     = json_tbl_lookup.get(tname.lower(), {})
            prefix = f"table[{tname}]"

            self._log("D2", f"{prefix}.name",
                      tname, jt.get("name"), "Table must exist in JSON")

            # Description
            src_desc  = st.get("description","") or ""
            json_desc = jt.get("description","") or ""
            if not src_desc and json_desc:
                self.results.append(CheckResult(
                    check_id="D2", attribute=f"{prefix}.description",
                    status="PASS", source_value="(none in BIM)",
                    json_value=json_desc,
                    note="JSON enriches with description not in BIM  --  correct"
                ))
            else:
                self._log("D2", f"{prefix}.description", src_desc, json_desc)

            # -- Table isHidden (S1) -------------------------------
            src_hidden_tbl  = st.get("hidden", False) or st.get("isHidden", False)
            json_hidden_tbl = jt.get("is_hidden", jt.get("isHidden", None))
            if src_hidden_tbl:
                self._log("D2", f"{prefix}.is_hidden",
                          src_hidden_tbl, json_hidden_tbl,
                          "Hidden table flag must be captured  --  hidden tables "
                          "are not visible in the field list but still used in "
                          "relationships and DAX. RE/OP must capture isHidden from "
                          "model.bim tables[].")

            # -- Table lineageTag -- COMMENTED OUT, uncomment when needed --
            # src_lt = st.get("lineageTag", "")
            # if src_lt:
            #     self._log("D2", f"{prefix}.lineageTag",
            #               src_lt, jt.get("lineageTag","") or jt.get("lineage_tag","") or None,
            #               "TABLE LINEAGE TAG: UUID that tracks table identity across "
            #               "renames. RE/OP must capture from model.bim tables[].lineageTag. "
            #               "Missing = cross-report composite model lineage breaks.")

            # -- Table isPrivate -----------------------------------
            src_priv = st.get("isPrivate", False)
            if src_priv:
                self._log("D2", f"{prefix}.isPrivate",
                          src_priv,
                          jt.get("isPrivate", jt.get("is_private", None)),
                          "PRIVATE TABLE: excluded from Analyze in Excel and external "
                          "tools. Must be preserved in target model.")

            # -- Table showAsVariationsOnly ------------------------
            src_savo = st.get("showAsVariationsOnly", False)
            if src_savo:
                self._log("D2", f"{prefix}.showAsVariationsOnly",
                          src_savo,
                          jt.get("showAsVariationsOnly", jt.get("show_as_variations_only", None)),
                          "VARIATIONS-ONLY TABLE: auto-datetime LocalDateTable hidden "
                          "from field list. Must be preserved so date drill hierarchies work.")

            # -- Detect DAX calculated tables ----------------------
            # A calculated table is defined by a DAX expression in BIM
            # rather than an M query. BIM stores them in:
            #   partitions[].source.type = "calculated"
            #   partitions[].source.expression = "<DAX expression>"
            # Examples: DateTable = CALENDARAUTO()
            #           Bridge = SUMMARIZE(Sales, Sales[Region])
            #           Union tables, role-playing dimension copies
            is_dax_table      = False
            dax_table_expr    = ""
            for p in st.get("partitions", []):
                src = p.get("source", {})
                if isinstance(src, dict):
                    src_type = (src.get("type","") or "").lower()
                    if src_type == "calculated":
                        is_dax_table   = True
                        dax_table_expr = src.get("expression","")
                        if isinstance(dax_table_expr, list):
                            dax_table_expr = "\n".join(dax_table_expr)
                        break
                # Also handle when source is directly a string expression
                elif isinstance(src, str) and src.strip():
                    # If there's no M let/in pattern, treat as DAX
                    if "let" not in src.lower()[:20] and "source" not in src.lower()[:40]:
                        is_dax_table   = True
                        dax_table_expr = src

            if is_dax_table:
                # DAX calculated table  --  expression must be in JSON
                json_dax_expr = (jt.get("dax_expression","") or
                                 jt.get("calculated_expression","") or
                                 jt.get("table_expression","") or "")
                self._log("D2", f"{prefix}.table_type",
                          "calculated_table", jt.get("table_type",""),
                          "DAX CALCULATED TABLE: table_type must be 'calculated_table'. "
                          "RE/OP must detect partitions[].source.type='calculated' "
                          "in model.bim and flag the table accordingly.")
                self._log("D2", f"{prefix}.dax_table_expression",
                          dax_table_expr.strip()[:150] if dax_table_expr.strip() else None,
                          json_dax_expr.strip()[:150] if json_dax_expr.strip() else None,
                          "DAX CALCULATED TABLE: the full DAX expression that defines "
                          "this table must be captured in JSON. "
                          "RE/OP must extract partitions[].source.expression from "
                          "model.bim. Without this expression the table cannot be "
                          "recreated in the target model. "
                          f"Source expression (first 150 chars): "
                          f"{dax_table_expr.strip()[:150]}")
                # Still check storage mode for calculated tables
                json_mode = self._get_json_connection_mode(jt)
                self._log("D2", f"{prefix}.storage_mode",
                          "import",  # calculated tables are always Import
                          json_mode or jt.get("storage_mode",""),
                          "DAX calculated tables always use Import storage mode")
            else:
                # Standard M-query sourced table
                for i, p in enumerate(st.get("partitions", [])):
                    ingestion = jt.get("ingestion", {})
                    steps     = ingestion.get("steps", [])
                    jp        = steps[i] if i < len(steps) else {}

                    src_mode  = p.get("mode", "")
                    json_mode = self._get_json_connection_mode(jt)
                    self._log("D2", f"{prefix}.partition[{i}].mode",
                              src_mode, json_mode,
                              "Import/DirectQuery mode must match")

                    src_raw = p.get("source", "")
                    # _parse_bim now returns source as a dict with 'expression' key
                    if isinstance(src_raw, dict):
                        src_expr_raw = src_raw.get("expression", "")
                    else:
                        src_expr_raw = src_raw
                    src_expr = "\n".join(src_expr_raw) \
                               if isinstance(src_expr_raw, list) \
                               else str(src_expr_raw or "")
                    json_expr = jp.get("native_expressions",{}).get("powerquery","") \
                                if jp else ""

                    def normalise_m(expr: str) -> str:
                        expr = expr.replace("\\\\", "\\")
                        expr = expr.replace("\r\n", "\n").replace("\r", "\n")
                        lines = [l.strip().rstrip(",")
                                 for l in expr.split("\n") if l.strip()]
                        lines = [l for l in lines if l.lower() != "let"]
                        return lines[0][:100] if lines else ""

                    src_norm  = normalise_m(src_expr)
                    json_norm = normalise_m(json_expr)
                    self._log("D2", f"{prefix}.partition[{i}].source_expression",
                              src_norm, json_norm,
                              "M source expression must be captured in ingestion steps")

    def _get_json_connection_mode(self, json_table: dict) -> str:
        """Extract connection_mode for a table from data_sources block."""
        ds_list = self.json.get("data_sources", [])
        for ds in ds_list:
            mode = ds.get("connection_mode","")
            if mode:
                return mode
        return ""

    # -- D3  --  Fields, types and transforms ---

    def check_d3_fields(self):
        """
        D3  --  Compare columns from model.bim against json['tables'][n]['columns'].
        Checks:
          - Column name, data type, nullable
          - columnType (Regular vs Calculated)
          - DAX expression for calculated columns
          - formatString, isHidden, displayFolder, summarizeBy,
            dataCategory, sortByColumn
        Also checks hierarchies (D3h) within this method.
        """
        print("[D3] Checking fields, types, transforms and hierarchies...")
        src_tables  = self.pbix.get("data_model", {}).get("tables", [])
        json_tables = self.json.get("tables", [])
        json_tbl_lookup = {t.get("name","").lower(): t for t in json_tables}

        BIM_TYPE_MAP = {
            "int64":    "integer",
            "double":   "decimal",
            "datetime": "datetime",
            "date":     "date",
            "string":   "string",
            "boolean":  "boolean",
            "binary":   "binary",
            "variant":  "variant",
        }

        for st in src_tables:
            tname = st.get("name","")
            if self._is_system_table(tname) or self._is_parameter_table(st):
                continue
            jt    = json_tbl_lookup.get(tname.lower(), {})
            jcols = {c.get("name","").lower(): c
                     for c in jt.get("columns", [])}

            for sc in st.get("columns", []):
                cname  = sc.get("name","")
                jc     = jcols.get(cname.lower(), {})
                prefix = f"column[{tname}.{cname}]"

                # -- Name ------------------------------------------
                self._log("D3", f"{prefix}.name",
                          cname, jc.get("name"))

                # -- Data type -------------------------------------
                src_type_raw  = (sc.get("data_type") or
                                 sc.get("dataType") or "").lower()
                src_type_norm = BIM_TYPE_MAP.get(src_type_raw, src_type_raw)
                json_type     = (jc.get("data_type") or "").lower()
                self._log("D3", f"{prefix}.data_type",
                          src_type_norm, json_type)

                # -- Nullable --------------------------------------
                src_nullable  = sc.get("is_nullable", sc.get("isNullable"))
                json_nullable = jc.get("nullable")
                src_bool  = True if src_nullable  is None else bool(src_nullable)
                json_bool = True if json_nullable is None else bool(json_nullable)
                if src_bool is True and json_bool is False:
                    semantic_role = (jc.get("semantic_role") or "").lower()
                    if "key" in semantic_role or "identifier" in semantic_role:
                        self.results.append(CheckResult(
                            check_id="D3",
                            attribute=f"{prefix}.nullable",
                            status="PASS",
                            source_value=src_bool,
                            json_value=json_bool,
                            note=f"JSON correctly marks {semantic_role} as non-nullable"
                        ))
                        continue
                self._log("D3", f"{prefix}.nullable", src_bool, json_bool)

                # -- DAX expression (calculated columns only) -------
                col_type = sc.get("type","") or sc.get("columnType","")
                expr_val = sc.get("expression") or sc.get("Expression") or ""
                is_calculated = (
                    col_type.lower() in ("calculated","calculatedtablecolumn") or
                    (isinstance(expr_val, str) and expr_val.strip() != "") or
                    (isinstance(expr_val, list) and any(e.strip() for e in expr_val))
                )
                if is_calculated:
                    src_expr_raw = sc.get("expression") or sc.get("Expression","")
                    src_expr = "\n".join(src_expr_raw) \
                               if isinstance(src_expr_raw, list) \
                               else str(src_expr_raw or "")
                    json_expr = (jc.get("expression") or
                                 jc.get("dax_expression") or
                                 jc.get("calculated_expression") or "")
                    self._log("D3", f"{prefix}.dax_expression",
                              src_expr.strip()[:120] if src_expr.strip() else None,
                              json_expr.strip()[:120] if json_expr.strip() else None,
                              "CALCULATED COLUMN: DAX expression must be captured "
                              "in JSON. RE/OP must extract columns[].expression from "
                              "model.bim for all columns where type='calculated'. "
                              "Missing expression = forward engineering cannot recreate "
                              "this calculated column.")

                # -- Format string ----------------------------------
                src_fmt  = sc.get("formatString","") or sc.get("format_string","")
                json_fmt = jc.get("format_string","") or jc.get("formatString","")
                if src_fmt:
                    self._log("D3", f"{prefix}.format_string",
                              src_fmt, json_fmt or None,
                              "Column format string must be captured "
                              "(e.g. 0.00%, #,##0, dd/MM/yyyy)")

                # -- isHidden ---------------------------------------
                src_hidden  = sc.get("isHidden", sc.get("is_hidden"))
                json_hidden = jc.get("is_hidden", jc.get("isHidden"))
                if src_hidden:   # only check if source marks it hidden
                    self._log("D3", f"{prefix}.is_hidden",
                              src_hidden, json_hidden,
                              "Hidden column flag must be captured  --  hidden columns "
                              "are not visible in the field list but still used in "
                              "relationships and DAX")

                # -- summarizeBy (default aggregation) -------------
                src_summ  = sc.get("summarizeBy","") or sc.get("summarize_by","")
                json_summ = jc.get("summarize_by","") or jc.get("summarizeBy","")
                if src_summ and src_summ.lower() not in ("","default","none"):
                    self._log("D3", f"{prefix}.summarize_by",
                              src_summ, json_summ or None,
                              "Default aggregation (summarizeBy) must be captured  --  "
                              "drives default behaviour when field dragged to visual")

                # -- dataCategory ----------------------------------
                src_dc  = sc.get("dataCategory","") or sc.get("data_category","")
                json_dc = jc.get("data_category","") or jc.get("dataCategory","")
                if src_dc:
                    self._log("D3", f"{prefix}.data_category",
                              src_dc, json_dc or None,
                              "Data category must be captured "
                              "(Address, City, Country, Latitude, Longitude, "
                              "ImageURL, Barcode, WebUrl)  --  drives map visuals "
                              "and image visuals")

                # -- sortByColumn ----------------------------------
                src_sbc  = sc.get("sortByColumn","") or sc.get("sort_by_column","")
                json_sbc = jc.get("sort_by_column","") or jc.get("sortByColumn","")
                if src_sbc:
                    self._log("D3", f"{prefix}.sort_by_column",
                              src_sbc, json_sbc or None,
                              "Sort-by column must be captured  --  e.g. Month Name "
                              "sorted by Month Number. Missing = wrong sort order "
                              "in visuals")

                # -- displayFolder ---------------------------------
                src_df  = sc.get("displayFolder","") or sc.get("display_folder","")
                json_df = jc.get("display_folder","") or jc.get("displayFolder","")
                if src_df:
                    self._log("D3", f"{prefix}.display_folder",
                              src_df, json_df or None,
                              "Display folder must be captured  --  organises fields "
                              "in the field list pane")

                # -- Column lineageTag -- COMMENTED OUT, uncomment when needed --
                # src_lt = sc.get("lineageTag","")
                # if src_lt:
                #     self._log("D3", f"{prefix}.lineageTag",
                #               src_lt,
                #               jc.get("lineageTag","") or jc.get("lineage_tag","") or None,
                #               "COLUMN LINEAGE TAG: UUID linking this column to visuals "
                #               "via queryRef. RE/OP must capture from model.bim "
                #               "columns[].lineageTag. Missing = forward-engineered "
                #               "visuals cannot bind to correct column.")

                # -- isNameInferred (Field Parameter placeholder cols) --
                if sc.get("isNameInferred", False):
                    self._log("D3", f"{prefix}.isNameInferred",
                              True,
                              jc.get("isNameInferred", jc.get("is_name_inferred", None)),
                              "INFERRED NAME COLUMN: Field Parameter placeholder column "
                              "with auto-generated name. RE/OP must capture this flag "
                              "to correctly recreate the field parameter table.")

                # -- isDataTypeInferred --------------------------------
                if sc.get("isDataTypeInferred", False):
                    self._log("D3", f"{prefix}.isDataTypeInferred",
                              True,
                              jc.get("isDataTypeInferred", jc.get("is_data_type_inferred", None)),
                              "INFERRED DATA TYPE: PBI inferred this column data type. "
                              "RE/OP should flag for explicit type review in target.")

                # -- changedProperties (explicit user overrides) --------
                src_cp = sc.get("changedProperties", [])
                if src_cp:
                    json_cp = jc.get("changedProperties", jc.get("changed_properties", []))
                    json_cp_set = set(json_cp) if isinstance(json_cp, list) else set()
                    for prop in src_cp:
                        self._log("D3", f"{prefix}.changedProperty[{prop}]",
                                  prop,
                                  prop if prop in json_cp_set else None,
                                  f"CHANGED PROPERTY: user explicitly set '{prop}' on "
                                  "this column. Must be preserved in target.")

                # -- variations (auto-datetime date column link) ---------
                src_var = sc.get("variations", [])
                if src_var:
                    json_var = jc.get("variations", [])
                    self._log("D3", f"{prefix}.variations.count",
                              len(src_var),
                              len(json_var) if json_var else None,
                              "DATE COLUMN VARIATIONS: links date column to its "
                              "auto-datetime LocalDateTable via relationship UUID. "
                              "Required for Analyze in Excel date drill. "
                              "RE/OP must capture variations[] from model.bim.")

                # -- extendedProperties (Field Parameter ParameterMetadata) --
                src_ep = sc.get("extendedProperties", [])
                if src_ep:
                    json_ep = jc.get("extendedProperties", jc.get("extended_properties", []))
                    self._log("D3", f"{prefix}.extendedProperties.count",
                              len(src_ep),
                              len(json_ep) if json_ep else None,
                              "EXTENDED PROPERTIES: Field Parameter columns carry "
                              "ParameterMetadata JSON (version, kind=2). "
                              "Required to recreate field parameter column correctly.")

                # -- relatedColumnDetails (Field Parameter groupByColumns) --
                src_rcd = sc.get("relatedColumnDetails", {})
                if src_rcd:
                    json_rcd = jc.get("relatedColumnDetails",
                                      jc.get("related_column_details", {}))
                    self._log("D3", f"{prefix}.relatedColumnDetails.present",
                              True,
                              True if json_rcd else None,
                              "RELATED COLUMN DETAILS: Field Parameter groupByColumns "
                              "reference. Required for slicer binding to work correctly.")

            # -- Hierarchies (D3h) ---------------------------------
            # BIM tables[].hierarchies[]  --  completely separate from columns
            src_hierarchies = st.get("hierarchies", [])
            json_hierarchies= jt.get("hierarchies", [])
            json_hier_lk    = {h.get("name","").lower(): h
                               for h in json_hierarchies}

            for sh in src_hierarchies:
                hname  = sh.get("name","")
                jh     = json_hier_lk.get(hname.lower(), {})
                hprefix= f"hierarchy[{tname}.{hname}]"

                self._log("D3", f"{hprefix}.name",
                          hname, jh.get("name") or None,
                          "HIERARCHY: hierarchy name must exist in JSON. "
                          "RE/OP must extract tables[].hierarchies[] from model.bim. "
                          "Hierarchies drive drilldown on charts and matrix rows.")

                # Check each level
                src_levels  = sh.get("levels", [])
                json_levels = jh.get("levels", []) if jh else []
                json_lvl_lk = {lv.get("name","").lower(): lv
                               for lv in json_levels}

                self._log("D3", f"{hprefix}.level_count",
                          len(src_levels), len(json_levels),
                          "Hierarchy level count must match")

                for sl in src_levels:
                    lname   = sl.get("name","")
                    ordinal = sl.get("ordinal", sl.get("order", 0))
                    col_ref = sl.get("column","") or sl.get("columnId","")
                    jl      = json_lvl_lk.get(lname.lower(), {})
                    lprefix = f"{hprefix}.level[{lname}]"

                    self._log("D3", f"{lprefix}.name",
                              lname, jl.get("name") or None,
                              "Hierarchy level name must be captured")
                    self._log("D3", f"{lprefix}.column",
                              col_ref, jl.get("column") or jl.get("column_ref") or None,
                              "Hierarchy level column reference must be captured  --  "
                              "this is the column that drives this level of the "
                              "hierarchy (e.g. 'Year' level uses 'Year' column)")
                    self._log("D3", f"{lprefix}.ordinal",
                              ordinal,
                              jl.get("ordinal", jl.get("order")) if jl else None,
                              "Hierarchy level ordinal (position) must be captured  --  "
                              "determines drilldown order")

        # -- M Query Parameters / Manage Parameters (D3-MQP) ----------
        # These live in model.expressions[] in BIM with IsParameterQuery=true
        # They are NOT tables -- they are named M query parameters like FilterYear,
        # CurrentDate, FolderPath etc. used inside partition M expressions.
        # The RE/OP JSON should capture them under a 'parameters' key.
        self._check_d3_mq_parameters()

    def _check_d3_mq_parameters(self):
        """
        D3-MQP  --  Validate M Query Parameters (Manage Parameters).
        Source: model.expressions[] in BIM (extracted by _parse_bim as mq_parameters).
        JSON:   json['parameters'] (root-level array).
        Each parameter has: name, kind, default_value.
        If the JSON has no 'parameters' key at all, every BIM parameter is MISSING.
        This is the correct and honest behaviour  --  makes the gap visible and actionable.
        """
        src_params = self.pbix.get("data_model", {}).get("mq_parameters", [])
        json_params = self.json.get("parameters", [])
        json_param_lkp = {p.get("name","").lower(): p for p in json_params}

        if not src_params:
            return   # No M Query parameters in this model  --  nothing to check

        print(f"     [D3-MQP] Checking {len(src_params)} M Query parameter(s)...")

        for sp in src_params:
            pname  = sp.get("name","")
            jp     = json_param_lkp.get(pname.lower(), {})
            prefix = f"mq_parameter[{pname}]"

            self._log("D3", f"{prefix}.name",
                      pname, jp.get("name") or None,
                      "M QUERY PARAMETER: parameter name must exist in JSON under "
                      "'parameters' key. RE/OP must extract model.expressions[] from "
                      "BIM where IsParameterQuery=true. Parameters like FilterYear, "
                      "CurrentDate, FolderPath are Manage Parameters that control "
                      "M expression behaviour and must be re-created in the target model.")

            if jp:
                # Only check default_value if parameter exists in JSON
                src_default  = sp.get("default_value","")
                json_default = jp.get("default_value","") or jp.get("value","") or \
                               jp.get("default","")
                if src_default:
                    self._log("D3", f"{prefix}.default_value",
                              src_default, json_default or None,
                              "M QUERY PARAMETER: default value must be captured  --  "
                              "this is the value used when no override is provided "
                              "and is needed to re-create the parameter correctly.")

                src_kind  = sp.get("kind","m").lower()
                json_kind = (jp.get("kind","") or jp.get("parameter_type","") or "").lower()
                self._log("D3", f"{prefix}.kind",
                          src_kind, json_kind or None,
                          "Parameter kind (m/dax) must be captured")

    # -- D4  --  Filters and parameters ---------

    def check_d4_filters(self):
        """
        D4  --  Validate filters and parameters.
        Checks:
          - Report-level filter count
          - Page-level filters per page: field, type, operator, values, hidden flag
          - Slicer count as proxy for filter coverage
        """
        print("[D4] Checking filters and parameters...")
        src_layout = self.pbix.get("layout", {})
        json_viz   = self.json.get("visualizations", {})

        # Report-level filters from PBIX layout
        src_rf  = src_layout.get("report_filters", [])
        json_rf = self.json.get("filters", {}).get("report_level", [])
        self._log("D4", "report_filters.count",
                  len(src_rf), len(json_rf),
                  "Number of report-level filters must match")

        # Page-level filters and slicer counts
        src_pages  = src_layout.get("pages", [])
        json_pages = json_viz.get("pages", [])
        json_pg_lookup = {p.get("display_name","").lower(): p
                          for p in json_pages}

        for sp in src_pages:
            pname = sp.get("name","")
            jp    = json_pg_lookup.get(pname.lower(), {})

            # -- Slicer count (proxy for filter coverage) ----------
            src_slicers  = sum(1 for v in sp.get("visuals",[])
                               if v.get("visual_type","").lower() == "slicer")
            json_slicers = sum(1 for v in jp.get("visuals",[])
                               if v.get("visual_type","").lower() == "slicer")
            self._log("D4", f"page[{pname}].slicer_count",
                      src_slicers, json_slicers,
                      "Slicer visual count per page must match")

            # -- Page-level filters --------------------------------
            # Extract from PBIX page filters block
            src_page_filters = sp.get("page_filters", [])
            json_page_filters = jp.get("page_filters", []) \
                                if jp else []
            # Count check
            self._log("D4", f"page[{pname}].page_filter_count",
                      len(src_page_filters), len(json_page_filters),
                      "Page-level filter count must match")

            # Per-filter detail checks
            for i, pf in enumerate(src_page_filters):
                fp = pname
                # Extract filter field (table + column)
                expr = pf.get("expression", {})
                col  = expr.get("Column", {})
                tbl  = col.get("Expression",{}).get("SourceRef",{}).get("Entity","")
                fld  = col.get("Property","")
                filter_field = f"{tbl}.{fld}" if tbl and fld else str(expr)[:80]

                # Extract filter type and values
                filt     = pf.get("filter", {})
                ftype    = pf.get("type","")
                how      = pf.get("howCreated","")
                is_hidden= pf.get("isHiddenInViewMode", False)

                # Extract IN clause values
                where = filt.get("Where",[])
                values_list = []
                for wc in where:
                    cond = wc.get("Condition",{})
                    in_c = cond.get("In",{})
                    for val_row in in_c.get("Values",[]):
                        for v in val_row:
                            lit = v.get("Literal",{}).get("Value","")
                            if lit:
                                values_list.append(lit.strip("'"))

                prefix = f"page[{pname}].page_filter[{i}]"
                # Look up matching filter in JSON
                jf = json_page_filters[i] if i < len(json_page_filters) else {}

                self._log("D4", f"{prefix}.filter_field",
                          filter_field, jf.get("filter_field",""),
                          "Page filter field (table.column) must be captured")
                self._log("D4", f"{prefix}.filter_type",
                          ftype, jf.get("filter_type",""),
                          "Page filter type (Categorical, Advanced, etc.) must be "
                          "captured")
                self._log("D4", f"{prefix}.filter_values",
                          values_list if values_list else None,
                          jf.get("filter_values",jf.get("values",[])) or None,
                          "Page filter IN-clause values must be captured. "
                          f"Source values: {values_list}")
                self._log("D4", f"{prefix}.is_hidden_in_view_mode",
                          is_hidden,
                          jf.get("is_hidden_in_view_mode",
                                 jf.get("isHiddenInViewMode", None)),
                          "isHiddenInViewMode flag must be captured  --  when True "
                          "the filter is active but invisible to end users in "
                          "reading mode. RE/OP must capture this flag.")

    # -- D5  --  DAX measures and relationships -

    def check_d5_measures_relationships(self):
        """
        D5  --  Compare DAX measures and relationships.
        JSON stores measures in json['calculations'] (not nested in tables).
        JSON stores relationships in json['relationships'] (root level).
        Field name mappings:
          expression    → expressions.dax
          is_active     → active
          cross_filter  → filter_direction
          from_table    → left_table_id  (contains table name after last $)
          to_table      → right_table_id (same pattern)
        """
        print("[D5] Checking DAX measures and relationships...")

        # -- Measures from model.bim ------------------------------
        src_tables   = self.pbix.get("data_model", {}).get("tables", [])
        # JSON measures are in root-level 'calculations' list
        json_calcs   = self.json.get("calculations", [])
        json_kpis    = self.json.get("kpi_lineage", [])
        # Build lookup by name (case-insensitive)
        json_meas_lkp = {m.get("name","").lower(): m for m in json_calcs}
        # Also check kpi_lineage as fallback
        json_kpi_lkp  = {k.get("kpi_name","").lower(): k for k in json_kpis}

        for st in src_tables:
            tname = st.get("name","")
            # Skip system date tables
            if self._is_system_table(tname):
                continue
            for sm in st.get("measures", []):
                mname  = sm.get("name","")
                mkey   = mname.lower()
                # Look in calculations first (exact), then fuzzy match
                jm = json_meas_lkp.get(mkey) or json_kpi_lkp.get(mkey)
                if not jm:
                    # Fuzzy: check if BIM name is contained in any JSON name or vice versa
                    jm = next(
                        (v for k, v in {**json_meas_lkp, **json_kpi_lkp}.items()
                         if mkey in k or k in mkey),
                        {}
                    )
                prefix = f"measure[{tname}.{mname}]"

                self._log("D5", f"{prefix}.name",
                          mname, jm.get("name") or jm.get("kpi_name"),
                          "Measure must exist in JSON calculations block")
                # JSON uses expressions.dax not expression
                json_expr = (jm.get("expressions", {}) or {}).get("dax","") \
                            or jm.get("formula","")
                # BIM may store expression as list of strings  --  join if needed
                src_expr_raw = sm.get("expression", "")
                src_expr = "\n".join(src_expr_raw) if isinstance(src_expr_raw, list) \
                           else str(src_expr_raw or "")
                json_expr_str = "\n".join(json_expr) if isinstance(json_expr, list) \
                                else str(json_expr or "")
                self._log("D5", f"{prefix}.expression",
                          src_expr.strip()[:100],
                          json_expr_str.strip()[:100],
                          "DAX expression must be captured in JSON")
                # format_string: JSON enriches with formatting BIM may not store
                src_fmt  = (sm.get("format_string") or "").strip()
                json_fmt = (jm.get("format_string") or "").strip()
                if not src_fmt and json_fmt:
                    self.results.append(CheckResult(
                        check_id="D5", attribute=f"{prefix}.format_string",
                        status="PASS", source_value="(none in BIM)",
                        json_value=json_fmt,
                        note="JSON enriches with format string  --  correct"
                    ))
                else:
                    self._log("D5", f"{prefix}.format_string", src_fmt, json_fmt)
                # description: JSON enriches with descriptions not in BIM
                src_desc  = (sm.get("description") or "").strip()
                json_desc_m = (jm.get("description") or "").strip()
                if not src_desc and json_desc_m:
                    self.results.append(CheckResult(
                        check_id="D5", attribute=f"{prefix}.description",
                        status="PASS", source_value="(none in BIM)",
                        json_value=json_desc_m[:60],
                        note="JSON enriches with description  --  correct"
                    ))
                else:
                    self._log("D5", f"{prefix}.description", src_desc, json_desc_m)

                # -- isHidden --------------------------------------
                src_hidden  = sm.get("isHidden", sm.get("is_hidden", False))
                json_hidden = jm.get("is_hidden", jm.get("isHidden", None))
                if src_hidden:  # only flag when source says hidden
                    self._log("D5", f"{prefix}.is_hidden",
                              src_hidden, json_hidden,
                              "Hidden measure flag must be captured  --  hidden measures "
                              "are invisible in the field list but still usable in "
                              "other DAX formulas")

                # -- displayFolder ---------------------------------
                src_df  = sm.get("displayFolder","") or sm.get("display_folder","")
                json_df = jm.get("display_folder","") or jm.get("displayFolder","")
                if src_df:
                    self._log("D5", f"{prefix}.display_folder",
                              src_df, json_df or None,
                              "Display folder must be captured  --  organises measures "
                              "in the field list pane")

                # -- KPI expressions (S4) -------------------------
                # BIM stores KPI under measures[].kpi: statusExpression,
                # targetExpression, trendExpression
                bim_kpi = sm.get("kpi", {}) or {}
                if bim_kpi:
                    json_kpi = jm.get("kpi", {}) or {}
                    for kpi_field in ("statusExpression", "targetExpression", "trendExpression"):
                        kpi_val_raw = bim_kpi.get(kpi_field, "")
                        kpi_val = "\n".join(kpi_val_raw) if isinstance(kpi_val_raw, list) else str(kpi_val_raw or "")
                        jkv = (json_kpi.get(kpi_field,"") or
                               json_kpi.get(kpi_field.lower(),"") or
                               jm.get(kpi_field.lower(),"") or "")
                        if kpi_val.strip():
                            self._log("D5", f"{prefix}.kpi.{kpi_field}",
                                      kpi_val.strip()[:80], jkv.strip()[:80] if jkv else None,
                                      f"KPI {kpi_field} must be captured in JSON. "
                                      "RE/OP must extract measures[].kpi from model.bim. "
                                      "Missing KPI expressions = KPI visual shows no status/target.")

        # -- USERELATIONSHIP cross-check (S6) ----------------------
        # Any measure using USERELATIONSHIP() must reference an
        # inactive relationship in the model. Cross-check that the
        # referenced relationship exists and is marked is_active=False.
        src_rels_all = self.pbix.get("data_model", {}).get("relationships", [])
        inactive_rels = {
            f"{r.get('from_table','').lower()}.{r.get('from_column','').lower()}"
            for r in src_rels_all
            if not r.get("is_active", True)
        }
        import re as _re_ur
        userel_pattern = _re_ur.compile(
            r"USERELATIONSHIP\s*\(\s*([^,]+)\s*,\s*([^)]+)\s*\)",
            _re_ur.IGNORECASE
        )
        for st in self.pbix.get("data_model", {}).get("tables", []):
            for sm in st.get("measures", []):
                mname   = sm.get("name","")
                expr_r  = sm.get("expression","")
                if isinstance(expr_r, list): expr_r = "\n".join(expr_r)
                for m in userel_pattern.finditer(expr_r or ""):
                    ref1 = m.group(1).strip().strip("[]'\"")
                    # ref1 is Table[Column]  --  extract table.column
                    col_ref = ref1.replace("][","_").replace("[",".").replace("]","").lower()
                    tbl_part = col_ref.split(".")[0] if "." in col_ref else col_ref
                    is_valid_inactive = any(
                        col_ref in k or tbl_part in k
                        for k in inactive_rels
                    )
                    self.results.append(CheckResult(
                        check_id="D5",
                        attribute=f"measure[{st.get('name','')}.{mname}].userelationship_ref[{ref1}]",
                        status="PASS" if is_valid_inactive else "FAIL",
                        source_value=ref1,
                        json_value="inactive_relationship_exists" if is_valid_inactive else "NO_INACTIVE_REL_FOUND",
                        note=(
                            "USERELATIONSHIP CHECK: every USERELATIONSHIP() call must "
                            "reference an inactive relationship in the model. "
                            + ("Reference verified against inactive relationship." if is_valid_inactive
                               else f"WARNING: No inactive relationship found matching '{ref1}'. "
                                    "RE/OP must ensure the referenced relationship exists "
                                    "in the JSON relationships block with is_active=False.")
                        )
                    ))

        # -- Relationships -----------------------------------------
        src_rels  = self.pbix.get("data_model", {}).get("relationships", [])
        # JSON uses root-level 'relationships' key
        json_rels = self.json.get("relationships", [])

        def extract_table_name(table_id: str) -> str:
            """Extract readable name from table_id like tbl_dm_customer_detail_table."""
            if not table_id:
                return ""
            # Format: tbl_<snake_case_name> → convert back to title form
            name = table_id.replace("tbl_","").replace("_"," ").title()
            return name

        def rel_key_src(r) -> str:
            return (f"{r.get('from_table','')}.{r.get('from_column','')} "
                    f"→ {r.get('to_table','')}.{r.get('to_column','')}")

        def rel_key_json(r) -> str:
            lt = extract_table_name(r.get("left_table_id",""))
            rt = extract_table_name(r.get("right_table_id","")) if r.get("right_table_id") else "LocalDateTable"
            return f"{lt}.{r.get('left_column','')} → {rt}.{r.get('right_column','')}"

        # Build json rel lookup by left_table_name + left_column (more specific)
        def tbl_name_from_id(tid: str) -> str:
            """Convert tbl_dm_customer_detail_table → DM Customer_Detail_Table."""
            if not tid:
                return ""
            name = tid.replace("tbl_","")
            # Convert snake_case back: split on _ and title-case each word
            # but preserve common prefixes (dm, fct)
            parts = name.split("_")
            result = []
            i = 0
            while i < len(parts):
                if parts[i].lower() in ("dm","fct") and i + 1 < len(parts):
                    result.append(parts[i].upper())
                    i += 1
                else:
                    result.append(parts[i].capitalize())
                    i += 1
            return " ".join(result)

        json_rel_lkp = {}
        for jr in json_rels:
            lt_name = tbl_name_from_id(jr.get("left_table_id","") or "")
            lc      = (jr.get("left_column") or "").lower()
            # Primary key: table_name + column_name
            key = f"{lt_name.lower()}|{lc}"
            json_rel_lkp[key] = jr
            # Fallback: column name only (for cases where table name format differs)
            json_rel_lkp.setdefault(f"|{lc}", jr)

        for sr in src_rels:
            ft  = (sr.get("from_table") or "").lower().replace("_"," ")
            # Skip relationships involving system date tables
            if self._is_system_table(sr.get("from_table","")) or \
               self._is_system_table(sr.get("to_table","")):
                continue
            fc  = (sr.get("from_column") or "").lower()
            tc  = (sr.get("to_column") or "").lower()
            # Try composite key first, then column-only fallback
            jr  = json_rel_lkp.get(f"{ft}|{fc}") or json_rel_lkp.get(f"|{fc}", {})
            prefix = f"relationship[{rel_key_src(sr)}]"

            # Cardinality: BIM normalised to many_to_one format by _parse_bim_cardinality
            # JSON uses: many_to_one, one_to_one, many_to_many, one_to_many
            # Also handle alternate JSON formats: manyToOne, ManyToOne etc.
            CARD_MAP = {
                # underscore formats (JSON common model)
                "many_to_one":  "many_to_one",
                "manytooone":   "many_to_one",
                "manytoone":    "many_to_one",
                "one_to_one":   "one_to_one",
                "onetoone":     "one_to_one",
                "many_to_many": "many_to_many",
                "manytomany":   "many_to_many",
                "one_to_many":  "one_to_many",
                "onetomany":    "one_to_many",
                # colon-separated formats from pbixray _extract_via_pbixray()
                "many:one":     "many_to_one",
                "one:many":     "one_to_many",
                "one:one":      "one_to_one",
                "many:many":    "many_to_many",
                # abbreviated forms also from pbixray
                "m:1":          "many_to_one",
                "1:m":          "one_to_many",
                "1:1":          "one_to_one",
                "m:m":          "many_to_many",
                "m:n":          "many_to_many",
            }
            src_card  = CARD_MAP.get(
                sr.get("cardinality","").lower().replace("-","_").replace(" ","_"),
                sr.get("cardinality",""))
            json_card = CARD_MAP.get(
                (jr.get("cardinality","") or "").lower().replace("-","_").replace(" ","_"),
                jr.get("cardinality",""))
            self._log("D5", f"{prefix}.cardinality", src_card, json_card)
            # cross_filter → filter_direction
            # Normalise vocabulary differences between BIM and JSON:
            # BIM uses: "bothDirections" / "oneDirection"
            # JSON uses: "bidirectional" / "single" / "oneDirection"
            CROSSFILTER_MAP = {
                "bothdirections": "bidirectional",
                "onedirection":   "single",
                "one":            "single",
                "both":           "bidirectional",
                "bidirectional":  "bidirectional",
                "single":         "single",
            }
            src_cf  = CROSSFILTER_MAP.get(
                (sr.get("cross_filter") or "").lower(), sr.get("cross_filter",""))
            json_cf = CROSSFILTER_MAP.get(
                (jr.get("filter_direction") or "").lower(), jr.get("filter_direction",""))
            self._log("D5", f"{prefix}.cross_filter[json:filter_direction]",
                      src_cf, json_cf)
            # is_active → active
            self._log("D5", f"{prefix}.is_active[json:active]",
                      sr.get("is_active"), jr.get("active"))

            # -- from_column and to_column -------------------------
            # Critical for joins  --  the column names on both sides of
            # the relationship must be captured, not just the table names.
            src_fc = sr.get("from_column","")
            src_tc = sr.get("to_column","")
            json_fc= jr.get("from_column","") or jr.get("left_column","")
            json_tc= jr.get("to_column","")   or jr.get("right_column","")
            self._log("D5", f"{prefix}.from_column",
                      src_fc, json_fc or None,
                      "Relationship from_column (foreign key column) must be "
                      "captured  --  BIM stores this as fromColumn. Without the "
                      "column name the relationship cannot be recreated in the "
                      "target model.")
            self._log("D5", f"{prefix}.to_column",
                      src_tc, json_tc or None,
                      "Relationship to_column (primary key column) must be "
                      "captured  --  BIM stores this as toColumn.")

            # joinOnDateBehavior: datePartOnly vs exact (critical for date tables)
            src_jdb = sr.get("joinOnDateBehavior","")
            if src_jdb:
                json_jdb = jr.get("joinOnDateBehavior",
                                  jr.get("join_on_date_behavior","")) or ""
                self._log("D5", f"{prefix}.joinOnDateBehavior",
                          src_jdb, json_jdb or None,
                          "JOIN ON DATE BEHAVIOR: 'datePartOnly' means the join "
                          "matches on date part only (ignores time component). "
                          "Without this, date relationships join on full timestamp "
                          "causing silent row count mismatches on datetime columns. "
                          "RE/OP must capture joinOnDateBehavior from model.bim.")

            # Relationship UUID name (used in USERELATIONSHIP() DAX calls)
            src_rname = sr.get("name","")
            if src_rname:
                json_rname = jr.get("name","") or jr.get("relationship_name","") or ""
                self._log("D5", f"{prefix}.relationship_uuid",
                          src_rname, json_rname or None,
                          "RELATIONSHIP UUID: BIM assigns each relationship a UUID name. "
                          "RE/OP must capture to allow USERELATIONSHIP() calls to resolve "
                          "in the target model.")



    def check_d6_visuals(self):
        """
        Compare report pages and visuals against the
        visualizations block in the homogeneous JSON.

        JSON structure (from sample):
          visualizations.pages[].visuals[]
            .visual_type
            .title
            .position {x, y, width, height, z_order}
            .fields[].{role, table, column, aggregation, query_ref}
        """
        print("[D6] Checking report visual layer...")
        src_layout = self.pbix.get("layout", {})
        json_viz   = self.json.get("visualizations", {})

        src_pages  = src_layout.get("pages", [])
        json_pages = json_viz.get("pages", [])

        # Page count
        self._log("D6", "page_count",
                  len(src_pages), len(json_pages),
                  "Total page count must match")

        json_pg_lookup = {p.get("display_name","").lower(): p for p in json_pages}

        for sp in src_pages:
            pname  = sp.get("name","")
            jp     = json_pg_lookup.get(pname.lower(), {})
            prefix = f"page[{pname}]"

            # Page metadata
            self._log("D6", f"{prefix}.name",          pname,              jp.get("display_name"))
            self._log("D6", f"{prefix}.width",         sp.get("width"),    jp.get("width"))
            self._log("D6", f"{prefix}.height",        sp.get("height"),   jp.get("height"))
            self._log("D6", f"{prefix}.visual_count",
                      sp.get("visual_count"), len(jp.get("visuals", [])),
                      "Visual count per page must match")

            # Visual-level comparison
            src_visuals  = sp.get("visuals", [])
            json_visuals = jp.get("visuals", [])

            # Build JSON visual lookup by visual_type + position
            # (IDs may differ between source and JSON in POC)
            def pos_key(v):
                pos = v.get("position", {})
                return (
                    v.get("visual_type",""),
                    round(pos.get("x",0),0),
                    round(pos.get("y",0),0),
                )

            json_vis_lookup = {}
            for jv in json_visuals:
                k = pos_key(jv)
                json_vis_lookup[k] = jv

            for sv in src_visuals:
                vtype  = sv.get("visual_type","")

                # Empty visual_type = canvas shape or background rectangle.
                # These ARE important for forward engineering  --  they define
                # the page background design (colour, border, z_order layering).
                # Without them the forward-engineered page will look visually
                # different. Flag as a gap the RE/OP tool must capture.
                if not vtype:
                    vx = round(sv.get("x",0), 0)
                    vy = round(sv.get("y",0), 0)
                    vw = round(sv.get("width",0), 0)
                    vh = round(sv.get("height",0), 0)
                    page_w = sp.get("width", 1280)
                    page_h = sp.get("height", 720)
                    is_fullpage = vw >= page_w * 0.8 and vh >= page_h * 0.8
                    shape_label = "background rectangle" if is_fullpage else "canvas shape"
                    self.results.append(CheckResult(
                        check_id="D6",
                        attribute=f"{prefix}.{shape_label}[@{vx},{vy}]",
                        status="MISSING",
                        source_value=f"x={vx},y={vy},w={vw},h={vh},z={sv.get('z_order',0)}",
                        json_value=None,
                        note=(
                            f"Canvas shape with no visual_type found in PBIX "
                            f"(likely a {shape_label}). "
                            f"Missing from homogeneous JSON. "
                            f"Without this, forward-engineered page will have "
                            f"incorrect background design and z_order layering. "
                            f"RE/OP must capture shape type, position, dimensions, "
                            f"z_order and style properties (fill colour, border)."
                        )
                    ))
                    continue
                vx     = round(sv.get("x",0), 0)
                vy     = round(sv.get("y",0), 0)
                key    = (vtype, vx, vy)
                jv     = json_vis_lookup.get(key, {})
                vprefix= f"page[{pname}].visual[{vtype}@{vx},{vy}]"

                self._log("D6", f"{vprefix}.visual_type",
                          vtype, jv.get("visual_type"),
                          "Visual type must be captured in JSON")
                # Skip position checks when JSON position is all-zero (0 or 0,0)
                # — means the RE/OP tool did not capture position for this visual type.
                jpos = jv.get("position", {})
                _jp_x = round(jpos.get("x", None) or 0, 0)
                _jp_y = round(jpos.get("y", None) or 0, 0)
                _jp_w = round(jpos.get("width", None) or 0, 0)
                _jp_h = round(jpos.get("height", None) or 0, 0)
                _json_pos_zero = (_jp_x == 0 and _jp_y == 0 and _jp_w == 0 and _jp_h == 0)
                if not _json_pos_zero:
                    self._log("D6", f"{vprefix}.position.x",      vx,                     _jp_x)
                    self._log("D6", f"{vprefix}.position.y",      vy,                     _jp_y)
                    self._log("D6", f"{vprefix}.position.width",  round(sv.get("width",0),0),  _jp_w)
                    self._log("D6", f"{vprefix}.position.height", round(sv.get("height",0),0), _jp_h)
                    self._log("D6", f"{vprefix}.position.z_order",
                              sv.get("z_order"), jpos.get("z_order"))

                # Field bindings
                src_fields  = sv.get("fields", [])
                json_fields = jv.get("fields", [])
                self._log("D6", f"{vprefix}.field_count",
                          len(src_fields), len(json_fields),
                          "Number of field bindings must match")

                # Compare each field by query_ref
                json_fld_lkp = {f.get("query_ref","").lower(): f for f in json_fields}
                for sf in src_fields:
                    qref   = sf.get("query_ref","")
                    jf     = json_fld_lkp.get(qref.lower(), {})
                    fprefix= f"{vprefix}.field[{qref}]"

                    self._log("D6", f"{fprefix}.role",
                              sf.get("role"), jf.get("role"))
                    self._log("D6", f"{fprefix}.table",
                              sf.get("table"), jf.get("table"))
                    self._log("D6", f"{fprefix}.column",
                              sf.get("column"), jf.get("column"))
                    self._log("D6", f"{fprefix}.aggregation",
                              sf.get("aggregation"), jf.get("aggregation"))

                # Per-visual filter count (R4)
                src_vis_filters  = sv.get("filters", [])
                json_vis_filters = jv.get("filters", jv.get("visual_filters", []))
                if src_vis_filters:
                    self._log("D6", f"{vprefix}.visual_filter_count",
                              len(src_vis_filters), len(json_vis_filters) if json_vis_filters else None,
                              "VISUAL FILTER (R4): per-visual filter count must match. "
                              "Visual-level filters restrict what data a specific visual shows "
                              "independently of page or report filters. "
                              "RE/OP must capture filters[] from the visual config in Report/Layout. "
                              "Missing = visual shows unfiltered data in target.")

        # Bookmarks
        src_bk  = src_layout.get("bookmarks", [])
        json_bk = self.json.get("bookmarks", [])
        self._log("D6", "bookmark_count",
                  len(src_bk), len(json_bk),
                  "Bookmark count must match")

        src_bk_names  = {b.get("name","").lower() for b in src_bk}
        json_bk_names = {b.get("name","").lower() for b in json_bk}
        for name in src_bk_names - json_bk_names:
            self._log("D6", f"bookmark[{name}]",
                      name, None, "Bookmark missing from JSON")

        # Theme name, theme file, and dataColors palette (R8)
        self._log("D6", "report_theme",
                  src_layout.get("theme",""), self.json.get("theme",""))

        # dataColors from theme (R8) -- primary colour and palette count
        json_theme_obj = self.json.get("theme_details", {}) or \
                         self.json.get("report_theme", {})
        src_theme_raw  = src_layout.get("theme_raw", {})   # populated by extractor if available
        json_data_colors = json_theme_obj.get("dataColors", json_theme_obj.get("data_colors", []))
        if src_theme_raw and src_theme_raw.get("dataColors"):
            src_colors = src_theme_raw["dataColors"]
            self._log("D6", "report_theme.dataColors.count",
                      len(src_colors), len(json_data_colors) if json_data_colors else None,
                      "THEME: dataColors palette count must be captured. "
                      "Mismatched palette = visuals use wrong brand colours.")
            if src_colors and json_data_colors:
                self._log("D6", "report_theme.dataColors.primary_color",
                          src_colors[0], json_data_colors[0] if json_data_colors else None,
                          "THEME: primary brand colour (first dataColors entry) must match.")
        elif json_data_colors:
            # JSON has dataColors but source theme not extracted -- flag for RE/OP
            self.results.append(CheckResult(
                check_id="D6", attribute="report_theme.dataColors",
                status="PASS", source_value="(theme not extracted from PBIX)",
                json_value=f"{len(json_data_colors)} colours in JSON",
                note="Theme dataColors captured in JSON. Verify palette visually in target."
            ))

    # -- D7  --  Visual display name and aggregation accuracy --

    def check_d7_display_names(self):
        """
        D7  --  Visual display name and aggregation accuracy check.

        When a visual has NO explicit title set, Power BI automatically
        displays the measure name or column label as the card/visual header.
        The RE/OP tool must capture this display name.

        Three scenarios detected:

        Option A  --  query_ref points to a named measure in the semantic model.
                   The display name should be the measure name, not the
                   engine-level query expression.

        Option B  --  query_ref is an inline aggregation (e.g. Min(Table.Col))
                   but a named measure with a similar name exists in the model.
                   RE/OP may have captured the wrong binding  --  should flag
                   as a named measure candidate.

        Option C  --  visual title is empty AND display_name field is missing
                   from the JSON. RE/OP must capture the effective display
                   name (measure name / column label) as a mandatory field.
        """
        print("[D7] Checking visual display names and aggregation accuracy...")

        src_layout  = self.pbix.get("layout", {})
        json_viz    = self.json.get("visualizations", {})
        src_pages   = src_layout.get("pages", [])
        json_pages  = json_viz.get("pages", [])

        # Build measure name lookup from model.bim for Option A/B detection
        bim_measures = {}
        for tbl in self.pbix.get("data_model", {}).get("tables", []):
            if self._is_system_table(tbl.get("name","")) or \
               self._is_parameter_table(tbl):
                continue
            for m in tbl.get("measures", []):
                mname = m.get("name","")
                bim_measures[mname.lower()] = {
                    "name":  mname,
                    "table": tbl.get("name",""),
                    "expr":  m.get("expression","")
                }

        # Also collect measure names from JSON calculations
        json_measure_names = {
            c.get("name","").lower()
            for c in self.json.get("calculations", [])
        }

        # Build JSON visual lookup by page name
        json_pg_lookup = {
            p.get("display_name","").lower(): p
            for p in json_pages
        }

        # Inline aggregation pattern  --  e.g. "Min(Table.Column)"
        inline_agg_pattern = re.compile(
            r'^(Sum|Count|Min|Max|Avg|Average|CountRows|DistinctCount|'
            r'CountDistinct|First|Last|Median|Percentile)\s*\(',
            re.IGNORECASE
        )

        VISUALS_WITH_LABELS = {
            "card", "kpiVisual", "singleRowCard",
            "multiRowCard", "gauge"
        }

        for sp in src_pages:
            pname    = sp.get("name","")
            jp       = json_pg_lookup.get(pname.lower(), {})
            json_vis = {
                v.get("visual_type","").lower(): v
                for v in jp.get("visuals", [])
            }

            for sv in sp.get("visuals", []):
                vtype  = sv.get("visual_type","")
                vx     = round(sv.get("x",0), 0)
                vy     = round(sv.get("y",0), 0)
                prefix = f"page[{pname}].visual[{vtype}@{vx},{vy}]"

                # Find matching JSON visual by type + position
                jv = next(
                    (v for v in jp.get("visuals", [])
                     if v.get("visual_type","") == vtype
                     and round(v.get("position",{}).get("x",0),0) == vx
                     and round(v.get("position",{}).get("y",0),0) == vy),
                    {}
                )

                for sf in sv.get("fields", []):
                    qref = sf.get("query_ref","")
                    if not qref:
                        continue

                    # -- Option C  --  display_name missing from JSON --------
                    # When title is empty, display_name must be in JSON
                    json_title       = (jv.get("title","") or "").strip()
                    json_display_name= (jv.get("display_name","") or "").strip()

                    if vtype.lower() in VISUALS_WITH_LABELS:
                        if not json_title and not json_display_name:
                            # Determine what the effective display name should be
                            m = inline_agg_pattern.match(qref)
                            if m:
                                # Inline aggregation  --  extract column part
                                inner = qref[qref.find("(")+1:qref.rfind(")")]
                                col_name = inner.split(".")[-1] if "." in inner else inner
                                effective_name = col_name
                            else:
                                # Named field/measure  --  use last part of query_ref
                                effective_name = qref.split(".")[-1] if "." in qref else qref

                            self.results.append(CheckResult(
                                check_id="D7",
                                attribute=f"{prefix}.display_name",
                                status="MISSING",
                                source_value=effective_name,
                                json_value=None,
                                note=(
                                    f"Visual title is empty. Power BI displays "
                                    f"'{effective_name}' as the card label. "
                                    f"RE/OP must capture 'display_name' field "
                                    f"in the JSON for this visual."
                                )
                            ))

                    # -- Option A  --  query_ref is a named measure ----------
                    # If query_ref matches a measure name exactly,
                    # the JSON should store the measure name not engine expr
                    qref_lower = qref.lower()
                    # Named measure query_ref format: "Table.MeasureName"
                    if "." in qref and not inline_agg_pattern.match(qref):
                        measure_part = qref.split(".")[-1].strip().lower()
                        if measure_part in bim_measures or \
                           measure_part in json_measure_names:
                            # This is a named measure  --  check JSON has it right
                            json_fields = jv.get("fields", [])
                            json_qrefs  = [
                                f.get("query_ref","").lower()
                                for f in json_fields
                            ]
                            if qref_lower not in json_qrefs:
                                self.results.append(CheckResult(
                                    check_id="D7",
                                    attribute=f"{prefix}.named_measure_binding",
                                    status="FAIL",
                                    source_value=qref,
                                    json_value=None,
                                    note=(
                                        f"Option A: query_ref '{qref}' points to a "
                                        f"named measure in the semantic model. "
                                        f"JSON does not have this binding. "
                                        f"RE/OP must capture the named measure "
                                        f"reference, not an inline aggregation."
                                    )
                                ))

                    # -- Option B  --  inline aggregation, named measure exists --
                    # query_ref is Min/Count/Sum(...) but a named measure
                    # with similar name exists  --  possible wrong binding
                    if inline_agg_pattern.match(qref):
                        inner = qref[qref.find("(")+1:qref.rfind(")")]
                        col_name = inner.split(".")[-1].strip().lower() \
                                   if "." in inner else inner.lower()
                        agg_used  = inline_agg_pattern.match(qref).group(1)

                        # Check if a measure name is similar to the column name
                        similar_measures = [
                            m["name"] for k, m in bim_measures.items()
                            if col_name in k or k in col_name
                        ]
                        # Also check JSON calculations
                        similar_json = [
                            c.get("name","") for c in
                            self.json.get("calculations", [])
                            if col_name in c.get("name","").lower()
                        ]

                        if similar_measures or similar_json:
                            candidates = similar_measures + similar_json
                            self.results.append(CheckResult(
                                check_id="D7",
                                attribute=f"{prefix}.aggregation_accuracy[{qref[:60]}]",
                                status="FAIL",
                                source_value=f"{agg_used}({inner})",
                                json_value=qref,
                                note=(
                                    f"Option B: Inline aggregation '{agg_used}' "
                                    f"used on column '{col_name}', but named "
                                    f"measure(s) exist with similar name: "
                                    f"{candidates[:3]}. "
                                    f"RE/OP/LLM must verify whether this visual "
                                    f"should reference the named measure instead. "
                                    f"Update LLM prompt to cross-check visual "
                                    f"field bindings against semantic model measures."
                                )
                            ))

    # -- D8  --  Conditional Formatting ------------

    def check_d8_conditional_formatting(self):
        """
        D8  --  Conditional Formatting check.

        Conditional formatting rules in Power BI are stored inside each
        visual's config block under vcObjects in Report/Layout. They drive
        colour, font, background and data bar formatting based on measure
        values or field values. If not captured in the homogeneous JSON,
        the forward-engineered PBIX will show default formatting and
        lose all alerting signals the original report provided.

        This check detects:
          - Colour-based rules (background, font, data bars)
          - Rule-based conditional expressions (if/then thresholds)
          - Field-value-based formatting (colour driven by a category field)
          - Icon set rules (KPI traffic lights, arrows)
        """
        print("[D8] Checking conditional formatting...")

        src_layout = self.pbix.get("layout", {})
        json_viz   = self.json.get("visualizations", {})
        json_pages = json_viz.get("pages", [])
        json_pg_lookup = {
            p.get("display_name","").lower(): p
            for p in json_pages
        }

        # Patterns that indicate conditional formatting in vcObjects
        CF_KEYS = {
            "dataPoint",                    # colour rules on data points
            "dataPointColor",               # colour by field
            "background",                   # background colour rules
            "fontColor",                    # font colour rules  (R12)
            "backgroundColorFormatting",    # background colour conditional rules (R12)
            "fontColorFormatting",          # font colour conditional rules (R12)
            "dataLabels",                   # data label conditional rules
            "indicator",                    # KPI indicator / icon sets
            "calloutValue",                 # KPI callout conditional
            "total",                        # conditional on totals row
            "values",                       # table/matrix value formatting
            "dataBarFormatting",            # data bar (in-cell bar chart) formatting (R12)
            "iconSet",                      # icon set rules: traffic lights, arrows (R12)
            "rowHighlighting",              # row highlighting rules in tables/matrices (R12)
            "topN",                         # Top N filter / conditional highlight (R12)
        }

        total_visuals_with_cf = 0
        total_captured        = 0

        for sp in src_layout.get("pages", []):
            pname = sp.get("name","")
            jp    = json_pg_lookup.get(pname.lower(), {})

            # Build JSON visual lookup by type + position
            json_vis_lookup = {}
            for jv in jp.get("visuals", []):
                pos = jv.get("position", {})
                key = (
                    jv.get("visual_type",""),
                    round(pos.get("x",0),0),
                    round(pos.get("y",0),0),
                )
                json_vis_lookup[key] = jv

            for sv in sp.get("visuals", []):
                vtype  = sv.get("visual_type","")
                if not vtype:
                    continue
                vx     = round(sv.get("x",0),0)
                vy     = round(sv.get("y",0),0)
                config = sv.get("config",{})
                vc_obj = config.get("vcObjects",{})
                prefix = f"page[{pname}].visual[{vtype}@{vx},{vy}]"

                # Detect conditional formatting rules in this visual
                cf_rules_found = []
                for cf_key in CF_KEYS:
                    if cf_key in vc_obj:
                        props = vc_obj[cf_key]
                        if isinstance(props, list) and props:
                            # Check if any property has a Conditional expression
                            for prop_block in props:
                                properties = prop_block.get("properties",{})
                                for prop_name, prop_val in properties.items():
                                    expr = prop_val.get("expr",{}) if isinstance(prop_val, dict) else {}
                                    if "Conditional" in expr or "FillRule" in expr or "ColorRule" in expr:
                                        cf_rules_found.append(f"{cf_key}.{prop_name}")

                # Also check singleVisual objects for conditional formatting
                sv_obj = config.get("singleVisual",{}).get("objects",{})
                for obj_key, obj_val in sv_obj.items():
                    if isinstance(obj_val, list):
                        for item in obj_val:
                            for prop_name, prop_val in item.get("properties",{}).items():
                                if isinstance(prop_val, dict):
                                    expr = prop_val.get("expr",{})
                                    if "Conditional" in expr or "FillRule" in expr:
                                        cf_rules_found.append(f"{obj_key}.{prop_name}")

                if not cf_rules_found:
                    continue  # No CF rules in this visual  --  nothing to check

                total_visuals_with_cf += 1

                # Check if JSON visual has conditional_formatting captured
                jv  = json_vis_lookup.get((vtype, vx, vy), {})
                json_cf = jv.get("conditional_formatting")

                if json_cf is None or json_cf == [] or json_cf == {}:
                    self.results.append(CheckResult(
                        check_id="D8",
                        attribute=f"{prefix}.conditional_formatting",
                        status="MISSING",
                        source_value=f"{len(cf_rules_found)} rule(s): {', '.join(cf_rules_found[:3])}",
                        json_value=None,
                        note=(
                            f"Conditional formatting rules detected in PBIX visual "
                            f"but not captured in homogeneous JSON. "
                            f"Rules found: {', '.join(cf_rules_found[:5])}. "
                            f"Without these rules the forward-engineered visual "
                            f"will show default formatting and lose all "
                            f"colour-coded alerting signals. "
                            f"RE/OP must extract vcObjects conditional expressions "
                            f"from Report/Layout for each visual."
                        )
                    ))
                else:
                    total_captured += 1
                    self.results.append(CheckResult(
                        check_id="D8",
                        attribute=f"{prefix}.conditional_formatting",
                        status="PASS",
                        source_value=f"{len(cf_rules_found)} rule(s)",
                        json_value=f"captured ({len(json_cf) if isinstance(json_cf, list) else 1} entry/entries)",
                        note="Conditional formatting rules captured in JSON"
                    ))

        if total_visuals_with_cf == 0:
            # No conditional formatting found in the PBIX
            self.results.append(CheckResult(
                check_id="D8",
                attribute="conditional_formatting.present",
                status="PASS",
                source_value="none",
                json_value="none",
                note="No conditional formatting rules found in this PBIX"
            ))
        print(f"     Found {total_visuals_with_cf} visual(s) with conditional formatting, "
              f"{total_captured} captured in JSON")

    # -- D9  --  Tooltip Configuration -------------

    def check_d9_tooltips(self):
        """
        D9  --  Tooltip Configuration check.

        Power BI supports two types of custom tooltips:

        Type 1  --  Field tooltips: additional fields added to the tooltip
        that do not appear in the visual itself. Stored in the visual's
        projections under the "Tooltips" role in Report/Layout.

        Type 2  --  Report page tooltips: an entire page designated as a
        tooltip that appears on hover. Stored in the page's config as
        displayOption: 2 (tooltip page) and referenced in the visual
        config via tooltipType and reportPageId.

        If not captured in the homogeneous JSON:
          - Field tooltips: users lose additional context on hover
          - Page tooltips: the rich hover mini-dashboard is lost entirely
            and Power BI falls back to the default tooltip
        """
        print("[D9] Checking tooltip configuration...")

        src_layout = self.pbix.get("layout", {})
        json_viz   = self.json.get("visualizations", {})
        json_pages = json_viz.get("pages", [])
        json_pg_lookup = {
            p.get("display_name","").lower(): p
            for p in json_pages
        }

        tooltip_pages_in_source = []
        tooltip_fields_found    = 0
        tooltip_fields_captured = 0

        for sp in src_layout.get("pages", []):
            pname  = sp.get("name","")
            jp     = json_pg_lookup.get(pname.lower(), {})

            # -- Detect tooltip pages ----------------------------------
            # A tooltip page has displayOption = 2 in its config
            page_config_raw = {}
            for section in src_layout.get("sections", []):
                if section.get("displayName","") == pname:
                    cfg_raw = section.get("config","{}")
                    try:
                        page_config_raw = json.loads(cfg_raw) \
                            if isinstance(cfg_raw, str) else cfg_raw
                    except Exception:
                        pass
                    break

            display_opt = page_config_raw.get("displayOption", 0)
            if display_opt == 2:
                tooltip_pages_in_source.append(pname)
                json_page_type = jp.get("page_type","")
                if json_page_type != "tooltip":
                    self.results.append(CheckResult(
                        check_id="D9",
                        attribute=f"page[{pname}].tooltip_page",
                        status="MISSING",
                        source_value="tooltip_page (displayOption=2)",
                        json_value=json_page_type or None,
                        note=(
                            f"Page '{pname}' is designated as a report page tooltip "
                            f"in the PBIX (displayOption=2) but is not marked as "
                            f"page_type: tooltip in the homogeneous JSON. "
                            f"Without this, the forward-engineered PBIX will not "
                            f"serve this page as a hover tooltip and visuals "
                            f"referencing it will fall back to default tooltips. "
                            f"RE/OP must capture page displayOption and tooltip "
                            f"page references."
                        )
                    ))
                else:
                    self.results.append(CheckResult(
                        check_id="D9",
                        attribute=f"page[{pname}].tooltip_page",
                        status="PASS",
                        source_value="tooltip_page",
                        json_value="tooltip",
                        note="Tooltip page correctly captured in JSON"
                    ))

            # -- Detect field tooltips per visual ----------------------
            # Field tooltips are in projections under role "Tooltips"
            for sv in sp.get("visuals", []):
                vtype = sv.get("visual_type","")
                if not vtype:
                    continue
                vx    = round(sv.get("x",0),0)
                vy    = round(sv.get("y",0),0)
                prefix = f"page[{pname}].visual[{vtype}@{vx},{vy}]"

                config = sv.get("config",{})
                sv_cfg = config.get("singleVisual",{})
                projections = sv_cfg.get("projections",{})

                # Check for Tooltips role in projections
                tooltip_fields = projections.get("Tooltips", []) or \
                                 projections.get("tooltips", []) or \
                                 projections.get("tooltip",  [])

                # Also check prototypeQuery for tooltip fields
                proto = sv_cfg.get("prototypeQuery",{})
                select_list = proto.get("Select",[])
                proto_tooltips = [
                    s for s in select_list
                    if s.get("Name","").startswith("Tooltip") or
                       "tooltip" in str(s).lower()
                ]

                all_tooltip_fields = list(tooltip_fields) + proto_tooltips

                if not all_tooltip_fields:
                    continue  # No custom tooltip fields on this visual

                tooltip_fields_found += 1

                # Find matching JSON visual
                jv = next(
                    (v for v in jp.get("visuals",[])
                     if v.get("visual_type","") == vtype
                     and round(v.get("position",{}).get("x",0),0) == vx
                     and round(v.get("position",{}).get("y",0),0) == vy),
                    {}
                )

                json_tooltip_cfg = jv.get("tooltip_config")

                if json_tooltip_cfg is None or json_tooltip_cfg == {}:
                    self.results.append(CheckResult(
                        check_id="D9",
                        attribute=f"{prefix}.tooltip_fields",
                        status="MISSING",
                        source_value=f"{len(all_tooltip_fields)} custom tooltip field(s)",
                        json_value=None,
                        note=(
                            f"Visual has {len(all_tooltip_fields)} custom tooltip "
                            f"field(s) in the PBIX that are not captured in the "
                            f"homogeneous JSON tooltip_config field. "
                            f"Users will lose additional hover context in the "
                            f"forward-engineered PBIX. "
                            f"RE/OP must extract the Tooltips projection role "
                            f"from each visual's projections block."
                        )
                    ))
                else:
                    tooltip_fields_captured += 1
                    self.results.append(CheckResult(
                        check_id="D9",
                        attribute=f"{prefix}.tooltip_fields",
                        status="PASS",
                        source_value=f"{len(all_tooltip_fields)} field(s)",
                        json_value="captured",
                        note="Custom tooltip fields captured in JSON"
                    ))

        if not tooltip_pages_in_source and tooltip_fields_found == 0:
            self.results.append(CheckResult(
                check_id="D9",
                attribute="tooltip_config.present",
                status="PASS",
                source_value="none",
                json_value="none",
                note="No custom tooltip configuration found in this PBIX"
            ))

        print(f"     Tooltip pages: {len(tooltip_pages_in_source)}  |  "
              f"Visuals with custom tooltip fields: {tooltip_fields_found} "
              f"({tooltip_fields_captured} captured)")

    # -- D7  --  External component references --


    # -- D10 --  Visual Interactions and Navigation --

    def check_d10_interactions_navigation(self):
        """
        D10 --  Visual Interactions and Navigation check.

        Validates:
          1. Cross-filter interaction settings between visual pairs
          2. Sync slicer configuration across pages
          3. All button action types and their type-specific targets:
             Back, Bookmark, Drill through, Page navigation, Q&A,
             Web URL, Apply all slicers, Clear all slicers, Data function
          4. Conditional action expressions (DAX-driven targets)
          5. Button state styling per state (default, hover, pressed, disabled)
        """
        print("[D10] Checking visual interactions and navigation...")

        src_layout = self.pbix.get("layout", {})
        json_viz   = self.json.get("visualizations", {})
        json_pages = json_viz.get("pages", [])
        json_pg_lkp = {p.get("display_name","").lower(): p for p in json_pages}

        # -- Action type → required value field mapping ----------------
        ACTION_VALUE_MAP = {
            "pagednavigation":    ("button_target_page",     "HIGH",   "Target page name for Page navigation button"),
            "pagenavigation":     ("button_target_page",     "HIGH",   "Target page name for Page navigation button"),
            "bookmark":           ("button_target_bookmark", "HIGH",   "Target bookmark name for Bookmark button"),
            "url":                ("button_target_url",      "HIGH",   "Target URL for Web URL button"),
            "weburl":             ("button_target_url",      "HIGH",   "Target URL for Web URL button"),
            "back":               (None,                     "HIGH",   "Back button  --  no target value needed"),
            "drillthrough":       ("drill_through_target",   "CRITICAL","Target drillthrough page AND filter context field for Drill through button"),
            "q&a":                ("qa_question",            "HIGH",   "Pre-filled Q&A question text if configured"),
            "qna":                ("qa_question",            "HIGH",   "Pre-filled Q&A question text if configured"),
            "applyallslicers":    ("apply_slicers_scope",    "HIGH",   "Apply all slicers  --  scope of deferred query mode"),
            "clearallslicers":    ("clear_slicers_scope",    "HIGH",   "Clear all slicers  --  scope: current page or all pages"),
            "datafunction":       ("data_function_name",     "HIGH",   "Data function name and parameters"),
        }

        BUTTON_VISUAL_TYPES = {
            "actionButton", "button", "shape", "textbox",
            "image",        "basicShape"
        }

        for sp in src_layout.get("pages", []):
            pname = sp.get("name","")
            jp    = json_pg_lkp.get(pname.lower(), {})

            # Build JSON visual lookup by type+position
            json_vis_lkp = {}
            for jv in jp.get("visuals", []):
                pos = jv.get("position",{})
                key = (jv.get("visual_type",""),
                       round(pos.get("x",0),0),
                       round(pos.get("y",0),0))
                json_vis_lkp[key] = jv

            for sv in sp.get("visuals", []):
                vtype  = sv.get("visual_type","")
                vx     = round(sv.get("x",0),0)
                vy     = round(sv.get("y",0),0)
                config = sv.get("config",{})
                sv_cfg = config.get("singleVisual",{})
                vc_obj = config.get("vcObjects",{})
                prefix = f"page[{pname}].button[{vtype}@{vx},{vy}]"

                # -- R17: drillFilterOtherVisuals = False (custom interaction override) --
                # When this flag is explicitly set to False, this visual does NOT
                # cross-filter other visuals when clicked. Default (absent/True) = cross-filters.
                # RE/OP must capture any visual where this is False  --  it's a deliberate
                # design decision that affects report interactivity.
                drill_filter = sv_cfg.get("drillFilterOtherVisuals", None)
                if drill_filter is False:
                    jv_r17  = json_vis_lkp.get((vtype, vx, vy), {})
                    json_dfo = jv_r17.get("drill_filter_other_visuals",
                                          jv_r17.get("drillFilterOtherVisuals", None))
                    self._log("D10", f"page[{pname}].visual[{vtype}@{vx},{vy}].drillFilterOtherVisuals",
                              False, json_dfo,
                              "VISUAL INTERACTION (R17): drillFilterOtherVisuals=False means "
                              "this visual does NOT cross-filter others when clicked. "
                              "This is a custom interaction override. "
                              "RE/OP must capture this flag so the target report preserves "
                              "the same interaction behaviour. "
                              "Missing = visual will unexpectedly cross-filter others in target.")
                action_block = None

                # Check vcObjects.action
                if "action" in vc_obj:
                    action_props = vc_obj["action"]
                    if isinstance(action_props, list) and action_props:
                        action_block = action_props[0].get("properties",{})

                # Check singleVisual.objects.action
                if not action_block:
                    sv_objects = sv_cfg.get("objects",{})
                    if "action" in sv_objects:
                        act = sv_objects["action"]
                        if isinstance(act, list) and act:
                            action_block = act[0].get("properties",{})

                if not action_block:
                    continue  # No action on this visual

                # -- Extract action type -------------------------------
                # Action type is stored as a literal string or a conditional
                action_type_raw = ""
                act_type_field  = action_block.get("type",{})
                if isinstance(act_type_field, dict):
                    # Literal value
                    action_type_raw = (
                        act_type_field.get("expr",{})
                                      .get("Literal",{})
                                      .get("Value","")
                        or act_type_field.get("value","")
                    ).strip("'\"").lower()

                    # Check for conditional action expression
                    if "Conditional" in act_type_field.get("expr",{}):
                        jv = json_vis_lkp.get((vtype,vx,vy), {})
                        json_button = jv.get("button_type") or jv.get("action_type")
                        self.results.append(CheckResult(
                            check_id="D10",
                            attribute=f"{prefix}.conditional_action_expression",
                            status="MISSING" if not json_button else "PASS",
                            source_value="conditional_dax_expression",
                            json_value=json_button,
                            note=(
                                "Button action type is conditional  --  driven by a DAX "
                                "measure that returns different targets based on context. "
                                "The conditional DAX expression must be captured in the JSON."
                            )
                        ))

                if not action_type_raw:
                    continue

                # -- Get the matching JSON visual ----------------------
                jv          = json_vis_lkp.get((vtype, vx, vy), {})
                json_btn    = jv.get("button_type","") or jv.get("action",{})

                # Log the action type itself
                self._log("D10", f"{prefix}.action_type",
                          action_type_raw,
                          (jv.get("button_type") or "").lower() or None,
                          f"Button action type must be captured in JSON")

                # -- Check type-specific value -------------------------
                action_key = action_type_raw.replace(" ","").replace("_","").lower()
                mapping    = ACTION_VALUE_MAP.get(action_key)

                if mapping:
                    json_field, severity, note = mapping

                    if json_field is None:
                        # Back button  --  no value needed, type is enough
                        self.results.append(CheckResult(
                            check_id="D10",
                            attribute=f"{prefix}.action[{action_type_raw}]",
                            status="PASS",
                            source_value=action_type_raw,
                            json_value="no-target-required",
                            note="Back button  --  action type captured, no target value required"
                        ))
                        continue

                    # Extract source value for this action type
                    src_val = None

                    if action_key in ("pagednavigation","pagenavigation"):
                        # Page navigation  --  get target page
                        nav_page = action_block.get("navigationSection",{})
                        src_val  = (nav_page.get("expr",{})
                                           .get("Literal",{})
                                           .get("Value","")).strip("'\"")

                    elif action_key == "bookmark":
                        bk = action_block.get("bookmarkAction",{})
                        src_val = (bk.get("expr",{})
                                     .get("Literal",{})
                                     .get("Value","")).strip("'\"")

                    elif action_key in ("url","weburl"):
                        url_prop = action_block.get("url",{}) or \
                                   action_block.get("navigationUrl",{})
                        src_val  = (url_prop.get("expr",{})
                                            .get("Literal",{})
                                            .get("Value","")).strip("'\"")

                    elif action_key == "drillthrough":
                        dt_page = action_block.get("pageNavigationDestination",{}) or \
                                  action_block.get("drillthroughPage",{})
                        src_val = (dt_page.get("expr",{})
                                          .get("Literal",{})
                                          .get("Value","drill-page-not-extracted")).strip("'\"")

                    elif action_key in ("q&a","qna"):
                        qa_q    = action_block.get("question",{})
                        src_val = (qa_q.get("expr",{})
                                       .get("Literal",{})
                                       .get("Value","")).strip("'\"") or "qa-no-prefill"

                    elif action_key == "applyallslicers":
                        src_val = "deferred-query-mode"

                    elif action_key == "clearallslicers":
                        scope   = action_block.get("scope",{})
                        src_val = (scope.get("expr",{})
                                        .get("Literal",{})
                                        .get("Value","current-page")).strip("'\"")

                    elif action_key == "datafunction":
                        fn = action_block.get("function",{})
                        src_val = (fn.get("expr",{})
                                     .get("Literal",{})
                                     .get("Value","")).strip("'\"")

                    # Get JSON value for this action's target
                    json_val = (jv.get(json_field) or
                                jv.get("navigation_target") or
                                jv.get("button_action",{}).get(json_field))

                    sev_level = severity
                    status    = "PASS" if (src_val and json_val) else \
                                "MISSING" if (src_val and not json_val) else "PASS"

                    self.results.append(CheckResult(
                        check_id="D10",
                        attribute=f"{prefix}.action[{action_type_raw}].{json_field}",
                        status=status,
                        source_value=src_val or "not-extracted",
                        json_value=json_val,
                        note=note
                    ))

                else:
                    # Unknown action type  --  flag it so RE/OP knows to capture it
                    self.results.append(CheckResult(
                        check_id="D10",
                        attribute=f"{prefix}.action[{action_type_raw}]",
                        status="MISSING",
                        source_value=action_type_raw,
                        json_value=None,
                        note=(
                            f"Unrecognised button action type '{action_type_raw}' found. "
                            f"This may be a new Power BI action type or a custom action. "
                            f"RE/OP must capture this action type and its target value."
                        )
                    ))

                # -- Button state styling ------------------------------
                # Check if JSON captures styling for each state
                STATES = ["default","hover","pressed","disabled"]
                json_states = jv.get("button_states", {})
                has_state_config = any(
                    k in vc_obj for k in ["default","hover","pressed","disabled",
                                          "enabled","hoverState","pressedState"]
                )
                if has_state_config and not json_states:
                    self.results.append(CheckResult(
                        check_id="D10",
                        attribute=f"{prefix}.button_state_styling",
                        status="MISSING",
                        source_value=f"states: {', '.join(STATES)}",
                        json_value=None,
                        note=(
                            "Button has per-state styling (text, icon, fill colour, "
                            "font colour) for default, hover, pressed and disabled states. "
                            "These are not captured in the JSON. Without them the "
                            "forward-engineered button will use default Power BI styling."
                        )
                    ))

        # -- Sync Slicers cross-page (R18) ---------------------------
        # Report/Layout config stores syncSlicers at report level.
        # Each slicer visual may have syncSlicerFiltersApply = true|false.
        # This check scans all slicer visuals for sync behaviour.
        json_sync_groups = self.json.get("sync_slicers", {}) or \
                           self.json.get("visualizations", {}).get("sync_slicers", {})
        sync_found = False
        for sp in src_layout.get("pages", []):
            pname = sp.get("name","")
            for sv in sp.get("visuals", []):
                if sv.get("visual_type","").lower() != "slicer":
                    continue
                config     = sv.get("config",{})
                sv_cfg     = config.get("singleVisual",{}) if isinstance(config,dict) else {}
                sync_cfg   = sv_cfg.get("syncSlicerFiltersApply", None)
                if sync_cfg is None and isinstance(config, dict):
                    sync_cfg = config.get("syncSlicerFiltersApply", None)
                if sync_cfg is not None:
                    sync_found = True
                    vx = round(sv.get("x",0),0)
                    vy = round(sv.get("y",0),0)
                    prefix_s = f"page[{pname}].slicer[@{vx},{vy}]"
                    json_val = None
                    if json_sync_groups:
                        # Try to find matching slicer in JSON sync group
                        json_val = True  # presence of sync_slicers block is sufficient signal
                    self._log("D10", f"{prefix_s}.syncSlicerFiltersApply",
                              sync_cfg, json_val,
                              "SYNC SLICER: syncSlicerFiltersApply flag must be captured. "
                              "When True, value changes on this slicer propagate to all "
                              "pages in the sync group. RE/OP must extract "
                              "syncSlicerFiltersApply from the slicer visual config and "
                              "capture the sync group in JSON under sync_slicers. "
                              "Missing = slicer behaves as page-local in target.")

        if not sync_found:
            self.results.append(CheckResult(
                check_id="D10", attribute="sync_slicers.present",
                status="PASS", source_value="no_sync_slicers_found",
                json_value="no_sync_slicers_found",
                note="No cross-page sync slicers found in this report  --  N/A"
            ))

        # ── Drillthrough page definitions (target side) ─────────────
        # D10 already checks the SOURCE side: buttons whose action.type =
        # "drillthrough" and their target page name.
        # This block checks the TARGET side: pages that ARE drillthrough
        # destinations, their key fields, keepAllFilters, and back button.
        #
        # In Report/Layout a drillthrough target page has:
        #   section.config.drillthrough  → present = page is a target
        #   section.config.drillthrough.keepAllFilters  → bool
        #   section.filters[]  → the drillthrough key fields
        #   a visual with visualType=actionButton + action.type=Back

        json_pages = self.json.get("visualizations", {}).get("pages", []) or                      self.json.get("pages", []) or []
        json_page_lkp = {p.get("name","").lower(): p for p in json_pages}

        dt_pages_found = False

        for sp in src_layout.get("pages", []):
            pname      = sp.get("name","")
            pconfig    = sp.get("page_config", {}) or {}

            # Detect drillthrough target page
            # Power BI stores drillthrough config in section.config.drillthrough
            dt_config  = pconfig.get("drillthrough", None)
            if dt_config is None:
                # Also check raw config string
                raw_cfg = sp.get("config", {})
                if isinstance(raw_cfg, str):
                    import json as _json
                    try: raw_cfg = _json.loads(raw_cfg)
                    except: raw_cfg = {}
                dt_config = raw_cfg.get("drillthrough", None)

            if dt_config is None:
                continue

            dt_pages_found = True
            jp = json_page_lkp.get(pname.lower(), {})
            prefix = f"drillthrough_page[{pname}]"

            # 1. Page is a drillthrough target
            self._log("D10", f"{prefix}.is_drillthrough_target",
                      True,
                      jp.get("is_drillthrough_target",
                             jp.get("drillthrough_target", None)),
                      "DRILLTHROUGH TARGET PAGE: this page is configured as a "
                      "drillthrough destination. RE/OP must capture the "
                      "drillthrough config from section.config.drillthrough. "
                      "Missing = target model has no drillthrough page.")

            # 2. keepAllFilters
            keep_all = None
            if isinstance(dt_config, dict):
                keep_all = dt_config.get("keepAllFilters",
                           dt_config.get("keep_all_filters", None))
            src_keep = keep_all if keep_all is not None else True  # PBI default = true
            json_keep = jp.get("keep_all_filters",
                               jp.get("keepAllFilters", None))
            self._log("D10", f"{prefix}.keepAllFilters",
                      src_keep, json_keep,
                      "DRILLTHROUGH keepAllFilters: when True, all report-level "
                      "filters carry over to the drillthrough page. "
                      "Wrong value = drillthrough shows unexpected data. "
                      "RE/OP must capture from section.config.drillthrough.")

            # 3. Drillthrough key fields (page filters on the drillthrough page)
            # These are the fields the user right-clicks on to trigger drillthrough
            src_dt_filters = sp.get("page_filters", [])
            json_dt_filters = jp.get("drillthrough_filters",
                                     jp.get("page_filters", []))
            src_count  = len(src_dt_filters)
            json_count = len(json_dt_filters) if json_dt_filters else None

            self._log("D10", f"{prefix}.drillthrough_key_fields.count",
                      src_count,
                      json_count,
                      f"DRILLTHROUGH KEY FIELDS: {src_count} key field(s) define "
                      "what data this drillthrough page filters on. "
                      "RE/OP must capture the page-level filters on the "
                      "drillthrough target page. Missing = drillthrough shows "
                      "unfiltered data in the target model.")

            for i, sf in enumerate(src_dt_filters):
                col_expr = (sf.get("expression", {})
                              .get("Column", {})
                              .get("Property", ""))
                tbl_expr = (sf.get("expression", {})
                              .get("Column", {})
                              .get("Expression", {})
                              .get("SourceRef", {})
                              .get("Entity", ""))
                field_ref = f"{tbl_expr}.{col_expr}" if tbl_expr else col_expr
                jf = json_dt_filters[i] if json_dt_filters and i < len(json_dt_filters) else {}
                json_field = (jf.get("expression",{})
                                .get("Column",{})
                                .get("Property","") or
                              jf.get("field","") or
                              jf.get("column",""))
                self._log("D10", f"{prefix}.drillthrough_key_field[{i}].field",
                          field_ref or f"field_{i}",
                          json_field or (field_ref if jf else None),
                          f"DRILLTHROUGH KEY FIELD: field '{field_ref}' must be "
                          "captured as a drillthrough filter on this page. "
                          "Without it the drillthrough context is lost.")

            # 4. Back button visual on the drillthrough page
            has_back_btn = False
            for sv in sp.get("visuals", []):
                vtype  = sv.get("visual_type","")
                config = sv.get("config", {})
                sv_cfg = config.get("singleVisual",{}) if isinstance(config,dict) else {}
                # Back button: actionButton with action type = "Back"
                objects = sv_cfg.get("objects",{})
                action  = (objects.get("action",[{}]) or [{}])[0]
                action_type = (action.get("properties",{})
                                     .get("actionType",{})
                                     .get("expr",{})
                                     .get("Literal",{})
                                     .get("Value",""))
                if vtype == "actionButton" and "Back" in str(action_type):
                    has_back_btn = True
                    break
                # Also check vcObjects path
                vc_obj = config.get("vcObjects",{}) if isinstance(config,dict) else {}
                action2 = (vc_obj.get("action",[{}]) or [{}])[0]
                if "Back" in str(action2):
                    has_back_btn = True
                    break

            json_has_back = jp.get("has_back_button",
                                   jp.get("back_button", None))
            self._log("D10", f"{prefix}.has_back_button",
                      has_back_btn,
                      json_has_back if json_has_back is not None else
                      (has_back_btn if jp else None),
                      "DRILLTHROUGH BACK BUTTON: a Back button visual must exist "
                      "on every drillthrough target page so users can return to "
                      "the source page. RE/OP must capture the back button "
                      "presence from the page's visualContainers.")

        if not dt_pages_found:
            self.results.append(CheckResult(
                check_id="D10", attribute="drillthrough_pages.present",
                status="PASS", source_value="no_drillthrough_pages",
                json_value="no_drillthrough_pages",
                note="No drillthrough target pages found in this report  --  N/A. "
                     "When a PBIX has drillthrough pages, this check captures: "
                     "is_drillthrough_target, keepAllFilters, key fields, "
                     "and back button presence."
            ))

    def check_d12_external(self):
        """
        Scan visual configs for embedded external component references:
        Power Apps, Power Automate, Paginated Reports, custom visuals,
        external URL buttons, Azure Maps / ArcGIS.
        """
        print("[D7] Checking external component references...")
        src_pages  = self.pbix.get("layout", {}).get("pages", [])
        json_pages = self.json.get("visualizations", {}).get("pages", [])
        json_pg_lkp= {p.get("display_name","").lower(): p for p in json_pages}

        EXT_VISUAL_TYPES = {
            "powerAppsVisual":       "Power Apps",
            "actionButton":          "Power Automate",
            "paginatedReportVisual": "Paginated Report",
            "arcgisMap":             "ArcGIS Map",
            "azureMap":              "Azure Map",
        }

        for sp in src_pages:
            pname = sp.get("name","")
            jp    = json_pg_lkp.get(pname.lower(), {})
            jvis_lkp = {
                v.get("visual_type","").lower(): v
                for v in jp.get("visuals", [])
            }

            for sv in sp.get("visuals", []):
                vtype  = sv.get("visual_type","")
                config = sv.get("config", {})
                sv_cfg = config.get("singleVisual", {})
                vc_obj = config.get("vcObjects", {})
                prefix = f"page[{pname}].external[{vtype}]"

                if vtype in EXT_VISUAL_TYPES:
                    label = EXT_VISUAL_TYPES[vtype]
                    jv    = jvis_lkp.get(vtype.lower(), {})

                    if vtype == "powerAppsVisual":
                        pa_cfg = sv_cfg.get("objects", {}).get("general", [{}])[0].get("properties", {})
                        self._log("D12", f"{prefix}.environmentId",
                                  pa_cfg.get("environmentId", {}).get("expr", {}).get("Literal", {}).get("Value"),
                                  jv.get("environment_id"),
                                  f"{label}: environmentId must be captured")
                        self._log("D12", f"{prefix}.appId",
                                  pa_cfg.get("appId", {}).get("expr", {}).get("Literal", {}).get("Value"),
                                  jv.get("app_id"),
                                  f"{label}: appId must be captured")

                    elif vtype == "actionButton":
                        action = sv_cfg.get("objects", {}).get("action", [{}])[0].get("properties", {})
                        self._log("D12", f"{prefix}.flowId",
                                  action.get("flowId", {}).get("expr", {}).get("Literal", {}).get("Value"),
                                  jv.get("flow_id"),
                                  f"{label}: flowId must be captured")

                    elif vtype == "paginatedReportVisual":
                        prv = sv_cfg.get("objects", {}).get("general", [{}])[0].get("properties", {})
                        self._log("D12", f"{prefix}.workspaceId",
                                  prv.get("workspaceId", {}).get("expr", {}).get("Literal", {}).get("Value"),
                                  jv.get("workspace_id"),
                                  f"{label}: workspaceId must be captured")
                        self._log("D12", f"{prefix}.reportId",
                                  prv.get("reportId", {}).get("expr", {}).get("Literal", {}).get("Value"),
                                  jv.get("report_id"),
                                  f"{label}: reportId must be captured")

                # Custom visuals  --  identified by GUID in visualType string (R10)
                guid_pattern = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
                if re.search(guid_pattern, vtype, re.IGNORECASE):
                    jv = jvis_lkp.get(vtype.lower(), {})
                    self._log("D12", f"{prefix}.custom_visual_guid",
                              vtype, jv.get("visual_type"),
                              "Custom visual GUID must match  --  from pbiviz.json, not package.json. "
                              "Custom visual must be downloaded from AppSource and added to target manually.")
                    version = sv_cfg.get("version", "")
                    self._log("D12", f"{prefix}.custom_visual_version",
                              version, jv.get("version"),
                              "Custom visual version must be captured")

                # R16 -- Forward-compatible custom visual detection by type-name length.
                # Standard built-in type names are short (e.g. "barChart", "slicer").
                # Custom visual type names are long GUIDs or company-prefixed strings (>15 chars).
                # This catches ALL custom visuals including htmlContent, WordCloud, any AppSource
                # visual without hardcoding their names  --  future-proof approach.
                STANDARD_VISUAL_TYPES = {
                    "barChart","clusteredBarChart","stackedBarChart","hundredPercentStackedBarChart",
                    "columnChart","clusteredColumnChart","stackedColumnChart","hundredPercentStackedColumnChart",
                    "lineChart","areaChart","stackedAreaChart","hundredPercentStackedAreaChart",
                    "lineStackedColumnComboChart","lineClusteredColumnComboChart",
                    "pieChart","donutChart","treemap","funnel","waterfall","scatterChart","bubbleChart",
                    "map","filledMap","shapeMap","azureMap","arcgisMap",
                    "card","multiRowCard","gauge","kpi",
                    "slicer","tableEx","matrix","pivotTable",
                    "image","textbox","shape","actionButton",
                    "powerAppsVisual","paginatedReportVisual","rdlReport",
                    "ribbonChart","decompositionTree","keyInfluencers","qnaVisual","aiNarrative",
                    "scorecard",
                }
                if (vtype and
                    len(vtype) > 15 and
                    vtype.lower() not in {v.lower() for v in STANDARD_VISUAL_TYPES} and
                    not re.search(guid_pattern, vtype, re.IGNORECASE)):  # already handled above
                    jv = jvis_lkp.get(vtype.lower(), {})
                    self.results.append(CheckResult(
                        check_id="D12",
                        attribute=f"{prefix}.custom_or_html_visual_type[{vtype}]",
                        status="PASS" if jv else "MISSING",
                        source_value=vtype,
                        json_value=jv.get("visual_type") if jv else None,
                        note=(
                            f"CUSTOM/HTML VISUAL (R16): visual type '{vtype}' is not a standard "
                            "built-in visual (detected by type name length >15 chars). "
                            "This may be htmlContent, WordCloud, or any other AppSource/custom visual. "
                            "Must be downloaded from AppSource and added to the target report manually. "
                            "Missing in target = visual shows an error message."
                        )
                    ))

                # Button URL actions
                for obj_key in vc_obj:
                    if "navigation" in obj_key.lower() or "action" in obj_key.lower():
                        props = vc_obj[obj_key][0].get("properties", {}) if vc_obj[obj_key] else {}
                        nav_url = props.get("navigationUrl", {}).get("expr", {}).get("Literal", {}).get("Value","")
                        if nav_url:
                            jv = jvis_lkp.get(vtype.lower(), {})
                            self._log("D12", f"{prefix}.button_url",
                                      nav_url, jv.get("navigation_target"),
                                      "External URL button action must be captured")

    # -- Run all checks -----------------------

    def run_cross_validation_mode(self):
        """
        Cross-validation mode  --  used when DataModel is binary and
        cannot be decoded directly.

        Instead of PBIX DataModel → JSON comparison, we:
          D1  --  Validate datasource entries in JSON are internally complete
          D2  --  Extract all table.column refs from Report/Layout and
               verify each one exists in the JSON data model block
          D3  --  Validate field data types are populated in JSON
          D5  --  Validate DAX measures in JSON are internally consistent
               (referenced tables/columns exist within the JSON itself)
        Then run D4, D6, D7 normally (these don't need DataModel).
        """
        print("\n[D1] Cross-validating datasource entries in homogeneous JSON...")
        self._cross_check_d1()

        print("[D2] Cross-validating table/column refs from Layout vs JSON model...")
        self._cross_check_d2()

        print("[D3] Cross-validating field definitions in JSON...")
        self._cross_check_d3()

        print("[D4] Checking filters and parameters...")
        self.check_d4_filters()

        print("[D5] Cross-validating DAX measure consistency in JSON...")
        self._cross_check_d5()

        print("[D6] Checking report visual layer...")
        self.check_d6_visuals()

        print("[D7] Checking visual display names and aggregation accuracy...")
        self.check_d7_display_names()

        print("[D8] Checking conditional formatting...")
        self.check_d8_conditional_formatting()

        print("[D9] Checking tooltip configuration...")
        self.check_d9_tooltips()

        print("[D10] Checking visual interactions and navigation...")
        self.check_d10_interactions_navigation()

        print("[D7] Checking external component references...")
        self.check_d12_external()

        # New checks that can run without a decoded DataModel
        print("[D2-RLS] Checking RLS roles from SecurityBindings...")
        self.check_d2_rls_ols()           # SecurityBindings is readable even when DataModel is binary
        print("[D5-DYNRLS] Scanning RLS filters for dynamic RLS patterns...")
        self.check_d5_dynamic_rls()       # Scans rls_roles which came from SecurityBindings
        print("[D6-IMAGES] Checking StaticResources images...")
        self.check_d6_images_logos()      # Uses layout and static resource list
        print("[D10-SYNC] Checking sync slicer flags...")
        # sync slicer check is embedded inside check_d10_interactions_navigation already

    def _cross_check_d1(self):
        """D1 cross-validation using json['data_sources'] (actual key name)."""
        json_sources = self.json.get("data_sources", [])
        if not json_sources:
            self._log("D1", "data_sources.present",
                      "expected", None,
                      "No data_sources block found in homogeneous JSON")
            return

        required_attrs = ["name", "source_type", "connection_mode",
                          "authentication_method"]
        for ds in json_sources:
            name = ds.get("name", "unknown")
            for attr in required_attrs:
                val = ds.get(attr)
                self._log("D1", f"datasource[{name}].{attr}", val, val)
                if not val:
                    self.results[-1].status      = "MISSING"
                    self.results[-1].source_value = "required"
                    self.results[-1].json_value   = None

    def _cross_check_d2(self):
        """D2 cross-validation using json['tables'] (actual root-level key)."""
        layout    = self.pbix.get("layout", {})
        # Use root-level 'tables' key
        json_tbls = {
            t.get("name","").lower(): {
                c.get("name","").lower()
                for c in t.get("columns", [])
            }
            for t in self.json.get("tables", [])
        }

        if not json_tbls:
            self._log("D2", "tables.present",
                      "expected", None,
                      "No tables found in homogeneous JSON root tables block")
            return

        seen_refs = set()
        for page in layout.get("pages", []):
            for vis in page.get("visuals", []):
                for fld in vis.get("fields", []):
                    qref = fld.get("query_ref", "")
                    if qref and qref not in seen_refs:
                        seen_refs.add(qref)
                        match = re.search(r'[\w\s]+\((.+?)\.(.+?)\)', qref)
                        if not match:
                            parts = qref.split(".", 1)
                            if len(parts) == 2:
                                tname, cname = parts[0].strip(), parts[1].strip()
                            else:
                                continue
                        else:
                            tname, cname = match.group(1).strip(), match.group(2).strip()

                        tkey = tname.lower()
                        ckey = cname.lower()
                        tbl_exists = tkey in json_tbls
                        col_exists = tbl_exists and ckey in json_tbls.get(tkey, set())

                        self._log("D2", f"layout_ref[{tname}].table_in_json",
                                  tname, tname if tbl_exists else None,
                                  "Table referenced in layout must exist in JSON tables block")
                        if tbl_exists:
                            self._log("D2", f"layout_ref[{tname}.{cname}].column_in_json",
                                      cname, cname if col_exists else None,
                                      "Column referenced in layout must exist in JSON tables block")

    def _cross_check_d3(self):
        """D3 cross-validation using json['tables'] and 'nullable' field name."""
        tables = self.json.get("tables", [])  # root-level key
        if not tables:
            self._log("D3", "tables.present",
                      "expected", None,
                      "No tables in JSON  --  cannot validate field definitions")
            return

        for tbl in tables:
            tname = tbl.get("name","")
            for col in tbl.get("columns", []):
                cname = col.get("name","")
                dtype = col.get("data_type","")
                self._log("D3", f"column[{tname}.{cname}].data_type",
                          dtype if dtype else "required", dtype,
                          "data_type must be populated in JSON")
                if not dtype:
                    self.results[-1].status      = "MISSING"
                    self.results[-1].source_value = "required"
                    self.results[-1].json_value   = None

    def _cross_check_d5(self):
        """D5 cross-validation using json['calculations'] and json['relationships']."""
        # Measures from calculations block
        calcs = self.json.get("calculations", [])
        for m in calcs:
            mname = m.get("name","")
            expr  = (m.get("expressions",{}) or {}).get("dax","")
            self._log("D5", f"measure[{mname}].expression",
                      expr if expr else "required", expr,
                      "DAX expression must be in expressions.dax")
            if not expr:
                self.results[-1].status      = "MISSING"
                self.results[-1].source_value = "required"
                self.results[-1].json_value   = None
            self._log("D5", f"measure[{mname}].format_string",
                      m.get("format_string"), m.get("format_string"))

        # Relationships from root-level relationships block
        rels = self.json.get("relationships", [])
        required_rel_attrs = ["left_column","right_column","cardinality",
                              "filter_direction","active"]
        for rel in rels:
            key = f"{rel.get('left_column','')}→{rel.get('right_column','')}"
            for attr in required_rel_attrs:
                val = rel.get(attr)
                self._log("D5", f"relationship[{key}].{attr}",
                          val if val is not None else "required", val)
                if val is None or val == "":
                    self.results[-1].status      = "MISSING"
                    self.results[-1].source_value = "required"
                    self.results[-1].json_value   = None

    def check_d11_visual_formatting(self):
        """
        D11 --  Visual formatting objects: labels, axes, data points,
        button styling, image sources, canvas colour settings.

        Validates that visual-level formatting defined in the singleVisual.objects
        block is captured in the JSON. These include:
          labels         --  data value font, size, bold, colour
          categoryLabels --  category label font, size, colour  
          wordWrap       --  text wrapping on cards
          categoryAxis   --  X-axis font, label colour
          valueAxis      --  Y-axis font, label colour, scale
          legend         --  legend show/hide, title
          dataPoint      --  per-series custom colour overrides
          labels (data)  --  data label show, position
          icon/text/shape  --  button styling objects
          general        --  visual background fill, border colour
        """
        print("[D11] Checking visual formatting objects...")
        src_pages  = self.pbix.get("layout", {}).get("pages", [])
        json_pages = self.json.get("visualizations", {}).get("pages", [])
        json_pg_lk = {p.get("display_name","").lower(): p
                      for p in json_pages}

        # Formatting object keys we specifically track
        FORMATTING_KEYS = {
            "labels":          ("data value labels  --  font, size, bold, colour",    "HIGH"),
            "categoryLabels":  ("category/header labels  --  font, size, colour",     "HIGH"),
            "wordWrap":        ("word wrap setting on cards and text",              "MEDIUM"),
            "categoryAxis":    ("X-axis  --  font, label colour, title",              "HIGH"),
            "valueAxis":       ("Y-axis  --  font, label colour, scale, display units","HIGH"),
            "legend":          ("legend  --  show/hide, position, title",             "MEDIUM"),
            "dataPoint":       ("per-series custom colour overrides",              "HIGH"),
            "labels":          ("data labels on charts  --  show, position, format",  "HIGH"),
            "background":      ("visual background colour and transparency",        "MEDIUM"),
            "border":          ("visual border colour, width, style",              "MEDIUM"),
            "shadow":          ("visual shadow settings",                          "LOW"),
            "title":           ("visual title text, font, colour",                 "HIGH"),
            "icon":            ("button icon type and shape",                      "MEDIUM"),
            "text":            ("button text label and font",                      "MEDIUM"),
            "shape":           ("button shape style (rounded, etc.)",             "MEDIUM"),
            "values":          ("textbox or table cell formatted values",          "MEDIUM"),
        }

        for sp in src_pages:
            pname  = sp.get("name","")
            jp     = json_pg_lk.get(pname.lower(), {})
            jvis_lk= {v.get("visual_type","").lower(): v
                      for v in jp.get("visuals",[])}

            for sv in sp.get("visuals",[]):
                vtype  = sv.get("visual_type","")
                if not vtype:
                    continue
                config = sv.get("config",{})
                sv_cfg = config.get("singleVisual",{})
                objs   = sv_cfg.get("objects",{})
                vx     = round(sv.get("x",0),0)
                vy     = round(sv.get("y",0),0)
                prefix = f"page[{pname}].visual[{vtype}@{vx},{vy}]"

                jv = jvis_lk.get(vtype.lower(),{})
                jv_fmt = jv.get("formatting",{}) or jv.get("visual_formatting",{})

                for obj_key, (desc, sev) in FORMATTING_KEYS.items():
                    if obj_key not in objs:
                        continue  # not configured in source  --  skip
                    obj_data = objs[obj_key]
                    if not obj_data:
                        continue

                    # Extract key properties from the object
                    props = {}
                    if isinstance(obj_data, list) and obj_data:
                        for entry in obj_data:
                            props.update(entry.get("properties",{}))

                    # Special handling for dataPoint  --  per-series colours
                    if obj_key == "dataPoint":
                        colours = []
                        if isinstance(obj_data, list):
                            for entry in obj_data:
                                ep = entry.get("properties",{})
                                fill = ep.get("fill",{})
                                if isinstance(fill,dict):
                                    solid = fill.get("solid",{})
                                    if isinstance(solid,dict):
                                        colour = (solid.get("color",{})
                                                  .get("expr",{})
                                                  .get("Literal",{})
                                                  .get("Value",""))
                                        if colour:
                                            colours.append(colour)
                        src_val = colours if colours else "custom_series_colours"
                        jv_colours = jv_fmt.get("data_point_colours",
                                     jv.get("data_point_colours",[]))
                        self._log("D11", f"{prefix}.{obj_key}.custom_colours",
                                  src_val, jv_colours or None,
                                  f"Custom per-series data point colours must be "
                                  f"captured. RE/OP must extract dataPoint[] colour "
                                  f"overrides from singleVisual.objects.dataPoint. "
                                  f"Source colours: {colours}")
                        continue

                    # Extract font/colour properties for axis and label objects
                    font_family = (props.get("fontFamily",{})
                                   .get("expr",{}).get("Literal",{})
                                   .get("Value",""))
                    font_size   = (props.get("fontSize",{})
                                   .get("expr",{}).get("Literal",{})
                                   .get("Value",""))
                    label_color = ""
                    if "labelColor" in props:
                        label_color = str(props["labelColor"])[:80]
                    show = (props.get("show",{})
                            .get("expr",{}).get("Literal",{})
                            .get("Value",""))

                    # Build source value summary
                    src_parts = []
                    if font_family: src_parts.append(f"font:{font_family[:30]}")
                    if font_size:   src_parts.append(f"size:{font_size}")
                    if label_color: src_parts.append(f"color:{label_color[:20]}")
                    if show:        src_parts.append(f"show:{show}")
                    src_val = " | ".join(src_parts) if src_parts else \
                              f"{obj_key}_configured"

                    jv_obj_val = (jv_fmt.get(obj_key) or
                                  jv.get(f"{obj_key}_formatting") or
                                  jv.get(obj_key))

                    self._log("D11", f"{prefix}.{obj_key}",
                              src_val, jv_obj_val,
                              f"{desc}. RE/OP must extract singleVisual"
                              f".objects.{obj_key} from Report/Layout. "
                              f"Source: {src_val[:80]}")

        # -- Canvas / page background colour -----------------------
        for sp in src_pages:
            pname = sp.get("name","")
            cfg   = sp.get("page_config",{})
            bg    = cfg.get("background",{})
            cs    = cfg.get("canvasSettings",{})
            wallp = cfg.get("wallpaper",{})
            jp    = json_pg_lk.get(pname.lower(),{})

            if bg:
                self._log("D11", f"page[{pname}].background_colour",
                          str(bg)[:120],
                          jp.get("background_colour") or jp.get("background"),
                          "Page background colour/image must be captured. "
                          "RE/OP must extract page config.background from "
                          "Report/Layout sections[].config")
            if cs:
                self._log("D11", f"page[{pname}].canvas_settings",
                          str(cs)[:120],
                          jp.get("canvas_settings"),
                          "Canvas settings (size, zoom, display option) must "
                          "be captured from sections[].config.canvasSettings")
            if wallp:
                self._log("D11", f"page[{pname}].wallpaper",
                          str(wallp)[:120],
                          jp.get("wallpaper"),
                          "Page wallpaper settings must be captured from "
                          "sections[].config.wallpaper")

        # -- Image visual source -----------------------------------
        for sp in src_pages:
            pname = sp.get("name","")
            jp    = json_pg_lk.get(pname.lower(),{})
            for sv in sp.get("visuals",[]):
                if sv.get("visual_type","") != "image":
                    continue
                config = sv.get("config",{})
                sv_cfg = config.get("singleVisual",{})
                objs   = sv_cfg.get("objects",{})
                img_props = {}
                for obj_list in objs.values():
                    if isinstance(obj_list,list):
                        for entry in obj_list:
                            img_props.update(entry.get("properties",{}))
                # Image URL or embedded reference
                img_url = (img_props.get("imageUrl",{})
                           .get("expr",{}).get("Literal",{})
                           .get("Value",""))
                img_src = (img_props.get("imageSource",{})
                           .get("expr",{}).get("Literal",{})
                           .get("Value",""))
                vx = round(sv.get("x",0),0)
                vy = round(sv.get("y",0),0)
                prefix = f"page[{pname}].visual[image@{vx},{vy}]"

                jv_imgs = [v for v in jp.get("visuals",[])
                           if v.get("visual_type","") == "image"]
                jv_img  = jv_imgs[0] if jv_imgs else {}

                self._log("D11", f"{prefix}.image_source",
                          img_url or img_src or "embedded",
                          jv_img.get("image_url") or
                          jv_img.get("image_source") or None,
                          "Image visual source (URL or embedded reference) must "
                          "be captured. If embedded PNG, RE/OP must extract the "
                          "embedded image data or its StaticResources path. "
                          "This is required to recreate the image in the target PBIX")

    # ══════════════════════════════════════════════════════════════
    # CHECKLIST EXTENDED CHECKS  –  items missing from D1-D14
    # Covers: Section 1 (canvas env), Section 2 (alt text, header icons,
    # subtitle), Section 3 (card formatting), Section 4 (slicer controls),
    # Section 5 (table row detail), Section 6 (axis/chart detail),
    # Section 9 (rich text), Section 10 (visualStyles), Section 11
    # (analytics overlays), and the visual-type-specific checklist items.
    # ══════════════════════════════════════════════════════════════

    def check_dcl_canvas_environment(self):
        """
        CL-1  –  Canvas & Environment layer properties not covered by D6/D11.
        Checks per page:
          - displayArea (sizing mode: 16:9, 4:3, Letter, Tooltip, Custom)
          - verticalAlignment (Top, Middle)
          - Filter pane: visibility, width, cardState (Applied vs Available)
        Source: Report/Layout sections[].config
        JSON:   visualizations.pages[n].canvas_settings / filter_pane
        """
        print("[CL-1] Checking canvas environment (displayArea, verticalAlignment, filter pane)...")
        src_pages  = self.pbix.get("layout", {}).get("pages", [])
        json_viz   = self.json.get("visualizations", {})
        json_pages = json_viz.get("pages", [])
        json_pg_lk = {p.get("display_name", "").lower(): p for p in json_pages}

        for sp in src_pages:
            pname   = sp.get("name", "")
            cfg     = sp.get("page_config", {}) or {}
            jp      = json_pg_lk.get(pname.lower(), {})
            prefix  = f"page[{pname}]"

            # displayArea (sizing mode)
            display_area = cfg.get("displayArea", cfg.get("displayOption"))
            if display_area is not None:
                self._log("CL1", f"{prefix}.displayArea",
                          str(display_area),
                          str(jp.get("display_area", jp.get("displayArea", ""))) or None,
                          "CANVAS: displayArea (16:9/4:3/Letter/Tooltip/Custom) must be "
                          "captured. Controls how report scales in Power BI Service. "
                          "RE/OP must extract from sections[].config.displayArea.")

            # verticalAlignment
            v_align = cfg.get("verticalAlignment")
            if v_align is not None:
                self._log("CL1", f"{prefix}.verticalAlignment",
                          str(v_align),
                          str(jp.get("vertical_alignment", jp.get("verticalAlignment", ""))) or None,
                          "CANVAS: verticalAlignment (Top/Middle) controls content anchor. "
                          "RE/OP must extract from sections[].config.verticalAlignment.")

            # Filter pane visibility + width
            flt_pane = cfg.get("filterConfig", cfg.get("filterPanel", {})) or {}
            fp_visibility = flt_pane.get("defaultFilterPaneEnabled",
                            flt_pane.get("visibility"))
            fp_width      = flt_pane.get("width")
            jp_fp         = (jp.get("filter_pane") or jp.get("canvas_settings", {}) or {})

            if fp_visibility is not None:
                self._log("CL1", f"{prefix}.filterPane.visibility",
                          str(fp_visibility),
                          str(jp_fp.get("visibility", "")) or None,
                          "FILTER PANE: visibility state (Visible/Collapsed/Hidden) must "
                          "be captured so the target pane opens in the same state.")
            if fp_width is not None:
                self._log("CL1", f"{prefix}.filterPane.width",
                          str(fp_width),
                          str(jp_fp.get("width", "")) or None,
                          "FILTER PANE: sidebar width (pixels) must be captured.")

            # cardState – Applied vs Available filter card styling
            card_state = flt_pane.get("cardState", cfg.get("cardState"))
            if card_state is not None:
                self._log("CL1", f"{prefix}.filterPane.cardState",
                          str(card_state)[:80],
                          str(jp_fp.get("card_state", "")) or None,
                          "FILTER PANE: cardState controls typography/background/border "
                          "for Applied vs Available filter cards. Must be captured for "
                          "visual fidelity of the filter experience.")

    def check_dcl_alt_text_header_icons(self):
        """
        CL-2  –  Universal container properties missing from D6/D11.
        Checks per visual:
          - altText (Alternative Text / screen-reader description)
          - headerIcons array (Pin, FocusMode, FilterIcon, OptionsMenu)
          - subtitle text/expression
        Source: Report/Layout visualContainers[].config singleVisual.objects
        JSON:   visualizations.pages[n].visuals[n]
        """
        print("[CL-2] Checking altText, headerIcons, subtitle per visual...")
        src_pages  = self.pbix.get("layout", {}).get("pages", [])
        json_viz   = self.json.get("visualizations", {})
        json_pages = json_viz.get("pages", [])
        json_pg_lk = {p.get("display_name", "").lower(): p for p in json_pages}

        for sp in src_pages:
            pname = sp.get("name", "")
            jp    = json_pg_lk.get(pname.lower(), {})

            json_vis_lk = {}
            for jv in jp.get("visuals", []):
                pos = jv.get("position", {})
                key = (jv.get("visual_type", ""),
                       round(pos.get("x", 0), 0),
                       round(pos.get("y", 0), 0))
                json_vis_lk[key] = jv

            for sv in sp.get("visuals", []):
                vtype  = sv.get("visual_type", "")
                if not vtype:
                    continue
                vx     = round(sv.get("x", 0), 0)
                vy     = round(sv.get("y", 0), 0)
                config = sv.get("config", {})
                sv_cfg = config.get("singleVisual", {}) if isinstance(config, dict) else {}
                objs   = sv_cfg.get("objects", {})
                vc_obj = config.get("vcObjects", {}) if isinstance(config, dict) else {}
                prefix = f"page[{pname}].visual[{vtype}@{vx},{vy}]"
                jv     = json_vis_lk.get((vtype, vx, vy), {})

                # --- altText -------------------------------------------
                alt_raw = (objs.get("general", [{}]) or [{}])[0].get("properties", {}).get("altText")
                if alt_raw is None:
                    alt_raw = (vc_obj.get("general", [{}]) or [{}])[0].get("properties", {}).get("altText") if vc_obj else None
                if alt_raw is not None:
                    src_alt = str(alt_raw.get("expr", {}).get("Literal", {}).get("Value", "")
                                  or alt_raw.get("value", ""))[:120]
                    json_alt = (jv.get("alt_text") or jv.get("altText") or "")
                    self._log("CL2", f"{prefix}.altText",
                              src_alt or "configured",
                              str(json_alt) or None,
                              "ALT TEXT: screen-reader accessibility description must be "
                              "captured from singleVisual.objects.general[].altText. "
                              "Required for WCAG accessibility compliance.")

                # --- headerIcons ----------------------------------------
                header_icons_raw = (objs.get("visualHeader", [{}]) or [{}])[0].get("properties", {})
                if not header_icons_raw:
                    header_icons_raw = (vc_obj.get("visualHeader", [{}]) or [{}])[0].get("properties", {}) if vc_obj else {}
                if header_icons_raw:
                    icon_keys = [k for k in header_icons_raw
                                 if any(t in k.lower() for t in
                                        ("pin", "focus", "filter", "option", "drill", "menu"))]
                    if icon_keys:
                        json_header = jv.get("header_icons", jv.get("visual_header_icons"))
                        self._log("CL2", f"{prefix}.headerIcons",
                                  ",".join(icon_keys),
                                  str(json_header) if json_header else None,
                                  "HEADER ICONS: Pin/FocusMode/FilterIcon/OptionsMenu visibility "
                                  "array must be captured. Missing = drill-down icons appear on "
                                  "flat charts in target, cluttering the header.")

                # --- subtitle -------------------------------------------
                title_props = (objs.get("title", [{}]) or [{}])[0].get("properties", {})
                subtitle_val = title_props.get("subTitle") or title_props.get("subtitle")
                if subtitle_val is None:
                    subtitle_val = (vc_obj.get("title", [{}]) or [{}])[0].get("properties", {}).get("subTitle") if vc_obj else None
                if subtitle_val is not None:
                    src_sub = str(subtitle_val.get("expr", {}).get("Literal", {}).get("Value", "")
                                  or subtitle_val.get("value", ""))[:100]
                    json_sub = (jv.get("subtitle") or "")
                    self._log("CL2", f"{prefix}.subtitle",
                              src_sub or "configured",
                              str(json_sub) or None,
                              "SUBTITLE: visual subtitle text/expression must be captured.")

    def check_dcl_card_formatting(self):
        """
        CL-3  –  Card / KPI visual specific formatting properties.
        Checks:
          - displayUnits (Auto/None/Thousands/Millions/Billions)
          - decimalPlaces (precision)
          - categoryLabel toggle + word-wrap
          - referenceLabels (secondary metric arrays)
          - shapeType (Rectangle/Rounded Rectangle/Snipped Corner) for new card
          - cardPadding (inner border gap)
        Source: singleVisual.objects
        JSON:   visualizations.pages[n].visuals[n].formatting
        """
        print("[CL-3] Checking Card/KPI formatting (displayUnits, decimalPlaces, referenceLabels)...")
        CARD_TYPES = {"card", "kpiVisual", "singleRowCard", "multiRowCard",
                      "gauge", "kpi", "newCard", "cardVisual"}

        src_pages  = self.pbix.get("layout", {}).get("pages", [])
        json_viz   = self.json.get("visualizations", {})
        json_pages = json_viz.get("pages", [])
        json_pg_lk = {p.get("display_name", "").lower(): p for p in json_pages}

        for sp in src_pages:
            pname = sp.get("name", "")
            jp    = json_pg_lk.get(pname.lower(), {})
            json_vis_lk = {}
            for jv in jp.get("visuals", []):
                pos = jv.get("position", {})
                key = (jv.get("visual_type", ""),
                       round(pos.get("x", 0), 0),
                       round(pos.get("y", 0), 0))
                json_vis_lk[key] = jv

            for sv in sp.get("visuals", []):
                vtype = sv.get("visual_type", "")
                if not vtype or vtype.lower() not in {v.lower() for v in CARD_TYPES}:
                    continue
                vx     = round(sv.get("x", 0), 0)
                vy     = round(sv.get("y", 0), 0)
                config = sv.get("config", {})
                sv_cfg = config.get("singleVisual", {}) if isinstance(config, dict) else {}
                objs   = sv_cfg.get("objects", {})
                prefix = f"page[{pname}].visual[{vtype}@{vx},{vy}]"
                jv     = json_vis_lk.get((vtype, vx, vy), {})
                jv_fmt = jv.get("formatting", {}) or {}

                def _get_prop(obj_key, prop_key):
                    block = (objs.get(obj_key, [{}]) or [{}])[0].get("properties", {})
                    val   = block.get(prop_key)
                    if isinstance(val, dict):
                        return val.get("expr", {}).get("Literal", {}).get("Value",
                               val.get("value", ""))
                    return val

                # displayUnits
                du = _get_prop("labels", "labelDisplayUnits") or _get_prop("calloutValue", "labelDisplayUnits")
                if du is not None:
                    self._log("CL3", f"{prefix}.displayUnits",
                              str(du), str(jv_fmt.get("display_units", "")) or None,
                              "CARD: displayUnits (Auto/None/Thousands/Millions/Billions) "
                              "must be captured so the callout value scales correctly.")

                # decimalPlaces
                dp = _get_prop("labels", "labelPrecision") or _get_prop("calloutValue", "labelPrecision")
                if dp is not None:
                    self._log("CL3", f"{prefix}.decimalPlaces",
                              str(dp), str(jv_fmt.get("decimal_places", "")) or None,
                              "CARD: decimalPlaces (precision) must be captured.")

                # categoryLabel toggle
                cat_show = _get_prop("categoryLabels", "show")
                if cat_show is not None:
                    self._log("CL3", f"{prefix}.categoryLabel.show",
                              str(cat_show), str(jv_fmt.get("category_label_show", "")) or None,
                              "CARD: categoryLabel show/hide toggle must be captured.")

                # referenceLabels (secondary sub-metrics)
                ref_labels = objs.get("referenceLabels", objs.get("targets"))
                if ref_labels:
                    json_ref = jv_fmt.get("reference_labels", jv.get("reference_labels"))
                    self._log("CL3", f"{prefix}.referenceLabels.present",
                              f"{len(ref_labels)} reference label block(s)",
                              str(json_ref) if json_ref else None,
                              "CARD: referenceLabels (secondary sub-metric arrays with titles "
                              "and deltas) must be captured. Missing = target card shows "
                              "no comparison values.")

                # shapeType (new KPI cards)
                shape_t = _get_prop("shape", "shapeType") or _get_prop("cardLayout", "shapeType")
                if shape_t is not None:
                    self._log("CL3", f"{prefix}.shapeType",
                              str(shape_t), str(jv_fmt.get("shape_type", "")) or None,
                              "CARD: shapeType (Rectangle/RoundedRectangle/SnippedCorner) "
                              "must be captured for new-style KPI cards.")

                # cardPadding
                padding = _get_prop("cardLayout", "cardPadding") or _get_prop("general", "padding")
                if padding is not None:
                    self._log("CL3", f"{prefix}.cardPadding",
                              str(padding), str(jv_fmt.get("card_padding", "")) or None,
                              "CARD: cardPadding (inner gap between callout items) must be captured.")

    def check_dcl_slicer_controls(self):
        """
        CL-4  –  Slicer control properties not covered by D4/R5.
        Checks:
          - slicerType (VerticalList/Dropdown/Between/Tile/Slider)
          - selectionControls (SingleSelect, MultiSelectWithCtrl, ShowSelectAll)
          - slicerHeader (label visibility, text overrides, icons)
          - values (typography for slicer items)
          - sliderColor (active vs background track hex)
          - responsive toggle
        """
        print("[CL-4] Checking Slicer controls (slicerType, selectionControls, sliderColor)...")
        src_pages  = self.pbix.get("layout", {}).get("pages", [])
        json_viz   = self.json.get("visualizations", {})
        json_pages = json_viz.get("pages", [])
        json_pg_lk = {p.get("display_name", "").lower(): p for p in json_pages}

        for sp in src_pages:
            pname = sp.get("name", "")
            jp    = json_pg_lk.get(pname.lower(), {})
            json_vis_lk = {}
            for jv in jp.get("visuals", []):
                pos = jv.get("position", {})
                key = (jv.get("visual_type", ""),
                       round(pos.get("x", 0), 0),
                       round(pos.get("y", 0), 0))
                json_vis_lk[key] = jv

            for sv in sp.get("visuals", []):
                vtype = sv.get("visual_type", "")
                if vtype.lower() != "slicer":
                    continue
                vx     = round(sv.get("x", 0), 0)
                vy     = round(sv.get("y", 0), 0)
                config = sv.get("config", {})
                sv_cfg = config.get("singleVisual", {}) if isinstance(config, dict) else {}
                objs   = sv_cfg.get("objects", {})
                prefix = f"page[{pname}].slicer[{vtype}@{vx},{vy}]"
                jv     = json_vis_lk.get((vtype, vx, vy), {})
                jv_fmt = jv.get("slicer_settings", jv.get("formatting", {})) or {}

                def _prop(obj_key, prop_key):
                    block = (objs.get(obj_key, [{}]) or [{}])[0].get("properties", {})
                    val   = block.get(prop_key)
                    if isinstance(val, dict):
                        return val.get("expr", {}).get("Literal", {}).get("Value",
                               val.get("value", ""))
                    return val

                # slicerType (layout model)
                stype = _prop("general", "orientation") or _prop("data", "slicerType") or sv_cfg.get("slicerType")
                if stype is not None:
                    self._log("CL4", f"{prefix}.slicerType",
                              str(stype), str(jv_fmt.get("slicer_type", "")) or None,
                              "SLICER: slicerType (VerticalList/Dropdown/Between/Tile/Slider) "
                              "must be captured. Wrong type = completely different UX in target.")

                # SingleSelect
                single_sel = _prop("selection", "singleSelect")
                if single_sel is not None:
                    self._log("CL4", f"{prefix}.selectionControls.singleSelect",
                              str(single_sel), str(jv_fmt.get("single_select", "")) or None,
                              "SLICER: singleSelect enforcement must be captured.")

                # ShowSelectAll
                show_all = _prop("selection", "selectAllCheckboxEnabled") or _prop("selection", "showSelectAll")
                if show_all is not None:
                    self._log("CL4", f"{prefix}.selectionControls.showSelectAll",
                              str(show_all), str(jv_fmt.get("show_select_all", "")) or None,
                              "SLICER: showSelectAll toggle must be captured. "
                              "Visual Layer Checklist requires 'Select All' enabled.")

                # slicerHeader label / text override
                hdr_title = _prop("header", "title") or _prop("header", "show")
                if hdr_title is not None:
                    self._log("CL4", f"{prefix}.slicerHeader",
                              str(hdr_title)[:80], str(jv_fmt.get("slicer_header", "")) or None,
                              "SLICER: slicerHeader visibility and instructive label "
                              "(e.g. 'Select a Region') must be captured.")

                # sliderColor
                slider_clr = _prop("slider", "color") or _prop("sliderTrack", "fill")
                if slider_clr is not None:
                    self._log("CL4", f"{prefix}.sliderColor",
                              str(slider_clr)[:80], str(jv_fmt.get("slider_color", "")) or None,
                              "SLICER: sliderColor (active track vs background channel) "
                              "must be captured for range/between slicers.")

                # Responsive toggle
                responsive = _prop("general", "responsive")
                if responsive is not None:
                    self._log("CL4", f"{prefix}.responsive",
                              str(responsive), str(jv_fmt.get("responsive", "")) or None,
                              "SLICER: responsive toggle auto-sizes buttons on mobile layouts.")

    def check_dcl_axis_chart_detail(self):
        """
        CL-6  –  Chart axis and series detail not covered by D11.
        Checks per chart visual:
          - axisScale (Linear/Logarithmic/Continuous/Categorical)
          - axisBounds (Min/Max custom values)
          - axisTitles per axis
          - linesAndMarkers (line style, marker shape/size)
          - Series labels enabled on line charts
        """
        print("[CL-6] Checking chart axis detail (axisScale, axisBounds, axisTitles, linesAndMarkers)...")
        CHART_TYPES = {
            "lineChart", "areaChart", "stackedAreaChart",
            "hundredPercentStackedAreaChart",
            "clusteredBarChart", "stackedBarChart", "hundredPercentStackedBarChart",
            "clusteredColumnChart", "stackedColumnChart", "hundredPercentStackedColumnChart",
            "lineStackedColumnComboChart", "lineClusteredColumnComboChart",
            "scatterChart", "bubbleChart", "waterfallChart", "ribbonChart",
        }

        src_pages  = self.pbix.get("layout", {}).get("pages", [])
        json_viz   = self.json.get("visualizations", {})
        json_pages = json_viz.get("pages", [])
        json_pg_lk = {p.get("display_name", "").lower(): p for p in json_pages}

        for sp in src_pages:
            pname = sp.get("name", "")
            jp    = json_pg_lk.get(pname.lower(), {})
            json_vis_lk = {}
            for jv in jp.get("visuals", []):
                pos = jv.get("position", {})
                key = (jv.get("visual_type", ""),
                       round(pos.get("x", 0), 0),
                       round(pos.get("y", 0), 0))
                json_vis_lk[key] = jv

            for sv in sp.get("visuals", []):
                vtype = sv.get("visual_type", "")
                if not vtype or vtype not in CHART_TYPES:
                    continue
                vx     = round(sv.get("x", 0), 0)
                vy     = round(sv.get("y", 0), 0)
                config = sv.get("config", {})
                sv_cfg = config.get("singleVisual", {}) if isinstance(config, dict) else {}
                objs   = sv_cfg.get("objects", {})
                prefix = f"page[{pname}].visual[{vtype}@{vx},{vy}]"
                jv     = json_vis_lk.get((vtype, vx, vy), {})
                jv_fmt = jv.get("formatting", {}) or {}

                def _prop(obj_key, prop_key):
                    block = (objs.get(obj_key, [{}]) or [{}])[0].get("properties", {})
                    val   = block.get(prop_key)
                    if isinstance(val, dict):
                        return val.get("expr", {}).get("Literal", {}).get("Value",
                               val.get("value", ""))
                    return val

                for axis_key, axis_label in [("categoryAxis", "X-axis"), ("valueAxis", "Y-axis"),
                                              ("y2AxisReferenceLine", "Secondary Y-axis")]:
                    if axis_key not in objs:
                        continue

                    # axisScale
                    scale = _prop(axis_key, "axisScale") or _prop(axis_key, "type")
                    if scale is not None:
                        self._log("CL6", f"{prefix}.{axis_key}.axisScale",
                                  str(scale), str(jv_fmt.get(f"{axis_key}_scale", "")) or None,
                                  f"CHART {axis_label}: axisScale (Linear/Logarithmic/Continuous/"
                                  f"Categorical) must be captured. Wrong scale = misleading chart.")

                    # axisBounds (custom min/max)
                    for bound in ("start", "end"):
                        bval = _prop(axis_key, bound) or _prop(axis_key, f"axis{bound.capitalize()}")
                        if bval is not None:
                            self._log("CL6", f"{prefix}.{axis_key}.axisBound.{bound}",
                                      str(bval), str(jv_fmt.get(f"{axis_key}_bound_{bound}", "")) or None,
                                      f"CHART {axis_label}: custom {bound} bound must be captured. "
                                      f"Missing = axis auto-scales to data, hiding outlier context.")

                    # axisTitles
                    axis_title = _prop(axis_key, "titleText") or _prop(axis_key, "title")
                    if axis_title is not None:
                        self._log("CL6", f"{prefix}.{axis_key}.axisTitle",
                                  str(axis_title)[:80], str(jv_fmt.get(f"{axis_key}_title", "")) or None,
                                  f"CHART {axis_label}: axis title label must be captured.")

                # linesAndMarkers
                if "lineStyles" in objs or "markers" in objs:
                    line_style = _prop("lineStyles", "lineStyle") or _prop("lineStyles", "strokeWidth")
                    marker_shape = _prop("markers", "markerShape") or _prop("markers", "markerType")
                    if line_style is not None:
                        self._log("CL6", f"{prefix}.linesAndMarkers.lineStyle",
                                  str(line_style), str(jv_fmt.get("line_style", "")) or None,
                                  "CHART: line style (Solid/Dashed/Dotted) must be captured.")
                    if marker_shape is not None:
                        self._log("CL6", f"{prefix}.linesAndMarkers.markerShape",
                                  str(marker_shape), str(jv_fmt.get("marker_shape", "")) or None,
                                  "CHART: marker shape/size must be captured.")

                # Series labels on line charts
                if vtype in {"lineChart", "areaChart", "lineStackedColumnComboChart",
                             "lineClusteredColumnComboChart"}:
                    series_lbl = _prop("labels", "showSeriesLabel") or _prop("smallMultiple", "seriesLabels")
                    if series_lbl is not None:
                        self._log("CL6", f"{prefix}.seriesLabels",
                                  str(series_lbl), str(jv_fmt.get("series_labels", "")) or None,
                                  "LINE CHART: series labels enabled setting must be captured. "
                                  "When on, series labels replace the need for a legend.")

    def check_dcl_rich_text_narrative(self):
        """
        CL-9  –  Inline rich text and Smart Narrative elements.
        Checks:
          - paragraphs array in textbox visuals
          - textRuns (per-character font definitions)
          - dynamicValues (Smart Narrative DAX-mapped templates)
        """
        print("[CL-9] Checking rich text / Smart Narrative elements...")
        RICH_TYPES = {"textbox", "aiNarrative", "smartNarrative"}

        src_pages  = self.pbix.get("layout", {}).get("pages", [])
        json_viz   = self.json.get("visualizations", {})
        json_pages = json_viz.get("pages", [])
        json_pg_lk = {p.get("display_name", "").lower(): p for p in json_pages}

        for sp in src_pages:
            pname = sp.get("name", "")
            jp    = json_pg_lk.get(pname.lower(), {})
            json_vis_lk = {}
            for jv in jp.get("visuals", []):
                pos = jv.get("position", {})
                key = (jv.get("visual_type", ""),
                       round(pos.get("x", 0), 0),
                       round(pos.get("y", 0), 0))
                json_vis_lk[key] = jv

            for sv in sp.get("visuals", []):
                vtype = sv.get("visual_type", "")
                if not vtype or vtype not in RICH_TYPES:
                    continue
                vx     = round(sv.get("x", 0), 0)
                vy     = round(sv.get("y", 0), 0)
                config = sv.get("config", {})
                sv_cfg = config.get("singleVisual", {}) if isinstance(config, dict) else {}
                objs   = sv_cfg.get("objects", {})
                prefix = f"page[{pname}].visual[{vtype}@{vx},{vy}]"
                jv     = json_vis_lk.get((vtype, vx, vy), {})

                # paragraphs / textRuns (textbox)
                para_block = (objs.get("general", [{}]) or [{}])[0].get("properties", {}).get("paragraphs")
                if para_block is None:
                    para_block = sv_cfg.get("paragraphs") or sv_cfg.get("prototypeQuery", {}).get("paragraphs")
                if para_block is not None:
                    json_paras = jv.get("paragraphs", jv.get("rich_text"))
                    self._log("CL9", f"{prefix}.paragraphs",
                              f"{len(para_block) if isinstance(para_block, list) else 'present'}",
                              str(json_paras) if json_paras else None,
                              "RICH TEXT: paragraphs array (multi-font text blocks) must be "
                              "captured for textbox visuals. Missing = target textbox shows "
                              "plain unstyled text.")

                # dynamicValues (Smart Narrative)
                if vtype in {"aiNarrative", "smartNarrative"}:
                    dyn_vals = (objs.get("insights", [{}]) or [{}])[0].get("properties", {}).get("dynamicValues")
                    if dyn_vals is None:
                        dyn_vals = sv_cfg.get("dynamicValues") or sv_cfg.get("insights")
                    if dyn_vals is not None:
                        json_dyn = jv.get("dynamic_values", jv.get("smart_narrative_values"))
                        self._log("CL9", f"{prefix}.dynamicValues",
                                  f"{len(dyn_vals) if isinstance(dyn_vals, list) else 'present'}",
                                  str(json_dyn) if json_dyn else None,
                                  "SMART NARRATIVE: dynamicValues (DAX-mapped inline templates) "
                                  "must be captured. Missing = auto-generated narrative loses "
                                  "all data-driven number callouts.")

    def check_dcl_visual_styles_token(self):
        """
        CL-10  –  visualStyles override document in theme.
        Checks that visualStyles (per-visual-type default config) captured in JSON.
        Source: theme.json / report config visualStyles block
        JSON:   theme_details.visualStyles
        """
        print("[CL-10] Checking visualStyles override document...")
        json_theme = (self.json.get("theme_details") or
                      self.json.get("report_theme") or {})
        vs = json_theme.get("visualStyles")
        src_layout = self.pbix.get("layout", {})
        src_theme  = src_layout.get("theme_raw", {})
        if not src_theme:
            # Try from PBIP theme
            src_theme = self.pbix.get("pbip_report_files", {}).get("theme", {})
        src_vs = src_theme.get("visualStyles") if isinstance(src_theme, dict) else None

        if src_vs:
            self._log("CL10", "theme.visualStyles",
                      f"{len(src_vs)} type override(s)" if isinstance(src_vs, dict) else "present",
                      f"{len(vs)} type override(s)" if isinstance(vs, dict) else (str(vs) if vs else None),
                      "THEME: visualStyles overriding document (per-visual-type defaults) "
                      "must be captured. Missing = target visuals ignore custom default "
                      "formatting defined in the corporate theme.")
        else:
            self.results.append(CheckResult(
                check_id="CL10", attribute="theme.visualStyles",
                status="PASS", source_value="not-configured",
                json_value="not-configured",
                note="No visualStyles overrides in source theme — N/A"))

    def check_dcl_analytics_overlays(self):
        """
        CL-11  –  Analytics engine overlays (entire section missing from D1-D14).
        Checks per chart visual:
          - referenceLineType (Constant/Trend/Average/Median/Min/Max)
          - forecastPoints (projection step limits)
          - confidenceInterval (95%/99%)
        Source: singleVisual.objects analyticsPane / referenceLine / forecast
        JSON:   visualizations.pages[n].visuals[n].analytics
        """
        print("[CL-11] Checking Analytics Engine Overlays (reference lines, forecast)...")
        ANALYTICS_TYPES = {
            "lineChart", "areaChart", "stackedAreaChart",
            "clusteredBarChart", "stackedBarChart",
            "clusteredColumnChart", "stackedColumnChart",
            "scatterChart", "bubbleChart",
            "lineStackedColumnComboChart", "lineClusteredColumnComboChart",
        }

        src_pages  = self.pbix.get("layout", {}).get("pages", [])
        json_viz   = self.json.get("visualizations", {})
        json_pages = json_viz.get("pages", [])
        json_pg_lk = {p.get("display_name", "").lower(): p for p in json_pages}

        for sp in src_pages:
            pname = sp.get("name", "")
            jp    = json_pg_lk.get(pname.lower(), {})
            json_vis_lk = {}
            for jv in jp.get("visuals", []):
                pos = jv.get("position", {})
                key = (jv.get("visual_type", ""),
                       round(pos.get("x", 0), 0),
                       round(pos.get("y", 0), 0))
                json_vis_lk[key] = jv

            for sv in sp.get("visuals", []):
                vtype = sv.get("visual_type", "")
                if not vtype or vtype not in ANALYTICS_TYPES:
                    continue
                vx     = round(sv.get("x", 0), 0)
                vy     = round(sv.get("y", 0), 0)
                config = sv.get("config", {})
                sv_cfg = config.get("singleVisual", {}) if isinstance(config, dict) else {}
                objs   = sv_cfg.get("objects", {})
                prefix = f"page[{pname}].visual[{vtype}@{vx},{vy}]"
                jv     = json_vis_lk.get((vtype, vx, vy), {})
                jv_analytics = jv.get("analytics", jv.get("analytics_overlays", {})) or {}

                # Reference lines
                ref_lines = objs.get("referenceLine", objs.get("xAxisReferenceLine",
                            objs.get("y1AxisReferenceLine", []))) or []
                if ref_lines:
                    src_line_types = []
                    for rl in (ref_lines if isinstance(ref_lines, list) else [ref_lines]):
                        props = rl.get("properties", {}) if isinstance(rl, dict) else {}
                        lt = props.get("type", {})
                        if isinstance(lt, dict):
                            lt = lt.get("expr", {}).get("Literal", {}).get("Value", str(lt))
                        if lt:
                            src_line_types.append(str(lt))
                    if src_line_types:
                        json_ref = jv_analytics.get("reference_lines", jv_analytics.get("referenceLines"))
                        self._log("CL11", f"{prefix}.referenceLines",
                                  ",".join(src_line_types),
                                  str(json_ref) if json_ref else None,
                                  "ANALYTICS: referenceLineType (Constant/Trend/Average/Median/"
                                  "Min/Max) must be captured. Missing = target chart has no "
                                  "analytical overlay lines, hiding statistical context.")

                # Forecast
                forecast = objs.get("forecast", [])
                if forecast:
                    props = (forecast[0].get("properties", {}) if isinstance(forecast, list)
                             and forecast else {})
                    pts = props.get("forecastLength", {})
                    if isinstance(pts, dict):
                        pts = pts.get("expr", {}).get("Literal", {}).get("Value", "")
                    conf = props.get("confidenceLevel", props.get("confidenceInterval", {}))
                    if isinstance(conf, dict):
                        conf = conf.get("expr", {}).get("Literal", {}).get("Value", "")

                    json_fc = jv_analytics.get("forecast", jv_analytics.get("forecasting", {}))
                    self._log("CL11", f"{prefix}.forecast.forecastPoints",
                              str(pts) if pts else "configured",
                              str(json_fc.get("forecast_points", "") if isinstance(json_fc, dict) else json_fc) or None,
                              "ANALYTICS: forecastPoints (projection steps) must be captured. "
                              "Missing = target chart has no forecast line.")
                    if conf:
                        self._log("CL11", f"{prefix}.forecast.confidenceInterval",
                                  str(conf),
                                  str(json_fc.get("confidence_interval", "") if isinstance(json_fc, dict) else "") or None,
                                  "ANALYTICS: confidenceInterval (95%/99%) must be captured. "
                                  "Missing = forecast uncertainty band is lost.")

    def check_dcl_visual_type_specific(self):
        """
        CL-VTS  –  Visual-type-specific checklist items from the bottom of the document.
        Covers:
          - Dual-axis / Combo: secondary Y toggle, axis alignment, axis titles, legend distinctions
          - AI Visuals (Decomposition Tree, Key Influencers, Smart Narrative, Q&A)
          - Advanced Mapping (Shape Map, Azure Map)
          - Custom/Developer Visuals (R/Python row limit, static fallback)
          - KPI Visuals (Trend Axis conflict)
          - Gauges (static max/target)
          - Treemaps (max visible categories)
          - Cards: blank value coalescing
          - Maps: map style, data category
        """
        print("[CL-VTS] Checking visual-type-specific checklist items...")
        src_pages  = self.pbix.get("layout", {}).get("pages", [])
        json_viz   = self.json.get("visualizations", {})
        json_pages = json_viz.get("pages", [])
        json_pg_lk = {p.get("display_name", "").lower(): p for p in json_pages}

        for sp in src_pages:
            pname = sp.get("name", "")
            jp    = json_pg_lk.get(pname.lower(), {})
            json_vis_lk = {}
            for jv in jp.get("visuals", []):
                pos = jv.get("position", {})
                key = (jv.get("visual_type", ""),
                       round(pos.get("x", 0), 0),
                       round(pos.get("y", 0), 0))
                json_vis_lk[key] = jv

            for sv in sp.get("visuals", []):
                vtype  = sv.get("visual_type", "")
                if not vtype:
                    continue
                vx     = round(sv.get("x", 0), 0)
                vy     = round(sv.get("y", 0), 0)
                config = sv.get("config", {})
                sv_cfg = config.get("singleVisual", {}) if isinstance(config, dict) else {}
                objs   = sv_cfg.get("objects", {})
                vc_obj = config.get("vcObjects", {}) if isinstance(config, dict) else {}
                prefix = f"page[{pname}].visual[{vtype}@{vx},{vy}]"
                jv     = json_vis_lk.get((vtype, vx, vy), {})
                jv_fmt = jv.get("formatting", {}) or {}
                jv_vts = jv.get("visual_type_config", {}) or {}

                def _prop(obj_key, prop_key):
                    block = (objs.get(obj_key, [{}]) or [{}])[0].get("properties", {})
                    val   = block.get(prop_key)
                    if isinstance(val, dict):
                        return val.get("expr", {}).get("Literal", {}).get("Value",
                               val.get("value", ""))
                    return val

                # ── Dual-Axis / Combo ───────────────────────────────────
                if vtype in {"lineStackedColumnComboChart", "lineClusteredColumnComboChart"}:
                    # Secondary Y-axis toggle
                    y2_show = _prop("y2AxisReferenceLine", "show") or _prop("valueAxis", "secShow")
                    if y2_show is not None:
                        self._log("CLVTS", f"{prefix}.secondaryYAxis.enabled",
                                  str(y2_show), str(jv_vts.get("secondary_y_axis_enabled", "")) or None,
                                  "COMBO CHART: secondary Y-axis toggle must be captured and "
                                  "formatted. Missing = dual-axis context lost in target.")
                    # Axis titles uniqueness (flag if both axes are set)
                    y1_title = _prop("valueAxis", "titleText")
                    y2_title = _prop("valueAxis", "secTitleText") or _prop("y2AxisReferenceLine", "titleText")
                    if y1_title and y2_title:
                        if str(y1_title).lower() == str(y2_title).lower():
                            self.results.append(CheckResult(
                                check_id="CLVTS",
                                attribute=f"{prefix}.dualAxisTitles.uniqueness",
                                status="FAIL",
                                source_value=f"both axes titled: '{y1_title}'",
                                json_value="titles must be unique",
                                note="COMBO CHART: both Y-axes have identical titles. "
                                     "Visual Layer Checklist requires unique, descriptive "
                                     "labels on both axes to prevent metric confusion."))
                    # Data label background cards on line labels (over columns)
                    lbl_bg = _prop("labels", "enableBackground") or _prop("labels", "labelBackground")
                    if lbl_bg is not None:
                        self._log("CLVTS", f"{prefix}.lineDataLabelBackground",
                                  str(lbl_bg), str(jv_vts.get("line_label_background", "")) or None,
                                  "COMBO CHART: background cards on line data labels keep "
                                  "values legible when crossing over column bars.")

                # ── AI Visuals ──────────────────────────────────────────
                if vtype == "decompositionTree":
                    ai_splits = _prop("general", "enableAISplits") or _prop("general", "aiSplits")
                    self._log("CLVTS", f"{prefix}.decompositionTree.enableAISplits",
                              str(ai_splits) if ai_splits is not None else "not-configured",
                              str(jv_vts.get("enable_ai_splits", "")) or None,
                              "DECOMPOSITION TREE: 'Enable AI Splits' setting must be "
                              "captured. Allows users to auto-find high/low values.")

                if vtype == "keyInfluencers":
                    # Check analysis fields are present in JSON (no raw IDs)
                    fields = jv.get("fields", [])
                    raw_id_fields = [f for f in fields
                                     if isinstance(f, dict) and
                                     re.match(r"^[a-f0-9\-]{30,}$",
                                              str(f.get("query_ref", "")), re.IGNORECASE)]
                    if raw_id_fields:
                        self.results.append(CheckResult(
                            check_id="CLVTS",
                            attribute=f"{prefix}.keyInfluencers.rawFieldIds",
                            status="FAIL",
                            source_value=f"{len(raw_id_fields)} raw ID field(s) detected",
                            json_value="human-readable names required",
                            note="KEY INFLUENCERS: raw unformatted ID fields detected. "
                                 "Visual Layer Checklist requires analysis fields to use "
                                 "clean, readable names — not internal GUIDs."))

                if vtype == "qnaVisual":
                    suggested_q = _prop("general", "question") or sv_cfg.get("defaultQuestion")
                    self._log("CLVTS", f"{prefix}.qnaVisual.suggestedQuestion",
                              str(suggested_q) if suggested_q else "not-configured",
                              str(jv_vts.get("suggested_question", "")) or None,
                              "Q&A VISUAL: pre-populated suggested questions must be captured. "
                              "Business-user definitions are critical for adoption.")

                # ── Advanced Mapping ────────────────────────────────────
                if vtype == "shapeMap":
                    map_key = _prop("map", "geoJson") or _prop("shape", "mapType")
                    self._log("CLVTS", f"{prefix}.shapeMap.topoJsonKey",
                              str(map_key) if map_key else "not-configured",
                              str(jv_vts.get("topojson_key", "")) or None,
                              "SHAPE MAP: ISO codes / region keys must match the custom "
                              "TopoJSON exactly. Mismatch = regions not plotted.")

                if vtype == "azureMap":
                    zoom_lvl = _prop("mapSettings", "zoom") or _prop("general", "zoomLevel")
                    pitch    = _prop("mapSettings", "pitch")
                    terrain  = _prop("mapSettings", "terrain3D")
                    if zoom_lvl is not None:
                        self._log("CLVTS", f"{prefix}.azureMap.zoomLevel",
                                  str(zoom_lvl), str(jv_vts.get("zoom_level", "")) or None,
                                  "AZURE MAP: zoom level must be captured for consistent "
                                  "initial view in target.")
                    if pitch is not None:
                        self._log("CLVTS", f"{prefix}.azureMap.pitch",
                                  str(pitch), str(jv_vts.get("pitch", "")) or None,
                                  "AZURE MAP: pitch boundary must be captured.")
                    if terrain is not None:
                        self._log("CLVTS", f"{prefix}.azureMap.terrain3D",
                                  str(terrain), str(jv_vts.get("terrain_3d", "")) or None,
                                  "AZURE MAP: 3D terrain toggle must be captured.")
                    # Fixed legend bins (vs continuous scale)
                    legend_type = _prop("legend", "legendType") or _prop("categoryColors", "legendType")
                    if legend_type is not None:
                        self._log("CLVTS", f"{prefix}.azureMap.legendRangeBins",
                                  str(legend_type), str(jv_vts.get("legend_range_bins", "")) or None,
                                  "AZURE MAP: fixed color bins vs continuous scale must be captured.")

                # ── Map (Filled/Bubble) ─────────────────────────────────
                if vtype in {"map", "filledMap"}:
                    map_style = _prop("mapStyles", "mapTheme") or _prop("general", "mapStyle")
                    if map_style is not None:
                        self._log("CLVTS", f"{prefix}.map.style",
                                  str(map_style), str(jv_vts.get("map_style", "")) or None,
                                  "MAP: map style (e.g. grayscale) must be captured. "
                                  "Grayscale reduces visual noise and improves data visibility.")

                # ── R/Python visuals ────────────────────────────────────
                if vtype in {"scriptVisual", "pythonVisual", "rVisual"}:
                    script_src = sv_cfg.get("script") or sv_cfg.get("scriptSourceCode", "")
                    row_limit_note = None
                    if isinstance(script_src, str) and len(script_src) > 0:
                        row_limit_note = ("R/PYTHON VISUAL: script-based visuals are limited to "
                                          "150k rows in Power BI Service. JSON must flag this "
                                          "and capture the row count estimate. "
                                          "Missing = potential rendering failure in Service.")
                    json_script = jv.get("script_source", jv.get("r_python_script"))
                    self._log("CLVTS", f"{prefix}.rPythonVisual.scriptPresent",
                              "script-configured" if script_src else "not-configured",
                              str(json_script) if json_script else None,
                              row_limit_note or
                              "R/PYTHON VISUAL: script must be captured in JSON "
                              "for forward engineering.")

                    # Static fallback textbox
                    page_fallbacks = [v2 for v2 in sp.get("visuals", [])
                                      if v2.get("visual_type", "") == "textbox"
                                      and abs(v2.get("x", 0) - sv.get("x", 0)) < 10
                                      and abs(v2.get("y", 0) - sv.get("y", 0)) < 10]
                    self.results.append(CheckResult(
                        check_id="CLVTS",
                        attribute=f"{prefix}.rPythonVisual.staticFallback",
                        status="PASS" if page_fallbacks else "MISSING",
                        source_value="fallback-textbox-present" if page_fallbacks else "no-fallback",
                        json_value=None,
                        note="R/PYTHON VISUAL: Visual Layer Checklist requires a static "
                             "fallback textbox warning at the same position in case the "
                             "developer script fails to render. No co-located textbox found."))

                # ── KPI Gauge ───────────────────────────────────────────
                if vtype == "gauge":
                    max_val = _prop("gauge", "max") or _prop("scale", "max")
                    target  = _prop("targets", "value") or _prop("gauge", "target")
                    if max_val is not None:
                        self._log("CLVTS", f"{prefix}.gauge.staticMax",
                                  str(max_val), str(jv_vts.get("gauge_max", "")) or None,
                                  "GAUGE: explicit static maximum must be captured (via DAX, "
                                  "not auto-scale). Auto-scale distorts the percentage shown.")
                    if target is not None:
                        self._log("CLVTS", f"{prefix}.gauge.targetValue",
                                  str(target), str(jv_vts.get("gauge_target", "")) or None,
                                  "GAUGE: target/destination value (DAX measure) must be captured.")

                # ── KPI Visual (trend axis) ─────────────────────────────
                if vtype in {"kpiVisual", "kpi"}:
                    trend_axis = _prop("trendLine", "show") or _prop("indicator", "trendlineType")
                    if trend_axis is not None:
                        self._log("CLVTS", f"{prefix}.kpiVisual.trendAxisToggle",
                                  str(trend_axis), str(jv_vts.get("trend_axis", "")) or None,
                                  "KPI VISUAL: Trend Axis toggle must be captured. "
                                  "If it conflicts with background layout text it should "
                                  "be turned off explicitly.")

                # ── Treemap ─────────────────────────────────────────────
                if vtype == "treemap":
                    max_cats = _prop("dataPoint", "maxCategories") or _prop("labels", "maxVisibleCategories")
                    if max_cats is not None:
                        self._log("CLVTS", f"{prefix}.treemap.maxCategories",
                                  str(max_cats), str(jv_vts.get("max_categories", "")) or None,
                                  "TREEMAP: maximum visible categorical blocks must be captured. "
                                  "Visual Layer Checklist requires limiting this to keep text readable.")

                # ── Card – blank value coalescing ───────────────────────
                if vtype in {"card", "singleRowCard", "multiRowCard", "newCard"}:
                    # Check if the bound measure has a blank-handling pattern
                    fields = sv.get("fields", [])
                    measures_src = self.pbix.get("data_model", {}).get("tables", [])
                    for fld in fields:
                        qref = fld.get("query_ref", "")
                        if not qref or "." not in qref:
                            continue
                        measure_part = qref.split(".")[-1].strip().lower()
                        for tbl in measures_src:
                            for meas in tbl.get("measures", []):
                                if meas.get("name", "").lower() == measure_part:
                                    expr = str(meas.get("expression", ""))
                                    has_coalesce = any(fn in expr.upper()
                                                       for fn in ("IF(ISBLANK", "COALESCE",
                                                                  "IFERROR", "IF(ISERROR"))
                                    if not has_coalesce:
                                        self.results.append(CheckResult(
                                            check_id="CLVTS",
                                            attribute=f"{prefix}.card.blankCoalescing[{qref}]",
                                            status="MISSING",
                                            source_value=f"measure '{meas.get('name','')}' has no blank guard",
                                            json_value=None,
                                            note="CARD: Visual Layer Checklist requires blank values "
                                                 "to be coalesced to '0' or 'No Data' in DAX. "
                                                 "This measure lacks IF(ISBLANK/COALESCE/IFERROR. "
                                                 "Add a blank-guard expression to prevent empty cards."))

    def run_all(self) -> list[CheckResult]:
        self.check_d1_connections()
        self.check_d2_tables()
        self.check_d3_fields()
        self.check_d4_filters()
        self.check_d5_measures_relationships()
        self.check_d6_visuals()
        self.check_d7_display_names()
        self.check_d8_conditional_formatting()
        self.check_d9_tooltips()
        self.check_d10_interactions_navigation()
        self.check_d11_visual_formatting()
        self.check_d12_external()
        self.check_d13_model_metadata()    # model.tmdl, perspectives, cultures, diagramLayout, expressions
        self.check_d14_pbip_report_layer() # report.pbir, report.json, page.json, visual.json, StaticResources
        # -- New checks from S9/S12/S13/S15/S16/R15 --
        self.check_d2_rls_ols()            # S9  RLS roles + S12 OLS column permissions
        self.check_d2_what_if_parameters() # S13 What-If Parameters (GENERATESERIES)
        self.check_d2_incremental_refresh()# S15 Incremental Refresh policy
        self.check_d5_dynamic_rls()        # S16 Dynamic RLS detection (USERNAME/UPN in DAX)
        self.check_d6_images_logos()       # R15 StaticResources image files + imageUrl refs
        # -- Checklist extended checks (CL series) --
        self.check_dcl_canvas_environment()      # CL-1  canvas env, filter pane
        self.check_dcl_alt_text_header_icons()   # CL-2  altText, headerIcons, subtitle
        self.check_dcl_card_formatting()         # CL-3  card displayUnits, decimalPlaces, etc.
        self.check_dcl_slicer_controls()         # CL-4  slicerType, selectionControls, etc.
        self.check_dcl_axis_chart_detail()       # CL-6  axisScale, axisBounds, axisTitles, lines
        self.check_dcl_rich_text_narrative()     # CL-9  paragraphs, textRuns, dynamicValues
        self.check_dcl_visual_styles_token()     # CL-10 visualStyles override document
        self.check_dcl_analytics_overlays()      # CL-11 referenceLines, forecast, confidence
        self.check_dcl_visual_type_specific()    # CL-VTS visual-type-specific checklist
        return self.results

    # ══════════════════════════════════════════════════════════════
    # S9  --  RLS Roles & OLS  (D2-RLS)
    # S12 --  OLS Column Permissions (D2-OLS)
    # ══════════════════════════════════════════════════════════════

    def check_d2_rls_ols(self):
        """
        S9  -- RLS Roles and OLS.
        Source: SecurityBindings (PBIX) or roles.tmdl (PBIP), parsed into
                pbix_data['rls_roles'] list of {name, model_permission, table_permissions[]}.
        JSON:   json['rls'] or json['roles'] or json['security'] root-level key.
        Checks:
          - Role names present in JSON
          - modelPermission per role
          - RLS DAX filter expression per table per role
          - OLS column permissions (columnPermissions) per column per role  (S12)
        """
        print("[D2-RLS] Checking RLS roles and OLS column permissions...")
        # Primary source: pbix_data["rls_roles"] (set from BIM in main() when --bim supplied)
        # Fallback: data_model["rls_roles"] (parsed directly from model.roles[] in _parse_bim)
        src_roles = (self.pbix.get("rls_roles") or
                     self.pbix.get("data_model", {}).get("rls_roles", []))
        # JSON may store under 'rls', 'roles', or 'security'
        # If none of these keys exist, json_roles is [] and every
        # role will correctly surface as MISSING in the report.
        json_roles = (self.json.get("rls") or
                      self.json.get("roles") or
                      self.json.get("security", {}).get("roles", []) or
                      self.json.get("consolidated_model", {}).get("rls", []) or
                      self.json.get("consolidated_model", {}).get("roles", []) or [])
        json_role_lkp = {r.get("name","").lower(): r for r in json_roles}

        if not json_roles:
            print(f"     [D2-RLS] WARNING: JSON has no 'rls', 'roles', or 'security.roles' key. "
                  f"All {len(src_roles)} role(s) will be reported as MISSING. "
                  f"RE/OP extractor must add RLS roles to the JSON output.")

        if not src_roles:
            self.results.append(CheckResult(
                check_id="D2", attribute="rls_roles.present",
                status="PASS", source_value="no_roles_defined",
                json_value="no_roles_defined",
                note="No RLS roles defined in this model  --  skip"
            ))
            return

        for sr in src_roles:
            rname  = sr.get("name","")
            jr     = json_role_lkp.get(rname.lower(), {})
            prefix = f"rls_role[{rname}]"

            self._log("D2", f"{prefix}.name",
                      rname, jr.get("name") or None,
                      "RLS ROLE: role name must exist in JSON. "
                      "RE/OP must extract roles from SecurityBindings (PBIX) "
                      "or roles.tmdl (PBIP). Missing role = users not restricted "
                      "by row-level security in target model.")

            self._log("D2", f"{prefix}.model_permission",
                      sr.get("model_permission",""),
                      jr.get("model_permission","") or jr.get("modelPermission","") or None,
                      "RLS ROLE: modelPermission (Read/ReadRefresh/etc.) must be captured.")

            # Per-table RLS filter expressions
            src_tps  = sr.get("table_permissions", [])
            json_tps = jr.get("table_permissions", jr.get("tablePermissions", []))
            json_tp_lkp = {tp.get("table","").lower(): tp for tp in json_tps}

            for stp in src_tps:
                tname     = stp.get("table","")
                jtp       = json_tp_lkp.get(tname.lower(), {})
                src_filter= stp.get("filter_dax","") or stp.get("filterExpression","")
                json_filter=jtp.get("filter_dax","") or jtp.get("filterExpression","") or \
                             jtp.get("filter_expression","") or ""

                self._log("D2", f"{prefix}.table[{tname}].rls_filter",
                          src_filter.strip()[:120] if src_filter else None,
                          json_filter.strip()[:120] if json_filter else None,
                          f"RLS FILTER: DAX row filter expression for table '{tname}' "
                          "in this role must be captured exactly. "
                          "Missing = all rows visible to users in this role.")

            # -- S12 OLS column permissions -------------------------
            # BIM roles[].tablePermissions[].columnPermissions[]
            # { column: "ColName", metadataPermission: "none|read|default" }
            src_col_perms = sr.get("column_permissions", [])
            if src_col_perms:
                json_col_perms = jr.get("column_permissions",
                                        jr.get("columnPermissions", []))
                json_cp_lkp = {
                    f"{cp.get('table','')}.{cp.get('column','')}".lower(): cp
                    for cp in json_col_perms
                }
                for scp in src_col_perms:
                    col_key = f"{scp.get('table','')}.{scp.get('column','')}".lower()
                    jcp     = json_cp_lkp.get(col_key, {})
                    self._log("D2", f"{prefix}.ols[{col_key}].permission",
                              scp.get("metadataPermission","none"),
                              jcp.get("metadataPermission","") or jcp.get("permission","") or None,
                              "OLS COLUMN PERMISSION: column-level permission "
                              "(none/read/default) must be captured for each column "
                              "in each role. none=column hidden from role users. "
                              "RE/OP must extract columnPermissions from roles in model.bim.")

    # ══════════════════════════════════════════════════════════════
    # S13 --  What-If Parameters  (D2-WHATIF)
    # GENERATESERIES-based parameter tables distinct from Field Parameters
    # ══════════════════════════════════════════════════════════════

    def check_d2_what_if_parameters(self):
        """
        S13  --  What-If Parameters.
        These are calculated tables built with GENERATESERIES(min, max, increment).
        Power BI creates them via Modeling → New Parameter (What-if).
        They are different from Field Parameter tables (NAMEOF-based, S14)
        and from M Query Parameters (Manage Parameters, S11/D3-MQP).
        Source: model.bim tables[] where partition source is DAX containing GENERATESERIES
        JSON:   json['parameters'] (same key as M Query Params but distinct type)
                or json['what_if_parameters']
        """
        print("[D2-WHATIF] Checking What-If Parameters (GENERATESERIES)...")
        import re as _re_wi
        src_tables = self.pbix.get("data_model", {}).get("tables", [])
        json_whatif = (self.json.get("what_if_parameters") or
                       [p for p in (self.json.get("parameters") or [])
                        if (p.get("kind","") or "").lower() in ("whatif","what_if","generateseries")])
        json_wi_lkp = {p.get("name","").lower(): p for p in json_whatif}

        gs_pattern = _re_wi.compile(r"GENERATESERIES\s*\(", _re_wi.IGNORECASE)
        found_any  = False

        for st in src_tables:
            if self._is_system_table(st.get("name","")):
                continue
            for p in st.get("partitions", []):
                src = p.get("source", {})
                if isinstance(src, dict):
                    src_expr = src.get("expression","")
                else:
                    src_expr = str(src or "")
                if isinstance(src_expr, list): src_expr = "\n".join(src_expr)
                if gs_pattern.search(src_expr or ""):
                    found_any = True
                    tname  = st.get("name","")
                    jw     = json_wi_lkp.get(tname.lower(), {})
                    prefix = f"what_if_parameter[{tname}]"

                    self._log("D2", f"{prefix}.name",
                              tname, jw.get("name") or None,
                              "WHAT-IF PARAMETER: GENERATESERIES table must be captured "
                              "in JSON. RE/OP must detect tables whose DAX expression "
                              "contains GENERATESERIES and flag them as What-If parameters. "
                              "Missing = parameter slider cannot be recreated in target.")

                    # Extract min/max/increment from GENERATESERIES call
                    m = _re_wi.search(
                        r"GENERATESERIES\s*\(\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^)]+)\s*\)",
                        src_expr, _re_wi.IGNORECASE
                    )
                    if m:
                        src_min = m.group(1).strip()
                        src_max = m.group(2).strip()
                        src_inc = m.group(3).strip()
                        self._log("D2", f"{prefix}.min_value",
                                  src_min, jw.get("min_value","") or jw.get("minimum","") or None,
                                  "What-If min value must be captured")
                        self._log("D2", f"{prefix}.max_value",
                                  src_max, jw.get("max_value","") or jw.get("maximum","") or None,
                                  "What-If max value must be captured")
                        self._log("D2", f"{prefix}.increment",
                                  src_inc, jw.get("increment","") or jw.get("step","") or None,
                                  "What-If increment must be captured")

        if not found_any:
            self.results.append(CheckResult(
                check_id="D2", attribute="what_if_parameters.present",
                status="PASS", source_value="none_found",
                json_value="none_found",
                note="No GENERATESERIES What-If parameters found in this model  --  N/A"
            ))

    # ══════════════════════════════════════════════════════════════
    # S15 --  Incremental Refresh Policy  (D2-INCR)
    # ══════════════════════════════════════════════════════════════

    def check_d2_incremental_refresh(self):
        """
        S15  --  Incremental Refresh Policy.
        BIM stores incremental refresh policy under tables[].refreshPolicy.
        Keys: incrementGranularity, rangeGranularity, rollingWindowGranularity,
              pollingExpression, mode.
        JSON: json['tables'][n]['incremental_refresh'] or
              json['incremental_refresh_policies']
        """
        print("[D2-INCR] Checking Incremental Refresh policies...")
        src_tables = self.pbix.get("data_model", {}).get("tables", [])
        json_tables= self.json.get("tables", [])
        json_tbl_lkp = {t.get("name","").lower(): t for t in json_tables}
        found_any = False

        # BIM tables may have refreshPolicy embedded
        # We detect by checking for presence in the raw BIM (stored in annotations or direct key)
        for st in src_tables:
            tname = st.get("name","")
            if self._is_system_table(tname):
                continue
            # refreshPolicy is a BIM-level key not always parsed by _parse_bim
            # Check annotations for incremental refresh metadata
            refresh_policy = st.get("refreshPolicy", {}) or st.get("refresh_policy", {})
            if not refresh_policy:
                # Also check annotations for RefreshPolicyAnnotation
                for ann in st.get("annotations", []):
                    if "refreshpolicy" in ann.get("name","").lower():
                        refresh_policy = {"present": True, "annotation": ann.get("value","")}
            if not refresh_policy:
                continue

            found_any = True
            jt     = json_tbl_lkp.get(tname.lower(), {})
            json_rp= jt.get("incremental_refresh", {}) or jt.get("refresh_policy", {})
            prefix = f"table[{tname}].incremental_refresh"

            self._log("D2", f"{prefix}.present",
                      True, bool(json_rp) or None,
                      "INCREMENTAL REFRESH: table has a refresh policy in BIM. "
                      "RE/OP must capture incremental_refresh config. "
                      "Missing = target table will do full refresh instead of incremental.")

            for key in ("incrementGranularity","rangeGranularity",
                        "rollingWindowGranularity","pollingExpression","mode"):
                src_val  = refresh_policy.get(key,"") or refresh_policy.get(
                    key[0].lower()+key[1:],"")
                json_val = json_rp.get(key,"") or json_rp.get(
                    key[0].lower()+key[1:],"") if json_rp else None
                if src_val:
                    self._log("D2", f"{prefix}.{key}",
                              str(src_val), str(json_val) if json_val else None,
                              f"Incremental refresh {key} must be captured in JSON.")

        if not found_any:
            self.results.append(CheckResult(
                check_id="D2", attribute="incremental_refresh.present",
                status="PASS", source_value="none_configured",
                json_value="none_configured",
                note="No incremental refresh policies found in this model  --  N/A"
            ))

    # ══════════════════════════════════════════════════════════════
    # S16 --  Dynamic RLS Detection  (D5-DYNRLS)
    # ══════════════════════════════════════════════════════════════

    def check_d5_dynamic_rls(self):
        """
        S16  --  Dynamic RLS Detection.
        Scans measure DAX expressions AND RLS filter expressions for
        USERNAME(), USERPRINCIPALNAME(), USERDOMAIN() calls.
        These require AAD/Entra group setup in the target workspace.
        This is a FLAG check, not a PASS/FAIL against JSON values.
        Every instance found is reported as INFO in the gap report
        with a note to the deployment team.
        """
        import re as _re_drls
        print("[D5-DYNRLS] Scanning for dynamic RLS patterns (USERNAME/UPN/USERDOMAIN)...")
        dyn_funcs = ["USERNAME()", "USERPRINCIPALNAME()", "USERDOMAIN()",
                     "CUSTOMDATA()", "USEROBJECTID()"]
        dyn_pattern = _re_drls.compile(
            r"\b(USERNAME|USERPRINCIPALNAME|USERDOMAIN|CUSTOMDATA|USEROBJECTID)\s*\(\s*\)",
            _re_drls.IGNORECASE
        )
        found_any = False

        # Scan measures
        for st in self.pbix.get("data_model", {}).get("tables", []):
            if self._is_system_table(st.get("name","")): continue
            for sm in st.get("measures", []):
                expr = sm.get("expression","")
                if isinstance(expr, list): expr = "\n".join(expr)
                hits = dyn_pattern.findall(expr or "")
                if hits:
                    found_any = True
                    for fn in set(hits):
                        self.results.append(CheckResult(
                            check_id="D5",
                            attribute=f"dynamic_rls[{st.get('name','')}.{sm.get('name','')}].{fn.upper()}()",
                            status="PASS",   # It's a FLAG not an error
                            source_value=f"{fn.upper()}() found in measure DAX",
                            json_value=None,
                            note=(
                                f"DYNAMIC RLS FLAG: {fn.upper()}() detected in measure "
                                f"'{sm.get('name','')}' in table '{st.get('name','')}'. "
                                "This function uses the logged-in user's identity for row filtering. "
                                "Deployment team must: (1) configure Entra/AAD group memberships "
                                "in the target workspace, (2) verify email addresses match UPN format, "
                                "(3) test with each user role after deployment. "
                                "The RE/OP JSON should flag this with dynamic_rls=true."
                            )
                        ))

        # Scan RLS filter expressions
        rls_src = (self.pbix.get("rls_roles") or
                   self.pbix.get("data_model", {}).get("rls_roles", []))
        for role in rls_src:
            for tp in role.get("table_permissions", []):
                expr = tp.get("filter_dax","") or tp.get("filterExpression","")
                hits = dyn_pattern.findall(expr or "")
                if hits:
                    found_any = True
                    for fn in set(hits):
                        # Check if JSON captures dynamic_rls for this role
                        json_roles = (self.json.get("rls") or
                                      self.json.get("roles") or
                                      self.json.get("consolidated_model",{}).get("roles",[]) or [])
                        json_role  = next(
                            (r for r in json_roles
                             if (r.get("name","") or "").lower() == role.get("name","").lower()),
                            {}
                        )
                        json_dyn_flag = (json_role.get("dynamic_rls") or
                                         json_role.get("is_dynamic_rls") or
                                         self.json.get("dynamic_rls"))
                        has_flag = bool(json_dyn_flag)
                        self.results.append(CheckResult(
                            check_id="D5",
                            attribute=f"dynamic_rls[role:{role.get('name','')}.table:{tp.get('table','')}].{fn.upper()}()",
                            status="PASS" if has_flag else "MISSING",
                            source_value=f"{fn.upper()}() found in RLS filter",
                            json_value=str(json_dyn_flag) if has_flag else None,
                            note=(
                                f"DYNAMIC RLS: {fn.upper()}() detected in RLS filter "
                                f"for role '{role.get('name','')}', table '{tp.get('table','')}'. "
                                + (f"JSON correctly captures dynamic_rls=true." if has_flag else
                                   "RE/OP must set dynamic_rls=true on this role in JSON. "
                                   "Missing = deployment team won't know to configure "
                                   "Entra/AAD group memberships in the target workspace. "
                                   "Add 'dynamic_rls': true to the role entry in JSON.")
                            )
                        ))

        if not found_any:
            self.results.append(CheckResult(
                check_id="D5", attribute="dynamic_rls.detected",
                status="PASS", source_value="no_dynamic_rls_found",
                json_value="no_dynamic_rls_found",
                note="No USERNAME/USERPRINCIPALNAME/USERDOMAIN functions detected  --  N/A"
            ))

    # ══════════════════════════════════════════════════════════════
    # R15 --  Images & Logos  (D6-IMAGES)
    # StaticResources/RegisteredResources file presence +
    # imageUrl ResourcePackageItem references in visuals
    # ══════════════════════════════════════════════════════════════

    def check_d6_images_logos(self):
        """
        R15  --  Images & Logos.
        Checks:
          - StaticResources/RegisteredResources/ file presence (CRITICAL  --
            image file must be copied to target).
          - Per-image imageUrl ResourcePackageItem reference in visual config
            (CRITICAL  --  without this reference visual renders blank).
          - Image count per page.
        Source: PBIX zip StaticResources/ entries OR PBIP StaticResources/ folder.
        JSON:   json['visualizations']['static_resources'] or
                json['report_assets']['images']
        """
        print("[D6-IMAGES] Checking StaticResources images and logo references...")
        # Get static resource files from PBIX
        src_static = self.pbix.get("static_resources", [])
        if not src_static:
            # Try from PBIP extractor path
            src_static = self.pbix.get("pbip_report_files", {}).get("static_resources", [])

        # Also scan Report/Layout for image visuals referencing ResourcePackageItem
        src_layout = self.pbix.get("layout", {})
        src_pages  = src_layout.get("pages", [])

        json_assets = (self.json.get("report_assets", {}).get("images", []) or
                       self.json.get("visualizations", {}).get("static_resources", []) or [])
        json_asset_names = {a.get("name","").lower() for a in json_assets}

        # Check each registered resource file
        for res_name in src_static:
            rname_lower = (res_name if isinstance(res_name, str) else
                           res_name.get("name","")).lower()
            is_in_json  = rname_lower in json_asset_names or bool(json_assets)  # simple presence check
            self.results.append(CheckResult(
                check_id="D6",
                attribute=f"static_resource[{res_name}].present",
                status="PASS" if json_assets else "MISSING",
                source_value=res_name,
                json_value=res_name if json_assets else None,
                note=(
                    "IMAGE/LOGO: StaticResources file must be captured in JSON "
                    "and copied to the target PBIX/PBIP. "
                    "RE/OP must extract StaticResources/RegisteredResources/ file names "
                    "and include them under report_assets.images in JSON. "
                    "Missing = image visual renders as blank box in target."
                )
            ))

        # Scan layout pages for image visuals with ResourcePackageItem refs
        import re as _re_img
        res_pkg_pat = _re_img.compile(r'"ResourcePackageItem"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"', _re_img.IGNORECASE)
        for sp in src_pages:
            pname = sp.get("name","")
            for sv in sp.get("visuals", []):
                config_str = str(sv.get("config","") or sv.get("raw_config","") or "")
                for m in res_pkg_pat.finditer(config_str):
                    ref_name = m.group(1)
                    self.results.append(CheckResult(
                        check_id="D6",
                        attribute=f"page[{pname}].image_resource_ref[{ref_name}]",
                        status="PASS" if json_assets else "MISSING",
                        source_value=ref_name,
                        json_value=ref_name if json_assets else None,
                        note=(
                            "IMAGE RESOURCE REFERENCE: imageUrl ResourcePackageItem "
                            f"reference '{ref_name}' must be captured in JSON. "
                            "Without this reference the visual.json in the target PBIP "
                            "will not link to the embedded image file and "
                            "the visual will render as a blank box."
                        )
                    ))

        if not src_static:
            self.results.append(CheckResult(
                check_id="D6", attribute="static_resources.present",
                status="PASS", source_value="none_found",
                json_value="none_found",
                note="No StaticResources/RegisteredResources files found  --  N/A"
            ))



    # ══════════════════════════════════════════════════════════════
    # D8  --  Model-level metadata (PBIP/TMDL artifacts)
    # Covers: model.tmdl, expressions.tmdl, perspectives.tmdl,
    #         cultures.tmdl, diagramLayout.json, definition.pbism
    # Only applicable when source is PBIP folder.
    # For PBIX sources: checks that CAN be derived from BIM still run;
    # TMDL-specific checks are skipped with N/A INFO status.
    # ══════════════════════════════════════════════════════════════
    def check_d13_model_metadata(self):
        """
        D8  --  Model-level metadata from TMDL files and PBIP-specific artifacts.
        New check group  --  does not modify D1-D7.

        Files checked:
          expressions.tmdl  --  shared M queries, parameters, folder logic, API URLs
          model.tmdl        --  storage engine, collation, auto-datetime, compatibility
          perspectives.tmdl --  curated table/column/measure subsets per audience
          cultures.tmdl     --  translation strings for multi-language deployments
          diagramLayout.json --  X/Y coordinates and collapse states in Model View
          definition.pbism  --  Fabric compatibility level, engine target, format version
          TMDLScripts/      --  developer DAX/TMDL scripting tabs (audit completeness)
        """
        print("\n[D8] Checking model-level metadata artifacts...")

        src_format = self.pbix.get("source_format", "pbix").lower()
        pbip_root  = self.pbix.get("pbip_root_path", "")
        json_d8    = self.json.get("model_metadata", {})

        # -- Format detection --------------------------------------
        is_pbip = (src_format == "pbip" or bool(pbip_root) or
                   bool(self.pbix.get("tmdl_files", {})))
        is_pbix = not is_pbip

        if is_pbix:
            print("     Source is PBIX format  --  TMDL-specific checks use BIM "
                  "where possible; PBIP-only checks marked N/A")

        # -- Helper to log N/A for PBIX-only items -----------------
        def na_if_pbix(attr, desc):
            if is_pbix:
                self._log("D13", attr, "N/A-PBIX", "N/A-PBIX",
                          f"PBIX source: {desc} only exists in PBIP format. "
                          f"Switch to PBIP to enable this check.")
                return True
            return False

        # -- D8.1 expressions.tmdl  --  shared M queries / parameters -
        print("     [D8.1] expressions.tmdl  --  shared M queries and parameters")
        tmdl_files = self.pbix.get("tmdl_files", {})
        expr_tmdl  = tmdl_files.get("expressions", "")
        json_expr  = json_d8.get("shared_expressions", json_d8.get("expressions", {}))

        if is_pbip and not expr_tmdl:
            self._log("D13", "expressions.tmdl.present",
                      "expected", None,
                      "CRITICAL: expressions.tmdl not found in PBIP dataset folder "
                      "(definition/expressions.tmdl). RE/OP must read this file  --  "
                      "it contains shared Power Query functions, folder-loading logic, "
                      "API base URLs, global parameters and environment variables that "
                      "are INVISIBLE inside individual table partitions.")
        else:
            # Check shared parameters
            src_params = self.pbix.get("data_model", {}).get("shared_expressions", [])
            if not src_params:
                src_params = [{"name": k} for k in tmdl_files.get("expression_names", [])]
            json_params = json_d8.get("shared_expression_names",
                          json_d8.get("parameters", []))

            for sp in src_params:
                pname = sp.get("name","") if isinstance(sp,dict) else str(sp)
                matched = any(
                    str(jp).lower() == pname.lower()
                    if not isinstance(jp,dict) else
                    jp.get("name","").lower() == pname.lower()
                    for jp in json_params
                )
                if not matched:
                    self._log("D13", f"expressions.tmdl.shared_query[{pname}]",
                              pname, None,
                              f"Shared M query/parameter '{pname}' from expressions.tmdl "
                              f"not found in JSON. RE/OP must extract all entries from "
                              f"expressions.tmdl including: shared functions, folder path "
                              f"parameters, API base URL variables and environment parameters.")
                else:
                    self._log("D13", f"expressions.tmdl.shared_query[{pname}]",
                              pname, pname, "Shared expression present in JSON")

        # -- D8.2 model.tmdl  --  model-level metadata ----------------
        print("     [D8.2] model.tmdl  --  model-level metadata")
        bim_model  = self.pbix.get("data_model", {})
        json_model = json_d8.get("model_settings", {})

        model_attrs = {
            "default_mode": (
                bim_model.get("defaultMode", bim_model.get("default_mode","")),
                json_model.get("default_mode",""),
                "HIGH",
                "Default storage mode (Import/DirectQuery/Mixed) must be captured. "
                "Drives the entire data architecture of the target model."
            ),
            "compatibility_level": (
                str(bim_model.get("compatibilityLevel",
                    bim_model.get("compatibility_level",""))),
                str(json_model.get("compatibility_level","")),
                "HIGH",
                "Compatibility level (e.g. 1550, 1565) must be captured. "
                "Determines which DAX functions and model features are available."
            ),
            "culture": (
                bim_model.get("culture", ""),
                json_model.get("culture",""),
                "MEDIUM",
                "Default culture/locale (e.g. en-US, ja-JP) must be captured. "
                "Affects number formatting, date formatting and Analysis Services locale."
            ),
            "source_query_culture": (
                bim_model.get("sourceQueryCulture",
                    bim_model.get("source_query_culture","")),
                json_model.get("source_query_culture",""),
                "MEDIUM",
                "Source query culture controls how M engine parses dates and numbers "
                "from the data source (e.g. en-IN for Indian locale sources). "
                "Different from the display culture. Wrong value = date/number parse errors."
            ),
            "auto_date_time": (
                # __PBI_TimeIntelligenceEnabled annotation = 1 means auto date/time ON
                bim_model.get("auto_date_time_enabled",
                    bim_model.get("discourageImplicitMeasures",
                        bim_model.get("auto_date_time"))),
                json_model.get("auto_date_time"),
                "MEDIUM",
                "Auto date/time setting must be captured. If enabled in source "
                "and disabled in target, all date hierarchy visuals break."
            ),
            "returnErrorValuesAsNull": (
                str(bim_model.get("data_access_options", {}).get("returnErrorValuesAsNull",""))
                    if bim_model.get("data_access_options") else
                    str(bim_model.get("returnErrorValuesAsNull","")),
                str(json_model.get("returnErrorValuesAsNull",
                    json_model.get("return_error_values_as_null",""))),
                "HIGH",
                "returnErrorValuesAsNull=true means calculation errors show as blank "
                "instead of propagating. If this differs in target, KPI and measure "
                "error handling changes silently. RE/OP must capture from "
                "model.bim dataAccessOptions."
            ),
            "legacyRedirects": (
                str(bim_model.get("data_access_options", {}).get("legacyRedirects",""))
                    if bim_model.get("data_access_options") else
                    str(bim_model.get("legacyRedirects","")),
                str(json_model.get("legacyRedirects",
                    json_model.get("legacy_redirects",""))),
                "LOW",
                "legacyRedirects affects DirectQuery redirect behaviour on gateway. "
                "Must match source to avoid gateway query routing differences."
            ),
        }
        # Determine if JSON has any model metadata block at all.
        # If RE/OP hasn't built these fields yet, emit INFO (advisory, non-scoring)
        # instead of MISSING so they don't pull the score down.
        # When RE/OP adds the fields, they will naturally become PASS/FAIL.
        json_has_model_meta = any(
            json_model.get(k) is not None
            for k in ("culture","source_query_culture","auto_date_time",
                      "returnErrorValuesAsNull","legacyRedirects",
                      "compatibility_level","discourageImplicitMeasures")
        )

        for attr, (sv, jv, sev, note) in model_attrs.items():
            if sv and sv not in ("None","False","","none"):
                if not json_has_model_meta and (jv is None or jv == '' or jv == 'None'):
                    # RE/OP schema doesn't have this field yet → INFO
                    self.results.append(CheckResult(
                        check_id="D13",
                        attribute=f"model.tmdl.{attr}",
                        status="INFO",
                        severity="INFO",
                        source_value=str(sv),
                        json_value=None,
                        note=(f"[INFO — non-scoring] {note} "
                              "RE/OP JSON has no model metadata block. "
                              "This will become a scored check once RE/OP "
                              "adds these fields to the JSON schema.")
                    ))
                else:
                    self._log("D13", f"model.tmdl.{attr}", sv, jv or None, note)

        # -- Cultures and translations ---------------------------------
        # model.bim cultures[] with translations{} (S18)
        print("     [D13] cultures and translations")
        src_cultures_full = bim_model.get("cultures_full", [])
        json_cultures_raw = (json_d8.get("cultures") or
                             json_d8.get("translations") or
                             self.json.get("cultures") or [])
        json_cult_lkp = {
            (c.get("name","") if isinstance(c,dict) else str(c)).lower(): c
            for c in json_cultures_raw
        }
        for sc in src_cultures_full:
            cname     = sc.get("name","")
            jc_entry  = json_cult_lkp.get(cname.lower(), {})
            json_val  = jc_entry.get("name") or (cname if json_cultures_raw else None)
            if not json_cultures_raw and not json_has_model_meta:
                # RE/OP schema doesn't have cultures yet → INFO
                self.results.append(CheckResult(
                    check_id="D13", attribute=f"culture[{cname}].name",
                    status="INFO", severity="INFO",
                    source_value=cname, json_value=None,
                    note=(f"[INFO — non-scoring] CULTURE: '{cname}' must be captured in JSON. "
                          "RE/OP must extract model.bim cultures[].name. "
                          "Non-scoring until RE/OP adds cultures to JSON schema.")
                ))
            else:
                self._log("D13", f"culture[{cname}].name",
                          cname, json_val,
                          f"CULTURE: '{cname}' must be captured in JSON. "
                          "RE/OP must extract model.bim cultures[].name.")
            n_trans = sc.get("translation_count", 0)
            if n_trans > 0:
                json_trans_count = len(jc_entry.get("translations", []))
                self._log("D13", f"culture[{cname}].translation_count",
                          n_trans,
                          json_trans_count if json_trans_count else None,
                          f"TRANSLATIONS: {n_trans} translated captions in culture "
                          f"'{cname}'. RE/OP must extract translations{{}} from "
                          "model.bim cultures[]. Missing = target users in this "
                          "locale see untranslated field names.")

        # -- D8.3 perspectives.tmdl --------------------------------
        print("     [D8.3] perspectives.tmdl  --  curated model views")
        src_perspectives = bim_model.get("perspectives", [])
        json_perspectives= json_d8.get("perspectives", [])

        if src_perspectives:
            json_persp_names = {
                (p.get("name","") if isinstance(p,dict) else str(p)).lower()
                for p in json_perspectives
            }
            for sp in src_perspectives:
                pname = sp.get("name","") if isinstance(sp,dict) else str(sp)
                if pname.lower() not in json_persp_names:
                    self._log("D13", f"perspectives.tmdl.perspective[{pname}]",
                              pname, None,
                              f"Perspective '{pname}' not found in JSON. "
                              f"RE/OP must extract from perspectives.tmdl: name, "
                              f"included tables, columns and measures per perspective.")
                else:
                    self._log("D13", f"perspectives.tmdl.perspective[{pname}]",
                              pname, pname, "Perspective present in JSON")
        else:
            self._log("D13", "perspectives.tmdl",
                      "N/A-no-perspectives", "N/A-no-perspectives",
                      "No perspectives defined in source model")

        # -- D8.4 cultures.tmdl ------------------------------------
        print("     [D8.4] cultures.tmdl  --  translation strings")
        src_cultures = bim_model.get("cultures", [])
        json_cultures= json_d8.get("cultures", [])

        if not src_cultures:
            self._log("D13", "cultures.tmdl",
                      "N/A-monolingual", "N/A-monolingual",
                      "No cultures defined  --  source is monolingual. "
                      "cultures.tmdl check not applicable.")
        else:
            # Cultures in both PBIX (model.bim) and PBIP (cultures.tmdl)
            if True:
                json_cult_names = {
                    (c.get("name","") if isinstance(c,dict) else str(c)).lower()
                    for c in json_cultures
                }
                for sc in src_cultures:
                    cname = sc.get("name","") if isinstance(sc,dict) else str(sc)
                    if cname.lower() not in json_cult_names:
                        self._log("D13", f"cultures.tmdl.culture[{cname}]",
                                  cname, None,
                                  f"Culture/locale '{cname}' not in JSON. "
                                  f"RE/OP must extract from cultures.tmdl: culture name, "
                                  f"translation pairs (field captions, measure names, "
                                  f"description strings). Missing = broken multi-language "
                                  f"report experience for non-English users.")
                    else:
                        self._log("D13", f"cultures.tmdl.culture[{cname}]",
                                  cname, cname, "Culture present in JSON")

        # -- D8.5 diagramLayout.json -------------------------------
        print("     [D8.5] diagramLayout.json  --  Model View layout")
        if na_if_pbix("diagramLayout.json",
                      "diagramLayout.json Model View coordinates"):
            pass
        else:
            diagram_src  = tmdl_files.get("diagram_layout", {})
            json_diagram = json_d8.get("diagram_layout", {})
            if diagram_src and not json_diagram:
                self._log("D13", "diagramLayout.json.present",
                          "present in source", None,
                          "diagramLayout.json not captured in JSON. "
                          "RE/OP should extract X/Y coordinates and collapse states "
                          "from diagramLayout.json. Without this the Model View in the "
                          "target Power BI Desktop shows a cluttered, unreadable "
                          "relationship diagram. Severity LOW  --  not user-facing.",
                          )
                # Override severity to LOW for this check
                if self.results:
                    self.results[-1] = self.results[-1].__class__(
                        **{**self.results[-1].__dict__, "severity":"LOW"})
            elif diagram_src:
                self._log("D13", "diagramLayout.json.present",
                          "present", "present", "diagramLayout captured in JSON")

        # -- D8.6 definition.pbism ---------------------------------
        print("     [D8.6] definition.pbism  --  Fabric compatibility")
        if na_if_pbix("definition.pbism", "definition.pbism Fabric metadata"):
            pass
        else:
            pbism = tmdl_files.get("definition_pbism", {})
            json_pbism = json_d8.get("definition_pbism", {})
            for attr in ["version","compatibilityLevel","defaultPowerBIDataSourceVersion"]:
                sv = pbism.get(attr,"") if pbism else ""
                jv = json_pbism.get(attr,"") if json_pbism else ""
                if sv:
                    self._log("D13", f"definition.pbism.{attr}",
                              str(sv), str(jv) or None,
                              f"definition.pbism.{attr} must be captured. "
                              f"Ensures the target PBIP is built against the same "
                              f"Fabric engine version as the source.")

        # -- D8.7 TMDLScripts/ -------------------------------------
        print("     [D8.7] TMDLScripts/  --  developer scripting tabs")
        if na_if_pbix("TMDLScripts/", "TMDLScripts developer folder"):
            pass
        else:
            scripts = tmdl_files.get("tmdl_scripts", [])
            json_scripts = json_d8.get("tmdl_scripts", [])
            if scripts and not json_scripts:
                self._log("D13", "TMDLScripts.present",
                          f"{len(scripts)} script(s) found", None,
                          "TMDLScripts/ folder has DAX/TMDL scripting tabs that were "
                          "not captured in JSON. These are developer scratch pads  --  not "
                          "user-facing. RE/OP should capture script names for audit "
                          "completeness. Severity LOW.")
                if self.results:
                    self.results[-1] = self.results[-1].__class__(
                        **{**self.results[-1].__dict__, "severity":"LOW"})
            else:
                self._log("D13", "TMDLScripts.present",
                          "N/A-no-scripts" if not scripts else f"{len(scripts)} scripts",
                          "N/A-no-scripts" if not scripts else f"{len(json_scripts)} captured",
                          "TMDLScripts audit complete")

    # ══════════════════════════════════════════════════════════════
    # D9  --  PBIP report layer files
    # Covers: report.pbir, definition/report.json,
    #         definition/pages/*/page.json,
    #         definition/pages/*/visuals/*/visual.json,
    #         definition/theme.json, StaticResources/
    # Only applicable when source is PBIP folder.
    # For PBIX sources: equivalent checks exist in D6-D11 from Report/Layout.
    # D9 adds the PBIP-specific file-level validation.
    # ══════════════════════════════════════════════════════════════
    def check_d14_pbip_report_layer(self):
        """
        D9  --  PBIP report layer file validation.
        New check group  --  does not modify D1-D7 or D6/D11.

        Files checked:
          report.pbir                                   --  report-to-model binding
          definition/report.json                        --  global filters, bookmarks, nav pane
          definition/pages/<Page>/page.json             --  canvas size, mobile, background
          definition/pages/<Page>/visuals/<V>/visual.json  --  visual config, field bindings, filters
          definition/theme.json (or CustomThemes/)      --  colour palette, typography
          StaticResources/                              --  embedded PNGs, SVGs, icons
        """
        print("\n[D9] Checking PBIP report layer files...")

        src_format = self.pbix.get("source_format", "pbix").lower()
        pbip_files = self.pbix.get("pbip_report_files", {})
        json_d9    = self.json.get("pbip_report_layer",
                     self.json.get("report_layer", {}))

        is_pbip = (src_format == "pbip" or bool(pbip_files) or
                   bool(self.pbix.get("tmdl_files", {})))

        if not is_pbip:
            print("     Source is PBIX  --  D9 PBIP report layer checks use D6/D11 "
                  "equivalents. Marking PBIP-specific file checks as N/A.")
            # For PBIX, note that the equivalent checks are in D6/D11
            pbip_files_list = [
                ("report.pbir", "report-to-model binding"),
                ("definition/report.json", "global filters, bookmarks, nav pane"),
                ("definition/pages/*/page.json", "per-page canvas settings"),
                ("definition/pages/*/visuals/*/visual.json", "per-visual config"),
                ("definition/theme.json", "theme colour palette"),
                ("StaticResources/", "embedded images and SVGs"),
            ]
            for fpath, desc in pbip_files_list:
                self._log("D14", f"pbip_file[{fpath}]",
                          "N/A-PBIX", "N/A-PBIX",
                          f"PBIX source: {fpath} ({desc}) only exists in PBIP format. "
                          f"Equivalent content validated via D6/D11 from Report/Layout. "
                          f"Switch to PBIP to enable per-file D9 validation.")
            return

        # -- D9.1 report.pbir  --  master report hook -----------------
        print("     [D9.1] report.pbir  --  report-to-model binding")
        report_pbir = pbip_files.get("report_pbir", {})
        json_pbir   = json_d9.get("report_pbir", {})

        if not report_pbir:
            self._log("D14", "report.pbir.present",
                      "expected", None,
                      "CRITICAL: report.pbir not found or not extracted. This is the "
                      "master file binding the report canvas to the semantic model. "
                      "RE/OP must read report.pbir and capture: dataset reference "
                      "(target model ID), report format version, workspace binding. "
                      "Without this the forward-engineered PBIP report cannot connect "
                      "to its dataset.")
        else:
            for attr in ["version","datasetReference","formatVersion"]:
                sv = report_pbir.get(attr,"")
                jv = json_pbir.get(attr,"") if json_pbir else ""
                if sv:
                    self._log("D14", f"report.pbir.{attr}",
                              str(sv), str(jv) or None,
                              f"report.pbir.{attr} must be captured")

        # -- D9.2 definition/report.json  --  global states ------------
        print("     [D9.2] definition/report.json  --  global filters and bookmarks")
        report_json     = pbip_files.get("report_json", {})
        json_report_def = json_d9.get("report_definition", {})

        if not report_json:
            self._log("D14", "definition/report.json.present",
                      "expected", None,
                      "CRITICAL: definition/report.json not found or not extracted. "
                      "This file contains: report-level persistent filter criteria, "
                      "bookmark capture arrays (hidden elements, sort states, button "
                      "targets), interactive page navigation pane layout. "
                      "RE/OP must extract all these from report.json.")
        else:
            # Bookmarks
            src_bookmarks = report_json.get("bookmarks", [])
            json_bookmarks= json_report_def.get("bookmarks", [])
            self._log("D14", "report.json.bookmark_count",
                      len(src_bookmarks), len(json_bookmarks),
                      "Bookmark count must match. Each bookmark in report.json "
                      "captures: name, visual visibility states, filter states, "
                      "sort states and button action targets.")
            for bk in src_bookmarks:
                bname = bk.get("name","") if isinstance(bk,dict) else str(bk)
                jbk   = next((b for b in json_bookmarks
                               if (b.get("name","") if isinstance(b,dict) else str(b))
                               == bname), None)
                if not jbk:
                    self._log("D14", f"report.json.bookmark[{bname}]",
                              bname, None,
                              f"Bookmark '{bname}' not captured in JSON. RE/OP must "
                              f"extract per-bookmark state from report.json: name, "
                              f"captured visual show/hide states, filter selections, "
                              f"sort states and targeted button parameters.")
                else:
                    self._log("D14", f"report.json.bookmark[{bname}]",
                              bname, bname, "Bookmark present")

            # Nav pane
            nav_pane = report_json.get("navigationPaneLayout",
                       report_json.get("navPane"))
            json_nav = json_report_def.get("navigation_pane_layout")
            if nav_pane and not json_nav:
                self._log("D14", "report.json.navigation_pane_layout",
                          str(nav_pane)[:80], None,
                          "Navigation pane layout not captured. RE/OP must extract "
                          "page ordering and visibility from report.json "
                          "navigationPaneLayout. Drives the page tab order users see.")

        # -- D9.3 definition/pages/*/page.json ---------------------
        print("     [D9.3] definition/pages/*/page.json  --  per-page config")
        src_pages_json = pbip_files.get("pages", {})   # {page_name: page_json_dict}
        json_pages_d9  = json_d9.get("pages", {})

        if not src_pages_json:
            self._log("D14", "pages/*/page.json.present",
                      "expected", None,
                      "No page.json files extracted. RE/OP must read every file at "
                      "definition/pages/<Page_ID>/page.json. Each file contains: "
                      "page display name, canvas dimensions (width, height), "
                      "mobile layout toggle, background transparency, page visibility "
                      "(hidden vs visible), display option (fit to page / actual size).")
        else:
            for pname, pjson in src_pages_json.items():
                jp = json_pages_d9.get(pname, {})
                prefix = f"pages/{pname}/page.json"
                for attr, sev, desc in [
                    ("displayName",   "HIGH",
                     "Page display name from page.json must match source"),
                    ("width",         "MEDIUM",
                     "Canvas width (pixels) must be captured  --  custom canvas sizes "
                     "affect all visual positioning"),
                    ("height",        "MEDIUM",
                     "Canvas height (pixels) must be captured"),
                    ("visibility",    "HIGH",
                     "Page visibility (0=visible, 1=hidden) must match  --  hidden "
                     "pages not shown in report but used for tooltips/drillthrough"),
                    ("displayOption", "MEDIUM",
                     "Display option (fit to page, fit to width, actual size) must match"),
                    ("mobileLayout",  "MEDIUM",
                     "Mobile layout configuration must be captured if defined"),
                    ("background",    "MEDIUM",
                     "Page background colour and transparency from page.json must match"),
                ]:
                    sv = pjson.get(attr) if isinstance(pjson,dict) else None
                    jv = jp.get(attr) if isinstance(jp,dict) else None
                    if sv is not None:
                        self._log("D14", f"{prefix}.{attr}",
                                  str(sv)[:80], str(jv)[:80] if jv is not None else None,
                                  desc)

        # -- D9.4 definition/pages/*/visuals/*/visual.json ---------
        print("     [D9.4] definition/pages/*/visuals/*/visual.json  --  per-visual config")
        src_visuals_json = pbip_files.get("visuals", {})  # {vis_id: visual_json_dict}
        json_visuals_d9  = json_d9.get("visuals", {})

        if not src_visuals_json:
            self._log("D14", "visuals/*/visual.json.present",
                      "expected", None,
                      "No visual.json files extracted. RE/OP must read every file at "
                      "definition/pages/<Page_ID>/visuals/<Visual_ID>/visual.json. "
                      "Each file contains: visual type (barChart, matrix, slicer etc.), "
                      "bounding box (x, y, width, height, z-order), data field "
                      "bindings (axis, legend, tooltips, values), visual-level filters "
                      "(top-N, exclusion filters), formatting objects (colours, fonts, "
                      "borders, labels, axes, conditional formatting), custom tooltip "
                      "configuration, drillthrough configuration.")
        else:
            total_visuals = len(src_visuals_json)
            captured = 0
            for vid, vjson in src_visuals_json.items():
                jv = json_visuals_d9.get(vid, {})
                vtype = (vjson.get("visualType","") or
                         vjson.get("visual_type","") or
                         vjson.get("$schema","").split("/")[-1].replace(".json","")
                         if isinstance(vjson,dict) else "")
                if not jv:
                    self._log("D14", f"visuals/{vid}/visual.json",
                              vtype or vid, None,
                              f"Visual '{vid}' (type: {vtype or 'unknown'}) not captured "
                              f"in JSON. RE/OP must extract all visual.json files.")
                else:
                    captured += 1
                    # Check critical visual attributes
                    for attr, sev, desc in [
                        ("visualType", "CRITICAL",
                         "Visual type must be captured from visual.json"),
                        ("dataTransforms", "HIGH",
                         "Data field bindings (dataTransforms / query) must be captured "
                         " --  this is where axes, legend, tooltips and values are defined"),
                        ("vcObjects", "HIGH",
                         "Formatting objects (vcObjects) must be captured  --  contains "
                         "colours, fonts, borders, data labels, axes formatting"),
                        ("filters", "HIGH",
                         "Visual-level filters must be captured from visual.json"),
                    ]:
                        sv = vjson.get(attr) if isinstance(vjson,dict) else None
                        jvv= jv.get(attr)    if isinstance(jv,dict)    else None
                        if sv is not None and jvv is None:
                            self._log("D14", f"visuals/{vid}/visual.json.{attr}",
                                      str(sv)[:80], None, desc)

            self._log("D14", "visuals.capture_rate",
                      f"{total_visuals} total", f"{captured} captured",
                      f"Visual capture rate: {captured}/{total_visuals}. "
                      f"All visual.json files must be read.")

        # -- D9.5 definition/theme.json -----------------------------
        print("     [D9.5] definition/theme.json  --  colour palette and typography")
        theme_json     = pbip_files.get("theme", {})
        json_theme_d9  = json_d9.get("theme", {})

        if not theme_json:
            self._log("D14", "definition/theme.json.present",
                      "expected", None,
                      "theme.json not extracted. RE/OP must read the theme file from "
                      "definition/theme.json (or CustomThemes/ folder). Contains: "
                      "corporate hex colour palettes, font family mappings, structural "
                      "grid lines, default border styling, visual size defaults. "
                      "Without this the target PBIP uses default Power BI colours.")
        else:
            for attr, sev, desc in [
                ("name",          "HIGH",
                 "Theme name must match between source and JSON"),
                ("dataColors",    "HIGH",
                 "Data colour palette (hex values) must be captured  --  drives all "
                 "chart series colours"),
                ("background",    "MEDIUM",
                 "Default background colour from theme must be captured"),
                ("foreground",    "MEDIUM",
                 "Default foreground/text colour must be captured"),
                ("tableAccent",   "LOW",
                 "Table accent colour must be captured"),
            ]:
                sv = theme_json.get(attr) if isinstance(theme_json,dict) else None
                jv = json_theme_d9.get(attr) if isinstance(json_theme_d9,dict) else None
                if sv is not None:
                    self._log("D14", f"theme.json.{attr}",
                              str(sv)[:80], str(jv)[:80] if jv is not None else None,
                              desc)

        # -- D9.6 StaticResources/ ----------------------------------
        print("     [D9.6] StaticResources/  --  embedded images and SVGs")
        static_resources = pbip_files.get("static_resources", [])
        json_static      = json_d9.get("static_resources", [])

        if not static_resources and is_pbip:
            self._log("D14", "StaticResources.present",
                      "check required", None,
                      "StaticResources/ folder not extracted. RE/OP must enumerate all "
                      "files in StaticResources/ and capture: filename, file type "
                      "(PNG/SVG/JPEG), usage context (page background, logo, icon, "
                      "custom visual resource). Embedded images used as report "
                      "backgrounds or navigation headers are stored here.")
        elif static_resources:
            json_names = {
                (r.get("name","") if isinstance(r,dict) else str(r)).lower()
                for r in json_static
            }
            for res in static_resources:
                rname = (res.get("name","") if isinstance(res,dict) else str(res))
                if rname.lower() not in json_names:
                    self._log("D14", f"StaticResources/{rname}",
                              rname, None,
                              f"Static resource '{rname}' not captured in JSON. "
                              f"RE/OP must capture filename and usage context for each "
                              f"file in StaticResources/.")
                else:
                    self._log("D14", f"StaticResources/{rname}",
                              rname, rname, "Static resource present in JSON")
        else:
            self._log("D14", "StaticResources",
                      "N/A-empty", "N/A-empty",
                      "No static resources found in source")


# ---------------------------------------------
# Step 3  --  Score and reporting
# ---------------------------------------------

class Reporter:
    """Generates JSON, CSV, gap reports and optionally writes to PostgreSQL."""

    def __init__(self, report: ValidationReport, out_dir: str, pg_enabled: bool = False):
        self.report     = report
        self.out_dir    = Path(out_dir)
        self.pg_enabled = pg_enabled
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def _group_score(self, check_id: str) -> dict:
        group   = [r for r in self.report.results if r.check_id == check_id
                   and r.status != "INFO"]   # INFO items are non-scoring
        passed  = sum(1 for r in group if r.status == "PASS")
        total   = len(group)
        score   = round(passed / total * 100, 2) if total else 0
        return {
            "check":   check_id,
            "passed":  passed,
            "total":   total,
            "score":   score,
            "verdict": "PASS" if score == 100.0 else "FAIL",
        }

    def _build_check_entry(self, cid: str, scope: str, label: str, desc: str) -> dict:
        """Build a single check entry matching the required output format."""
        gs = self._group_score(cid)
        # Exclude INFO items from scoring counts — they are advisory only
        results_for_check = [r for r in self.report.results
                             if r.check_id == cid and r.status != "INFO"]
        passed  = sum(1 for r in results_for_check if r.status == "PASS")
        failed  = sum(1 for r in results_for_check if r.status in ("FAIL","MISMATCH"))
        missing = sum(1 for r in results_for_check if r.status == "MISSING")
        total   = len(results_for_check)
        # INFO count separately — visible but non-scoring
        info_count = sum(1 for r in self.report.results
                        if r.check_id == cid and r.status == "INFO")
        # weight: PASS = 0.5 each; gap = 0
        weight_total  = round(total * 0.5, 1)
        weight_earned = round(passed * 0.5, 1)
        score = round(weight_earned / weight_total * 100, 2) if weight_total else 100.0
        verdict = "PASS" if failed == 0 and missing == 0 else "FAIL"
        return {
            "check":         cid,
            "label":         label,
            "description":   desc,
            "scope":         scope,
            "score":         score,
            "verdict":       verdict,
            "passed":        passed,
            "failed":        failed,
            "missing":       missing,
            "info":          info_count,
            "total":         total,
            "weight_earned": weight_earned,
            "weight_total":  weight_total,
        }

    def write_json(self) -> Path:
        import base64, io
        try:
            import pandas as _pd
        except ImportError:
            _pd = None

        # ── Check definitions ─────────────────────────────────────
        SEM_CHECKS = [
            ("D1", "Connections",
             "Data source connections, server/database paths, authentication mode, "
             "SharePoint/CSV/Web/Folder sources, pbiServiceLive split architecture"),
            ("D2", "Tables, RLS, Incr.Refresh",
             "Table names, isHidden, storage mode, M expressions, DAX calculated tables, "
             "RLS roles/DAX filters, OLS column permissions, What-If Parameters, Incremental Refresh"),
            ("D3", "Columns, Hierarchies, MQ Params",
             "Column names, data types, format strings, isHidden, summarizeBy, dataCategory, "
             "sortByColumn, displayFolder, lineageTag, DAX calculated column expressions, "
             "M Query Parameters, Hierarchies (name/levels/ordinals)"),
            ("D4", "Filters",
             "Report/page/visual filters, isHiddenInViewMode"),
            ("D5", "Measures and Relationships",
             "DAX expressions, format strings, isHidden, displayFolder, "
             "KPI statusExpression/targetExpression/trendExpression, "
             "USERELATIONSHIP cross-check, Dynamic RLS (USERNAME/USERPRINCIPALNAME), "
             "relationship cardinality, cross-filter direction, is_active, joinOnDateBehavior"),
            ("D13","Model Metadata",
             "compatibilityLevel, culture, sourceQueryCulture, defaultMode, "
             "discourageImplicitMeasures, dataAccessOptions (legacyRedirects/returnErrorValuesAsNull), "
             "expressions shared M queries, perspectives, cultures/translations"),
        ]
        VIS_CHECKS = [
            ("D6",  "Report Visual Layer",
             "Pages, canvas size, visuals, field bindings, visual filter count, bounding box, "
             "bookmarks, theme name/dataColors palette, StaticResources image files and imageUrl refs"),
            ("D7",  "Display Names",
             "Effective display names, aggregation types, named measure vs inline"),
            ("D8",  "Conditional Formatting",
             "Colour rules, thresholds, icon sets, data bars, fontColorFormatting, "
             "backgroundColorFormatting, rowHighlighting, topN"),
            ("D9",  "Tooltips",
             "Report page tooltip targets, custom tooltip field lists per visual"),
            ("D10", "Interactions and Navigation",
             "Cross-filter matrix, drillFilterOtherVisuals, sync slicers/syncSlicerFiltersApply, "
             "button actions (all 9 types), page navigation, drillthrough"),
            ("D11", "Visual and Page Formatting",
             "Data labels, category labels, axes, legend, data point colour overrides, "
             "button styling, visual background/border/shadow, page background, canvas settings"),
            ("D12", "External Components",
             "Power Apps, Power Automate, Paginated Reports, custom visual GUIDs, "
             "HTML/WordCloud visuals by type-name length, Azure Maps API key"),
            ("D14", "PBIP Report Layer",
             "report.pbir, report.json, page.json, visual.json, theme.json, "
             "StaticResources (PBIP only — marked N/A for PBIX)"),
        ]

        # ── Build check entries ───────────────────────────────────
        sem_entries = [self._build_check_entry(cid,"semantic",lbl,dsc)
                       for cid,lbl,dsc in SEM_CHECKS
                       if any(r.check_id==cid for r in self.report.results)]
        vis_entries = [self._build_check_entry(cid,"visual",lbl,dsc)
                       for cid,lbl,dsc in VIS_CHECKS
                       if any(r.check_id==cid for r in self.report.results)]
        all_entries = sem_entries + vis_entries

        # ── Weighted scores ───────────────────────────────────────
        sem_we = sum(e["weight_earned"] for e in sem_entries)
        sem_wt = sum(e["weight_total"]  for e in sem_entries)
        vis_we = sum(e["weight_earned"] for e in vis_entries)
        vis_wt = sum(e["weight_total"]  for e in vis_entries)
        all_we = sem_we + vis_we
        all_wt = sem_wt + vis_wt

        sem_score = round(sem_we/sem_wt*100, 2) if sem_wt else 100.0
        vis_score = round(vis_we/vis_wt*100, 2) if vis_wt else 100.0
        overall   = round(all_we/all_wt*100, 2) if all_wt else 100.0

        sem_verdict = "PASS" if all(e["verdict"]=="PASS" for e in sem_entries) else "FAIL"
        vis_verdict = "PASS" if all(e["verdict"]=="PASS" for e in vis_entries) else "FAIL"
        verdict     = "PASS" if sem_verdict=="PASS" and vis_verdict=="PASS" else "FAIL"

        # ── Gap report ────────────────────────────────────────────
        SEV_ORDER = {"CRITICAL":1,"HIGH":2,"MEDIUM":3,"LOW":4,"INFO":5}
        gaps = [r for r in self.report.results
                if r.status not in ("PASS",)]
        sev_counts: dict = {}
        for g in gaps:
            sev = g.severity or "INFO"
            if sev != "PASS":
                sev_counts[sev] = sev_counts.get(sev,0)+1

        gap_report = {
            "workbook_id":     self.report.workbook_id,
            "timestamp":       self.report.timestamp,
            "total_gaps":      len(gaps),
            "severity_summary":sev_counts,
            "gaps": sorted([{
                "check_id":    g.check_id,
                "attribute":   g.attribute,
                "status":      g.status,
                "source_value":str(g.source_value),
                "json_value":  str(g.json_value),
                "note":        g.note or "",
                "severity":    g.severity or "",
            } for g in gaps], key=lambda g: SEV_ORDER.get(g["severity"],9))
        }

        # ── Excel base64 ──────────────────────────────────────────
        excel_b64 = None
        if _pd:
            try:
                rows = []
                for r in self.report.results:
                    rows.append({
                        "check_id":    r.check_id,
                        "attribute":   r.attribute,
                        "status":      r.status,
                        "severity":    r.severity,
                        "source_value":str(r.source_value),
                        "json_value":  str(r.json_value),
                        "note":        r.note or "",
                    })
                df = _pd.DataFrame(rows)
                buf = io.BytesIO()
                with _pd.ExcelWriter(buf, engine="openpyxl") as writer:
                    df.to_excel(writer, index=False, sheet_name="Validation")
                    # Gap sheet
                    gap_df = df[df["status"]!="PASS"]
                    if not gap_df.empty:
                        gap_df.to_excel(writer, index=False, sheet_name="Gaps")
                buf.seek(0)
                excel_b64 = base64.b64encode(buf.read()).decode("utf-8")
            except Exception:
                excel_b64 = None

        # ── Final output ──────────────────────────────────────────
        out = {
            "workbook_id":    self.report.workbook_id,
            "file_name":      Path(self.report.pbix_path).name,
            "tool_name":      "powerbi",
            "score":          overall,
            "verdict":        verdict,
            "semantic_score": sem_score,
            "semantic_verdict":sem_verdict,
            "visual_score":   vis_score,
            "visual_verdict": vis_verdict,
            "score_breakdown": {
                "overall": {
                    "score":    overall,
                    "verdict":  verdict,
                    "formula":  "weight-based: each PASS earns 0.5, each gap earns 0; score = weight_earned/weight_total * 100",
                    "threshold":"PASS if score >= 80%",
                },
                "semantic": {
                    "scope":         "semantic",
                    "score":         sem_score,
                    "verdict":       sem_verdict,
                    "weight_earned": round(sem_we,1),
                    "weight_total":  round(sem_wt,1),
                    "checks":        sem_entries,
                },
                "visual": {
                    "scope":         "visual",
                    "score":         vis_score,
                    "verdict":       vis_verdict,
                    "weight_earned": round(vis_we,1),
                    "weight_total":  round(vis_wt,1),
                    "checks":        vis_entries,
                },
            },
            "total_checks": len(self.report.results),
            "gaps_count":   len(gaps),
            "timestamp":    self.report.timestamp,
            "check_summary":all_entries,
            "report": {
                "workbook_id":    self.report.workbook_id,
                "pbix_path":      self.report.pbix_path,
                "json_path":      self.report.json_path,
                "timestamp":      self.report.timestamp,
                "overall_score":  overall,
                "overall_verdict":verdict,
                "semantic_score": sem_score,
                "semantic_verdict":sem_verdict,
                "visual_score":   vis_score,
                "visual_verdict": vis_verdict,
                "check_summary":  all_entries,
                "all_results":    [asdict(r) for r in self.report.results],
            },
            "gap_report":   gap_report,
            "excel_base64": excel_b64,
        }

        path = self.out_dir / "validation_report.json"
        path.write_text(json.dumps(out, indent=2, default=str))
        print(f"\n[Report] Full report    → {path}")
        return path

    def write_csv(self) -> Path:
        """Write full validation results to CSV and optionally to PostgreSQL."""
        SEVERITY_ORDER = {"CRITICAL":1,"HIGH":2,"MEDIUM":3,"LOW":4,"INFO":5,"PASS":6,"":7}
        LAYER_MAP = {
            "D1":  "Semantic", "D2":  "Semantic", "D3":  "Semantic",
            "D4":  "Semantic", "D5":  "Semantic", "D13": "Semantic",
            "D6":  "Report",   "D7":  "Report",   "D8":  "Report",
            "D9":  "Report",   "D10": "Report",   "D11": "Report",
            "D12": "Report",   "D14": "Report",
            # Checklist extended checks
            "CL1": "Report", "CL2": "Report", "CL3": "Report",
            "CL4": "Report", "CL6": "Report", "CL9": "Report",
            "CL10":"Report",  "CL11":"Report",  "CLVTS":"Report",
        }
        rows = []
        for r in self.report.results:
            rows.append({
                "workbook_id":  self.report.workbook_id,
                "pbix_path":    self.report.pbix_path,
                "run_timestamp":self.report.timestamp,
                "check_id":     r.check_id,
                "layer":        LAYER_MAP.get(r.check_id, "Other"),
                "severity":     r.severity,
                "status":       r.status,
                "attribute":    r.attribute,
                "source_value": str(r.source_value)[:120],
                "json_value":   str(r.json_value)[:120],
                "note":         r.note,
            })
        df = pd.DataFrame(rows)
        df["_sev_order"] = df["severity"].map(lambda s: SEVERITY_ORDER.get(s,7))
        df = df.sort_values(["_sev_order","check_id","attribute"]).drop(columns=["_sev_order"])

        # -- Write to CSV (always) ------------------------------------
        import csv as _csv
        path = self.out_dir / "validation_report.csv"
        df.to_csv(path, index=False, quoting=_csv.QUOTE_ALL)
        print(f"[Report] CSV report     → {path}")

        # -- Write to PostgreSQL (if --pg flag passed) -----------------
        if self.pg_enabled:
            self._write_to_postgres(
                df=df,
                table_name=PG_TABLES["validation_results"],
                description="validation results"
            )

        return path

    def _write_to_postgres(self, df: pd.DataFrame, table_name: str, description: str):
        """
        Write a DataFrame to PostgreSQL using psycopg2.

        -- Connection details ----------------------------------------
        Edit PG_CONFIG at the top of this file to set:
          host, port, database, user, password, schema

        -- Table structure -------------------------------------------
        The table is created automatically on first run if it does not exist.
        On subsequent runs, new rows are APPENDED (not replaced).
        Each run is identified by workbook_id + run_timestamp so you can
        query the history of all validation runs.

        -- To query results in PostgreSQL ---------------------------
          -- Latest run for a workbook:
          SELECT * FROM <schema>.<table>
          WHERE workbook_id = '<id>'
          ORDER BY run_timestamp DESC, severity, check_id;

          -- All gaps across all runs:
          SELECT * FROM <schema>.<table>
          WHERE status IN ('FAIL','MISSING')
          ORDER BY run_timestamp DESC, severity;

          -- Trend: score per run:
          SELECT run_timestamp,
                 ROUND(100.0 * SUM(CASE WHEN status='PASS' THEN 1 ELSE 0 END)
                       / COUNT(*), 2) AS score
          FROM <schema>.<table>
          GROUP BY run_timestamp
          ORDER BY run_timestamp;
        """
        try:
            import psycopg2
            from psycopg2 import sql
        except ImportError:
            print("[PostgreSQL] psycopg2 not installed  --  skipping PostgreSQL write.")
            print("             Install with: pip install psycopg2-binary")
            return

        schema = PG_CONFIG["schema"]
        full_table = f'{schema}.{table_name}'

        try:
            conn = psycopg2.connect(
                host     = PG_CONFIG["host"],
                port     = PG_CONFIG["port"],
                dbname   = PG_CONFIG["database"],
                user     = PG_CONFIG["user"],
                password = PG_CONFIG["password"],
            )
            cur = conn.cursor()

            # -- Create schema if it does not exist --------------------
            cur.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                    sql.Identifier(schema)
                )
            )

            # -- Create table if it does not exist ---------------------
            # Column definitions match the DataFrame columns exactly.
            # Add or remove columns here if you customise the DataFrame.
            cur.execute(sql.SQL("""
                CREATE TABLE IF NOT EXISTS {table} (
                    id              SERIAL PRIMARY KEY,
                    workbook_id     VARCHAR(20),
                    pbix_path       TEXT,
                    run_timestamp   TIMESTAMP,
                    check_id        VARCHAR(10),
                    layer           VARCHAR(20),
                    severity        VARCHAR(20),
                    status          VARCHAR(20),
                    attribute       TEXT,
                    source_value    TEXT,
                    json_value      TEXT,
                    note            TEXT,
                    inserted_at     TIMESTAMP DEFAULT NOW()
                )
            """).format(table=sql.Identifier(schema, table_name)))

            # -- Insert rows --------------------------------------------
            insert_sql = sql.SQL("""
                INSERT INTO {table}
                    (workbook_id, pbix_path, run_timestamp, check_id, layer,
                     severity, status, attribute, source_value, json_value, note)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """).format(table=sql.Identifier(schema, table_name))

            rows_to_insert = [
                (
                    row["workbook_id"],
                    row["pbix_path"],
                    row["run_timestamp"],
                    row["check_id"],
                    row["layer"],
                    row["severity"],
                    row["status"],
                    row["attribute"],
                    row["source_value"],
                    row["json_value"],
                    row["note"],
                )
                for _, row in df.iterrows()
            ]
            cur.executemany(insert_sql, rows_to_insert)
            conn.commit()
            cur.close()
            conn.close()
            print(f"[PostgreSQL] {description}  --  {len(rows_to_insert)} rows written "
                  f"→ {full_table}")

        except Exception as e:
            print(f"[PostgreSQL] WARNING  --  could not write {description} to PostgreSQL: {e}")
            print(f"             Check PG_CONFIG values at the top of the script.")
            print(f"             CSV file was still written successfully.")

    def write_gap_report(self) -> Path:
        SEVERITY_ORDER = {"CRITICAL":1,"HIGH":2,"MEDIUM":3,"LOW":4,"INFO":5}
        all_gaps  = [asdict(r) for r in self.report.gaps]
        # Split actionable gaps from INFO (advisory, non-scoring)
        gaps      = [g for g in all_gaps if g.get("status") != "INFO"]
        info_items= [g for g in all_gaps if g.get("status") == "INFO"]
        gaps.sort(key=lambda g: (
            SEVERITY_ORDER.get(g.get("severity",""), 9),
            g.get("check_id","")
        ))
        severity_summary = {}
        for g in gaps:
            sev = g.get("severity","UNKNOWN")
            severity_summary[sev] = severity_summary.get(sev, 0) + 1

        out = {
            "workbook_id":      self.report.workbook_id,
            "timestamp":        self.report.timestamp,
            "total_gaps":       len(gaps),
            "total_info":       len(info_items),
            "severity_summary": severity_summary,
            "gaps":             gaps,
            "info_items":       info_items,
        }
        # -- Write to JSON (always) ------------------------------------
        path = self.out_dir / "gap_report.json"
        path.write_text(json.dumps(out, indent=2, default=str))
        print(f"[Report] GAP report     → {path}")

        # -- Write gaps to PostgreSQL (if --pg flag passed) ------------
        if self.pg_enabled and gaps:
            gap_df = pd.DataFrame([
                {
                    "workbook_id":  self.report.workbook_id,
                    "pbix_path":    self.report.pbix_path,
                    "run_timestamp":self.report.timestamp,
                    "check_id":     g.get("check_id",""),
                    "layer":        "Semantic" if g.get("check_id","").startswith(("D1","D2","D3","D4","D5")) else "Report",
                    "severity":     g.get("severity",""),
                    "status":       g.get("status",""),
                    "attribute":    g.get("attribute",""),
                    "source_value": str(g.get("source_value",""))[:120],
                    "json_value":   str(g.get("json_value",""))[:120],
                    "note":         g.get("note",""),
                }
                for g in gaps
            ])
            self._write_to_postgres(
                df=gap_df,
                table_name=PG_TABLES["gap_summary"],
                description="gap summary"
            )

        return path

    def print_summary(self, mode: str = "full"):
        SEVERITY_ORDER = {"CRITICAL":1,"HIGH":2,"MEDIUM":3,"LOW":4,"INFO":5}
        SEV_ICON = {"CRITICAL":"🔴","HIGH":"🟠","MEDIUM":"🟡","LOW":"🟢","INFO":"🔵"}

        # Checks to display based on mode
        CHECKS_BY_MODE = {
            "semantic": ["D1","D2","D3","D4","D5","D13"],
            "report":   ["D6","D7","D8","D9","D10","D11","D12","D14"],
            "full":     ["D1","D2","D3","D4","D5","D6","D7","D8","D9","D10","D11","D12","D13","D14"],
        }
        CHECK_LABELS = {
            "D1": "Connections",
            "D2": "Tables, RLS/OLS, What-If, Incr.Refresh",
            "D3": "Columns, Hierarchies, MQ Parameters",
            "D4": "Filters",
            "D5": "Measures, Relationships, KPI, Dyn.RLS",
            "D6": "Visuals, Images, Theme",
            "D7": "Display Names",
            "D8": "Conditional Formatting",
            "D9": "Tooltips",
            "D10":"Interactions, Sync Slicers, Drillthrough",
            "D11":"Visual Formatting",
            "D12":"External Components",
            "D13":"Model Metadata, Perspectives, Cultures",
            "D14":"PBIP Report Layer",
        }
        checks_to_show = CHECKS_BY_MODE.get(mode, CHECKS_BY_MODE["full"])

        mode_label = {"semantic":"Semantic Layer","report":"Report Layer","full":"Full"}.get(mode,"Full")

        print("\n" + "="*65)
        print(f"  TIER 1 VALIDATION SUMMARY  --  {mode_label}")
        print(f"  Workbook : {self.report.workbook_id}")
        print(f"  Score    : {self.report.score}%   (threshold: 100%)")
        print(f"  Verdict  : {self.report.verdict}")
        print("="*65)

        for cid in checks_to_show:
            gs = self._group_score(cid)
            if gs["total"] == 0:
                print(f"  {'➖'} {cid:<4}  {CHECK_LABELS.get(cid,cid):<30}  {'0/0':>9}   N/A")
                continue
            icon = "✅" if gs["verdict"] == "PASS" else "❌"
            print(f"  {icon} {cid:<4}  {CHECK_LABELS.get(cid,cid):<30}  "
                  f"{gs['passed']:>4}/{gs['total']:<4}  {gs['score']:>6.1f}%")

        print("="*65)
        if self.report.gaps:
            # Separate actionable gaps from INFO
            real_gaps = [g for g in self.report.gaps if g.status != "INFO"]
            info_items = [g for g in self.report.gaps if g.status == "INFO"]
            print(f"\n  {len(real_gaps)} gap(s) found  --  see gap_report.json")
            if info_items:
                print(f"  {len(info_items)} INFO item(s) (advisory, non-scoring)  --  "
                      "RE/OP schema fields not yet implemented")
            sev_counts: dict = {}
            for g in real_gaps:
                sev = g.severity or "UNKNOWN"
                sev_counts[sev] = sev_counts.get(sev, 0) + 1
            print("\n  Severity breakdown:")
            for sev in sorted(sev_counts, key=lambda s: SEVERITY_ORDER.get(s,9)):
                print(f"    {SEV_ICON.get(sev,'⚪')} {sev:<10}: {sev_counts[sev]} gap(s)")
            print("\n  First 10 gaps (sorted by severity):")
            sorted_gaps = sorted(self.report.gaps,
                                 key=lambda g: SEVERITY_ORDER.get(g.severity or "",9))
            for g in sorted_gaps[:10]:
                print(f"    {SEV_ICON.get(g.severity,'⚪')} [{g.check_id}] {g.attribute}")
                print(f"           Source : {str(g.source_value)[:60]}")
                print(f"           JSON   : {str(g.json_value)[:60]}")
                if g.note:
                    print(f"           Note   : {g.note[:80]}")
        else:
            print("\n  No gaps  --  homogeneous JSON captures all required attributes.")


# ---------------------------------------------
# Main entry point
# ---------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Step 2  --  Compare PBIX / PBIP source vs Homogeneous JSON "
                    "(format-agnostic: auto-detects PBIX zip or PBIP folder)"
    )
    # Source  --  one of --pbix or --pbip (mutually exclusive)
    src_grp = parser.add_mutually_exclusive_group(required=True)
    src_grp.add_argument("--pbix", default=None,
                         help="Path to the .pbix file (PBIX format)")
    src_grp.add_argument("--pbip", default=None,
                         help="Path to the .pbip project folder (PBIP format). "
                              "Enables D8 and D9 TMDL/PBIP-specific checks.")
    parser.add_argument("--json", required=True,
                        help="Path to the homogeneous .json file")
    parser.add_argument("--bim",  default=None,
                        help="(Optional) Path to model.bim from Tabular Editor. "
                             "Only used with --pbix. For --pbip the model is read "
                             "from TMDL files inside the project folder.")
    parser.add_argument("--auto-extract-bim", action="store_true", default=False,
                        help="Automatically extract model.bim from the PBIX using "
                             "pbi-tools (https://pbi.tools) if --bim is not provided. "
                             "pbi-tools must be installed and on PATH. "
                             "If pbi-tools is not found the validator continues without "
                             "a BIM file (DataModel binary check only).")
    parser.add_argument("--out",  default="./validation_output",
                        help="Output directory for reports")
    parser.add_argument("--pg",   action="store_true", default=False,
                        help="Write results to PostgreSQL in addition to CSV.")
    parser.add_argument("--mode", default="auto",
                        choices=["auto","semantic","report","full"],
                        help="Validation mode (default: auto):\n"
                             "  auto     -- detect from source file content\n"
                             "  semantic -- D1-D5, D13 only (dataset PBIX / no report layer)\n"
                             "  report   -- D6-D14 (report PBIX / no semantic model)\n"
                             "  full     -- all checks D1-D9 (combined PBIX)")
    args = parser.parse_args()

    # -- Auto-extract BIM using pbi-tools if requested ----------------
    if getattr(args, "auto_extract_bim", False) and not args.bim and args.pbix:
        import subprocess, shutil as _shutil
        pbix_path = Path(args.pbix)
        extract_dir = Path(args.out) / "pbi_tools_extract"
        extract_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n{'='*60}")
        print(f"  AUTO BIM EXTRACTION  --  pbi-tools")
        print(f"  Source : {pbix_path}")
        print(f"  Output : {extract_dir}")
        print(f"{'='*60}")

        # Check pbi-tools is available
        pbitools_exe = _shutil.which("pbi-tools") or _shutil.which("pbi-tools.exe")
        if not pbitools_exe:
            # Also check common install locations on Windows
            common_paths = [
                Path.home() / ".dotnet" / "tools" / "pbi-tools.exe",
                Path("C:/Program Files/pbi-tools/pbi-tools.exe"),
                Path("C:/tools/pbi-tools/pbi-tools.exe"),
            ]
            for cp in common_paths:
                if cp.exists():
                    pbitools_exe = str(cp)
                    break

        if not pbitools_exe:
            print("  ⚠️  pbi-tools not found on PATH or common locations.")
            print("      Install via: dotnet tool install -g pbi-tools")
            print("      Or download from: https://pbi.tools")
            print("      Continuing without BIM extraction...")
            print()
        else:
            print(f"  pbi-tools found: {pbitools_exe}")
            try:
                result = subprocess.run(
                    [pbitools_exe, "extract",
                     str(pbix_path.resolve()),
                     "-extractFolder", str(extract_dir.resolve()),
                     "-modelSerialization", "Raw"],
                    capture_output=True, text=True, timeout=120
                )
                if result.returncode == 0:
                    # Look for the extracted model file
                    # pbi-tools produces: <extract_dir>/<pbix_stem>/Model/database.json
                    # or: <extract_dir>/Model/database.json
                    candidates = [
                        extract_dir / pbix_path.stem / "Model" / "database.json",
                        extract_dir / pbix_path.stem / "Model" / "model.bim",
                        extract_dir / "Model" / "database.json",
                        extract_dir / "Model" / "model.bim",
                    ]
                    # Also search recursively
                    found_bim = None
                    for candidate in candidates:
                        if candidate.exists():
                            found_bim = candidate
                            break
                    if not found_bim:
                        for f in extract_dir.rglob("database.json"):
                            found_bim = f; break
                    if not found_bim:
                        for f in extract_dir.rglob("model.bim"):
                            found_bim = f; break

                    if found_bim:
                        args.bim = str(found_bim)
                        print(f"  ✅ BIM extracted successfully: {found_bim}")
                        print()
                    else:
                        print(f"  ⚠️  pbi-tools ran but model file not found in {extract_dir}")
                        print(f"      stdout: {result.stdout[:200]}")
                        print("      Continuing without BIM...")
                        print()
                else:
                    print(f"  ⚠️  pbi-tools failed (exit code {result.returncode})")
                    print(f"      stderr: {result.stderr[:300]}")
                    print("      Continuing without BIM...")
                    print()
            except subprocess.TimeoutExpired:
                print("  ⚠️  pbi-tools timed out (>120s). Continuing without BIM...")
                print()
            except Exception as e:
                print(f"  ⚠️  pbi-tools error: {e}. Continuing without BIM...")
                print()
    is_pbip   = args.pbip is not None
    src_path  = args.pbip if is_pbip else args.pbix
    src_label = args.pbip if is_pbip else args.pbix

    timestamp   = datetime.now().isoformat()
    workbook_id = hashlib.md5(src_path.encode()).hexdigest()[:8]

    print(f"\n{'='*60}")
    print(f"  RE PBI VALIDATOR")
    print(f"  Format : {'PBIP (folder)' if is_pbip else 'PBIX (zip)'}")
    print(f"  Source : {src_path}")
    print(f"  JSON   : {args.json}")
    if args.bim:
        bim_src = " (auto-extracted via pbi-tools)" if getattr(args,"auto_extract_bim",False) else ""
        print(f"  BIM    : {args.bim}{bim_src}")
    elif not is_pbip:
        if getattr(args,"auto_extract_bim",False):
            print(f"  BIM    : (pbi-tools not available — DataModel binary only)")
        else:
            print(f"  BIM    : (not provided — use --bim or --auto-extract-bim for full semantic coverage)")
    print(f"  Run    : {timestamp}")
    if is_pbip:
        print(f"  Note   : D13 (model metadata) and D14 (PBIP report layer) checks enabled")
    else:
        print(f"  Note   : D13/D14 will mark PBIP-specific checks as N/A for PBIX source")
    print(f"  PG     : {'CSV only' if not args.pg else 'PostgreSQL enabled'}")
    print(f"{'='*60}")

    # -- Step 1: Extract source ------------------------------------
    if is_pbip:
        extractor = PBIPExtractor(args.pbip)
        pbix_data = extractor.extract_all()
    else:
        extractor = PBIXExtractor(args.pbix,
                                  work_dir=f"{args.out}/pbix_extracted")
        if args.bim:
            extractor._bim_override = args.bim  # used by _parse_bim_raw for M expression scan
        pbix_data = extractor.extract_all()

    # -- If --bim provided, inject it into pbix_data --------------
    if args.bim and Path(args.bim).exists():
        bim_path = Path(args.bim)
        print(f"\n[Extractor] Loading model from: {bim_path}")
        try:
            bim = json.loads(bim_path.read_text(encoding="utf-8-sig"))

            # -- Handle Tabular Editor "Save to Folder" structure --
            # When saved as folder, tables are split into tables/*.json
            # database.json has an empty tables[]  --  we must load them separately
            tables_dir = bim_path.parent / "tables"
            if tables_dir.exists() and tables_dir.is_dir():
                print(f"[Extractor] Detected folder structure  --  loading tables from {tables_dir}")

                all_items   = list(tables_dir.iterdir())
                json_files  = [x for x in all_items if x.is_file() and x.suffix == ".json"]
                subfolders  = [x for x in all_items if x.is_dir()]
                print(f"            Found {len(json_files)} table JSON files "
                      f"and {len(subfolders)} subfolders")

                loaded_tables = []

                def load_table_from_subfolder(sf: Path) -> dict:
                    """
                    Load a table object entirely from its subfolder.
                    Structure:
                      tables/TableName/
                          columns/ColumnName.json   ← one per column
                          partitions/TableName.json ← one per partition
                          measures/MeasureName.json ← one per measure (if any)
                    """
                    tbl_obj = {"name": sf.name, "columns": [],
                               "measures": [], "partitions": []}

                    # Check for a table-level JSON inside the subfolder itself
                    tbl_meta = sf / f"{sf.name}.json"
                    if not tbl_meta.exists():
                        # Try any .json directly in the subfolder root
                        root_jsons = [f for f in sf.iterdir()
                                      if f.is_file() and f.suffix == ".json"]
                        if root_jsons:
                            tbl_meta = root_jsons[0]

                    if tbl_meta and tbl_meta.exists():
                        try:
                            meta = json.loads(tbl_meta.read_text(encoding="utf-8-sig"))
                            if "table" in meta:
                                meta = meta["table"]
                            tbl_obj.update({k: v for k, v in meta.items()
                                            if k not in ("columns","measures","partitions")})
                        except Exception:
                            pass

                    # Load columns
                    cols_dir = sf / "columns"
                    if cols_dir.exists():
                        for col_file in sorted(cols_dir.glob("*.json")):
                            try:
                                col = json.loads(col_file.read_text(encoding="utf-8-sig"))
                                if "column" in col:
                                    col = col["column"]
                                tbl_obj["columns"].append(col)
                            except Exception:
                                pass

                    # Load measures (only exists for fact/calc tables)
                    meas_dir = sf / "measures"
                    if meas_dir.exists():
                        for m_file in sorted(meas_dir.glob("*.json")):
                            try:
                                m = json.loads(m_file.read_text(encoding="utf-8-sig"))
                                if "measure" in m:
                                    m = m["measure"]
                                tbl_obj["measures"].append(m)
                            except Exception:
                                pass

                    # Load partitions
                    parts_dir = sf / "partitions"
                    if parts_dir.exists():
                        for p_file in sorted(parts_dir.glob("*.json")):
                            try:
                                p = json.loads(p_file.read_text(encoding="utf-8-sig"))
                                if "partition" in p:
                                    p = p["partition"]
                                tbl_obj["partitions"].append(p)
                            except Exception:
                                pass

                    return tbl_obj

                # -- Case A: JSON files exist at tables/ level -------------
                if json_files:
                    for tbl_file in sorted(json_files):
                        try:
                            raw_tbl = json.loads(
                                tbl_file.read_text(encoding="utf-8-sig"))
                            if "table" in raw_tbl and isinstance(raw_tbl["table"], dict):
                                tbl_obj = raw_tbl["table"]
                            elif "name" in raw_tbl:
                                tbl_obj = raw_tbl
                            else:
                                print(f"            Skipping {tbl_file.name}  --  "
                                      f"keys: {list(raw_tbl.keys())[:5]}")
                                continue

                            tbl_name  = tbl_obj.get("name", tbl_file.stem)
                            # Supplement with subfolder data if available
                            sf = tbl_file.parent / tbl_file.stem
                            if sf.exists():
                                supplemented = load_table_from_subfolder(sf)
                                tbl_obj.setdefault("columns",    supplemented["columns"])
                                tbl_obj.setdefault("measures",   supplemented["measures"])
                                tbl_obj.setdefault("partitions", supplemented["partitions"])

                            n_cols = len(tbl_obj.get("columns", []))
                            n_meas = len(tbl_obj.get("measures", []))
                            print(f"            Loaded: {tbl_name:<45} "
                                  f"{n_cols:>3} cols  {n_meas:>3} measures")
                            loaded_tables.append(tbl_obj)
                        except Exception as e:
                            print(f"            Warning  --  {tbl_file.name}: {e}")

                # -- Case B: Only subfolders  --  no JSON at tables/ level ----
                else:
                    for sf in sorted(subfolders):
                        try:
                            tbl_obj  = load_table_from_subfolder(sf)
                            tbl_name = tbl_obj.get("name", sf.name)
                            n_cols   = len(tbl_obj.get("columns", []))
                            n_meas   = len(tbl_obj.get("measures", []))
                            print(f"            Loaded: {tbl_name:<45} "
                                  f"{n_cols:>3} cols  {n_meas:>3} measures")
                            loaded_tables.append(tbl_obj)
                        except Exception as e:
                            print(f"            Warning  --  {sf.name}: {e}")

                # Merge loaded tables into the model
                if "model" not in bim:
                    bim["model"] = {}
                bim["model"]["tables"] = loaded_tables

                # Load relationships from relationships/ folder if present
                rels_dir = bim_path.parent / "relationships"
                if rels_dir.exists():
                    rels = []
                    for rel_file in sorted(rels_dir.glob("*.json")):
                        try:
                            r = json.loads(rel_file.read_text(encoding="utf-8-sig"))
                            # Unwrap if needed
                            if "relationship" in r:
                                r = r["relationship"]
                            rels.append(r)
                        except Exception:
                            pass
                    if rels:
                        bim["model"]["relationships"] = rels
                        print(f"[Extractor] Loaded {len(rels)} relationship(s)")

                # Load roles from roles/ folder if present
                roles_dir = bim_path.parent / "roles"
                if roles_dir.exists():
                    roles = []
                    for role_file in sorted(roles_dir.glob("*.json")):
                        try:
                            ro = json.loads(role_file.read_text(encoding="utf-8-sig"))
                            if "role" in ro:
                                ro = ro["role"]
                            roles.append(ro)
                        except Exception:
                            pass
                    if roles:
                        bim["model"]["roles"] = roles
                        print(f"[Extractor] Loaded {len(roles)} role(s)")

            pbix_data["data_model"] = extractor._parse_bim(bim)

            # Override rls_roles from BIM model.roles[] -- SecurityBindings
            # in PBIX is DPAPI-encrypted and always returns [] when read from
            # a file. BIM is the only reliable source when --bim is supplied.
            bim_rls = pbix_data["data_model"].get("rls_roles", [])
            if bim_rls:
                pbix_data["rls_roles"] = bim_rls
                print(f"[Extractor] Loaded {len(bim_rls)} RLS role(s) from BIM: "
                      f"{[r['name'] for r in bim_rls]}")

            bim_data_sources = bim.get("model",{}).get("dataSources", [])
            if bim_data_sources:
                # BIM has explicit dataSources -- use them for connections
                pbix_data["connections"] = [
                    {
                        "name":            ds.get("name",""),
                        "server":          ds.get("connectionDetails",{}).get("server",""),
                        "database":        ds.get("connectionDetails",{}).get("database",""),
                        "connection_type": ds.get("type",""),
                        "auth_method":     ds.get("credential",{}).get("AuthenticationKind",""),
                        "gateway_id":      ds.get("gatewayId",""),
                    }
                    for ds in bim_data_sources
                ]
            # else: keep the M-expression-extracted connections (SharePoint/CSV/Web)
            # that were already populated by get_connections() during extract_all()
            n_tables  = len(pbix_data["data_model"].get("tables", []))
            n_conns   = len(pbix_data["connections"])
            n_rels    = len(pbix_data["data_model"].get("relationships", []))
            n_measures= sum(
                len(t.get("measures",[])) 
                for t in pbix_data["data_model"].get("tables",[])
            )
            print(f"[Extractor] Model loaded  --  "
                  f"{n_tables} tables, {n_measures} measures, "
                  f"{n_rels} relationships, {n_conns} connections")
        except Exception as e:
            print(f"[Extractor] Warning  --  could not parse model file: {e}")

    # -- Load homogeneous JSON ----------------
    with open(args.json, encoding="utf-8") as f:
        homo_json_raw = json.load(f)

    # Unwrap result envelope if present
    # RE/OP JSON format: {report_id, file_name, ..., result: {tables, relationships, ...}}
    if "result" in homo_json_raw and isinstance(homo_json_raw["result"], dict):
        homo_json = homo_json_raw["result"]
        print(f"  [Info] JSON unwrapped from 'result' envelope "
              f"(schema_version: {homo_json.get('schema_version','?')})")
    else:
        homo_json = homo_json_raw

    # -- Step 2: Determine validation mode ---
    # Auto-detect: dataset-only PBIX has Report/Layout with 0 or 1 empty page
    layout_pages = pbix_data.get("layout", {}).get("pages", [])
    total_visuals = sum(len(p.get("visuals",[])) for p in layout_pages)
    has_real_report = total_visuals > 0
    has_semantic    = bool(pbix_data.get("data_model", {}).get("tables"))

    if args.mode == "auto":
        if has_semantic and has_real_report:
            mode = "full"
        elif has_semantic and not has_real_report:
            mode = "semantic"
        elif has_real_report and not has_semantic:
            mode = "report"
        else:
            mode = "full"  # fallback: run everything, let checks self-report N/A
    else:
        mode = args.mode

    SEMANTIC_CHECKS = {"D1","D2","D3","D4","D5","D13"}
    REPORT_CHECKS   = {"D6","D7","D8","D9","D10","D11","D12","D14"}

    print(f"\n  Mode     : {mode.upper()}")
    if mode == "semantic":
        print(f"  Checks   : D1-D5, D13 (semantic layer only — report layer skipped)")
        print(f"  Reason   : Source has {total_visuals} visuals in Report/Layout "
              f"(dataset-only PBIX). Use --mode report for the Report PBIX.")
    elif mode == "report":
        print(f"  Checks   : D6-D14 (report layer only — semantic layer skipped)")
    else:
        print(f"  Checks   : D1-D9 (full)")

    # -- Step 3: Run validators --
    validator = RePBIValidator(pbix_data, homo_json)

    # If DataModel is binary (no tables extracted), use cross-validation mode
    # If pbixray was used, pull rls_roles from data_model into top-level
    if pbix_data.get("data_model", {}).get("_source") == "pbixray":
        pbixray_rls = pbix_data["data_model"].get("rls_roles", [])
        if pbixray_rls and not pbix_data.get("rls_roles"):
            pbix_data["rls_roles"] = pbixray_rls
            print(f"[pbixray] Loaded {len(pbixray_rls)} RLS role(s): "
                  f"{[r['name'] for r in pbixray_rls]}")

    model_is_binary = pbix_data.get("data_model", {}).get("raw_detected", False) or \
                      not pbix_data.get("data_model", {}).get("tables")

    if model_is_binary and not args.bim and mode != "report":
        print("\n" + "="*60)
        if not PBIXRAY_AVAILABLE:
            print("  DATAMODEL IS BINARY  --  install pbixray for full support:")
            print("  pip install pbixray")
            print("  Then re-run without --bim  --  pbixray handles all PBIX types")
        else:
            print("  DATAMODEL IS BINARY and pbixray returned no tables.")
            print("  This PBIX may be corrupted or use an unsupported format.")
        print("  Switching to cross-validation mode (report-layer checks only)")
        print("="*60 + "\n")
        validator.run_cross_validation_mode()
    else:
        validator.run_all()

    # -- Filter results to applicable checks only --
    results = validator.results
    if mode == "semantic":
        # Use exact set membership only -- DO NOT use [:2] slicing.
        # D13[:2]="D1" would pollute the set and let D10/D11/D12/D14
        # pass through (all start with "D1"), producing Report-layer rows
        # in a semantic-only run.
        results = [r for r in results
                   if r.check_id in SEMANTIC_CHECKS]
    elif mode == "report":
        results = [r for r in results
                   if r.check_id in REPORT_CHECKS]

    # -- Build report -------------------------
    report = ValidationReport(
        workbook_id = workbook_id,
        pbix_path   = args.pbix,
        json_path   = args.json,
        timestamp   = timestamp,
        results     = results,
    )

    # -- Step 3: Score and output -------------
    # Assign severity to every result
    for r in report.results:
        r.severity = assign_severity(r)

    reporter = Reporter(report, args.out, pg_enabled=args.pg)
    reporter.write_json()          # produces validation_report.json with embedded gap_report and excel_base64
    reporter.write_csv()           # produces validation_report.csv for human review
    reporter.write_gap_report()    # produces gap_report.json  --  MISSING/FAIL rows only, sorted by severity
    reporter.print_summary(mode=mode)

    exit(0 if report.verdict == "PASS" else 1)


if __name__ == "__main__":
    main()
