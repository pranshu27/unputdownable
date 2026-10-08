"""
fe_report_validator.py
======================
Validates a target PBIP Report folder against an Enriched (FE) Report JSON file.

Direction : Enriched JSON  →  PBIP  (JSON is source of truth, PBIP is validated)
Checks    : R1 – R18  (57 sub-checks)

Custom visuals: Checks for ANY custom visual (identified by GUID pattern or
'customVisual' type), not limited to specific visual names. Flags all custom
visuals that require manual download from AppSource.

Visual interactions (R17): Default Power BI behaviour = all visuals cross-filter
each other. Only validates when JSON explicitly captures interaction overrides.
If JSON has no overrides, checks that PBIP also has no unexpected overrides.

Sync slicers (R18): Validates cross-page slicer sync groups.

Usage
-----
python fe_report_validator.py \
    --json  path/to/enriched_report.json \
    --pbip  path/to/MyReport.Report \
    --out   ./output

Outputs
-------
  fe_report_<timestamp>_full.csv
  fe_report_<timestamp>_summary.json
  fe_report_<timestamp>_gaps.json        FAIL/MISSING/MISMATCH only
  fe_report_<timestamp>_deploy.json      Deployment action items (separate)
"""

import argparse, csv, json, os, re, sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    check_id:    str
    sub_id:      str
    status:      str          # PASS | FAIL | MISSING | MISMATCH | INFO
    severity:    str
    src_value:   Optional[str]
    tgt_value:   Optional[str]
    note:        str
    deploy_flag: bool = False


SEV_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}

CHECK_LABELS = {
    "R1":  "Pages",
    "R2":  "Visuals",
    "R3":  "Field Bindings",
    "R4":  "Visual Filters",
    "R5":  "Page Filters",
    "R6":  "Report Filters",
    "R7":  "Bookmarks",
    "R8":  "Theme & Page Backgrounds",
    "R9":  "Visual Formatting Objects",
    "R10": "Custom Visuals",
    "R11": "Button Actions & Navigation",
    "R12": "Conditional Formatting",
    "R13": "Tooltips",
    "R14": "Drillthrough",
    "R15": "Images & Logos",
    "R16": "HTML & Embedded Custom Visuals",
    "R17": "Visual Interactions (Edit Interactions)",
    "R18": "Sync Slicers (Cross-Page)",
    "R19": "Canvas Environment (displayArea, Filter Pane)",
    "R20": "Alt Text, Header Icons, Subtitle",
    "R21": "Card / KPI Formatting",
    "R22": "Slicer Controls",
    "R23": "Chart Axis & Series Detail",
    "R24": "Analytics Overlays (Trend Lines, Forecast)",
    "R25": "Visual-Type-Specific Checklist",
}
ALL_CHECKS = [f"R{i}" for i in range(1, 26)]

# GUID pattern used by Power BI for custom visuals
_GUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)

def _is_custom_visual_type(vtype: str) -> bool:
    """Returns True if the visual type looks like a custom visual GUID or is explicitly 'customVisual'."""
    if not vtype:
        return False
    vt = str(vtype).strip()
    return bool(_GUID_RE.fullmatch(vt)) or vt.lower() == "customvisual"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _norm(v) -> str:
    if v is None:
        return ""
    s = re.sub(r"\s+", " ", str(v)).strip().lower()
    return s.replace('"', "'")

def _sval(v) -> str:
    if v is None:
        return "None"
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)[:200]
    return str(v)

def _norm_queryref(qr: str) -> str:
    """Strip aggregation wrappers: Sum(Table.Col) → Table.Col"""
    qr = _norm(qr)
    m = re.match(r"^\w+\((.+)\)$", qr)
    return m.group(1).strip() if m else qr

def _read_json_file(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ─────────────────────────────────────────────────────────────────────────────
# PBIP Report extractor
# ─────────────────────────────────────────────────────────────────────────────

class PbipReportExtractor:
    """
    Reads a PBIP Report folder (schema v2.x).
    Key structure differences:
      - visual data under 'visual' key (not 'singleVisual')
      - projections: visual.query.queryState.<Role>.projections[].queryRef
      - z-order: position.z
      - hidden pages: page.json visibility == 'hidden'
      - page order from definition/pages/pages.json
    """

    def __init__(self, pbip_root: str):
        self.root = Path(pbip_root)
        self.defn = self.root / 'definition'
        if not self.defn.exists():
            candidate = self.root / (self.root.name + '.Report') / 'definition'
            if candidate.exists():
                self.defn = candidate
        self.pages_dir   = self.defn / 'pages'
        self.report_json = _read_json_file(self.defn / 'report.json')
        self.static_dir  = self.root / 'StaticResources'
        pages_meta = _read_json_file(self.pages_dir / 'pages.json')
        self._page_order = pages_meta.get('pageOrder', [])

    def pages(self) -> list:
        if not self.pages_dir.exists():
            return []
        result = []
        seen = set()
        ordered_dirs = []
        for folder in self._page_order:
            d = self.pages_dir / folder
            if d.is_dir():
                ordered_dirs.append(d)
                seen.add(folder)
        for d in sorted(self.pages_dir.iterdir()):
            if d.is_dir() and d.name not in seen:
                ordered_dirs.append(d)
        for page_dir in ordered_dirs:
            pj = _read_json_file(page_dir / 'page.json')
            if not pj:
                continue
            result.append({
                'name':          pj.get('displayName', page_dir.name),
                'folder':        page_dir.name,
                'dir':           page_dir,
                'raw':           pj,
                'isHidden':      pj.get('visibility', '') == 'hidden',
                'displayOption': pj.get('displayOption'),
                'width':         pj.get('width'),
                'height':        pj.get('height'),
                'filters':       pj.get('filters', []),
                'background':    pj.get('background'),
                'drillthrough':  pj.get('drillthrough', {}),
            })
        return result

    def page_by_name(self, name: str) -> Optional[dict]:
        for p in self.pages():
            if _norm(p['name']) == _norm(name):
                return p
        return None

    def visuals(self, page_dir: Path) -> list:
        vis_dir = page_dir / 'visuals'
        if not vis_dir.exists():
            return []
        result = []
        for v_dir in sorted(vis_dir.iterdir()):
            if not v_dir.is_dir():
                continue
            vj = _read_json_file(v_dir / 'visual.json')
            if not vj:
                continue
            sv  = vj.get('visual', vj.get('singleVisual', {}))
            pos = vj.get('position', {})
            projections = []
            for role, role_data in sv.get('query', {}).get('queryState', {}).items():
                for proj in role_data.get('projections', []):
                    projections.append({
                        'queryRef':  proj.get('queryRef', ''),
                        'role':      role,
                        'nativeRef': proj.get('nativeQueryRef', ''),
                    })
            result.append({
                'id':                  v_dir.name,
                'type':                sv.get('visualType', ''),
                'x':                   pos.get('x'),
                'y':                   pos.get('y'),
                'width':               pos.get('width'),
                'height':              pos.get('height'),
                'zOrder':              pos.get('z'),
                'filters':             sv.get('filters', []),
                'projections':         projections,
                'objects':             sv.get('objects', {}),
                'action':              sv.get('action', {}),
                'tooltipType':         sv.get('tooltipType', ''),
                'interactionSettings': sv.get('interactionSettings', vj.get('interactionSettings', {})),
                'syncSlicers':         sv.get('syncSlicers', vj.get('syncSlicers', {})),
                'raw':                 vj,
            })
        return result

    def report_filters(self) -> list:
        return self.report_json.get('filters', [])

    def bookmarks(self) -> list:
        return self.report_json.get('bookmarks', [])

    def theme(self) -> dict:
        theme_name = self.report_json.get('themeCollection', {}).get('name')
        for sub in ('SharedResources/BaseThemes', 'BaseThemes', 'SharedResources'):
            d = self.static_dir / sub
            if not d.exists():
                continue
            for f in d.glob('*.json'):
                try:
                    data = json.loads(f.read_text(encoding='utf-8'))
                    return {'name': theme_name or f.stem, 'data': data}
                except Exception:
                    pass
        return {'name': theme_name, 'data': {}}

    def static_files(self) -> set:
        if not self.static_dir.exists():
            return set()
        return {f.name.lower() for f in self.static_dir.rglob('*') if f.is_file()}

    def custom_visuals_manifest(self) -> list:
        result = []
        for p in self.root.rglob('pbiviz.json'):
            try:
                data = json.loads(p.read_text(encoding='utf-8'))
                visual = data.get('visual', data)
                result.append({
                    'name':    visual.get('displayName', visual.get('name', '')),
                    'guid':    visual.get('guid', ''),
                    'version': visual.get('version', ''),
                    'source':  str(p),
                })
            except Exception:
                pass
        return result


class EnrichedReportExtractor:
    """
    Adapts the actual RE/FE Report JSON schema.
    d['result']['visualizations']['pages'][] ->
      display_name, width, height,
      visuals[].{visual_type, position.{x,y,width,height,z_order},
                 fields[].{role,table,column,aggregation,query_ref},
                 filters[], tooltip_config, conditional_formatting}
    """

    def __init__(self, data: dict):
        if 'result' in data:
            self.r = data['result']
        elif 'visualizations' in data:
            self.r = data
        else:
            self.r = data.get('report', data)
        self._pages = self.r.get('visualizations', {}).get('pages', [])

    def pages(self) -> list:
        result = []
        for p in self._pages:
            visuals = []
            for v in p.get('visuals', []):
                pos = v.get('position', {})
                visuals.append({
                    'visual_type':          v.get('visual_type', ''),
                    'type':                 v.get('visual_type', ''),
                    'x':                    pos.get('x'),
                    'y':                    pos.get('y'),
                    'width':                pos.get('width'),
                    'height':               pos.get('height'),
                    'z_order':              pos.get('z_order'),
                    'zOrder':               pos.get('z_order'),
                    'fields':               v.get('fields', []),
                    'filters':              v.get('filters', []),
                    'visual_filters':       v.get('filters', []),
                    'conditional_formatting': v.get('conditional_formatting', {}),
                    'tooltip_config':       v.get('tooltip_config', {}),
                    'interaction_settings': v.get('interaction_settings', {}),
                    'sync_slicers':         v.get('sync_slicers', {}),
                    'action': {
                        'type':        v.get('button_type', ''),
                        'destination': v.get('navigation_target', ''),
                    } if (v.get('button_type') or v.get('navigation_target')) else {},
                })
            result.append({
                'name':           p.get('display_name', ''),
                'display_name':   p.get('display_name', ''),
                'width':          p.get('width'),
                'height':         p.get('height'),
                'canvas_width':   p.get('width'),
                'canvas_height':  p.get('height'),
                'is_hidden':      p.get('hidden', p.get('is_hidden', False)),
                'isHidden':       p.get('hidden', p.get('is_hidden', False)),
                'display_option': p.get('display_option'),
                'filters':        p.get('filters', []),
                'page_filters':   p.get('filters', []),
                'background':     p.get('background'),
                'drillthrough':   p.get('drillthrough', {}),
                'visuals':        visuals,
            })
        return result

    def report_filters(self) -> list:
        return self.r.get('report_filters', self.r.get('filters', []))

    def bookmarks(self) -> list:
        return self.r.get('bookmarks', [])

    def theme(self) -> dict:
        t = self.r.get('theme', {})
        return t if isinstance(t, dict) else {'name': str(t) if t else None}

    def custom_visuals(self) -> list:
        return self.r.get('custom_visuals', [])


class FEReportValidator:
    def __init__(self, json_path: str, pbip_path: str):
        raw = _read_json(json_path)
        self.src = EnrichedReportExtractor(raw)
        self.tgt = PbipReportExtractor(pbip_path)
        self.results:      list[CheckResult] = []
        self.deploy_flags: list[dict] = []

    def _log(self, cid, sid, status, sev, src, tgt, note, deploy=False):
        r = CheckResult(check_id=cid, sub_id=sid, status=status, severity=sev,
                        src_value=_sval(src), tgt_value=_sval(tgt), note=note,
                        deploy_flag=deploy)
        self.results.append(r)
        if deploy:
            self.deploy_flags.append({
                "check": f"{cid}.{sid}", "severity": sev,
                "note": note, "src": _sval(src)
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
    # R1 — Pages
    # ══════════════════════════════════════════════════════════════
    def check_r1_pages(self):
        print("[R1] Pages...")
        j_pages = self.src.pages()
        p_pages = self.tgt.pages()
        p_lower = {_norm(p["name"]): p for p in p_pages}

        # R1.1 count
        if len(j_pages) == len(p_pages):
            self._pass("R1", "page.count", "CRITICAL", len(j_pages), len(p_pages))
        else:
            self._mismatch("R1", "page.count", "CRITICAL", len(j_pages), len(p_pages),
                           f"Page count mismatch. JSON={len(j_pages)}, PBIP={len(p_pages)}.")

        for jp in j_pages:
            jname = jp.get("name", jp.get("display_name", "")) if isinstance(jp, dict) else str(jp)
            jdata = jp if isinstance(jp, dict) else {}

            # R1.2 existence
            pp = p_lower.get(_norm(jname))
            if not pp:
                self._missing("R1", f"page.exists[{jname}]", "CRITICAL", jname,
                              f"Page '{jname}' not found in PBIP definition/pages/.")
                continue
            self._pass("R1", f"page.exists[{jname}]", "CRITICAL", jname, pp["name"])

            # R1.3 canvas size
            jw = jdata.get("width", jdata.get("canvas_width"))
            jh = jdata.get("height", jdata.get("canvas_height"))
            if jw and jh:
                pw, ph = pp.get("width"), pp.get("height")
                if str(jw) == str(pw) and str(jh) == str(ph):
                    self._pass("R1", f"page.canvas[{jname}]", "HIGH", f"{jw}x{jh}", f"{pw}x{ph}")
                else:
                    self._mismatch("R1", f"page.canvas[{jname}]", "HIGH",
                                   f"{jw}x{jh}", f"{pw}x{ph}",
                                   f"Canvas size mismatch for page '{jname}'.")

            # R1.4 hidden flag
            j_hidden = jdata.get("is_hidden", jdata.get("isHidden", jdata.get("hidden", False)))
            p_hidden = pp.get("isHidden", False)
            if bool(j_hidden) != bool(p_hidden):
                self._mismatch("R1", f"page.isHidden[{jname}]", "HIGH", j_hidden, p_hidden,
                               f"Page hidden flag mismatch for '{jname}'. "
                               f"Tooltip and drillthrough pages must be hidden.")
            else:
                self._pass("R1", f"page.isHidden[{jname}]", "HIGH", j_hidden, p_hidden)

            # R1.5 displayOption
            jdo = jdata.get("display_option", jdata.get("displayOption"))
            pdo = pp.get("displayOption")
            if jdo is not None and str(jdo) != str(pdo):
                self._mismatch("R1", f"page.displayOption[{jname}]", "MEDIUM", jdo, pdo,
                               f"Display option mismatch for page '{jname}'.")
            elif jdo is not None:
                self._pass("R1", f"page.displayOption[{jname}]", "MEDIUM", jdo, pdo)

    # ══════════════════════════════════════════════════════════════
    # R2 — Visuals
    # ══════════════════════════════════════════════════════════════
    def check_r2_visuals(self):
        print("[R2] Visuals...")
        p_pages = {_norm(p["name"]): p for p in self.tgt.pages()}

        for jp in self.src.pages():
            jname = jp.get("name", "") if isinstance(jp, dict) else str(jp)
            pp = p_pages.get(_norm(jname))
            if not pp:
                continue

            j_visuals = jp.get("visuals", []) if isinstance(jp, dict) else []
            p_visuals  = self.tgt.visuals(pp["dir"])

            # R2.1 count
            if len(j_visuals) == len(p_visuals):
                self._pass("R2", f"visual.count[{jname}]", "CRITICAL",
                           len(j_visuals), len(p_visuals))
            else:
                self._mismatch("R2", f"visual.count[{jname}]", "CRITICAL",
                               len(j_visuals), len(p_visuals),
                               f"Visual count mismatch on page '{jname}'. "
                               f"JSON={len(j_visuals)}, PBIP={len(p_visuals)}.")

            # Match visuals by position (x,y) as primary key
            def _pos_key(v):
                if isinstance(v, dict):
                    x = v.get("x", v.get("position", {}).get("x"))
                    y = v.get("y", v.get("position", {}).get("y"))
                    return (str(x), str(y))
                return (None, None)

            p_vis_map = {_pos_key(v): v for v in p_visuals}

            for jv in j_visuals:
                jdata = jv if isinstance(jv, dict) else {}
                jtype = jdata.get("visual_type", jdata.get("type", ""))
                jx    = jdata.get("x", jdata.get("position", {}).get("x"))
                jy    = jdata.get("y", jdata.get("position", {}).get("y"))
                jw    = jdata.get("width", jdata.get("position", {}).get("width"))
                jh    = jdata.get("height", jdata.get("position", {}).get("height"))
                label = f"{jname}@({jx},{jy})"

                pv = p_vis_map.get((str(jx), str(jy)))
                if not pv:
                    self._missing("R2", f"visual.exists[{label}]", "CRITICAL",
                                  f"{jtype}@({jx},{jy})",
                                  f"Visual of type '{jtype}' at position ({jx},{jy}) not found in PBIP page '{jname}'.")
                    continue

                # R2.2 type
                ptype = pv.get("type", "")
                if _norm(jtype) != _norm(ptype):
                    self._mismatch("R2", f"visual.type[{label}]", "CRITICAL",
                                   jtype, ptype,
                                   f"Visual type mismatch at ({jx},{jy}) on page '{jname}'.")
                else:
                    self._pass("R2", f"visual.type[{label}]", "CRITICAL", jtype, ptype)

                # R2.3 bounding box
                for dim, jval, pval in [("width", jw, pv.get("width")),
                                         ("height", jh, pv.get("height"))]:
                    if jval is not None and str(jval) != str(pval):
                        self._mismatch("R2", f"visual.{dim}[{label}]", "HIGH",
                                       jval, pval, f"Visual {dim} mismatch at ({jx},{jy}).")
                    elif jval is not None:
                        self._pass("R2", f"visual.{dim}[{label}]", "HIGH", jval, pval)

                # R2.4 z-order
                jz = jdata.get("z_order", jdata.get("zOrder"))
                pz = pv.get("zOrder")
                if jz is not None and str(jz) != str(pz):
                    self._mismatch("R2", f"visual.zOrder[{label}]", "HIGH", jz, pz,
                                   f"z-order mismatch at ({jx},{jy}) on '{jname}'. "
                                   "Affects overlapping visual layering.")
                elif jz is not None:
                    self._pass("R2", f"visual.zOrder[{label}]", "HIGH", jz, pz)

    # ══════════════════════════════════════════════════════════════
    # R3 — Field bindings
    # ══════════════════════════════════════════════════════════════
    def check_r3_field_bindings(self):
        print("[R3] Field bindings...")
        p_pages = {_norm(p["name"]): p for p in self.tgt.pages()}

        for jp in self.src.pages():
            jname = jp.get("name", "") if isinstance(jp, dict) else str(jp)
            pp = p_pages.get(_norm(jname))
            if not pp:
                continue
            p_vis_map = {(_norm_queryref(str(v.get("x"))), _norm_queryref(str(v.get("y")))): v
                         for v in self.tgt.visuals(pp["dir"])}

            for jv in (jp.get("visuals", []) if isinstance(jp, dict) else []):
                jdata = jv if isinstance(jv, dict) else {}
                jx, jy = str(jdata.get("x", "")), str(jdata.get("y", ""))
                label  = f"{jname}@({jx},{jy})"
                pv     = p_vis_map.get((_norm_queryref(jx), _norm_queryref(jy)))
                if not pv:
                    continue

                j_fields = jdata.get("fields", jdata.get("field_bindings", []))
                if not j_fields:
                    continue

                # Build sets of normalised queryRefs from PBIP projections
                # p_refs_count: one entry per projection (for count check)
                # p_refs_match: includes both normalised forms (for existence check)
                p_refs_count = set()
                p_refs_match = set()
                for sel in pv.get("projections", []):
                    if isinstance(sel, dict):
                        qr = sel.get("queryRef", sel.get("nativeRef", sel.get("NativeReferenceName", "")))
                        if qr:
                            p_refs_count.add(_norm_queryref(qr))
                            p_refs_match.add(_norm_queryref(qr))
                            p_refs_match.add(_norm(qr))
                p_refs = p_refs_match  # alias for existence checks below

                if isinstance(j_fields, list):
                    j_fields_flat = j_fields
                elif isinstance(j_fields, dict):
                    j_fields_flat = []
                    for role, flds in j_fields.items():
                        if isinstance(flds, list):
                            j_fields_flat.extend(flds)
                        else:
                            j_fields_flat.append(flds)
                else:
                    j_fields_flat = []

                # R3.1 count
                if len(j_fields_flat) != len(p_refs_count) and len(p_refs_count) > 0:
                    self._mismatch("R3", f"fields.count[{label}]", "HIGH",
                                   len(j_fields_flat), len(p_refs_count),
                                   f"Field binding count mismatch for visual at ({jx},{jy}) on '{jname}'.")
                elif p_refs_count:
                    self._pass("R3", f"fields.count[{label}]", "HIGH",
                               len(j_fields_flat), len(p_refs_count))

                # R3.2 each field exists in PBIP
                # JSON field has query_ref (actual schema field name)
                for jf in j_fields_flat:
                    if isinstance(jf, dict):
                        # Prefer query_ref (actual JSON schema key), fallback to name
                        fname = jf.get("query_ref", jf.get("queryRef", jf.get("name", str(jf))))
                    else:
                        fname = str(jf)
                    fnorm = _norm_queryref(fname)
                    fnorm2 = _norm(fname)
                    if fnorm not in p_refs and fnorm2 not in p_refs:
                        self._missing("R3", f"field.queryRef[{label}.{fname[:60]}]", "HIGH",
                                      fname,
                                      f"Field '{fname}' from JSON not found in PBIP visual at ({jx},{jy}).")
                    else:
                        self._pass("R3", f"field.queryRef[{label}.{fname[:60]}]", "HIGH",
                                   fname, "found in projections")

                    # R3.3 stale name check
                    enriched_name = jf.get("enriched_name", None) if isinstance(jf, dict) else None
                    if enriched_name and enriched_name != fname:
                        if _norm_queryref(enriched_name) not in p_refs and fnorm in p_refs:
                            self._mismatch("R3", f"field.staleName[{label}.{fname[:50]}]", "HIGH",
                                           enriched_name, fname,
                                           f"Visual at ({jx},{jy}) uses pre-enrichment field name '{fname}' "
                                           f"instead of enriched name '{enriched_name}'.")

    # ══════════════════════════════════════════════════════════════
    # R4 — Visual-level filters
    # ══════════════════════════════════════════════════════════════
    def check_r4_visual_filters(self):
        print("[R4] Visual filters...")
        p_pages = {_norm(p["name"]): p for p in self.tgt.pages()}

        for jp in self.src.pages():
            jname = jp.get("name", "") if isinstance(jp, dict) else str(jp)
            pp = p_pages.get(_norm(jname))
            if not pp:
                continue
            p_vis_list = self.tgt.visuals(pp["dir"])
            p_vis_map  = {(str(v.get("x")), str(v.get("y"))): v for v in p_vis_list}

            for jv in (jp.get("visuals", []) if isinstance(jp, dict) else []):
                jdata = jv if isinstance(jv, dict) else {}
                jx, jy = str(jdata.get("x", "")), str(jdata.get("y", ""))
                label  = f"{jname}@({jx},{jy})"
                pv     = p_vis_map.get((jx, jy))
                if not pv:
                    continue

                j_filters = jdata.get("visual_filters", jdata.get("filters", []))
                p_filters  = pv.get("filters", [])

                # R4.1 count
                if len(j_filters) == len(p_filters):
                    self._pass("R4", f"vfilter.count[{label}]", "CRITICAL",
                               len(j_filters), len(p_filters))
                else:
                    self._mismatch("R4", f"vfilter.count[{label}]", "CRITICAL",
                                   len(j_filters), len(p_filters),
                                   f"Visual filter count mismatch at ({jx},{jy}) on '{jname}'.")

                # R4.2 filter fields
                for i, jf in enumerate(j_filters):
                    jfield = jf.get("target", jf.get("field", "")) if isinstance(jf, dict) else str(jf)
                    jftype = jf.get("type", jf.get("filter_type", "")) if isinstance(jf, dict) else ""
                    if i < len(p_filters):
                        pf = p_filters[i]
                        pfield = pf.get("target", pf.get("field", "")) if isinstance(pf, dict) else str(pf)
                        if _norm(jfield) != _norm(pfield):
                            self._mismatch("R4", f"vfilter.field[{label}.{i}]", "HIGH",
                                           jfield, pfield,
                                           f"Visual filter field mismatch at position {i} on visual ({jx},{jy}).")
                        else:
                            self._pass("R4", f"vfilter.field[{label}.{i}]", "HIGH", jfield, pfield)

                    # R4.3 isHiddenInViewMode
                    j_hidden = jf.get("is_hidden_in_view_mode", jf.get("isHiddenInViewMode", False)) if isinstance(jf, dict) else False
                    if i < len(p_filters):
                        p_hidden = p_filters[i].get("isHiddenInViewMode", False) if isinstance(p_filters[i], dict) else False
                        if bool(j_hidden) != bool(p_hidden):
                            self._mismatch("R4", f"vfilter.hidden[{label}.{i}]", "HIGH",
                                           j_hidden, p_hidden,
                                           f"isHiddenInViewMode mismatch for visual filter {i} at ({jx},{jy}).")
                        else:
                            self._pass("R4", f"vfilter.hidden[{label}.{i}]", "HIGH", j_hidden, p_hidden)

    # ══════════════════════════════════════════════════════════════
    # R5 — Page-level filters
    # ══════════════════════════════════════════════════════════════
    def check_r5_page_filters(self):
        print("[R5] Page filters...")
        p_pages = {_norm(p["name"]): p for p in self.tgt.pages()}

        for jp in self.src.pages():
            jname = jp.get("name", "") if isinstance(jp, dict) else str(jp)
            pp = p_pages.get(_norm(jname))
            if not pp:
                continue

            j_filters = jp.get("page_filters", jp.get("filters", [])) if isinstance(jp, dict) else []
            p_filters  = pp.get("filters", [])

            # R5.1 count
            if len(j_filters) == len(p_filters):
                self._pass("R5", f"pgfilter.count[{jname}]", "HIGH",
                           len(j_filters), len(p_filters))
            else:
                self._mismatch("R5", f"pgfilter.count[{jname}]", "HIGH",
                               len(j_filters), len(p_filters),
                               f"Page filter count mismatch for page '{jname}'.")

            for i, jf in enumerate(j_filters):
                jfield = jf.get("target", jf.get("field", "")) if isinstance(jf, dict) else str(jf)
                # R5.2 field
                if i < len(p_filters):
                    pf = p_filters[i]
                    pfield = pf.get("target", pf.get("field", "")) if isinstance(pf, dict) else str(pf)
                    if _norm(jfield) != _norm(pfield):
                        self._mismatch("R5", f"pgfilter.field[{jname}.{i}]", "HIGH",
                                       jfield, pfield, f"Page filter field mismatch at position {i}.")
                    else:
                        self._pass("R5", f"pgfilter.field[{jname}.{i}]", "HIGH", jfield, pfield)

                # R5.3 isHiddenInViewMode
                j_hidden = jf.get("is_hidden_in_view_mode", jf.get("isHiddenInViewMode", False)) if isinstance(jf, dict) else False
                if i < len(p_filters):
                    p_hidden = p_filters[i].get("isHiddenInViewMode", False) if isinstance(p_filters[i], dict) else False
                    if bool(j_hidden) != bool(p_hidden):
                        self._mismatch("R5", f"pgfilter.hidden[{jname}.{i}]", "HIGH",
                                       j_hidden, p_hidden,
                                       f"isHiddenInViewMode mismatch for page filter {i} on '{jname}'.")
                    else:
                        self._pass("R5", f"pgfilter.hidden[{jname}.{i}]", "HIGH", j_hidden, p_hidden)

    # ══════════════════════════════════════════════════════════════
    # R6 — Report-level filters
    # ══════════════════════════════════════════════════════════════
    def check_r6_report_filters(self):
        print("[R6] Report filters...")
        j_filters = self.src.report_filters()
        p_filters  = self.tgt.report_filters()

        # R6.1 count
        if len(j_filters) == len(p_filters):
            self._pass("R6", "rptfilter.count", "HIGH", len(j_filters), len(p_filters))
        else:
            self._mismatch("R6", "rptfilter.count", "HIGH", len(j_filters), len(p_filters),
                           f"Report filter count mismatch. JSON={len(j_filters)}, PBIP={len(p_filters)}.")

        # R6.2 fields
        for i, jf in enumerate(j_filters):
            jfield = jf.get("target", jf.get("field", "")) if isinstance(jf, dict) else str(jf)
            if i < len(p_filters):
                pf = p_filters[i]
                pfield = pf.get("target", pf.get("field", "")) if isinstance(pf, dict) else str(pf)
                if _norm(jfield) != _norm(pfield):
                    self._mismatch("R6", f"rptfilter.field[{i}]", "HIGH", jfield, pfield,
                                   f"Report filter field mismatch at position {i}.")
                else:
                    self._pass("R6", f"rptfilter.field[{i}]", "HIGH", jfield, pfield)

    # ══════════════════════════════════════════════════════════════
    # R7 — Bookmarks
    # ══════════════════════════════════════════════════════════════
    def check_r7_bookmarks(self):
        print("[R7] Bookmarks...")
        j_bmarks = self.src.bookmarks()
        p_bmarks  = self.tgt.bookmarks()

        if not j_bmarks:
            self._info("R7", "bookmarks.present", "none", "No bookmarks in JSON — N/A")
            return

        # R7.1 count
        if len(j_bmarks) == len(p_bmarks):
            self._pass("R7", "bookmark.count", "MEDIUM", len(j_bmarks), len(p_bmarks))
        else:
            self._mismatch("R7", "bookmark.count", "MEDIUM", len(j_bmarks), len(p_bmarks),
                           f"Bookmark count mismatch. JSON={len(j_bmarks)}, PBIP={len(p_bmarks)}.")

        p_bmark_lower = {}
        for pb in p_bmarks:
            bname = pb.get("displayName", pb.get("name", "")) if isinstance(pb, dict) else str(pb)
            p_bmark_lower[_norm(bname)] = pb

        for jb in j_bmarks:
            jbname = jb.get("name", jb.get("displayName", "")) if isinstance(jb, dict) else str(jb)
            jbdata = jb if isinstance(jb, dict) else {}

            # R7.2 name
            pb = p_bmark_lower.get(_norm(jbname))
            if not pb:
                self._missing("R7", f"bookmark.exists[{jbname}]", "MEDIUM", jbname,
                              f"Bookmark '{jbname}' not found in PBIP report.json.")
                continue
            self._pass("R7", f"bookmark.exists[{jbname}]", "MEDIUM", jbname, jbname)

            # R7.3 visual states
            j_states = jbdata.get("visual_states", jbdata.get("explorationState", {}))
            p_states  = pb.get("explorationState", {}) if isinstance(pb, dict) else {}
            if j_states and not p_states:
                self._missing("R7", f"bookmark.visualStates[{jbname}]", "HIGH",
                              _sval(j_states),
                              f"Bookmark '{jbname}' has visual states in JSON but none captured in PBIP.")
            elif j_states:
                self._pass("R7", f"bookmark.visualStates[{jbname}]", "HIGH",
                           "states present", "states present")

            # R7.4 filter states
            j_filter_state = jbdata.get("filter_state", jbdata.get("filters", {}))
            p_filter_state = pb.get("filters", {}) if isinstance(pb, dict) else {}
            if j_filter_state and not p_filter_state:
                self._missing("R7", f"bookmark.filterState[{jbname}]", "HIGH",
                              _sval(j_filter_state),
                              f"Bookmark '{jbname}' has filter state in JSON but none in PBIP.")
            elif j_filter_state:
                self._pass("R7", f"bookmark.filterState[{jbname}]", "HIGH",
                           "filter state present", "filter state present")

    # ══════════════════════════════════════════════════════════════
    # R8 — Theme & page backgrounds
    # ══════════════════════════════════════════════════════════════
    def check_r8_theme(self):
        print("[R8] Theme & backgrounds...")
        j_theme = self.src.theme()
        p_theme  = self.tgt.theme()

        # R8.1 theme name
        jtn = j_theme.get("name", j_theme) if isinstance(j_theme, dict) else str(j_theme)
        ptn = p_theme.get("name")
        if jtn and _norm(jtn) != _norm(ptn):
            self._mismatch("R8", "theme.name", "HIGH", jtn, ptn,
                           "Theme name mismatch. Target PBIP may apply wrong visual styling.")
        elif jtn:
            self._pass("R8", "theme.name", "HIGH", jtn, ptn)

        # R8.2 dataColors
        j_colors = j_theme.get("dataColors", []) if isinstance(j_theme, dict) else []
        p_colors  = p_theme.get("data", {}).get("dataColors", []) if isinstance(p_theme, dict) else []
        if j_colors:
            if len(j_colors) == len(p_colors):
                self._pass("R8", "theme.dataColors.count", "HIGH",
                           len(j_colors), len(p_colors))
            else:
                self._mismatch("R8", "theme.dataColors.count", "HIGH",
                               len(j_colors), len(p_colors),
                               "dataColors palette count mismatch.")
            if j_colors and p_colors and _norm(j_colors[0]) != _norm(p_colors[0]):
                self._mismatch("R8", "theme.dataColors.primary", "HIGH",
                               j_colors[0], p_colors[0], "Primary theme color mismatch.")
            elif j_colors and p_colors:
                self._pass("R8", "theme.dataColors.primary", "HIGH", j_colors[0], p_colors[0])

        # R8.3 page backgrounds
        p_pages_map = {_norm(p["name"]): p for p in self.tgt.pages()}
        for jp in self.src.pages():
            jname = jp.get("name", "") if isinstance(jp, dict) else str(jp)
            pp = p_pages_map.get(_norm(jname))
            if not pp:
                continue
            j_bg = jp.get("background", jp.get("has_background", False)) if isinstance(jp, dict) else False
            p_bg = pp.get("background")
            j_has_bg = bool(j_bg)
            p_has_bg = bool(p_bg)
            if j_has_bg != p_has_bg:
                self._mismatch("R8", f"page.background[{jname}]", "MEDIUM",
                               j_has_bg, p_has_bg,
                               f"Page background presence mismatch for '{jname}'.")
            else:
                self._pass("R8", f"page.background[{jname}]", "MEDIUM", j_has_bg, p_has_bg)

        # R8.4 background image files in StaticResources
        p_static = self.tgt.static_files()
        for jp in self.src.pages():
            jdata = jp if isinstance(jp, dict) else {}
            bg_file = jdata.get("background_image", jdata.get("background_file"))
            if bg_file:
                if bg_file.lower() in p_static:
                    self._pass("R8", f"page.bgFile[{bg_file}]", "MEDIUM", bg_file, "found")
                else:
                    self._missing("R8", f"page.bgFile[{bg_file}]", "MEDIUM", bg_file,
                                  f"Background image file '{bg_file}' not found in PBIP StaticResources/.")

    # ══════════════════════════════════════════════════════════════
    # R9 — Visual formatting objects
    # ══════════════════════════════════════════════════════════════
    def check_r9_formatting(self):
        print("[R9] Visual formatting objects...")
        p_pages = {_norm(p["name"]): p for p in self.tgt.pages()}
        FMT_KEYS = {"labels", "categoryLabels", "categoryAxis", "valueAxis",
                    "legend", "dataPoint", "background", "border", "title",
                    "plotArea", "xAxis", "yAxis", "wordWrap", "values"}

        for jp in self.src.pages():
            jname = jp.get("name", "") if isinstance(jp, dict) else str(jp)
            pp = p_pages.get(_norm(jname))
            if not pp:
                continue
            p_vis_map = {(str(v.get("x")), str(v.get("y"))): v
                         for v in self.tgt.visuals(pp["dir"])}

            for jv in (jp.get("visuals", []) if isinstance(jp, dict) else []):
                jdata  = jv if isinstance(jv, dict) else {}
                jx, jy = str(jdata.get("x", "")), str(jdata.get("y", ""))
                label  = f"{jname}@({jx},{jy})"
                pv     = p_vis_map.get((jx, jy))
                if not pv:
                    continue

                j_fmt  = jdata.get("formatting", jdata.get("objects", {}))
                p_objs = pv.get("objects", {})

                if not j_fmt:
                    # R9.3 canvas shapes
                    jtype = jdata.get("visual_type", jdata.get("type", ""))
                    if jtype in ("shape", "basicShape", "line", "rectangle", "oval"):
                        jfill  = jdata.get("fill_color", jdata.get("fill"))
                        jbord  = jdata.get("border_color", jdata.get("border"))
                        pfill  = p_objs.get("background", [{}])[0].get("properties", {}).get("color", {})
                        if jfill and not pfill:
                            self._missing("R9", f"shape.fill[{label}]", "MEDIUM", jfill,
                                          f"Canvas shape at ({jx},{jy}) missing fill color in PBIP.")
                        elif jfill:
                            self._pass("R9", f"shape.fill[{label}]", "MEDIUM", jfill, pfill)
                    continue

                # R9.1 formatting categories
                j_keys = set(j_fmt.keys()) & FMT_KEYS if isinstance(j_fmt, dict) else set()
                p_keys = set(p_objs.keys()) & FMT_KEYS
                missing_fmt = j_keys - p_keys
                for mk in missing_fmt:
                    self._missing("R9", f"fmt.category[{label}.{mk}]", "MEDIUM",
                                  mk, f"Formatting object '{mk}' missing from visual at ({jx},{jy}).")
                if not missing_fmt and j_keys:
                    self._pass("R9", f"fmt.categories[{label}]", "MEDIUM",
                               list(j_keys), list(p_keys & j_keys))

                # R9.2 spot-check key properties per present category
                for fkey in j_keys & p_keys:
                    j_props = j_fmt.get(fkey, {})
                    p_items = p_objs.get(fkey, [{}])
                    p_props = p_items[0].get("properties", {}) if p_items else {}
                    for prop_name, jval in (j_props.items() if isinstance(j_props, dict) else []):
                        pval = p_props.get(prop_name)
                        if jval is not None and pval is not None and _norm(str(jval)) != _norm(str(pval)):
                            self._mismatch("R9", f"fmt.prop[{label}.{fkey}.{prop_name}]", "MEDIUM",
                                           jval, pval,
                                           f"Formatting property '{fkey}.{prop_name}' mismatch at ({jx},{jy}).")
                        elif jval is not None and pval is not None:
                            self._pass("R9", f"fmt.prop[{label}.{fkey}.{prop_name}]", "MEDIUM",
                                       jval, pval)

    # ══════════════════════════════════════════════════════════════
    # R10 — Custom visuals (generic — any GUID-type visual)
    # ══════════════════════════════════════════════════════════════
    def check_r10_custom_visuals(self):
        print("[R10] Custom visuals...")
        # Collect all custom visual types from JSON
        j_custom = {}
        for jp in self.src.pages():
            for jv in (jp.get("visuals", []) if isinstance(jp, dict) else []):
                jdata = jv if isinstance(jv, dict) else {}
                vtype = jdata.get("visual_type", jdata.get("type", ""))
                if _is_custom_visual_type(vtype):
                    vname = jdata.get("visual_name", jdata.get("name", vtype))
                    j_custom[_norm(vtype)] = {"type": vtype, "name": vname}

        # Also from explicit custom_visuals list in JSON
        for cv in self.src.custom_visuals():
            guid = cv.get("guid", cv.get("type", "")) if isinstance(cv, dict) else str(cv)
            name = cv.get("name", cv.get("display_name", guid)) if isinstance(cv, dict) else guid
            if guid:
                j_custom[_norm(guid)] = {"type": guid, "name": name}

        if not j_custom:
            self._info("R10", "custom_visuals.present", "none", "No custom visuals in JSON — N/A")
            return

        # PBIP custom visual manifests
        p_manifests = self.tgt.custom_visuals_manifest()
        p_guid_map  = {_norm(m["guid"]): m for m in p_manifests if m["guid"]}
        p_name_map  = {_norm(m["name"]): m for m in p_manifests if m["name"]}

        # PBIP visual.json GUIDs in use on pages
        p_page_guids = set()
        for pg in self.tgt.pages():
            for pv in self.tgt.visuals(pg["dir"]):
                vt = pv.get("type", "")
                if _is_custom_visual_type(vt):
                    p_page_guids.add(_norm(vt))

        for guid_norm, cv_info in j_custom.items():
            vtype  = cv_info["type"]
            vname  = cv_info["name"]
            label  = vname or vtype

            # R10.1 GUID in PBIP page visuals
            if guid_norm in p_page_guids:
                self._pass("R10", f"cv.guid[{label}]", "CRITICAL", vtype, "found in PBIP visuals")
            else:
                self._missing("R10", f"cv.guid[{label}]", "CRITICAL", vtype,
                              f"Custom visual GUID '{vtype}' ({vname}) not found in any PBIP page visual. "
                              "Visual may be missing or substituted with a native visual.")

            # R10.2 manifest in pbiviz.json
            pm = p_guid_map.get(guid_norm) or p_name_map.get(_norm(vname))
            if pm:
                j_ver = cv_info.get("version") if isinstance(cv_info, dict) else None
                p_ver = pm.get("version")
                if j_ver and _norm(j_ver) != _norm(p_ver):
                    self._mismatch("R10", f"cv.version[{label}]", "HIGH",
                                   j_ver, p_ver,
                                   f"Custom visual version mismatch for '{label}'. "
                                   f"JSON expects {j_ver}, PBIP has {p_ver}.")
                else:
                    self._pass("R10", f"cv.version[{label}]", "HIGH",
                               j_ver or "any", p_ver or "found")
            else:
                self._missing("R10", f"cv.manifest[{label}]", "HIGH", label,
                              f"No pbiviz.json manifest found for custom visual '{label}' ({vtype}). "
                              "Custom visual must be downloaded from AppSource and added to PBIP manually.")

            # R10.3 deployment flag for all custom visuals
            self._log("R10", f"cv.deploy[{label}]", "INFO", "HIGH",
                      label, "manual AppSource install required",
                      f"Custom visual '{label}' (GUID: {vtype}) requires manual installation from "
                      f"AppSource into the PBIP file. PBIP cannot embed certified custom visuals automatically. "
                      f"Deployment team must install before publishing to Fabric workspace.",
                      deploy=True)

    # ══════════════════════════════════════════════════════════════
    # R11 — Button actions & navigation
    # ══════════════════════════════════════════════════════════════
    def check_r11_buttons(self):
        print("[R11] Button actions & navigation...")
        p_pages = {_norm(p["name"]): p for p in self.tgt.pages()}

        for jp in self.src.pages():
            jname = jp.get("name", "") if isinstance(jp, dict) else str(jp)
            pp = p_pages.get(_norm(jname))
            if not pp:
                continue
            p_vis_map = {(str(v.get("x")), str(v.get("y"))): v
                         for v in self.tgt.visuals(pp["dir"])}

            for jv in (jp.get("visuals", []) if isinstance(jp, dict) else []):
                jdata  = jv if isinstance(jv, dict) else {}
                jtype  = jdata.get("visual_type", jdata.get("type", ""))
                if jtype not in ("button", "actionButton", "navigationButton", "shape"):
                    j_action = jdata.get("action", {})
                    if not j_action:
                        continue
                jx, jy = str(jdata.get("x", "")), str(jdata.get("y", ""))
                label  = f"{jname}@({jx},{jy})"
                pv     = p_vis_map.get((jx, jy))
                if not pv:
                    continue

                j_action = jdata.get("action", {}) if isinstance(jdata, dict) else {}
                if not j_action:
                    continue

                j_action_type = j_action.get("type", j_action.get("action_type", ""))
                p_action       = pv.get("action", {}) if isinstance(pv, dict) else {}
                p_action_type  = p_action.get("type", "")

                # R11.1 action type
                if _norm(j_action_type) != _norm(p_action_type):
                    self._mismatch("R11", f"btn.actionType[{label}]", "HIGH",
                                   j_action_type, p_action_type,
                                   f"Button action type mismatch at ({jx},{jy}) on '{jname}'.")
                else:
                    self._pass("R11", f"btn.actionType[{label}]", "HIGH",
                               j_action_type, p_action_type)

                # R11.2 target (page or bookmark)
                j_dest = j_action.get("destination", j_action.get("target", j_action.get("bookmark")))
                p_dest = p_action.get("destination", p_action.get("target", p_action.get("bookmark")))
                if j_dest and _norm(str(j_dest)) != _norm(str(p_dest) if p_dest else ""):
                    self._mismatch("R11", f"btn.dest[{label}]", "HIGH", j_dest, p_dest,
                                   f"Button action destination mismatch at ({jx},{jy}).")
                elif j_dest:
                    self._pass("R11", f"btn.dest[{label}]", "HIGH", j_dest, p_dest)

                # R11.3 URL target
                j_url = j_action.get("url", j_action.get("uri"))
                if j_url:
                    p_url = p_action.get("url", p_action.get("uri"))
                    if _norm(j_url) != _norm(p_url):
                        self._mismatch("R11", f"btn.url[{label}]", "MEDIUM", j_url, p_url,
                                       f"Button URL target mismatch at ({jx},{jy}). "
                                       "Check for environment-specific URL differences.")
                    else:
                        self._pass("R11", f"btn.url[{label}]", "MEDIUM", j_url, p_url)

                # R11.4 Power Automate deployment flag
                if "powerautomate" in _norm(j_action_type) or "flow" in _norm(j_action_type):
                    self._log("R11", f"btn.powerAutomate[{label}]", "INFO", "HIGH",
                              label, "manual re-linking required",
                              f"Power Automate button at ({jx},{jy}) on '{jname}'. "
                              "Flow IDs are environment-specific and must be re-linked in target workspace.",
                              deploy=True)

    # ══════════════════════════════════════════════════════════════
    # R12 — Conditional formatting
    # ══════════════════════════════════════════════════════════════
    def check_r12_conditional_formatting(self):
        print("[R12] Conditional formatting...")
        p_pages = {_norm(p["name"]): p for p in self.tgt.pages()}
        CF_KEYS = {"colorRules", "iconSets", "dataBarFormatting", "colorScale",
                   "backgroundColorRule", "fontColorRule"}

        for jp in self.src.pages():
            jname = jp.get("name", "") if isinstance(jp, dict) else str(jp)
            pp = p_pages.get(_norm(jname))
            if not pp:
                continue
            p_vis_map = {(str(v.get("x")), str(v.get("y"))): v
                         for v in self.tgt.visuals(pp["dir"])}

            for jv in (jp.get("visuals", []) if isinstance(jp, dict) else []):
                jdata = jv if isinstance(jv, dict) else {}
                jx, jy = str(jdata.get("x", "")), str(jdata.get("y", ""))
                label  = f"{jname}@({jx},{jy})"
                j_cf   = jdata.get("conditional_formatting", jdata.get("cf", {}))
                if not j_cf:
                    continue

                pv = p_vis_map.get((jx, jy))
                if not pv:
                    continue
                p_objs = pv.get("objects", {})

                # R12.1 CF rules present
                j_cf_keys = set(j_cf.keys()) & CF_KEYS if isinstance(j_cf, dict) else set()
                p_cf_keys = set(p_objs.keys()) & CF_KEYS
                missing_cf = j_cf_keys - p_cf_keys
                for mk in missing_cf:
                    self._missing("R12", f"cf.rule[{label}.{mk}]", "HIGH",
                                  mk, f"Conditional formatting rule '{mk}' missing from visual at ({jx},{jy}).")
                if not missing_cf and j_cf_keys:
                    self._pass("R12", f"cf.rules[{label}]", "HIGH",
                               list(j_cf_keys), list(p_cf_keys & j_cf_keys))

                # R12.2 CF types
                for cfk in j_cf_keys & p_cf_keys:
                    jv_cf = j_cf.get(cfk, {})
                    jcft = jv_cf.get("type") if isinstance(jv_cf, dict) else None
                    if jcft:
                        self._pass("R12", f"cf.type[{label}.{cfk}]", "HIGH", jcft, cfk)

                # R12.3 thresholds / measure refs
                j_thresh = j_cf.get("thresholds", j_cf.get("threshold_values", [])) if isinstance(j_cf, dict) else []
                if j_thresh:
                    p_thresh_found = any("threshold" in str(p_objs).lower() or
                                         "rules" in str(p_objs).lower() for _ in [1])
                    if p_thresh_found:
                        self._pass("R12", f"cf.thresholds[{label}]", "MEDIUM",
                                   j_thresh, "threshold rules found")
                    else:
                        self._missing("R12", f"cf.thresholds[{label}]", "MEDIUM",
                                      j_thresh,
                                      f"CF threshold values from JSON not matched in PBIP for visual at ({jx},{jy}).")

    # ══════════════════════════════════════════════════════════════
    # R13 — Tooltips
    # ══════════════════════════════════════════════════════════════
    def check_r13_tooltips(self):
        print("[R13] Tooltips...")
        p_pages = {_norm(p["name"]): p for p in self.tgt.pages()}
        p_page_names = {_norm(p["name"]) for p in self.tgt.pages()}

        for jp in self.src.pages():
            jname = jp.get("name", "") if isinstance(jp, dict) else str(jp)
            pp = p_pages.get(_norm(jname))
            if not pp:
                continue
            p_vis_map = {(str(v.get("x")), str(v.get("y"))): v
                         for v in self.tgt.visuals(pp["dir"])}

            for jv in (jp.get("visuals", []) if isinstance(jp, dict) else []):
                jdata  = jv if isinstance(jv, dict) else {}
                jx, jy = str(jdata.get("x", "")), str(jdata.get("y", ""))
                label  = f"{jname}@({jx},{jy})"
                pv     = p_vis_map.get((jx, jy))
                if not pv:
                    continue

                j_tooltip = jdata.get("tooltip", jdata.get("tooltip_config", {}))
                if not j_tooltip:
                    # R13.3 default tooltip — verify no unexpected tooltip page in PBIP
                    p_tt_type = pv.get("tooltipType", "")
                    if p_tt_type and "page" in _norm(p_tt_type):
                        self._fail("R13", f"tooltip.unexpected[{label}]", "LOW",
                                   "default (no tooltip)", p_tt_type,
                                   f"Visual at ({jx},{jy}) has no tooltip in JSON but PBIP assigns a page tooltip.")
                    continue

                j_tt_type = j_tooltip.get("type", j_tooltip.get("tooltip_type", "")) if isinstance(j_tooltip, dict) else ""
                j_tt_page = j_tooltip.get("page", j_tooltip.get("tooltip_page", "")) if isinstance(j_tooltip, dict) else ""

                # R13.1 report page tooltip
                if j_tt_page or "page" in _norm(j_tt_type):
                    p_tt_page = pv.get("tooltipType", "")
                    if j_tt_page and _norm(j_tt_page) not in p_page_names:
                        self._missing("R13", f"tooltip.page[{label}]", "HIGH", j_tt_page,
                                      f"Tooltip page '{j_tt_page}' referenced by visual at ({jx},{jy}) not found in PBIP pages.")
                    elif j_tt_page:
                        self._pass("R13", f"tooltip.page[{label}]", "HIGH", j_tt_page, j_tt_page)

                # R13.2 custom tooltip fields
                j_tt_fields = j_tooltip.get("fields", []) if isinstance(j_tooltip, dict) else []
                if j_tt_fields:
                    p_proj = pv.get("projections", [])
                    p_refs = {_norm_queryref(sel.get("queryRef", "")) for sel in p_proj if isinstance(sel, dict)}
                    for jf in j_tt_fields:
                        fname = jf.get("name", str(jf)) if isinstance(jf, dict) else str(jf)
                        if _norm_queryref(fname) not in p_refs:
                            self._missing("R13", f"tooltip.field[{label}.{fname}]", "MEDIUM", fname,
                                          f"Tooltip field '{fname}' missing from visual at ({jx},{jy}).")
                        else:
                            self._pass("R13", f"tooltip.field[{label}.{fname}]", "MEDIUM", fname, "found")

    # ══════════════════════════════════════════════════════════════
    # R14 — Drillthrough
    # ══════════════════════════════════════════════════════════════
    def check_r14_drillthrough(self):
        print("[R14] Drillthrough...")
        found = False
        p_pages = {_norm(p["name"]): p for p in self.tgt.pages()}

        for jp in self.src.pages():
            jname = jp.get("name", "") if isinstance(jp, dict) else str(jp)
            jdata = jp if isinstance(jp, dict) else {}
            j_dt  = jdata.get("drillthrough", jdata.get("drill_through", {}))
            if not j_dt:
                continue
            found = True

            # R14.1 drillthrough target page exists and is hidden
            pp = p_pages.get(_norm(jname))
            if not pp:
                self._missing("R14", f"dt.page[{jname}]", "HIGH", jname,
                              f"Drillthrough target page '{jname}' not found in PBIP.")
                continue

            p_dt = pp.get("drillthrough", {})
            is_hidden = pp.get("isHidden", False)
            if not is_hidden:
                self._fail("R14", f"dt.hidden[{jname}]", "HIGH", True, is_hidden,
                           f"Drillthrough page '{jname}' exists in PBIP but is not hidden. "
                           "Drillthrough pages must be hidden from navigation.")
            else:
                self._pass("R14", f"dt.hidden[{jname}]", "HIGH", True, is_hidden)

            # R14.2 filter fields
            j_dt_filters = j_dt.get("filters", j_dt.get("fields", [])) if isinstance(j_dt, dict) else []
            p_dt_filters = p_dt.get("filters", []) if isinstance(p_dt, dict) else []
            if len(j_dt_filters) != len(p_dt_filters):
                self._mismatch("R14", f"dt.filters[{jname}]", "HIGH",
                               len(j_dt_filters), len(p_dt_filters),
                               f"Drillthrough filter count mismatch for page '{jname}'.")
            else:
                self._pass("R14", f"dt.filters[{jname}]", "HIGH",
                           len(j_dt_filters), len(p_dt_filters))

            # R14.3 keepAllFilters
            j_kaf = j_dt.get("keep_all_filters", j_dt.get("keepAllFilters", None)) if isinstance(j_dt, dict) else None
            p_kaf = p_dt.get("keepAllFilters", None) if isinstance(p_dt, dict) else None
            if j_kaf is not None and str(j_kaf) != str(p_kaf):
                self._mismatch("R14", f"dt.keepAllFilters[{jname}]", "MEDIUM",
                               j_kaf, p_kaf, f"keepAllFilters mismatch for drillthrough page '{jname}'.")
            elif j_kaf is not None:
                self._pass("R14", f"dt.keepAllFilters[{jname}]", "MEDIUM", j_kaf, p_kaf)

        if not found:
            self._info("R14", "drillthrough.present", "none", "No drillthrough pages in JSON — N/A")

    # ══════════════════════════════════════════════════════════════
    # R15 — Images & logos
    # ══════════════════════════════════════════════════════════════
    def check_r15_images(self):
        print("[R15] Images & logos...")
        p_static = self.tgt.static_files()
        p_pages  = {_norm(p["name"]): p for p in self.tgt.pages()}
        found    = False

        for jp in self.src.pages():
            jname = jp.get("name", "") if isinstance(jp, dict) else str(jp)
            pp = p_pages.get(_norm(jname))
            if not pp:
                continue
            p_vis_map = {(str(v.get("x")), str(v.get("y"))): v
                         for v in self.tgt.visuals(pp["dir"])}

            for jv in (jp.get("visuals", []) if isinstance(jp, dict) else []):
                jdata  = jv if isinstance(jv, dict) else {}
                jtype  = jdata.get("visual_type", jdata.get("type", ""))
                if jtype not in ("image", "imageVisual", "logo", "img"):
                    if not jdata.get("image_url", jdata.get("image_file")):
                        continue
                found = True
                jx, jy = str(jdata.get("x", "")), str(jdata.get("y", ""))
                label  = f"{jname}@({jx},{jy})"
                pv     = p_vis_map.get((jx, jy))

                # R15.1 image file in StaticResources
                img_file = jdata.get("image_url", jdata.get("image_file", jdata.get("src")))
                if img_file:
                    img_basename = os.path.basename(img_file).lower()
                    if img_basename in p_static:
                        self._pass("R15", f"img.file[{label}]", "HIGH", img_basename, "found in StaticResources")
                    else:
                        self._missing("R15", f"img.file[{label}]", "HIGH", img_basename,
                                      f"Image file '{img_basename}' not found in PBIP StaticResources/.")

                # R15.2 imageUrl in visual.json
                if pv:
                    p_objs = pv.get("objects", {})
                    p_img_ref = (p_objs.get("image", [{}])[0]
                                       .get("properties", {})
                                       .get("imageUrl", {})
                                       .get("expr", {})
                                       .get("Literal", {})
                                       .get("Value", ""))
                    if img_file and _norm(img_file) != _norm(p_img_ref):
                        self._mismatch("R15", f"img.ref[{label}]", "HIGH",
                                       img_file, p_img_ref,
                                       f"Image reference mismatch in visual.json at ({jx},{jy}).")
                    elif img_file:
                        self._pass("R15", f"img.ref[{label}]", "HIGH", img_file, p_img_ref)

                # R15.3 scaling mode
                j_scale = jdata.get("scaling_mode", jdata.get("image_scaling"))
                if j_scale and pv:
                    p_scale = (pv.get("objects", {})
                                 .get("image", [{}])[0]
                                 .get("properties", {})
                                 .get("scaling", {})
                                 .get("expr", {})
                                 .get("Literal", {})
                                 .get("Value", ""))
                    if _norm(j_scale) != _norm(p_scale):
                        self._mismatch("R15", f"img.scaling[{label}]", "LOW", j_scale, p_scale,
                                       f"Image scaling mode mismatch at ({jx},{jy}).")
                    else:
                        self._pass("R15", f"img.scaling[{label}]", "LOW", j_scale, p_scale)

        if not found:
            self._info("R15", "images.present", "none", "No image visuals in JSON — N/A")

    # ══════════════════════════════════════════════════════════════
    # R16 — HTML & embedded custom visuals (content rendering)
    # ══════════════════════════════════════════════════════════════
    def check_r16_html_embedded(self):
        print("[R16] HTML & embedded custom visuals...")
        p_pages = {_norm(p["name"]): p for p in self.tgt.pages()}
        found   = False
        HTML_INDICATORS = {"htmlcontent", "htmlvisual", "html", "htmlrenderer"}

        for jp in self.src.pages():
            jname = jp.get("name", "") if isinstance(jp, dict) else str(jp)
            pp = p_pages.get(_norm(jname))
            if not pp:
                continue
            p_vis_map = {(str(v.get("x")), str(v.get("y"))): v
                         for v in self.tgt.visuals(pp["dir"])}

            for jv in (jp.get("visuals", []) if isinstance(jp, dict) else []):
                jdata  = jv if isinstance(jv, dict) else {}
                jtype  = _norm(jdata.get("visual_type", jdata.get("type", "")))
                j_html = jdata.get("html_content", jdata.get("html_expression"))

                # Identify HTML-type custom visuals: GUID or known HTML keywords
                is_html_cv = (j_html is not None or
                              any(kw in jtype for kw in HTML_INDICATORS) or
                              (_is_custom_visual_type(jtype) and j_html is not None))
                if not is_html_cv:
                    continue
                found = True

                jx, jy = str(jdata.get("x", "")), str(jdata.get("y", ""))
                label  = f"{jname}@({jx},{jy})"
                pv     = p_vis_map.get((jx, jy))

                # R16.1 custom visual GUID in PBIP
                if _is_custom_visual_type(jtype):
                    p_type = pv.get("type", "") if pv else ""
                    if _norm(jtype) == _norm(p_type):
                        self._pass("R16", f"html.guid[{label}]", "HIGH", jtype, p_type)
                    else:
                        self._missing("R16", f"html.guid[{label}]", "HIGH", jtype,
                                      f"HTML/embedded custom visual GUID '{jtype}' not found in PBIP at ({jx},{jy}). "
                                      "Requires manual download from AppSource. Content will not render until installed.")

                # R16.2 HTML expression / measure binding
                if j_html and pv:
                    p_projs = pv.get("projections", [])
                    p_refs  = {_norm_queryref(s.get("queryRef", "")) for s in p_projs if isinstance(s, dict)}
                    jhtml_ref = jdata.get("html_measure", jdata.get("measure_ref", j_html))
                    if _norm_queryref(str(jhtml_ref)) in p_refs:
                        self._pass("R16", f"html.binding[{label}]", "HIGH",
                                   jhtml_ref, "found in projections")
                    else:
                        self._missing("R16", f"html.binding[{label}]", "HIGH", jhtml_ref,
                                      f"HTML measure/expression binding '{jhtml_ref}' not found in PBIP visual at ({jx},{jy}). "
                                      "Content will not render until custom visual is installed.")

                # Deployment flag for every HTML/embedded custom visual
                self._log("R16", f"html.deploy[{label}]", "INFO", "HIGH",
                          label, "AppSource install required",
                          f"HTML/embedded custom visual at ({jx},{jy}) on page '{jname}' requires "
                          "manual installation from AppSource. Content rendering depends on the custom visual package.",
                          deploy=True)

        if not found:
            self._info("R16", "html.present", "none", "No HTML/embedded custom visuals in JSON — N/A")

    # ══════════════════════════════════════════════════════════════
    # R17 — Visual interactions (edit interactions)
    # ══════════════════════════════════════════════════════════════
    def check_r17_interactions(self):
        """
        Default Power BI behaviour: all visuals cross-filter each other.
        This check only validates when overrides are explicitly captured.
        - If JSON has overrides → verify same overrides in PBIP.
        - If JSON has NO overrides → verify PBIP also has no unexpected overrides.
        """
        print("[R17] Visual interactions...")
        p_pages = {_norm(p["name"]): p for p in self.tgt.pages()}
        any_checked = False

        for jp in self.src.pages():
            jname = jp.get("name", "") if isinstance(jp, dict) else str(jp)
            pp = p_pages.get(_norm(jname))
            if not pp:
                continue
            p_vis_list = self.tgt.visuals(pp["dir"])
            p_vis_map  = {(str(v.get("x")), str(v.get("y"))): v for v in p_vis_list}

            for jv in (jp.get("visuals", []) if isinstance(jp, dict) else []):
                jdata  = jv if isinstance(jv, dict) else {}
                jx, jy = str(jdata.get("x", "")), str(jdata.get("y", ""))
                label  = f"{jname}@({jx},{jy})"
                pv     = p_vis_map.get((jx, jy))
                if not pv:
                    continue

                j_interactions = jdata.get("interaction_settings", jdata.get("interactions", {}))
                p_interactions = pv.get("interactionSettings", {})

                if j_interactions:
                    # JSON has explicit interaction overrides → validate against PBIP
                    any_checked = True
                    if isinstance(j_interactions, dict):
                        for target_id, j_mode in j_interactions.items():
                            p_mode = p_interactions.get(target_id) if isinstance(p_interactions, dict) else None
                            # R17.1 overrides match
                            if _norm(str(j_mode)) == _norm(str(p_mode) if p_mode else ""):
                                self._pass("R17", f"interaction.override[{label}->{target_id}]", "HIGH",
                                           j_mode, p_mode)
                            else:
                                self._mismatch("R17", f"interaction.override[{label}->{target_id}]", "HIGH",
                                               j_mode, p_mode,
                                               f"Visual interaction override mismatch: visual at ({jx},{jy}) -> "
                                               f"target '{target_id}' on page '{jname}'. "
                                               f"JSON expects '{j_mode}', PBIP has '{p_mode}'.")

                    # R17.2 no extra overrides in PBIP that JSON didn't capture
                    if isinstance(p_interactions, dict) and isinstance(j_interactions, dict):
                        extra = set(p_interactions.keys()) - set(j_interactions.keys())
                        for ex in extra:
                            self._fail("R17", f"interaction.extra[{label}->{ex}]", "MEDIUM",
                                       "not in JSON", p_interactions[ex],
                                       f"PBIP has interaction override for '{ex}' from visual at ({jx},{jy}) "
                                       "that was not captured in JSON.")

                else:
                    # JSON has no overrides → verify PBIP also has no overrides (R17.3 — default behaviour)
                    any_checked = True
                    if p_interactions:
                        self._fail("R17", f"interaction.unexpectedOverride[{label}]", "MEDIUM",
                                   "no overrides (default)", _sval(p_interactions),
                                   f"Visual at ({jx},{jy}) on '{jname}' has no interaction overrides in JSON "
                                   "(default behaviour expected), but PBIP has custom interaction settings. "
                                   "This may indicate the FE agent missed capturing interaction customisations.")
                    else:
                        self._pass("R17", f"interaction.default[{label}]", "MEDIUM",
                                   "default", "default — no overrides in PBIP")

        if not any_checked:
            self._info("R17", "interactions.present", "none",
                       "No interaction data to validate — N/A")

    # ══════════════════════════════════════════════════════════════
    # R18 — Sync slicers (cross-page)
    # ══════════════════════════════════════════════════════════════
    def check_r18_sync_slicers(self):
        print("[R18] Sync slicers...")
        p_pages = {_norm(p["name"]): p for p in self.tgt.pages()}
        found   = False

        for jp in self.src.pages():
            jname = jp.get("name", "") if isinstance(jp, dict) else str(jp)
            pp = p_pages.get(_norm(jname))
            if not pp:
                continue
            p_vis_map = {(str(v.get("x")), str(v.get("y"))): v
                         for v in self.tgt.visuals(pp["dir"])}

            for jv in (jp.get("visuals", []) if isinstance(jp, dict) else []):
                jdata  = jv if isinstance(jv, dict) else {}
                j_sync = jdata.get("sync_slicers", jdata.get("syncSlicers", {}))
                if not j_sync:
                    continue
                found = True

                jx, jy = str(jdata.get("x", "")), str(jdata.get("y", ""))
                label  = f"{jname}@({jx},{jy})"
                pv     = p_vis_map.get((jx, jy))
                if not pv:
                    continue
                p_sync = pv.get("syncSlicers", {})

                # R18.1 sync group exists in PBIP
                if not p_sync:
                    self._missing("R18", f"sync.group[{label}]", "HIGH", _sval(j_sync),
                                  f"Slicer at ({jx},{jy}) on '{jname}' has sync group in JSON but none in PBIP visual.")
                    continue
                self._pass("R18", f"sync.group[{label}]", "HIGH", "sync group present", "sync group present")

                # R18.2 page list in sync group
                j_pages_in_sync = j_sync.get("pages", j_sync.get("syncedPages", [])) if isinstance(j_sync, dict) else []
                p_pages_in_sync = p_sync.get("pageGuids", p_sync.get("pages", [])) if isinstance(p_sync, dict) else []
                if len(j_pages_in_sync) != len(p_pages_in_sync):
                    self._mismatch("R18", f"sync.pageCount[{label}]", "HIGH",
                                   len(j_pages_in_sync), len(p_pages_in_sync),
                                   f"Sync slicer page count mismatch for slicer at ({jx},{jy}). "
                                   "Slicer may not propagate to all expected pages.")
                else:
                    self._pass("R18", f"sync.pageCount[{label}]", "HIGH",
                               len(j_pages_in_sync), len(p_pages_in_sync))

                # R18.3 visibility per page
                j_visibility = j_sync.get("visibility", j_sync.get("showSlicerOnPage", {})) if isinstance(j_sync, dict) else {}
                p_visibility = p_sync.get("showSlicerOnPage", {}) if isinstance(p_sync, dict) else {}
                if isinstance(j_visibility, dict):
                    for pg_id, j_visible in j_visibility.items():
                        p_visible = p_visibility.get(pg_id)
                        if p_visible is None:
                            self._missing("R18", f"sync.visibility[{label}.{pg_id}]", "MEDIUM",
                                          j_visible,
                                          f"Sync slicer visibility for page '{pg_id}' not found in PBIP.")
                        elif bool(j_visible) != bool(p_visible):
                            self._mismatch("R18", f"sync.visibility[{label}.{pg_id}]", "MEDIUM",
                                           j_visible, p_visible,
                                           f"Sync slicer showSlicerOnPage mismatch for page '{pg_id}'.")
                        else:
                            self._pass("R18", f"sync.visibility[{label}.{pg_id}]", "MEDIUM",
                                       j_visible, p_visible)

        if not found:
            self._info("R18", "sync.present", "none", "No sync slicers in JSON — N/A")

    # ══════════════════════════════════════════════════════════════
    # Run all
    # ══════════════════════════════════════════════════════════════

    # ══════════════════════════════════════════════════════════════
    # CHECKLIST EXTENDED CHECKS  –  R19-R27 (FE direction: JSON → PBIP)
    # Validates that the forward-engineered PBIP contains the properties
    # identified as missing in the gap analysis.
    # ══════════════════════════════════════════════════════════════

    # ══════════════════════════════════════════════════════════════
    # Checklist extended checks R19-R25  (FE direction: JSON → PBIP)
    # self.src  = EnrichedReportExtractor  (JSON source of truth)
    # self.tgt  = PbipReportExtractor      (PBIP target to validate)
    # Helpers: _pass(cid,sid,sev,src,tgt), _fail(cid,sid,sev,src,tgt,note)
    #          _missing(cid,sid,sev,src,note), _mismatch(cid,sid,sev,src,tgt,note)
    # PBIP visual dict keys: type, x, y, objects (dict), raw
    # JSON visual dict keys: visual_type, x, y  (no objects block)
    # ══════════════════════════════════════════════════════════════

    def _objs_prop_fe(self, objs, obj_key, prop_key):
        """Read a named property from a PBIP visual.objects block."""
        b = (objs.get(obj_key, [{}]) or [{}])[0].get("properties", {}) if isinstance(objs, dict) else {}
        v = b.get(prop_key)
        if isinstance(v, dict):
            return v.get("expr", {}).get("Literal", {}).get("Value", v.get("value"))
        return v

    def _match_pbip_visual(self, p_visuals, vtype, vx, vy):
        """Match a PBIP visual by type and position."""
        for pv in p_visuals:
            ptype = pv.get("type", pv.get("visual_type", ""))
            px = round(pv.get("x") or 0, 0)
            py = round(pv.get("y") or 0, 0)
            if ptype == vtype and px == vx and py == vy:
                return pv
        return None

    def _src_raw_pages(self):
        """Return raw JSON pages list for properties not exposed by EnrichedReportExtractor."""
        return self.src.r.get("visualizations", {}).get("pages", [])

    def check_r19_canvas_environment(self):
        """R19 – displayArea, verticalAlignment, Filter Pane per page."""
        print("[R19] Canvas environment (displayArea, verticalAlignment, filter pane)...")
        j_raw_pages = self._src_raw_pages()
        p_pages     = {_norm(p["name"]): p for p in self.tgt.pages()}

        for jp in j_raw_pages:
            jname = jp.get("display_name", jp.get("name", ""))
            pp    = p_pages.get(_norm(jname))
            if not pp:
                continue
            raw_p = pp.get("raw", {})
            label = f"page[{jname}]"

            # displayArea
            j_da = jp.get("display_area", jp.get("displayArea", jp.get("canvas_settings", {}) if isinstance(jp.get("canvas_settings"), dict) else {}))
            if isinstance(j_da, dict):
                j_da = j_da.get("displayArea")
            p_da = raw_p.get("displayArea", raw_p.get("displayOption"))
            if j_da is not None:
                if _norm(str(j_da)) != _norm(str(p_da or "")):
                    self._mismatch("R19", f"{label}.displayArea", "MEDIUM", j_da, p_da,
                                   "CANVAS: displayArea (sizing mode) mismatch. "
                                   "Affects how the report page scales in Power BI Service.")
                else:
                    self._pass("R19", f"{label}.displayArea", "MEDIUM", j_da, p_da)

            # verticalAlignment
            j_va = jp.get("vertical_alignment", jp.get("verticalAlignment"))
            p_va = raw_p.get("verticalAlignment")
            if j_va is not None:
                if _norm(str(j_va)) != _norm(str(p_va or "")):
                    self._mismatch("R19", f"{label}.verticalAlignment", "LOW", j_va, p_va,
                                   "CANVAS: verticalAlignment (Top/Middle) mismatch.")
                else:
                    self._pass("R19", f"{label}.verticalAlignment", "LOW", j_va, p_va)

            # Filter Pane visibility
            j_fp = jp.get("filter_pane", {}) or {}
            j_fpv = j_fp.get("visibility") if isinstance(j_fp, dict) else None
            p_fp  = raw_p.get("filterConfig", {}) or {}
            p_fpv = p_fp.get("defaultFilterPaneEnabled", p_fp.get("visibility"))
            if j_fpv is not None:
                if _norm(str(j_fpv)) != _norm(str(p_fpv or "")):
                    self._mismatch("R19", f"{label}.filterPane.visibility", "MEDIUM",
                                   j_fpv, p_fpv, "Filter pane visibility mismatch.")
                else:
                    self._pass("R19", f"{label}.filterPane.visibility", "MEDIUM", j_fpv, p_fpv)

            # Filter Pane width
            j_fpw = j_fp.get("width") if isinstance(j_fp, dict) else None
            if j_fpw is not None:
                p_fpw = p_fp.get("width")
                if _norm(str(j_fpw)) != _norm(str(p_fpw or "")):
                    self._mismatch("R19", f"{label}.filterPane.width", "LOW",
                                   j_fpw, p_fpw, "Filter pane width mismatch.")
                else:
                    self._pass("R19", f"{label}.filterPane.width", "LOW", j_fpw, p_fpw)

    def check_r20_alt_text_header_icons(self):
        """R20 – altText, headerIcons, subtitle per visual (JSON → PBIP)."""
        print("[R20] altText, headerIcons, subtitle per visual...")
        j_pages = self.src.pages()
        p_pages = {_norm(p["name"]): p for p in self.tgt.pages()}

        for jp_page in j_pages:
            jname = jp_page.get("name", jp_page.get("display_name", ""))
            pp    = p_pages.get(_norm(jname))
            if not pp:
                continue
            p_visuals = self.tgt.visuals(pp["dir"])

            for jv in jp_page.get("visuals", []):
                vtype = jv.get("visual_type", jv.get("type", ""))
                jx    = round(jv.get("x") or 0, 0)
                jy    = round(jv.get("y") or 0, 0)
                pv    = self._match_pbip_visual(p_visuals, vtype, jx, jy)
                if not pv:
                    continue
                label  = f"page[{jname}].visual[{vtype}@{jx},{jy}]"
                p_objs = pv.get("objects", {}) or {}

                # altText – JSON stores it in alt_text field; PBIP in objects.general[].altText
                j_alt = jv.get("alt_text", jv.get("altText"))
                if j_alt is not None:
                    p_alt_raw = (p_objs.get("general", [{}]) or [{}])[0].get("properties", {}).get("altText")
                    p_alt = None
                    if isinstance(p_alt_raw, dict):
                        p_alt = p_alt_raw.get("expr", {}).get("Literal", {}).get("Value", p_alt_raw.get("value"))
                    if _norm(str(j_alt)) != _norm(str(p_alt or "")):
                        self._mismatch("R20", f"{label}.altText", "MEDIUM", j_alt, p_alt,
                                       "ALT TEXT: screen-reader description mismatch. "
                                       "Required for WCAG accessibility compliance.")
                    else:
                        self._pass("R20", f"{label}.altText", "MEDIUM", j_alt, p_alt)

                # headerIcons – presence check only (JSON captures as list, PBIP in visualHeader objects)
                j_icons = jv.get("header_icons", jv.get("visual_header_icons"))
                if j_icons is not None:
                    p_hdr = (p_objs.get("visualHeader", [{}]) or [{}])[0].get("properties", {})
                    if not p_hdr:
                        self._missing("R20", f"{label}.headerIcons", "LOW", j_icons,
                                      "HEADER ICONS: JSON specifies icon config but PBIP "
                                      "visual has no visualHeader objects block.")
                    else:
                        self._pass("R20", f"{label}.headerIcons", "LOW", j_icons, "configured")

                # subtitle
                j_sub = jv.get("subtitle")
                if j_sub is not None:
                    p_sub_raw = (p_objs.get("title", [{}]) or [{}])[0].get("properties", {}).get("subTitle")
                    p_sub = None
                    if isinstance(p_sub_raw, dict):
                        p_sub = p_sub_raw.get("expr", {}).get("Literal", {}).get("Value", p_sub_raw.get("value"))
                    if _norm(str(j_sub)) != _norm(str(p_sub or "")):
                        self._mismatch("R20", f"{label}.subtitle", "LOW", j_sub, p_sub,
                                       "SUBTITLE mismatch.")
                    else:
                        self._pass("R20", f"{label}.subtitle", "LOW", j_sub, p_sub)

    def check_r21_card_formatting(self):
        """R21 – Card displayUnits, decimalPlaces, referenceLabels, shapeType, cardPadding."""
        print("[R21] Card/KPI formatting (displayUnits, decimalPlaces, referenceLabels)...")
        CARD_TYPES = {"card", "kpiVisual", "singleRowCard", "multiRowCard",
                      "gauge", "kpi", "newCard", "cardVisual"}
        j_pages = self.src.pages()
        p_pages = {_norm(p["name"]): p for p in self.tgt.pages()}

        for jp_page in j_pages:
            jname = jp_page.get("name", jp_page.get("display_name", ""))
            pp    = p_pages.get(_norm(jname))
            if not pp:
                continue
            p_visuals = self.tgt.visuals(pp["dir"])

            for jv in jp_page.get("visuals", []):
                vtype = jv.get("visual_type", jv.get("type", ""))
                if vtype.lower() not in {v.lower() for v in CARD_TYPES}:
                    continue
                jx    = round(jv.get("x") or 0, 0)
                jy    = round(jv.get("y") or 0, 0)
                pv    = self._match_pbip_visual(p_visuals, vtype, jx, jy)
                if not pv:
                    continue
                label  = f"page[{jname}].visual[{vtype}@{jx},{jy}]"
                p_objs = pv.get("objects", {}) or {}
                # JSON stores formatting under a formatting sub-dict
                j_fmt  = jv.get("formatting", {}) or {}

                # displayUnits
                j_du = j_fmt.get("display_units")
                if j_du is not None:
                    p_du = self._objs_prop_fe(p_objs, "labels", "labelDisplayUnits") or                            self._objs_prop_fe(p_objs, "calloutValue", "labelDisplayUnits")
                    if _norm(str(j_du)) != _norm(str(p_du or "")):
                        self._mismatch("R21", f"{label}.displayUnits", "MEDIUM", j_du, p_du,
                                       "CARD: displayUnits (scaling) mismatch.")
                    else:
                        self._pass("R21", f"{label}.displayUnits", "MEDIUM", j_du, p_du)

                # decimalPlaces
                j_dp = j_fmt.get("decimal_places")
                if j_dp is not None:
                    p_dp = self._objs_prop_fe(p_objs, "labels", "labelPrecision") or                            self._objs_prop_fe(p_objs, "calloutValue", "labelPrecision")
                    if _norm(str(j_dp)) != _norm(str(p_dp or "")):
                        self._mismatch("R21", f"{label}.decimalPlaces", "MEDIUM", j_dp, p_dp,
                                       "CARD: decimalPlaces mismatch.")
                    else:
                        self._pass("R21", f"{label}.decimalPlaces", "MEDIUM", j_dp, p_dp)

                # categoryLabel show
                j_cl = j_fmt.get("category_label_show")
                if j_cl is not None:
                    p_cl = self._objs_prop_fe(p_objs, "categoryLabels", "show")
                    if _norm(str(j_cl)) != _norm(str(p_cl or "")):
                        self._mismatch("R21", f"{label}.categoryLabel.show", "LOW", j_cl, p_cl,
                                       "CARD: categoryLabel show/hide mismatch.")
                    else:
                        self._pass("R21", f"{label}.categoryLabel.show", "LOW", j_cl, p_cl)

                # referenceLabels
                j_ref = j_fmt.get("reference_labels", jv.get("reference_labels"))
                if j_ref is not None:
                    p_ref = p_objs.get("referenceLabels", p_objs.get("targets"))
                    if not p_ref:
                        self._missing("R21", f"{label}.referenceLabels", "HIGH", j_ref,
                                      "CARD: referenceLabels specified in JSON but absent in PBIP. "
                                      "Target card will show no secondary comparison values.")
                    else:
                        self._pass("R21", f"{label}.referenceLabels", "HIGH", j_ref, "present")

                # shapeType
                j_st = j_fmt.get("shape_type")
                if j_st is not None:
                    p_st = self._objs_prop_fe(p_objs, "shape", "shapeType") or                            self._objs_prop_fe(p_objs, "cardLayout", "shapeType")
                    if _norm(str(j_st)) != _norm(str(p_st or "")):
                        self._mismatch("R21", f"{label}.shapeType", "LOW", j_st, p_st,
                                       "CARD: shapeType mismatch.")
                    else:
                        self._pass("R21", f"{label}.shapeType", "LOW", j_st, p_st)

    def check_r22_slicer_controls(self):
        """R22 – Slicer slicerType, selectionControls, slicerHeader, sliderColor, responsive."""
        print("[R22] Slicer controls (slicerType, selectionControls, sliderColor)...")
        j_pages = self.src.pages()
        p_pages = {_norm(p["name"]): p for p in self.tgt.pages()}

        for jp_page in j_pages:
            jname = jp_page.get("name", jp_page.get("display_name", ""))
            pp    = p_pages.get(_norm(jname))
            if not pp:
                continue
            p_visuals = self.tgt.visuals(pp["dir"])

            for jv in jp_page.get("visuals", []):
                if jv.get("visual_type", "").lower() != "slicer":
                    continue
                jx    = round(jv.get("x") or 0, 0)
                jy    = round(jv.get("y") or 0, 0)
                pv    = self._match_pbip_visual(p_visuals, "slicer", jx, jy)
                if not pv:
                    continue
                label  = f"page[{jname}].slicer[@{jx},{jy}]"
                p_objs = pv.get("objects", {}) or {}
                j_sset = jv.get("slicer_settings", jv.get("formatting", {})) or {}

                checks = [
                    ("slicer_type",      "general",    "orientation",              "SLICER: slicerType mismatch — completely different layout in target.", "HIGH"),
                    ("single_select",    "selection",  "singleSelect",             "SLICER: singleSelect mismatch.", "HIGH"),
                    ("show_select_all",  "selection",  "selectAllCheckboxEnabled", "SLICER: showSelectAll mismatch.", "MEDIUM"),
                    ("slicer_header",    "header",     "title",                    "SLICER: slicerHeader label mismatch.", "MEDIUM"),
                    ("slider_color",     "slider",     "color",                    "SLICER: sliderColor (active track) mismatch.", "LOW"),
                    ("responsive",       "general",    "responsive",               "SLICER: responsive toggle mismatch.", "LOW"),
                ]
                for json_k, obj_k, prop_k, note, sev in checks:
                    j_val = j_sset.get(json_k)
                    if j_val is None:
                        continue
                    p_val = self._objs_prop_fe(p_objs, obj_k, prop_k)
                    if _norm(str(j_val)) != _norm(str(p_val or "")):
                        self._mismatch("R22", f"{label}.{json_k}", sev, j_val, p_val, note)
                    else:
                        self._pass("R22", f"{label}.{json_k}", sev, j_val, p_val)

    def check_r23_axis_chart_detail(self):
        """R23 – Chart axisScale, axisBounds, axisTitles, linesAndMarkers, seriesLabels."""
        print("[R23] Chart axis detail (axisScale, axisBounds, axisTitles, linesAndMarkers)...")
        CHART_TYPES = {
            "lineChart", "areaChart", "stackedAreaChart", "hundredPercentStackedAreaChart",
            "clusteredBarChart", "stackedBarChart", "hundredPercentStackedBarChart",
            "clusteredColumnChart", "stackedColumnChart", "hundredPercentStackedColumnChart",
            "lineStackedColumnComboChart", "lineClusteredColumnComboChart",
            "scatterChart", "bubbleChart", "waterfallChart", "ribbonChart",
        }
        j_pages = self.src.pages()
        p_pages = {_norm(p["name"]): p for p in self.tgt.pages()}

        for jp_page in j_pages:
            jname = jp_page.get("name", jp_page.get("display_name", ""))
            pp    = p_pages.get(_norm(jname))
            if not pp:
                continue
            p_visuals = self.tgt.visuals(pp["dir"])

            for jv in jp_page.get("visuals", []):
                vtype = jv.get("visual_type", jv.get("type", ""))
                if vtype not in CHART_TYPES:
                    continue
                jx    = round(jv.get("x") or 0, 0)
                jy    = round(jv.get("y") or 0, 0)
                pv    = self._match_pbip_visual(p_visuals, vtype, jx, jy)
                if not pv:
                    continue
                label  = f"page[{jname}].visual[{vtype}@{jx},{jy}]"
                p_objs = pv.get("objects", {}) or {}
                j_fmt  = jv.get("formatting", {}) or {}

                for axis_k, axis_lbl in [("categoryAxis", "X-axis"), ("valueAxis", "Y-axis")]:
                    for json_k, prop_k, note, sev in [
                        (f"{axis_k}_scale", "axisScale",  f"CHART {axis_lbl}: axisScale (Linear/Log/Categorical) mismatch.", "HIGH"),
                        (f"{axis_k}_bound_start", "start", f"CHART {axis_lbl}: min axis bound mismatch.", "HIGH"),
                        (f"{axis_k}_bound_end",   "end",   f"CHART {axis_lbl}: max axis bound mismatch.", "HIGH"),
                        (f"{axis_k}_title",  "titleText", f"CHART {axis_lbl}: axis title label mismatch.", "MEDIUM"),
                    ]:
                        j_val = j_fmt.get(json_k)
                        if j_val is None:
                            continue
                        p_val = self._objs_prop_fe(p_objs, axis_k, prop_k)
                        if _norm(str(j_val)) != _norm(str(p_val or "")):
                            self._mismatch("R23", f"{label}.{json_k}", sev, j_val, p_val, note)
                        else:
                            self._pass("R23", f"{label}.{json_k}", sev, j_val, p_val)

                # linesAndMarkers
                for json_k, obj_k, prop_k, note, sev in [
                    ("line_style",   "lineStyles", "lineStyle",   "CHART: line style (Solid/Dashed/Dotted) mismatch.", "MEDIUM"),
                    ("marker_shape", "markers",    "markerShape", "CHART: marker shape mismatch.", "LOW"),
                ]:
                    j_val = j_fmt.get(json_k)
                    if j_val is None:
                        continue
                    p_val = self._objs_prop_fe(p_objs, obj_k, prop_k)
                    if _norm(str(j_val)) != _norm(str(p_val or "")):
                        self._mismatch("R23", f"{label}.{json_k}", sev, j_val, p_val, note)
                    else:
                        self._pass("R23", f"{label}.{json_k}", sev, j_val, p_val)

    def check_r24_analytics_overlays(self):
        """R24 – Analytics reference lines, forecast points, confidence interval."""
        print("[R24] Analytics overlays (reference lines, forecast, confidence interval)...")
        ANALYTICS_TYPES = {
            "lineChart", "areaChart", "stackedAreaChart",
            "clusteredBarChart", "stackedBarChart",
            "clusteredColumnChart", "stackedColumnChart",
            "scatterChart", "bubbleChart",
            "lineStackedColumnComboChart", "lineClusteredColumnComboChart",
        }
        j_pages = self.src.pages()
        p_pages = {_norm(p["name"]): p for p in self.tgt.pages()}

        for jp_page in j_pages:
            jname = jp_page.get("name", jp_page.get("display_name", ""))
            pp    = p_pages.get(_norm(jname))
            if not pp:
                continue
            p_visuals = self.tgt.visuals(pp["dir"])

            for jv in jp_page.get("visuals", []):
                vtype = jv.get("visual_type", jv.get("type", ""))
                if vtype not in ANALYTICS_TYPES:
                    continue
                jx    = round(jv.get("x") or 0, 0)
                jy    = round(jv.get("y") or 0, 0)
                pv    = self._match_pbip_visual(p_visuals, vtype, jx, jy)
                if not pv:
                    continue
                label      = f"page[{jname}].visual[{vtype}@{jx},{jy}]"
                p_objs     = pv.get("objects", {}) or {}
                j_analytics = jv.get("analytics", jv.get("analytics_overlays", {})) or {}

                # Reference lines
                j_ref = j_analytics.get("reference_lines", j_analytics.get("referenceLines"))
                if j_ref is not None:
                    p_ref = p_objs.get("referenceLine",
                            p_objs.get("xAxisReferenceLine",
                            p_objs.get("y1AxisReferenceLine")))
                    if not p_ref:
                        self._missing("R24", f"{label}.referenceLines", "HIGH", j_ref,
                                      "ANALYTICS: JSON specifies reference lines but PBIP visual "
                                      "has none. Target chart will lack analytical overlay lines.")
                    else:
                        self._pass("R24", f"{label}.referenceLines", "HIGH", j_ref, "present")

                # Forecast
                j_fc = j_analytics.get("forecast", j_analytics.get("forecasting"))
                if j_fc is not None:
                    p_fc = p_objs.get("forecast", [])
                    if not p_fc:
                        self._missing("R24", f"{label}.forecast", "HIGH", j_fc,
                                      "ANALYTICS: JSON specifies forecast but PBIP visual has "
                                      "no forecast config. Target chart will have no trend line.")
                    else:
                        self._pass("R24", f"{label}.forecast", "HIGH", j_fc, "present")
                        # Confidence interval
                        j_ci = j_fc.get("confidence_interval") if isinstance(j_fc, dict) else None
                        if j_ci is not None:
                            p_ci = self._objs_prop_fe(p_objs, "forecast", "confidenceLevel")
                            if _norm(str(j_ci)) != _norm(str(p_ci or "")):
                                self._mismatch("R24", f"{label}.forecast.confidenceInterval",
                                               "MEDIUM", j_ci, p_ci,
                                               "ANALYTICS: confidence interval mismatch in forecast.")
                            else:
                                self._pass("R24", f"{label}.forecast.confidenceInterval",
                                           "MEDIUM", j_ci, p_ci)

    def check_r25_visual_type_specific(self):
        """R25 – Decomp Tree, KPI, Gauge, Treemap, Azure Map, Map style, dual-axis."""
        print("[R25] Visual-type-specific checklist items...")
        j_pages = self.src.pages()
        p_pages = {_norm(p["name"]): p for p in self.tgt.pages()}

        for jp_page in j_pages:
            jname = jp_page.get("name", jp_page.get("display_name", ""))
            pp    = p_pages.get(_norm(jname))
            if not pp:
                continue
            p_visuals = self.tgt.visuals(pp["dir"])

            for jv in jp_page.get("visuals", []):
                vtype = jv.get("visual_type", jv.get("type", ""))
                if not vtype:
                    continue
                jx    = round(jv.get("x") or 0, 0)
                jy    = round(jv.get("y") or 0, 0)
                pv    = self._match_pbip_visual(p_visuals, vtype, jx, jy)
                if not pv:
                    continue
                label  = f"page[{jname}].visual[{vtype}@{jx},{jy}]"
                p_objs = pv.get("objects", {}) or {}
                j_vts  = jv.get("visual_type_config", {}) or {}
                j_fmt  = jv.get("formatting", {}) or {}

                # Decomposition Tree – AI Splits
                if vtype == "decompositionTree":
                    j_ai = j_vts.get("enable_ai_splits")
                    if j_ai is not None:
                        p_ai = self._objs_prop_fe(p_objs, "general", "enableAISplits")
                        if _norm(str(j_ai)) != _norm(str(p_ai or "")):
                            self._mismatch("R25", f"{label}.enableAISplits", "MEDIUM", j_ai, p_ai,
                                           "DECOMP TREE: enableAISplits setting mismatch.")
                        else:
                            self._pass("R25", f"{label}.enableAISplits", "MEDIUM", j_ai, p_ai)

                # Q&A Visual – suggested question
                if vtype == "qnaVisual":
                    j_q = j_vts.get("suggested_question")
                    if j_q is not None:
                        p_q = self._objs_prop_fe(p_objs, "general", "question")
                        if _norm(str(j_q)) != _norm(str(p_q or "")):
                            self._mismatch("R25", f"{label}.suggestedQuestion", "MEDIUM", j_q, p_q,
                                           "Q&A: suggested question mismatch.")
                        else:
                            self._pass("R25", f"{label}.suggestedQuestion", "MEDIUM", j_q, p_q)

                # Gauge – static max and target
                if vtype == "gauge":
                    for json_k, obj_k, prop_k, note, sev in [
                        ("gauge_max",    "gauge",   "max",   "GAUGE: static max mismatch — target may auto-scale.", "HIGH"),
                        ("gauge_target", "targets", "value", "GAUGE: target value mismatch.", "HIGH"),
                    ]:
                        j_val = j_vts.get(json_k)
                        if j_val is None:
                            continue
                        p_val = self._objs_prop_fe(p_objs, obj_k, prop_k)
                        if _norm(str(j_val)) != _norm(str(p_val or "")):
                            self._mismatch("R25", f"{label}.{json_k}", sev, j_val, p_val, note)
                        else:
                            self._pass("R25", f"{label}.{json_k}", sev, j_val, p_val)

                # KPI Visual – Trend Axis toggle
                if vtype in {"kpiVisual", "kpi"}:
                    j_ta = j_vts.get("trend_axis")
                    if j_ta is not None:
                        p_ta = self._objs_prop_fe(p_objs, "trendLine", "show")
                        if _norm(str(j_ta)) != _norm(str(p_ta or "")):
                            self._mismatch("R25", f"{label}.trendAxis", "MEDIUM", j_ta, p_ta,
                                           "KPI: Trend Axis toggle mismatch.")
                        else:
                            self._pass("R25", f"{label}.trendAxis", "MEDIUM", j_ta, p_ta)

                # Treemap – max visible categories
                if vtype == "treemap":
                    j_mc = j_vts.get("max_categories")
                    if j_mc is not None:
                        p_mc = self._objs_prop_fe(p_objs, "dataPoint", "maxCategories")
                        if _norm(str(j_mc)) != _norm(str(p_mc or "")):
                            self._mismatch("R25", f"{label}.maxCategories", "LOW", j_mc, p_mc,
                                           "TREEMAP: maxCategories mismatch — text may be unreadable.")
                        else:
                            self._pass("R25", f"{label}.maxCategories", "LOW", j_mc, p_mc)

                # Azure Map – zoom, pitch, 3D terrain
                if vtype == "azureMap":
                    for json_k, obj_k, prop_k, note, sev in [
                        ("zoom_level", "mapSettings", "zoom",      "AZURE MAP: zoom level mismatch.", "MEDIUM"),
                        ("pitch",      "mapSettings", "pitch",     "AZURE MAP: pitch boundary mismatch.", "LOW"),
                        ("terrain_3d", "mapSettings", "terrain3D", "AZURE MAP: 3D terrain toggle mismatch.", "LOW"),
                    ]:
                        j_val = j_vts.get(json_k)
                        if j_val is None:
                            continue
                        p_val = self._objs_prop_fe(p_objs, obj_k, prop_k)
                        if _norm(str(j_val)) != _norm(str(p_val or "")):
                            self._mismatch("R25", f"{label}.{json_k}", sev, j_val, p_val, note)
                        else:
                            self._pass("R25", f"{label}.{json_k}", sev, j_val, p_val)

                # Map style (filled map / bubble map)
                if vtype in {"map", "filledMap"}:
                    j_ms = j_vts.get("map_style")
                    if j_ms is not None:
                        p_ms = self._objs_prop_fe(p_objs, "mapStyles", "mapTheme")
                        if _norm(str(j_ms)) != _norm(str(p_ms or "")):
                            self._mismatch("R25", f"{label}.mapStyle", "LOW", j_ms, p_ms,
                                           "MAP: map style (e.g. grayscale) mismatch.")
                        else:
                            self._pass("R25", f"{label}.mapStyle", "LOW", j_ms, p_ms)

                # Dual-axis combo – secondary Y-axis label uniqueness
                if vtype in {"lineStackedColumnComboChart", "lineClusteredColumnComboChart"}:
                    j_y2 = j_vts.get("secondary_y_axis_enabled")
                    if j_y2 is not None:
                        p_y2 = self._objs_prop_fe(p_objs, "valueAxis", "secShow")
                        if _norm(str(j_y2)) != _norm(str(p_y2 or "")):
                            self._mismatch("R25", f"{label}.secondaryYAxis", "MEDIUM", j_y2, p_y2,
                                           "COMBO CHART: secondary Y-axis enabled mismatch.")
                        else:
                            self._pass("R25", f"{label}.secondaryYAxis", "MEDIUM", j_y2, p_y2)

    def run_all(self):
        self.check_r1_pages()
        self.check_r2_visuals()
        self.check_r3_field_bindings()
        self.check_r4_visual_filters()
        self.check_r5_page_filters()
        self.check_r6_report_filters()
        self.check_r7_bookmarks()
        self.check_r8_theme()
        self.check_r9_formatting()
        self.check_r10_custom_visuals()
        self.check_r11_buttons()
        self.check_r12_conditional_formatting()
        self.check_r13_tooltips()
        self.check_r14_drillthrough()
        self.check_r15_images()
        self.check_r16_html_embedded()
        self.check_r17_interactions()
        self.check_r18_sync_slicers()
        # Checklist extended checks (R19-R25)
        self.check_r19_canvas_environment()
        self.check_r20_alt_text_header_icons()
        self.check_r21_card_formatting()
        self.check_r22_slicer_controls()
        self.check_r23_axis_chart_detail()
        self.check_r24_analytics_overlays()
        self.check_r25_visual_type_specific()


# ─────────────────────────────────────────────────────────────────────────────
# Output writers
# ─────────────────────────────────────────────────────────────────────────────

SEV_WEIGHTS = {"CRITICAL": 5, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "PASS": 0.5, "INFO": 0.5}
PASS_THRESHOLD = 80.0

REPORT_DESCRIPTIONS = {
    "R1":  "Page existence, canvas size, hidden flag, display option",
    "R2":  "Visual count per page, visual type, bounding box, z-order",
    "R3":  "Field bindings: queryRef existence and count per visual role",
    "R4":  "Visual-level filter count, target field, isHiddenInViewMode",
    "R5":  "Page-level filter count, target field, isHiddenInViewMode",
    "R6":  "Report-level filter count and target fields",
    "R7":  "Bookmark existence, visual states, filter states",
    "R8":  "Theme name, dataColors palette, page background presence and image files",
    "R9":  "Visual formatting object categories and key properties",
    "R10": "Custom visual GUID existence, pbiviz.json manifest, AppSource deployment flag",
    "R11": "Button action type, navigation target, URL target, Power Automate re-linking flag",
    "R12": "Conditional formatting rules, CF type, threshold values",
    "R13": "Report page tooltip reference, custom tooltip fields, default tooltip check",
    "R14": "Drillthrough target page existence, filter fields, keepAllFilters",
    "R15": "Image file existence in StaticResources, imageUrl reference, scaling mode",
    "R16": "HTML/embedded custom visual GUID, measure binding, AppSource deployment flag",
    "R17": "Visual interaction overrides vs default cross-filter behaviour",
    "R18": "Sync slicer group existence, page list, visibility per page",
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
    base = os.path.join(out_dir, f"fe_report_{ts_f}")

    overall_score, overall_earned, overall_total = _weighted_score(results)
    overall_verdict = _verdict(overall_score)

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
            "description":   REPORT_DESCRIPTIONS.get(cid, ""),
            "scope":         "visual",
            "score":         grp_score,
            "verdict":       _verdict(grp_score) if grp_score is not None else "N/A",
            "passed":        passed,
            "failed":        failed,
            "missing":       missing,
            "total":         total,
            "weight_earned": round(we, 2),
            "weight_total":  round(wt, 2),
        })

    all_results_out = [{
        "check_id":     r.check_id,
        "attribute":    r.sub_id,
        "status":       r.status,
        "source_value": r.src_value,
        "json_value":   r.tgt_value,
        "note":         r.note,
        "severity":     r.severity if r.status != "PASS" else "PASS",
    } for r in results]

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
        "workbook_id":     workbook_id,
        "file_name":       file_name,
        "tool_name":       "fe_report_validator",
        "score":           overall_score,
        "verdict":         overall_verdict,
        "visual_score":    overall_score,
        "visual_verdict":  overall_verdict,
        "score_breakdown": {
            "overall": {
                "score":     overall_score,
                "verdict":   overall_verdict,
                "formula":   "severity-weighted: CRITICAL=5, HIGH=3, MEDIUM=2, LOW=1, INFO/PASS=0.5",
                "threshold": "PASS if score >= 80%",
            },
            "visual": {
                "scope":         "visual",
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
            "workbook_id":    workbook_id,
            "pbip_path":      pbip_path or "",
            "json_path":      json_path or "",
            "timestamp":      ts,
            "overall_score":  overall_score,
            "overall_verdict": overall_verdict,
            "visual_score":   overall_score,
            "visual_verdict": overall_verdict,
            "check_summary":  check_summary,
            "all_results":    all_results_out,
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
    print(f"  FE REPORT VALIDATOR — SUMMARY")
    print(f"  Score        : {score}%   (threshold: {PASS_THRESHOLD}%)")
    print(f"  Deploy flags : {len(deploy_flags)}")
    print("="*65)
    for cid in ALL_CHECKS:
        grp      = [r for r in results if r.check_id == cid]
        non_info = [r for r in grp if r.status != "INFO"]
        gp = sum(1 for r in non_info if r.status == "PASS")
        gt = len(non_info)
        if gt == 0:
            print(f"  ➖  {cid:<4} {CHECK_LABELS.get(cid,''):<42} {'0/0':>9}   N/A")
        else:
            we  = sum(SEV_WEIGHTS.get(r.severity, 1) for r in non_info if r.status == "PASS")
            wt  = sum(SEV_WEIGHTS.get(r.severity, 1) for r in non_info)
            pct = round(we / wt * 100, 1) if wt else 0
            icon = "✅" if pct >= 100 else "❌"
            print(f"  {icon}  {cid:<4} {CHECK_LABELS.get(cid,''):<42} {gp:>4}/{gt:<4} {pct:>6.1f}%")
    n_all  = [r for r in results if r.status != "INFO"]
    n_pass = sum(1 for r in n_all if r.status == "PASS")
    print(f"\n  {'─'*63}")
    print(f"  Total checks : {len(n_all)}  |  Passed : {n_pass}  |  Gaps : {gaps}")
    print(f"  Score        : {score}%")
    if deploy_flags:
        print(f"\n  ⚠️  {len(deploy_flags)} deployment action items — see deploy_report in output JSON")
    print(f"{'='*65}\n")


def main():
    ap = argparse.ArgumentParser(description="FE Report Validator — Enriched JSON vs PBIP Report")
    ap.add_argument("--json",  required=True, help="Path to enriched report JSON file")
    ap.add_argument("--pbip",  required=True, help="Path to target PBIP Report folder")
    ap.add_argument("--out",   default="./output", help="Output folder (default: ./output)")
    args = ap.parse_args()

    if not os.path.isfile(args.json):
        sys.exit(f"ERROR: JSON file not found: {args.json}")
    if not os.path.isdir(args.pbip):
        sys.exit(f"ERROR: PBIP folder not found: {args.pbip}")

    print(f"\nFE Report Validator")
    print(f"  JSON : {args.json}")
    print(f"  PBIP : {args.pbip}")
    print(f"  Out  : {args.out}\n")

    v = FEReportValidator(args.json, args.pbip)
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
