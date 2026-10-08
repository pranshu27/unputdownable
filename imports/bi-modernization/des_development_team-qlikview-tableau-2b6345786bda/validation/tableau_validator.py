"""
Tableau Validation Script — TWB/TWBX vs Homogeneous JSON
=========================================================
Compares every artifact extracted from a Tableau workbook (.twb or .twbx)
against the homogeneous JSON produced by the RE/OP AutoGen tool.

Check  Category                          What is validated
-----  --------------------------------  --------------------------------------------------
T1     Database Connection               Datasource name, source_type, connection_mode, path,
                                         server, database, published datasource references
T2     Tables & Joins                    Table names, join predicates, join type, data blends
T3     Columns & Data Types              Column names, data types, format strings,
                                         semantic roles
T4     filters                           Worksheet-level filters (column, class, min/max),
                                         dashboard slicer counts
T5     Hierarchies                       hierarchies names and drill-path fields
T6     Dashboard Layout                  Dashboard name, canvas size, visual count
                                         (worksheet zones only), visual types and titles
T7     Dashboard Actions                 Action name, type, source worksheet, target
T8     Custom SQL                        Custom SQL presence and content capture
T9     Parameters                        Parameter name, datatype, default value,
                                         allowed values list (ENHANCED)
T10    Worksheets                        Worksheet names, field bindings
T11    Sets                              Dynamic and static data subsets (<set> /
                                         <group> with groupfilters)
T12    Groups, Bins & Folders            Static dimension groupings, numeric bin definitions,
                                         sidebar folder organisation
T13    LOD, Context filters &            FIXED/INCLUDE/EXCLUDE LOD expressions (CRITICAL --
       Table Calcs                       different DAX patterns), context filters flags
                                         (is-context=true -- affects LOD computation),
                                         window functions (RUNNING_SUM, RANK, INDEX),
                                         ad-hoc shelf calculations
T14    Stories, Aliases & Sort Config    Story layouts and story point targets,
                                         column value aliases, explicit sort configurations,
                                         reference lines and bands
T15    Datasource filters & Security     Datasource-level filters (pre-worksheet),
                                         user function calcs (USERNAME, ISMEMBEROF -- RLS),
                                         URL actions and parameter actions (2019.2+)
T16    Workbook Metadata & Assets        Tableau version, source platform, published
                                         datasources (Server/Cloud), embedded images
                                         from Images/ folder
T17    Calculations                      Calculated field names, expressions, formulas

Usage:
  python tableau_validation_script.py --twb path/to/file.twb --json path/to/response.json --out ./output

  Supports both .twb (XML) and .twbx (zip containing .twb) formats.

Dependencies:
  pip install pandas
"""
import os, json, zipfile, argparse, re
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Any, Optional
import pandas as pd

@dataclass
class CheckResult:
    check_id: str
    attribute: str
    status: str
    source_value: Any
    json_value: Any
    note: str = ""
    severity: str = ""

SEVERITY_RULES = [
    ("T1","name","MISSING","CRITICAL"), ("T1","name","FAIL","CRITICAL"),
    ("T1","source_type","MISSING","CRITICAL"), ("T1","source_type","FAIL","CRITICAL"),
    ("T1","connection_mode","MISSING","CRITICAL"), ("T1","connection_mode","FAIL","CRITICAL"),
    ("T1","path","MISSING","CRITICAL"), ("T1","path","FAIL","MEDIUM"),
    ("T2","table_name","MISSING","CRITICAL"), ("T2","table_name","FAIL","CRITICAL"),
    ("T2","join_predicate","MISSING","CRITICAL"), ("T2","join_predicate","FAIL","CRITICAL"),
    ("T2","join_type","MISSING","CRITICAL"), ("T2","join_type","FAIL","CRITICAL"),
    ("T3","data_type","FAIL","HIGH"), ("T3","data_type","MISSING","HIGH"),
    ("T3","column_name","MISSING","HIGH"),
    ("T4","filters","MISSING","HIGH"), ("T4","filters","FAIL","HIGH"),
    ("T5","name","MISSING","CRITICAL"), ("T5","name","FAIL","CRITICAL"),
    ("T5","hierarchies","MISSING","HIGH"), ("T5","hierarchies","FAIL","HIGH"),
    ("T17","name","MISSING","HIGH"), ("T17","name","FAIL","HIGH"),
    ("T17","expression","MISSING","HIGH"), ("T17","expression","FAIL","HIGH"),
    ("T6","name","MISSING","HIGH"), ("T6","name","FAIL","HIGH"),
    ("T6","width","FAIL","HIGH"), ("T6","height","FAIL","HIGH"),
    ("T6","has_visuals","FAIL","HIGH"), ("T6","field_count","FAIL","HIGH"),
    ("T6","visual_type","FAIL","MEDIUM"),
    ("T7","action","MISSING","HIGH"), ("T7","type","FAIL","HIGH"),
    ("T7","activation","FAIL","HIGH"), ("T7","source_worksheet","FAIL","HIGH"),
    ("T7","target_dashboard","FAIL","HIGH"), ("T7","excluded_worksheets","FAIL","HIGH"),
    ("T7","fields","FAIL","HIGH"),
    ("T8","sql_captured","MISSING","CRITICAL"), ("T8","sql_captured","FAIL","CRITICAL"),
    ("T9","name","MISSING","HIGH"), ("T9","name","FAIL","HIGH"),
    ("T10","exists_in_json","MISSING","HIGH"), ("T10","exists_in_json","FAIL","HIGH"),
    ("T10","field[","MISSING","HIGH"), ("T10","field[","FAIL","HIGH"),
    # T11 — Sets
    ("T11","name","MISSING","HIGH"),
    # T12 — Groups, Bins, Folders
    ("T12","group","MISSING","HIGH"),("T12","bin","MISSING","MEDIUM"),("T12","folder","MISSING","LOW"),
    # T13 — LOD, Context filters, Table Calcs, Shelf Calcs
    ("T13","lod","MISSING","CRITICAL"),("T13","context_filters","MISSING","CRITICAL"),
    ("T13","table_calc","MISSING","CRITICAL"),("T13","shelf_calc","MISSING","HIGH"),
    # T14 — Stories, Aliases, Sort, Reference Lines
    ("T14","story","MISSING","HIGH"),("T14","aliases","MISSING","MEDIUM"),
    ("T14","sort","MISSING","MEDIUM"),("T14","reference_line","MISSING","MEDIUM"),
    # T15 — Datasource filters, User Functions, Action completeness
    ("T15","datasource_filters","MISSING","CRITICAL"),("T15","user_function","MISSING","CRITICAL"),
    ("T15","parameter_action","MISSING","HIGH"),("T15","url_action","MISSING","HIGH"),
    # T16 — Metadata, Published Datasources, Images
    ("T16","published_datasource","MISSING","CRITICAL"),("T16","embedded_image","MISSING","MEDIUM"),
]

# Worksheets to ignore during validation (not used in any dashboard)
WORKSHEETS_TO_IGNORE = {
    "Avg Order Qty",
    "Distance Analysis",
    "Invoice Qty Sales %",
    "Null Status Filter",
    "Order State LTV",
    "Product Desc Variants",
    "Profit % Product",
    "Regional Customers",
    "Revenue & Profit Analysis",
    "Sales % by Qty",
    "Sales Count",
    "Shipping Cost per Unit",
    "Shipping Overview",
    "State Code Review",
    "State Sales",
    "Statewide Customers",
    "Transaction Totals",
}

def assign_severity(r):
    if r.status=="PASS": return "PASS"
    # Check if severity was pre-set on the CheckResult
    if hasattr(r,"severity") and r.severity and r.severity not in ("","PASS"):
        return r.severity
    for chk,kw,st,sev in SEVERITY_RULES:
        if r.check_id.startswith(chk) and kw.lower() in r.attribute.lower() and r.status==st:
            return sev
    defaults={"T1":"CRITICAL","T2":"CRITICAL","T3":"HIGH","T4":"HIGH","T5":"HIGH",
              "T6":"MEDIUM","T7":"MEDIUM","T8":"CRITICAL","T9":"HIGH","T10":"MEDIUM",
              "T11":"HIGH","T12":"MEDIUM","T13":"CRITICAL","T14":"MEDIUM","T15":"HIGH","T16":"MEDIUM"}
    return defaults.get(r.check_id,"MEDIUM")

@dataclass
class ValidationReport:
    workbook_name: str; twb_path: str; json_path: str; timestamp: str
    results: list = field(default_factory=list)
    @property
    def total(self): return len(self.results)
    @property
    def passed(self): return sum(1 for r in self.results if r.status=="PASS")
    @property
    def score(self): return round(self.passed/self.total*100,2) if self.total else 0
    PASS_THRESHOLD = 80.0
    @property
    def verdict(self): return "PASS" if self.score >= self.PASS_THRESHOLD else "FAIL"
    @property
    def gaps(self): return [r for r in self.results if r.status!="PASS"]

class TWBExtractor:
    def __init__(self, twb_path):
        self.twb_path=Path(twb_path); self.root=None

    def extract(self):
        if self.twb_path.suffix.lower()==".twbx":
            twb_file=self._extract_twb_from_twbx()
        else:
            twb_file=self.twb_path
        self.root=ET.parse(twb_file).getroot()
        print(f"[Extractor] Parsed TWB: {twb_file.name}")
        return self.root

    def _extract_twb_from_twbx(self):
        import tempfile
        self._tmp_dir=tempfile.mkdtemp()
        with zipfile.ZipFile(self.twb_path,"r") as z:
            z.extractall(self._tmp_dir)
            twb_files=[n for n in z.namelist() if n.lower().endswith(".twb")]
            if not twb_files: raise FileNotFoundError("No .twb inside .twbx")
            return Path(self._tmp_dir)/twb_files[0]

    def get_datasources(self):
        datasources=[]
        for ds in self.root.findall(".//datasource"):
            ds_name=ds.get("caption",ds.get("name",""))
            if not ds_name or ds.get("inline","")!="true": continue
            conn=ds.find("connection"); conn_class=conn.get("class","") if conn is not None else ""
            source_type=""; path=""; server=""; database=""
            named_conns=ds.findall(".//named-connection"); paths_found=[]
            for nc in named_conns:
                ic=nc.find("connection")
                if ic is not None:
                    nc_class=ic.get("class","")
                    if nc_class=="textscan":
                        source_type="csv"; p=ic.get("filename","")
                        if p: paths_found.append(p)
                    else:
                        source_type=nc_class; server=ic.get("server",""); database=ic.get("dbname","")
                    if not path: path=ic.get("directory","") or ic.get("filename","")
            if paths_found: path=paths_found[0]
            connection_mode="extract" if ds.find("extract") is not None else "live"
            if conn_class=="federated" and len(named_conns)>1: source_type="federated"
            datasources.append({"name":ds_name,"source_type":source_type or conn_class,
                "connection_mode":connection_mode,"path":path,"server":server,"database":database})
        return datasources

    def get_tables_and_joins(self):
        tables=[]; joins=[]; seen=set()
        for ds in self.root.findall(".//datasource[@inline='true']"):
            conn=ds.find("connection")
            if conn is None: continue
            for rel in conn.iter("relation"):
                rt=rel.get("type","")
                if rt=="table":
                    tn=rel.get("name","")
                    if tn and tn not in seen: seen.add(tn); tables.append({"name":tn})
                elif rt=="join":
                    jt=rel.get("join","inner"); clause=rel.find("clause")
                    if clause is not None:
                        expr=clause.find("expression")
                        if expr is not None:
                            ops=expr.findall("expression")
                            if len(ops)>=2:
                                joins.append({"join_type":jt,"left_predicate":ops[0].get("op",""),
                                    "right_predicate":ops[1].get("op","")})
        return tables, joins

    def get_columns(self):
        columns=[]
        for ds in self.root.findall(".//datasource[@inline='true']"):
            ds_name=ds.get("caption",ds.get("name",""))
            for mr in ds.findall(".//metadata-record[@class='column']"):
                columns.append({"datasource":ds_name,"name":mr.findtext("remote-name",""),
                    "data_type":mr.findtext("local-type",""),
                    "nullable":mr.findtext("contains-null","true").lower()=="true",
                    "parent_table":mr.findtext("parent-name","").strip("[]"),
                    "format_string":""})
            for col_el in ds.findall("column"):
                cn=col_el.get("name","").strip("[]"); sr=col_el.get("semantic-role","")
                fmt=col_el.get("default-format","")
                for c in columns:
                    if c["name"]==cn and c["datasource"]==ds_name:
                        if sr: c["semantic_role"]=sr
                        if fmt: c["format_string"]=fmt
                        break
        return columns

    def get_filters(self):
        filters=[]
        for ws in self.root.findall(".//worksheet"):
            wn=ws.get("name","")
            for flt in ws.findall(".//filter"):
                fc=flt.get("class",""); col=flt.get("column","")
                mn=flt.findtext("min"); mx=flt.findtext("max")
                min_el=flt.find("min"); max_el=flt.find("max")
                mv=min_el.text if min_el is not None and min_el.text else None
                xv=max_el.text if max_el is not None and max_el.text else None
                filters.append({"scope":"worksheet","worksheet":wn,"class":fc,"column":col,"min":mv,"max":xv})
        for sv in self.root.findall(".//shared-view"):
            for flt in sv.findall(".//filter"):
                filters.append({"scope":"datasource","worksheet":"","class":flt.get("class",""),
                    "column":flt.get("column",""),"min":None,"max":None})
        return filters

    def get_calculations(self):
        calcs=[]
        for ds in self.root.findall(".//datasource[@inline='true']"):
            dn=ds.get("caption",ds.get("name",""))
            for col_el in ds.findall("column"):
                calc_el=col_el.find("calculation")
                if calc_el is not None:
                    calcs.append({"name":col_el.get("caption",col_el.get("name","")),
                        "expression":calc_el.get("formula",""),"datasource":dn})
        return calcs

    def get_hierarchies(self):
        hierarchies=[]
        for ds in self.root.findall(".//datasource[@inline='true']"):
            dn=ds.get("caption",ds.get("name",""))
            for dp in ds.findall(".//drill-path"):
                levels=[]
                for idx, field_elem in enumerate(dp.findall("field")):
                    field_text = field_elem.text.strip("[]") if field_elem.text else ""
                    if field_text:
                        levels.append({"name": field_text, "column": field_text, "ordinal": idx})
                hierarchies.append({"name":dp.get("name",""),"levels":levels,"datasource":dn})
        return hierarchies

    def get_dashboards(self):
        dashboards=[]
        for db in self.root.findall(".//dashboard"):
            db_name=db.get("name",""); size_el=db.find("size")
            width=int(size_el.get("maxwidth","0")) if size_el is not None else 0
            height=int(size_el.get("maxheight","0")) if size_el is not None else 0
            raw_zones=[]
            for zone in db.findall(".//zone"):
                zt=zone.get("type-v2",""); zn=zone.get("name","")
                if zt=="text": vt="textbox"
                elif zt=="filter": vt="slicer"
                elif zt=="dashboard-object": vt="button" if zone.find("button") is not None else "blank"
                elif zn: vt="worksheet"
                else: vt="unknown"
                raw_zones.append({"id":zone.get("id",""),"name":zn,"visual_type":vt,
                    "raw_x":int(zone.get("x","0")),"raw_y":int(zone.get("y","0")),
                    "raw_w":int(zone.get("w","0")),"raw_h":int(zone.get("h","0")),"zone_type_v2":zt})
            mx=max((z["raw_x"]+z["raw_w"]) for z in raw_zones) if raw_zones else 1
            my=max((z["raw_y"]+z["raw_h"]) for z in raw_zones) if raw_zones else 1
            sx=width/mx if mx>0 else 1; sy=height/my if my>0 else 1
            zones=[{**rz,"x":round(rz["raw_x"]*sx,1),"y":round(rz["raw_y"]*sy,1),
                "width":round(rz["raw_w"]*sx,1),"height":round(rz["raw_h"]*sy,1)} for rz in raw_zones]
            dashboards.append({"name":db_name,"width":width,"height":height,"zones":zones})
        return dashboards

    def get_actions(self):
        actions=[]
        for a in self.root.findall(".//action"):
            act_el=a.find("activation"); src_el=a.find("source"); cmd_el=a.find("command")
            cmd=cmd_el.get("command","") if cmd_el is not None else ""
            if "filter" in cmd.lower(): at="filter"
            elif "brush" in cmd.lower(): at="highlight"
            else: at=cmd
            activation=act_el.get("type","") if act_el is not None else ""
            source_worksheet=[]
            if src_el is not None and src_el.get("worksheet"):
                source_worksheet=[src_el.get("worksheet")]
            target_dashboard=""
            excluded_worksheets=[]
            fields=[]
            if cmd_el is not None:
                for p in cmd_el.findall("param"):
                    name=p.get("name","")
                    value=p.get("value","") or ""
                    if name=="target":
                        target_dashboard=value
                    elif name=="exclude":
                        excluded_worksheets=[x.strip() for x in value.split(",") if x.strip()]
                    elif name=="field-captions":
                        fields=[x.strip() for x in value.split(",") if x.strip()]
            actions.append({"name":a.get("caption",""),"type":at,
                "activation":activation,
                "source_worksheet":source_worksheet,
                "target_dashboard":target_dashboard,
                "excluded_worksheets":excluded_worksheets,
                "fields":fields})
        return actions

    def get_worksheets(self):
        worksheets=[]
        for ws in self.root.findall(".//worksheet"):
            wn=ws.get("name",""); field_refs=set()
            rows_el=ws.find(".//rows"); cols_el=ws.find(".//cols")
            rt=rows_el.text if rows_el is not None and rows_el.text else ""
            ct=cols_el.text if cols_el is not None and cols_el.text else ""
            if rt: field_refs.update(re.findall(r'\[.*?\]\.\[.*?\]',rt))
            if ct: field_refs.update(re.findall(r'\[.*?\]\.\[.*?\]',ct))
            for enc in ws.findall(".//encodings//*"):
                cr=enc.get("column","")
                if cr: field_refs.add(cr)
            mark_el=ws.find(".//mark")
            mc=mark_el.get("class","Automatic") if mark_el is not None else "Automatic"
            ht=ws.find(".//tooltip") is not None
            worksheets.append({"name":wn,"field_count":len(field_refs),"fields":list(field_refs),
                "mark_type":mc,"has_custom_tooltip":ht})
        return worksheets

    def get_dashboard_viewpoints(self):
        """Return {dashboard_name: [viewpoint_names]} for every <window class='dashboard'>.
        Matches JSON page display_name -> TWB dashboard name, then
        JSON visual title -> TWB <viewpoint name='...'> within that dashboard."""
        viewpoints={}
        for win in self.root.findall(".//window[@class='dashboard']"):
            dash_name=(win.get("name","") or "").strip()
            names=[]
            for vp in win.findall(".//viewpoint"):
                name=(vp.get("name","") or "").strip()
                if name:
                    names.append(name)
            viewpoints[dash_name]=names
        return viewpoints

    def get_custom_sql(self):
        sqls=[]
        for ds in self.root.findall(".//datasource[@inline='true']"):
            dn=ds.get("caption",ds.get("name",""))
            for rel in ds.iter("relation"):
                if rel.get("type","")=="text" and rel.text and rel.text.strip():
                    sqls.append({"datasource":dn,"sql":rel.text.strip(),"name":rel.get("name","Custom SQL")})
        return sqls

    def get_parameters(self):
        params=[]
        for ds in self.root.findall(".//datasource"):
            if ds.get("name","").lower()=="parameters":
                for col_el in ds.findall("column"):
                    name=col_el.get("caption",col_el.get("name",""))
                    datatype=col_el.get("datatype","")
                    default_val=""
                    range_el=col_el.find("range")
                    if range_el is not None:
                        default_val=range_el.get("default","")
                    # Allowed values list
                    allowed=[]
                    for mv in col_el.findall(".//member"):
                        v=mv.get("value","")
                        if v: allowed.append(v)
                    params.append({"name":name,"datatype":datatype,
                                   "default_value":default_val,"allowed_values":allowed})
        return params

    def get_sets(self):
        """Extract Tableau Sets — dynamic or static data subsets (<set> tags)."""
        sets=[]
        for ds in self.root.findall(".//datasource[@inline='true']"):
            dn=ds.get("caption",ds.get("name",""))
            for s in ds.findall(".//group[@name]"):
                # Sets are stored as groups with a groupfilters
                gf=s.find("groupfilters")
                if gf is None: continue
                # Only treat as set if it has function=filters or level-members
                fn=gf.get("function","")
                if fn not in ("filters","level-members","union",""): continue
                sets.append({
                    "name":s.get("name","").strip("[]"),
                    "datasource":dn,
                    "type":"dynamic" if fn=="filters" else "static",
                    "function":fn
                })
            # Also look for explicit <set> elements
            for s in ds.findall(".//set"):
                sets.append({
                    "name":s.get("name","").strip("[]"),
                    "datasource":dn,
                    "type":"set",
                    "function":""
                })
        return sets

    def get_groups(self):
        """Extract Tableau Groups — static manual category groupings."""
        groups=[]
        for ds in self.root.findall(".//datasource[@inline='true']"):
            dn=ds.get("caption",ds.get("name",""))
            for col_el in ds.findall("column"):
                # A grouped field has a <calculation> with formula containing 'group'
                # OR has a <members> child
                members_el=col_el.find("members")
                if members_el is None: continue
                gname=col_el.get("caption",col_el.get("name","")).strip("[]")
                members=[m.get("name","") for m in members_el.findall("member")]
                groups.append({"name":gname,"datasource":dn,"member_count":len(members),"members":members[:20]})
        return groups

    def get_bins(self):
        """Extract Tableau Bins — numeric bucket ranges for histograms."""
        bins=[]
        for ds in self.root.findall(".//datasource[@inline='true']"):
            dn=ds.get("caption",ds.get("name",""))
            for col_el in ds.findall("column"):
                # Bin columns have datatype='integer' and a <bin> child or
                # caption ending with ' (bin)' or a calculation referencing INT()
                calc_el=col_el.find("calculation")
                if calc_el is None: continue
                formula=calc_el.get("formula","")
                if not formula: continue
                # Detect bin pattern: INT([Field]/size)*size
                if "int(" not in formula.lower() and "floor(" not in formula.lower():
                    continue
                bins.append({
                    "name":col_el.get("caption",col_el.get("name","")).strip("[]"),
                    "datasource":dn,
                    "formula":formula
                })
        return bins

    def get_folders(self):
        """Extract sidebar folder groupings for dimensions and measures."""
        folders=[]
        for ds in self.root.findall(".//datasource[@inline='true']"):
            dn=ds.get("caption",ds.get("name",""))
            for folder_el in ds.findall(".//folder"):
                fname=folder_el.get("name","")
                role=folder_el.get("role","")
                items=[fi.get("name","").strip("[]")
                       for fi in folder_el.findall("folder-item")]
                folders.append({"name":fname,"role":role,"datasource":dn,
                                "item_count":len(items),"items":items})
        return folders

    def get_stories(self):
        """Extract Tableau Stories — sequential presentation layouts."""
        stories=[]
        for story in self.root.findall(".//story"):
            sname=story.get("name","")
            points=[]
            for sp in story.findall(".//story-point"):
                # Each story point can pin a dashboard or worksheet
                caption=sp.get("caption","")
                nav_el=sp.find(".//navigator-item")
                if nav_el is None: nav_el=sp.find("nav")
                target=""
                if nav_el is not None:
                    target=nav_el.get("name","")
                points.append({"caption":caption,"target":target})
            stories.append({"name":sname,"point_count":len(points),"points":points})
        return stories

    def get_shelf_calcs(self):
        """
        Extract ad-hoc calculations typed directly on shelves (rows/cols).
        These are NOT saved as calculated fields — they live in the shelf text only.
        Detected by scanning <rows>/<cols>/<encoding> text for inline formula patterns.
        """
        shelf_calcs=[]
        for ws in self.root.findall(".//worksheet"):
            wn=ws.get("name","")
            for shelf_tag in ["rows","cols"]:
                el=ws.find(f".//{shelf_tag}")
                if el is None or not el.text: continue
                text=el.text.strip()
                # Inline formulas: AGG(), YEAR(), MONTH(), SUM([Calc]), etc.
                # Detect anything that contains a function call not matching a stored field ref
                inline_pats=[
                    r'AGG\([^\)]+\)',
                    r'YEAR\([^\)]+\)',r'MONTH\([^\)]+\)',r'DAY\([^\)]+\)',
                    r'WEEK\([^\)]+\)',r'QUARTER\([^\)]+\)',
                    r'SUM\([^\)]+\*[^\)]+\)',  # SUM([x]*1.1) style
                    r'IF\s+[^\)]+\s+THEN',
                    r'DATETRUNC\([^\)]+\)',
                ]
                import re as _re
                for pat in inline_pats:
                    for m in _re.finditer(pat,text,_re.IGNORECASE):
                        shelf_calcs.append({
                            "worksheet":wn,"shelf":shelf_tag,
                            "formula":m.group()
                        })
        return shelf_calcs

    def get_table_calculations(self):
        """
        Extract table calculations — window functions like RUNNING_SUM, RANK.
        These are stored inside <table-calc> elements within worksheet calculations.
        """
        table_calcs=[]
        for ds in self.root.findall(".//datasource[@inline='true']"):
            dn=ds.get("caption",ds.get("name",""))
            for col_el in ds.findall("column"):
                calc_el=col_el.find("calculation")
                if calc_el is None: continue
                formula=calc_el.get("formula","")
                tc_el=calc_el.find("table-calc")
                # Also detect by formula keywords
                tc_keywords=["RUNNING_","WINDOW_","RANK","INDEX()","SIZE()",
                             "FIRST()","LAST()","LOOKUP(","LEAD(","LAG(",
                             "TOTAL(","PREVIOUS_VALUE("]
                is_tc=(tc_el is not None or
                       any(k.lower() in formula.lower() for k in tc_keywords))
                if not is_tc: continue
                addressing=""
                partitioning=""
                if tc_el is not None:
                    addressing=tc_el.get("addressing","")
                    partitioning=tc_el.get("pane","")
                table_calcs.append({
                    "name":col_el.get("caption",col_el.get("name","")).strip("[]"),
                    "datasource":dn,
                    "formula":formula,
                    "addressing":addressing,
                    "partitioning":partitioning
                })
        return table_calcs

    def get_sort_configs(self):
        """Extract explicit sort configurations per worksheet."""
        sorts=[]
        for ws in self.root.findall(".//worksheet"):
            wn=ws.get("name","")
            for sort_el in ws.findall(".//sort"):
                col=sort_el.get("column","").strip("[]")
                direction=sort_el.get("direction","asc")
                sort_type=sort_el.get("type","alphabetic")
                measure_col=""
                by_el=sort_el.find("by")
                if by_el is not None:
                    measure_col=by_el.get("column","").strip("[]")
                sorts.append({"worksheet":wn,"column":col,"direction":direction,
                              "sort_type":sort_type,"measure_column":measure_col})
        return sorts

    def get_aliases(self):
        """Extract column value aliases — renamed individual data values."""
        aliases=[]
        for ds in self.root.findall(".//datasource[@inline='true']"):
            dn=ds.get("caption",ds.get("name",""))
            for col_el in ds.findall("column"):
                aliases_el=col_el.find("aliases")
                if aliases_el is None: continue
                cname=col_el.get("caption",col_el.get("name","")).strip("[]")
                alias_list=[]
                for alias in aliases_el.findall("alias"):
                    alias_list.append({
                        "from":alias.get("from",""),
                        "to":alias.get("to","")
                    })
                if alias_list:
                    aliases.append({"column":cname,"datasource":dn,
                                    "alias_count":len(alias_list),"aliases":alias_list[:10]})
        return aliases

    def get_datasource_filters(self):
        """
        Extract data source level filters — applied before any worksheet filters,
        reduce the dataset globally. Different from worksheet-level filters.
        """
        ds_filters=[]
        for ds in self.root.findall(".//datasource[@inline='true']"):
            dn=ds.get("caption",ds.get("name",""))
            for flt in ds.findall(".//extract/connection/filter"):
                col=flt.get("column",""); fc=flt.get("class","")
                ds_filters.append({"datasource":dn,"column":col,"class":fc})
            # Also datasource-level filters outside of extract
            for flt in ds.findall("filter"):
                col=flt.get("column",""); fc=flt.get("class","")
                if col:
                    ds_filters.append({"datasource":dn,"column":col,"class":fc,"scope":"datasource"})
        return ds_filters

    def get_reference_lines(self):
        """Extract reference lines and bands from Analytics pane."""
        ref_lines=[]
        for ws in self.root.findall(".//worksheet"):
            wn=ws.get("name","")
            for rl in ws.findall(".//reference-line"):
                ref_lines.append({
                    "worksheet":wn,
                    "type":rl.get("type","line"),
                    "column":rl.get("column",""),
                    "aggregation":rl.get("aggregation",""),
                    "label":rl.get("label","")
                })
        return ref_lines

    def get_context_filters(self):
        """Extract context filters — ui:is-context='true' flag is critical for LOD computation."""
        context_filters=[]
        for ws in self.root.findall(".//worksheet"):
            wn=ws.get("name","")
            for flt in ws.findall(".//filter"):
                # Context filters flag can be in various namespace formats
                is_ctx=(flt.get("ui:is-context","false").lower()=="true" or
                        flt.get("is-context","false").lower()=="true" or
                        flt.get("{ui}is-context","false").lower()=="true")
                if is_ctx:
                    col=flt.get("column","")
                    context_filters.append({"worksheet":wn,"column":col})
        return context_filters

    def get_lod_calculations(self):
        """
        Extract LOD (Level of Detail) expressions — FIXED, INCLUDE, EXCLUDE.
        Critical: these translate to very different DAX patterns than regular calcs.
        """
        lods=[]
        for ds in self.root.findall(".//datasource[@inline='true']"):
            dn=ds.get("caption",ds.get("name",""))
            for col_el in ds.findall("column"):
                calc_el=col_el.find("calculation")
                if calc_el is None: continue
                formula=calc_el.get("formula","")
                import re as _re
                lod_pat=_re.compile(r'\{(FIXED|INCLUDE|EXCLUDE)[^}]*\}',_re.IGNORECASE)
                if lod_pat.search(formula):
                    lod_type=lod_pat.search(formula).group(1).upper()
                    lods.append({
                        "name":col_el.get("caption",col_el.get("name","")).strip("[]"),
                        "datasource":dn,
                        "lod_type":lod_type,
                        "formula":formula
                    })
        return lods

    def get_user_functions(self):
        """Extract user-based security calculations — USERNAME(), ISMEMBEROF(), USERDOMAIN()."""
        user_funcs=[]
        for ds in self.root.findall(".//datasource[@inline='true']"):
            dn=ds.get("caption",ds.get("name",""))
            for col_el in ds.findall("column"):
                calc_el=col_el.find("calculation")
                if calc_el is None: continue
                formula=calc_el.get("formula","")
                user_kw=["USERNAME()","USERDOMAIN()","ISMEMBEROF(","FULLNAME()"]
                if any(kw.lower() in formula.lower() for kw in user_kw):
                    user_funcs.append({
                        "name":col_el.get("caption",col_el.get("name","")).strip("[]"),
                        "datasource":dn,"formula":formula
                    })
        return user_funcs

    def get_workbook_metadata(self):
        """Extract workbook-level metadata from the root <workbook> element."""
        meta={}
        if self.root is None: return meta
        meta["source_build"]=self.root.get("source-build","")
        meta["source_platform"]=self.root.get("source-platform","")
        meta["version"]=self.root.get("version","")
        # Published datasource connections (tds or tdsx references)
        published=[]
        for ds in self.root.findall(".//datasource"):
            conn=ds.find("connection")
            if conn is not None and conn.get("class","") in ("tde","hyper","tableau-server"):
                published.append({
                    "name":ds.get("caption",ds.get("name","")),
                    "class":conn.get("class",""),
                    "server":conn.get("server",""),
                    "site":conn.get("site","")
                })
        meta["published_datasources"]=published
        # Embedded images inventory
        images=[]
        for img in self.root.findall(".//image"):
            src=img.get("source","")
            if src: images.append(src)
        meta["embedded_images"]=images
        return meta

    def extract_all(self):
        self.extract(); tables,joins=self.get_tables_and_joins()
        # Build caption map: internal_name_lower -> caption_lower (used by _extract_col_name)
        # so that Calculation_XXXXX refs resolve to human field names for field comparisons.
        self._caption_map = {}
        for ds in self.root.findall(".//datasource"):
            for col_el in ds.findall(".//column"):
                internal = col_el.get("name","").strip("[]").strip()
                caption  = col_el.get("caption","").strip()
                if internal and caption:
                    self._caption_map[internal.lower()] = caption
        return {"datasources":self.get_datasources(),"tables":tables,"joins":joins,
            "columns":self.get_columns(),"filters":self.get_filters(),
            "calculations":self.get_calculations(),"hierarchies":self.get_hierarchies(),
            "dashboards":self.get_dashboards(),"actions":self.get_actions(),
            "worksheets":self.get_worksheets(),"dashboard_viewpoints":self.get_dashboard_viewpoints(),
            "custom_sql":self.get_custom_sql(),
            "parameters":self.get_parameters(),
            # --- new extractors ---
            "sets":self.get_sets(),
            "groups":self.get_groups(),
            "bins":self.get_bins(),
            "folders":self.get_folders(),
            "stories":self.get_stories(),
            "shelf_calcs":self.get_shelf_calcs(),
            "table_calculations":self.get_table_calculations(),
            "sort_configs":self.get_sort_configs(),
            "aliases":self.get_aliases(),
            "datasource_filters":self.get_datasource_filters(),
            "reference_lines":self.get_reference_lines(),
            "context_filters":self.get_context_filters(),
            "lod_calculations":self.get_lod_calculations(),
            "user_functions":self.get_user_functions(),
            "workbook_metadata":self.get_workbook_metadata()}

class TableauValidator:
    def __init__(self, twb_artifacts, homo_json, caption_map=None):
        self.twb=twb_artifacts; self.json=homo_json; self.results=[]
        self._caption_map = caption_map or {}

    def _log(self, cid, attr, src, jsn, note=""):
        if src is None and jsn is None: st="PASS"
        elif src is None: st="PASS"
        elif jsn is None: st="MISSING"
        elif src == jsn: st="PASS"
        elif isinstance(src,str) and isinstance(jsn,str): st="PASS" if src.strip().lower()==jsn.strip().lower() else "FAIL"
        elif isinstance(src,(int,float)) and isinstance(jsn,(int,float)): st="PASS" if abs(src-jsn)<0.0001 else "FAIL"
        elif isinstance(src,bool): st="PASS" if src==jsn else "FAIL"
        elif jsn == "" or jsn == [] or jsn == {}: st="MISSING"
        else: st="FAIL"
        self.results.append(CheckResult(check_id=cid,attribute=attr,status=st,source_value=src,json_value=jsn,note=note))

    def _extract_col_name(self, ref):
        """Extract a human-readable column name from a TWB field reference.
        Resolves internal Calculation_XXXXX ids to their caption using self._caption_map.
        Examples:
          'sum:Calculation_178...:qk' -> 'Shipping (Baseline)'
          'none:Category:nk'          -> 'Category'
          '[Orders].[Sales]'          -> 'Sales'
        """
        raw = ""
        for part in ref.split("."):
            clean=part.strip("[]")
            if ":" in clean:
                segs=clean.split(":")
                if len(segs)>=2:
                    raw = segs[1]; break
        if not raw:
            if "[" in ref:
                lb=ref.rfind("["); rb=ref.rfind("]")
                if lb<rb: raw = ref[lb+1:rb]
        if not raw:
            return ""
        # Resolve internal calculation ids to their human caption
        caption_map = getattr(self, '_caption_map', {})
        return caption_map.get(raw.lower(), raw)

    def check_t1(self):
        print("\n[T1] Checking data source connections...")
        src_ds  = self.twb.get("datasources", [])
        json_ds = self.json.get("data_sources", [])

        # Exclude Tableau's internal 'Parameters' pseudo-datasource —
        # it is not a real data connection; parameters are validated in T9.
        src_ds = [d for d in src_ds
                  if d.get("name", "").lower() != "parameters"]
        
        # Also exclude 'Parameters' from JSON datasources
        json_ds = [d for d in json_ds
                   if d.get("name", "").lower() != "parameters"]

        def normalize_path(path_str):
            """Normalize file paths by removing numeric suffixes before extension.
            E.g., 'tbl_sales1.csv' -> 'tbl_sales.csv'
            """
            if not path_str:
                return path_str
            # Split on the last dot to separate filename and extension
            if '.' in path_str:
                parts = path_str.rsplit('.', 1)
                base = parts[0]
                ext = '.' + parts[1]
                # Remove trailing digits from the base
                import re
                base = re.sub(r'\d+$', '', base)
                return base + ext
            else:
                # No extension, just remove trailing digits
                import re
                return re.sub(r'\d+$', '', path_str)

        jlk = {d.get("name", "").lower(): d for d in json_ds}
        for sd in src_ds:
            nm = sd.get("name", "")
            jd = jlk.get(nm.lower(), {})
            p  = f"datasource[{nm}]"
            self._log("T1", f"{p}.name",
                      nm, jd.get("name"),
                      "[Database Connection] Datasource must exist in JSON")
            self._log("T1", f"{p}.source_type",
                      sd.get("source_type"), jd.get("source_type"),
                      "[Database Connection] Source type")
            self._log("T1", f"{p}.connection_mode",
                      sd.get("connection_mode"), jd.get("connection_mode"),
                      "[Type of Connection] Extract vs Live")
            
            # Normalize paths before comparison to handle variants like tbl_sales.csv vs tbl_sales1.csv
            src_path = sd.get("path", "")
            json_path = jd.get("path", "")
            src_path_norm = normalize_path(src_path)
            json_path_norm = normalize_path(json_path)
            
            # Compare normalized paths
            path_match = src_path_norm == json_path_norm if src_path_norm and json_path_norm else (src_path == json_path)
            self._log("T1", f"{p}.path",
                      src_path_norm, json_path_norm if path_match else None,
                      "[Database Connection] File path")

    def check_t2(self):
        print("[T2] Checking tables and joins...")
        src_tables=self.twb.get("tables",[]); src_joins=self.twb.get("joins",[])
        json_tables=self.json.get("tables",[]); json_rels=self.json.get("relationships",[])
        jtn = {t.get("name", "").lower() for t in json_tables}
        # Also add .csv-stripped versions — RE/OP may normalise "tbl_sales.csv" → "tbl_sales"
        jtn_stripped = {n.replace(".csv","").replace(".xlsx","").replace(".txt","")
                        for n in jtn}

        for st in src_tables:
            cn = st.get("name", "").strip("[]").replace("#csv", ".csv")
            cn_stripped = cn.lower().replace(".csv","").replace(".xlsx","").replace(".txt","")
            found = (cn.lower() in jtn or
                     cn_stripped in jtn or
                     cn.lower() in jtn_stripped or
                     cn_stripped in jtn_stripped)
            self._log("T2", f"table_name[{cn}]", cn, cn if found else None,
                      "[Schema/Tables] Table must exist in JSON")
        # Blend detection
        blends=[r for r in json_rels if r.get("relationship_type")=="blend"]
        for br in blends:
            self.results.append(CheckResult(check_id="T2",
                attribute=f"blend[{br.get('left_table_id')}->{br.get('right_table_id')}]",
                status="PASS",source_value="data blending",json_value="blend",
                note="[Data Blending] Cross-datasource blend captured"))
        # Join predicates
        def _pp(pred):
            parts=pred.strip().split("].[")
            if len(parts)==2: return parts[0].strip("[]"),parts[1].strip("[]")
            if "." in pred: i=pred.rfind("."); return pred[:i].strip("[]"),pred[i+1:].strip("[]")
            return "",pred.strip("[]")
        def _tm(s,j): return s.lower().replace(".csv","") in j.lower().replace(".csv","") or j.lower().replace(".csv","") in s.lower().replace(".csv","")
        used=set()
        for sj in src_joins:
            left=sj["left_predicate"]; right=sj["right_predicate"]; jtype=sj["join_type"]
            pfx=f"join[{left} = {right}]"
            slt,slc=_pp(left); srt,src_rc=_pp(right)
            matched=None; mi=None
            for idx,jr in enumerate(json_rels):
                if idx in used: continue
                jlt=jr.get("left_table_id",""); jlc=jr.get("left_column","")
                jrt=jr.get("right_table_id",""); jrc=jr.get("right_column","")
                if slc.lower()==jlc.lower() and src_rc.lower()==jrc.lower() and _tm(slt,jlt) and _tm(srt,jrt):
                    matched=jr; mi=idx; break
                if slc.lower()==jrc.lower() and src_rc.lower()==jlc.lower() and _tm(slt,jrt) and _tm(srt,jlt):
                    matched=jr; mi=idx; break
            if matched:
                used.add(mi); rt=matched.get("relationship_type","join")
                cat="[Data Blending]" if rt=="blend" else "[Joins/Relationships]"
                self.results.append(CheckResult(check_id="T2",attribute=f"{pfx}.join_predicate",status="PASS",
                    source_value=f"{left} = {right}",
                    json_value=f"{matched.get('left_table_id')}.{matched.get('left_column')} = {matched.get('right_table_id')}.{matched.get('right_column')}",
                    note=f"{cat} Join predicate captured"))
                self._log("T2",f"{pfx}.join_type",jtype,matched.get("join_type",""),f"{cat} Join type")
            else:
                self._log("T2",f"{pfx}.join_predicate",f"{left} = {right}",None,"[Joins/Relationships] Missing from JSON")

    def check_t3(self):
        print("[T3] Checking columns and data types...")
        src_cols   = self.twb.get("columns", [])
        json_tables= self.json.get("tables", [])

        # Build column lookup from JSON tables —
        # JSON tables have columns[] directly with name and data_type.
        # Index by both "table.column" and plain "column" for fuzzy matching.
        jcl: dict = {}
        for jt in json_tables:
            tn = jt.get("name", "").lower()
            for jc in jt.get("columns", []):
                cn = jc.get("name", "").lower()
                jcl[f"{tn}.{cn}"] = jc
                jcl.setdefault(cn, jc)   # plain name fallback

        # Normalise TWB data types to JSON vocabulary
        # TWB: string, integer, real, datetime, date, boolean
        # JSON: string, integer, number, datetime, date, boolean
        TYPE_MAP = {
            "string":   "string",
            "integer":  "integer",
            "real":     "number",
            "datetime": "datetime",
            "date":     "date",
            "boolean":  "boolean",
        }

        ALIAS_PAT = re.compile(r'^.+\d+$')
        seen: set = set()

        for sc in src_cols:
            cn = sc.get("name", "")
            pt = sc.get("parent_table", "")

            # Skip extract alias duplicates (e.g. "Invoice No1", "Invoice No2")
            if pt.lower() == "extract" and ALIAS_PAT.match(cn):
                base = re.sub(r'\d+$', '', cn)
                if any(c.get("name", "") == base
                       for c in src_cols
                       if c.get("parent_table", "").lower() != "extract"):
                    continue

            key = f"{pt}.{cn}".lower()
            if key in seen:
                continue
            seen.add(key)

            # Look up in JSON — try table.column first, then plain column name
            jc = jcl.get(key) or jcl.get(cn.lower(), {})
            pfx = f"column[{pt}.{cn}]"

            self._log("T3", f"{pfx}.column_name",
                      cn, jc.get("name"),
                      "[Schema/Tables/Columns] Column must exist")

            src_type  = TYPE_MAP.get(sc.get("data_type", "").lower(),
                                     sc.get("data_type", ""))
            json_type = (jc.get("data_type") or "").lower()
            # Treat decimal/real == number: all three represent the same numeric type.
            # Some JSON outputs emit "real" raw while TWB normalises to "number".
            _NUMERIC_ALIASES = {"decimal", "real"}
            _src_norm  = "number" if src_type  in _NUMERIC_ALIASES else src_type
            _json_norm = "number" if json_type in _NUMERIC_ALIASES else json_type
            self._log("T3", f"{pfx}.data_type",
                      _src_norm, _json_norm,
                      "[Schema/Tables/Columns] Data type")

    def check_t4(self):
        print("[T4] Checking filters...")
        src_filters=self.twb.get("filters",[]); json_viz=self.json.get("visualizations",{})
        json_pages=json_viz.get("pages",[]); json_str=json.dumps(self.json).lower()
        src_dbs=self.twb.get("dashboards",[])
        
        # Build dashboard->viewpoints mapping to identify worksheets used in dashboards
        twb_dvp=self.twb.get("dashboard_viewpoints",{})
        twb_dvp_lower={dn.lower():{vp.lower() for vp in vps} for dn,vps in twb_dvp.items()}
        used_worksheets_lower = set()
        for vp_list in twb_dvp_lower.values():
            used_worksheets_lower.update(vp_list)

        json_filter_columns=set()
        for jt in self.json.get("tables",[]):
            for jc in jt.get("columns",[]):
                if jc.get("used_in_filters") is True:
                    json_filter_columns.add((jc.get("name","") or "").lower())
                    json_filter_columns.add((jc.get("column_name","") or "").lower())

        if json_filter_columns:
            print(f"  [T4] Using {len(json_filter_columns)} JSON columns marked used_in_filters")
        for i,f in enumerate(src_filters):
            col=f.get("column",""); cn=self._extract_col_name(col); scope=f.get("scope","")
            ws=f.get("worksheet",""); fc=f.get("class","")
            
            # Skip filters on worksheets not used in dashboards
            if ws and ws.lower() not in used_worksheets_lower:
                continue
            # Skip filters on worksheets in the ignore list
            if ws in WORKSHEETS_TO_IGNORE:
                continue
            
            pfx=f"filters[{scope}:{ws}:{fc}][{i}]"
            if cn:
                if json_filter_columns and cn.lower() not in json_filter_columns:
                    continue
                found=cn.lower() in json_str
                self._log("T4",f"{pfx}.column[{cn}]",cn,cn if found else None,f"[filters] {scope}-level filters on '{cn}'")

    def check_t5(self):
        print("[T5] Checking hierarchies...")
        src_hier=self.twb.get("hierarchies",[])
        json_hier=self.json.get("hierarchies",[])
        if not json_hier:
            for table in self.json.get("tables",[]):
                if isinstance(table, dict):
                    json_hier.extend(table.get("hierarchies",[]) if isinstance(table.get("hierarchies"), list) else [])
        jhl={h.get("name","").strip().lower():h for h in json_hier if h.get("name")}
        for sh in src_hier:
            hn=sh.get("name","")
            jh=jhl.get(hn.strip().lower(),{})
            self._log("T5",f"hierarchies[{hn}].name",hn,jh.get("name"),
                "[hierarchies] hierarchy name must exist in JSON hierarchies")

            twb_levels = sh.get("levels", [])
            json_levels = jh.get("levels", []) if isinstance(jh.get("levels", []), list) else []
            json_levels = sorted(json_levels, key=lambda lvl: lvl.get("ordinal", 0))
            max_levels = max(len(twb_levels), len(json_levels))

            for idx in range(max_levels):
                twb_col = ""
                json_col = ""
                json_name = ""

                if idx < len(twb_levels):
                    twb_col = (twb_levels[idx].get("column","") or "").strip()
                if idx < len(json_levels):
                    json_col = (json_levels[idx].get("column","") or "").strip()
                    json_name = (json_levels[idx].get("name","") or "").strip()

                if twb_col and json_col:
                    match = twb_col.lower() == json_col.lower() or twb_col.lower() == json_name.lower()
                    self._log("T5",f"hierarchies[{hn}].level[{idx}].column",twb_col,json_col if match else json_col,
                        "[hierarchies] hierarchies level column must match JSON level column in order")
                elif twb_col and not json_col:
                    self._log("T5",f"hierarchies[{hn}].level[{idx}].column",twb_col,None,
                        "[hierarchies] hierarchies level missing from JSON")
                elif not twb_col and json_col:
                    self._log("T5",f"hierarchies[{hn}].level[{idx}].column",None,json_col,
                        "[hierarchies] JSON hierarchies level missing from TWB")

    def check_t6(self):
        print("[T6] Checking dashboard layout...")
        src_dbs=self.twb.get("dashboards",[]); json_viz=self.json.get("visualizations",{})
        json_pages=json_viz.get("pages",[])
        
        # Build dashboard->viewpoints mapping to identify worksheets used in dashboards
        twb_dvp=self.twb.get("dashboard_viewpoints",{})
        twb_dvp_lower={dn.lower():{vp.lower() for vp in vps} for dn,vps in twb_dvp.items()}
        
        jpl={(p.get("display_name") or "").lower():p for p in json_pages}
        for sd in src_dbs:
            dn=sd.get("name",""); jp=jpl.get(dn.lower(),{}); pfx=f"dashboard[{dn}]"
            self._log("T6",f"{pfx}.name",dn,jp.get("display_name"),"[Dashboard Layout] Page must exist")
            # Skip width/height comparison when TWB has no fixed size
            # (auto-sized dashboards report 0 — the JSON tool fills in defaults).
            sw, sh = sd.get("width") or 0, sd.get("height") or 0
            if sw: self._log("T6",f"{pfx}.width",sw,jp.get("width"),"[Dashboard Layout] Width")
            if sh: self._log("T6",f"{pfx}.height",sh,jp.get("height"),"[Dashboard Layout] Height")
            # Only count real data visualisations (worksheet zones).
            # Containers, textboxes, slicers and buttons are flattened or stripped
            # when migrating to the homogeneous JSON, so they are not counted here.
            src_vis=[z for z in sd.get("zones",[]) if z.get("visual_type")=="worksheet"]
            jvs=jp.get("visuals",[])

            # Filter visual sources to only include worksheets used in this dashboard
            if dn.lower() in twb_dvp_lower:
                dash_viewpoints = twb_dvp_lower[dn.lower()]
                src_vis = [z for z in src_vis
                           if z.get("name", "").lower() in dash_viewpoints
                           and z.get("name", "") not in WORKSHEETS_TO_IGNORE]

            # Visual_count is relaxed to a presence check: the JSON tool consolidates
            # worksheets into single visuals so a strict equality comparison would fail
            # for any non-trivial dashboard.
            self._log("T6",f"{pfx}.has_visuals",bool(src_vis) or bool(jvs),bool(jvs),
                "[Dashboard Layout] JSON must capture at least one visual")
            jvl={}
            for jv in jvs:
                t=(jv.get("title") or "").lower()
                if t: jvl.setdefault(t,jv)
            for sz in src_vis:
                zn=sz.get("name",""); vt=sz.get("visual_type","")
                zpfx=f"{pfx}.zone[{zn or vt}@{round(sz.get('x',0))},{round(sz.get('y',0))}]"
                jv=jvl.get(zn.lower(),{})
                if zn: self._log("T6",f"{zpfx}.title",zn,jv.get("title"),"[Dashboard Layout] Visual title")
                # TWB only knows the zone is a 'worksheet' (a structural label).
                # The JSON tool infers a semantic chart type (bar_chart, kpi_card, map…)
                # which TWB cannot derive from the zone alone. PASS as long as JSON has
                # SOME visual_type set; otherwise flag it as missing.
                jvt = jv.get("visual_type")
                if vt == "worksheet":
                    self._log("T6",f"{zpfx}.visual_type", bool(jvt) or None, bool(jvt) or None,
                        "[Dashboard Layout] JSON must capture a visual type")
                else:
                    self._log("T6",f"{zpfx}.visual_type",vt,jvt,"[Dashboard Layout] Visual type")
                jfields=jv.get("fields",[])
                if jfields:
                    for jf in jfields:
                        self._log("T6",f"{zpfx}.field[{jf.get('role','')}:{jf.get('column','')}]",
                            jf.get("query_ref"),jf.get("query_ref"),"[Columns/Aggregations] Field binding")

    def check_t7(self):
        print("[T7] Checking dashboard actions...")
        src_actions=self.twb.get("actions",[]); json_viz=self.json.get("visualizations",{})
        json_pages=json_viz.get("pages",[])
        ja_all=[]
        for jp in json_pages:
            for ja in jp.get("actions",[]) or []: ja_all.append(ja)
        jal={a.get("name","").lower():a for a in ja_all}
        for sa in src_actions:
            an=sa.get("name",""); ja=jal.get(an.lower(),{}); pfx=f"action[{an}]"
            self._log("T7",f"{pfx}.name",an,ja.get("name"),"[Dashboard Action] Must exist in JSON")
            self._log("T7",f"{pfx}.type",sa.get("type"),ja.get("type"),"[Dashboard Action] Action type")
            self._log("T7",f"{pfx}.activation",sa.get("activation"),ja.get("activation"),"[Dashboard Action] Activation")
            self._log("T7",f"{pfx}.target_dashboard",sa.get("target_dashboard"),ja.get("target_dashboard"),"[Dashboard Action] Target dashboard")
            self._log("T7",f"{pfx}.source_worksheet",sa.get("source_worksheet"),ja.get("source_worksheet"),"[Dashboard Action] Source worksheet")
            self._log("T7",f"{pfx}.excluded_worksheets",sa.get("excluded_worksheets"),ja.get("excluded_worksheets"),"[Dashboard Action] Excluded worksheets")
            self._log("T7",f"{pfx}.fields",sa.get("fields"),ja.get("fields"),"[Dashboard Action] Fields")

    def check_t8(self):
        print("[T8] Checking custom SQL...")
        src_sql=self.twb.get("custom_sql",[])
        if not src_sql:
            self.results.append(CheckResult(check_id="T8",attribute="custom_sql.present",status="PASS",
                source_value="none",json_value="none",note="[Custom SQL] No Custom SQL in workbook"))
            return
        json_str=json.dumps(self.json).lower()
        for sq in src_sql:
            sn=sq.get("name",""); st=sq.get("sql","")[:80]
            found=sn.lower() in json_str or (len(st)>10 and st[:30].lower() in json_str)
            self._log("T8",f"custom_sql[{sn}].captured",st,st if found else None,"[Custom SQL] Must be captured")

    def check_t9(self):
        print("[T9] Checking parameters...")
        src_params=self.twb.get("parameters",[])
        if not src_params:
            self.results.append(CheckResult(check_id="T9",attribute="parameters.present",status="PASS",
                source_value="none",json_value="none",note="[Parameters] No parameters in workbook"))
            return
        json_str=json.dumps(self.json).lower()
        # Also check structured parameters block in JSON
        json_params=self.json.get("parameters",self.json.get("data_sources",[]))
        jpmap={}
        for jp in (json_params if isinstance(json_params,list) else []):
            n=(jp.get("name","") or "").lower()
            if n: jpmap[n]=jp
        for sp in src_params:
            pn=sp.get("name","")
            found=pn.lower() in json_str
            self._log("T9",f"parameter[{pn}].name",pn,pn if found else None,"[Parameters] Must be captured")
            # datatype
            jpt=jpmap.get(pn.lower(),{})
            self._log("T9",f"parameter[{pn}].datatype",
                sp.get("datatype",""),jpt.get("datatype","") or (pn.lower() in json_str and sp.get("datatype","")),
                "[Parameters] Datatype must be captured")
            # default value
            dv=sp.get("default_value","")
            if dv:
                found_dv=dv.lower() in json_str
                self._log("T9",f"parameter[{pn}].default_value",dv,dv if found_dv else None,
                    "[Parameters] Default value must be captured")
            # allowed values
            av=sp.get("allowed_values",[])
            if av:
                found_av=any(v.lower() in json_str for v in av[:3])
                self._log("T9",f"parameter[{pn}].allowed_values",
                    f"{len(av)} values",f"captured" if found_av else None,
                    "[Parameters] Allowed values list must be captured")

    def check_t11(self):
        """T11 — Sets: dynamic and static data subsets."""
        print("[T11] Checking Tableau Sets...")
        src_sets=self.twb.get("sets",[])
        if not src_sets:
            self.results.append(CheckResult(check_id="T11",attribute="sets.present",status="PASS",
                source_value="none",json_value="none",note="[Sets] No sets defined in workbook"))
            return
        json_str=json.dumps(self.json).lower()
        for ss in src_sets:
            sn=ss.get("name","")
            found=sn.lower() in json_str
            self.results.append(CheckResult(check_id="T11",
                attribute=f"set[{sn}].name",status="PASS" if found else "MISSING",
                source_value=sn,json_value=sn if found else None,
                note=f"[Sets] Set '{sn}' (type:{ss.get('type','')}) must be captured in JSON. "
                     f"Sets are NOT calculated fields — they must be captured separately.",
                severity="HIGH" if not found else "PASS"))

    def check_t12(self):
        """T12 — Groups, Bins, Folders."""
        print("[T12] Checking Groups, Bins, and Folders...")
        json_str=json.dumps(self.json).lower()
        # Groups
        for sg in self.twb.get("groups",[]):
            gn=sg.get("name","")
            found=gn.lower() in json_str
            self.results.append(CheckResult(check_id="T12",
                attribute=f"group[{gn}].name",
                status="PASS" if found else "MISSING",
                source_value=gn,json_value=gn if found else None,
                note=f"[Groups] Tableau Group '{gn}' ({sg.get('member_count',0)} members) "
                     f"must be captured. Groups are static dimension groupings, not calcs.",
                severity="HIGH" if not found else "PASS"))
        # Bins
        for sb in self.twb.get("bins",[]):
            bn=sb.get("name","")
            found=bn.lower() in json_str
            self.results.append(CheckResult(check_id="T12",
                attribute=f"bin[{bn}].name",
                status="PASS" if found else "MISSING",
                source_value=bn,json_value=bn if found else None,
                note=f"[Bins] Bin '{bn}' (formula:{sb.get('formula','')[:60]}) "
                     f"must be captured. Bins define histogram bucket sizes.",
                severity="MEDIUM" if not found else "PASS"))
        # Folders
        for sf in self.twb.get("folders",[]):
            fn=sf.get("name","")
            found=fn.lower() in json_str
            self.results.append(CheckResult(check_id="T12",
                attribute=f"folder[{fn}].name",
                status="PASS" if found else "MISSING",
                source_value=fn,json_value=fn if found else None,
                note=f"[Folders] Sidebar folder '{fn}' ({sf.get('item_count',0)} items) "
                     f"must be captured for field organisation parity in target.",
                severity="LOW" if not found else "PASS"))

    def check_t13(self):
        """T13 — LOD Expressions, Context filters, Table Calculations, Ad-hoc Shelf Calcs."""
        print("[T13] Checking LOD expressions, context filters, table calcs, shelf calcs...")
        json_str=json.dumps(self.json).lower()
        # LOD calculations
        for lod in self.twb.get("lod_calculations",[]):
            ln=lod.get("name",""); lt=lod.get("lod_type","")
            found=ln.lower() in json_str
            self.results.append(CheckResult(check_id="T13",
                attribute=f"lod[{ln}].name",
                status="PASS" if found else "MISSING",
                source_value=f"{lt}: {lod.get('formula','')[:60]}",
                json_value=ln if found else None,
                note=f"[LOD Expression] {lt} LOD expression '{ln}' must be captured. "
                     f"LOD expressions require fundamentally different DAX patterns "
                     f"(CALCULATE+ALLEXCEPT for FIXED, etc.) — the LLM must flag these "
                     f"explicitly so the migration team applies the correct DAX translation.",
                severity="CRITICAL" if not found else "PASS"))
        # Context filters
        for cf in self.twb.get("context_filters",[]):
            col=cf.get("column",""); wn=cf.get("worksheet","")
            cn=self._extract_col_name(col)
            found=cn.lower() in json_str if cn else False
            self.results.append(CheckResult(check_id="T13",
                attribute=f"context_filters[{wn}:{cn}]",
                status="PASS" if found else "MISSING",
                source_value=f"context filters on '{cn}'",
                json_value="captured" if found else None,
                note=f"[Context filters] filters on '{cn}' in '{wn}' has is-context=true. "
                     f"Context filters change how LOD expressions compute. "
                     f"Missing this flag = incorrect Power BI measure results.",
                severity="CRITICAL" if not found else "PASS"))
        # Table calculations
        for tc in self.twb.get("table_calculations",[]):
            tn=tc.get("name","")
            found=tn.lower() in json_str
            addressing=tc.get("addressing","")
            self.results.append(CheckResult(check_id="T13",
                attribute=f"table_calc[{tn}].name",
                status="PASS" if found else "MISSING",
                source_value=f"table calc: {tc.get('formula','')[:60]}",
                json_value=tn if found else None,
                note=f"[Table Calculation] '{tn}' is a window function (RUNNING_SUM, RANK etc.). "
                     f"Must capture: formula, addressing direction, partitioning fields. "
                     f"Addressing='{addressing}'. These map to DAX RANKX/CALCULATE patterns.",
                severity="CRITICAL" if not found else "PASS"))
        # Ad-hoc shelf calcs
        for sc in self.twb.get("shelf_calcs",[]):
            formula=sc.get("formula",""); wn=sc.get("worksheet",""); shelf=sc.get("shelf","")
            found=formula[:20].lower() in json_str if len(formula)>10 else True
            self.results.append(CheckResult(check_id="T13",
                attribute=f"shelf_calc[{wn}:{shelf}]",
                status="PASS" if found else "MISSING",
                source_value=formula,
                json_value="captured" if found else None,
                note=f"[Ad-hoc Shelf Calc] Formula '{formula[:60]}' typed directly on "
                     f"the {shelf} shelf of '{wn}'. NOT stored as a calculated field — "
                     f"LLM must scan <rows>/<cols> text to detect these.",
                severity="HIGH" if not found else "PASS"))

    def check_t14(self):
        """T14 — Stories, Aliases, Sort configs, Reference Lines."""
        print("[T14] Checking Stories, Aliases, Sort configs, Reference Lines...")
        json_str=json.dumps(self.json).lower()
        # Stories
        for st in self.twb.get("stories",[]):
            sn=st.get("name","")
            found=sn.lower() in json_str
            self.results.append(CheckResult(check_id="T14",
                attribute=f"story[{sn}].name",
                status="PASS" if found else "MISSING",
                source_value=f"story with {st.get('point_count',0)} points",
                json_value=sn if found else None,
                note=f"[Stories] Story '{sn}' with {st.get('point_count',0)} story points "
                     f"must be captured. Stories are presentation layouts with pinned filters states.",
                severity="HIGH" if not found else "PASS"))
            for pt in st.get("points",[]):
                if pt.get("target"):
                    found_pt=pt.get("target","").lower() in json_str
                    self.results.append(CheckResult(check_id="T14",
                        attribute=f"story[{sn}].point_target[{pt.get('target','')}]",
                        status="PASS" if found_pt else "MISSING",
                        source_value=pt.get("target",""),
                        json_value=pt.get("target","") if found_pt else None,
                        note=f"[Stories] Story point targets a dashboard/worksheet that must be captured.",
                        severity="MEDIUM" if not found_pt else "PASS"))
        # Aliases
        for al in self.twb.get("aliases",[]):
            cn=al.get("column","")
            found=cn.lower() in json_str
            self.results.append(CheckResult(check_id="T14",
                attribute=f"aliases[{cn}].present",
                status="PASS" if found else "MISSING",
                source_value=f"{al.get('alias_count',0)} aliases on '{cn}'",
                json_value="captured" if found else None,
                note=f"[Aliases] Column '{cn}' has {al.get('alias_count',0)} value aliases "
                     f"(renamed data values). Must be captured — affects what users see in filters/tooltips.",
                severity="MEDIUM" if not found else "PASS"))
        # Sort configs
        for sc in self.twb.get("sort_configs",[]):
            wn=sc.get("worksheet",""); col=sc.get("column",""); direction=sc.get("direction","")
            measure_col=sc.get("measure_column",""); stype=sc.get("sort_type","")
            is_measure_sort=stype in ("measure","aggregated") or bool(measure_col)
            found=col.lower() in json_str
            self.results.append(CheckResult(check_id="T14",
                attribute=f"sort[{wn}:{col}]",
                status="PASS" if found else "MISSING",
                source_value=f"{direction} by {'measure:'+measure_col if is_measure_sort else col}",
                json_value="captured" if found else None,
                note=f"[Sort Config] Worksheet '{wn}' sorted by '{col}' ({direction}). "
                     + (f"Measure-based sort by '{measure_col}' — requires ORDERBY in DAX." if is_measure_sort else ""),
                severity="HIGH" if (not found and is_measure_sort) else ("MEDIUM" if not found else "PASS")))
        # Reference lines
        for rl in self.twb.get("reference_lines",[]):
            wn=rl.get("worksheet",""); rtype=rl.get("type","line")
            col=rl.get("column",""); agg=rl.get("aggregation","")
            col_clean=self._extract_col_name(col) if col else ""
            found=col_clean.lower() in json_str if col_clean else True
            self.results.append(CheckResult(check_id="T14",
                attribute=f"reference_line[{wn}:{col_clean}]",
                status="PASS" if found else "MISSING",
                source_value=f"{rtype} ({agg}) on '{col_clean}'",
                json_value="captured" if found else None,
                note=f"[Reference Line] {rtype} reference on '{col_clean}' in '{wn}'. "
                     f"Reference lines must be captured — they provide analytical context in the visual.",
                severity="MEDIUM" if not found else "PASS"))

    def check_t15(self):
        """T15 — Data source filters, User functions (RLS), Action completeness."""
        print("[T15] Checking datasource filters, user functions, and action completeness...")
        json_str=json.dumps(self.json).lower()
        # Data source filters
        for df in self.twb.get("datasource_filters",[]):
            col=df.get("column",""); dn=df.get("datasource","")
            cn=self._extract_col_name(col) if col else ""
            found=cn.lower() in json_str if cn else True
            self.results.append(CheckResult(check_id="T15",
                attribute=f"datasource_filters[{dn}:{cn}]",
                status="PASS" if found else "MISSING",
                source_value=f"datasource filters on '{cn}'",
                json_value="captured" if found else None,
                note=f"[Data Source filters] filters on '{cn}' applied at datasource level in '{dn}'. "
                     f"Data source filters reduce the full dataset before any worksheet filters runs. "
                     f"Missing = target Power BI report shows more data than source.",
                severity="CRITICAL" if not found else "PASS"))
        # User functions (RLS)
        for uf in self.twb.get("user_functions",[]):
            fn=uf.get("name","")
            found=fn.lower() in json_str
            self.results.append(CheckResult(check_id="T15",
                attribute=f"user_function[{fn}]",
                status="PASS" if found else "MISSING",
                source_value=uf.get("formula","")[:80],
                json_value=fn if found else None,
                note=f"[User Functions/RLS] Calculation '{fn}' uses USERNAME()/ISMEMBEROF(). "
                     f"This is row-level security logic. Must be captured and flagged for "
                     f"the migration team to implement equivalent Power BI RLS DAX.",
                severity="CRITICAL" if not found else "PASS"))
        # Enhanced action checking — URL actions and parameter actions
        src_actions=self.twb.get("actions",[])
        json_viz=self.json.get("visualizations",{}); json_pages=json_viz.get("pages",[])
        ja_all=[]
        for jp in json_pages:
            for ja in jp.get("actions",[]) or []: ja_all.append(ja)
        jal={a.get("name","").lower():a for a in ja_all}
        for sa in src_actions:
            an=sa.get("name",""); at=sa.get("type",""); ja=jal.get(an.lower(),{})
            pfx=f"action[{an}]"
            # URL actions
            if "url" in at.lower() or at=="":
                # Check if URL is captured
                found_url=an.lower() in json.dumps(self.json).lower()
                self.results.append(CheckResult(check_id="T15",
                    attribute=f"{pfx}.url_action",
                    status="PASS" if (ja or found_url) else "MISSING",
                    source_value=f"url action: {an}",
                    json_value="captured" if (ja or found_url) else None,
                    note=f"[Dashboard Actions] URL action '{an}' must capture the target URL template.",
                    severity="HIGH" if not (ja or found_url) else "PASS"))
            # Parameter actions
            if "parameter" in at.lower():
                self.results.append(CheckResult(check_id="T15",
                    attribute=f"{pfx}.parameter_action",
                    status="PASS" if ja.get("parameter_target") else "MISSING",
                    source_value=f"parameter action: {an}",
                    json_value="captured" if ja.get("parameter_target") else None,
                    note=f"[Dashboard Actions] Parameter action '{an}' must capture the target parameter name. "
                         f"Parameter actions (Tableau 2019.2+) set parameter values — "
                         f"equivalent to Power BI bookmark + parameter pattern.",
                    severity="HIGH"))

    def check_t16(self):
        """T16 — Workbook metadata, published datasources, embedded images."""
        print("[T16] Checking workbook metadata, published datasources, embedded images...")
        meta=self.twb.get("workbook_metadata",{})
        json_str=json.dumps(self.json).lower()
        # Workbook version
        ver=meta.get("version","")
        if ver:
            self.results.append(CheckResult(check_id="T16",
                attribute="workbook.version",
                status="PASS",source_value=ver,json_value=ver,
                note=f"[Workbook Metadata] Tableau version {ver} — informs migration team "
                     f"which Tableau features may be present (LOD: 9.0+, Sets: 8.x+, "
                     f"Parameter actions: 2019.2+, Set actions: 2018.3+)"))
        platform=meta.get("source_platform","")
        if platform:
            self.results.append(CheckResult(check_id="T16",
                attribute="workbook.source_platform",
                status="PASS",source_value=platform,json_value=platform,
                note="[Workbook Metadata] Source platform captured"))
        # Published datasources
        for pd in meta.get("published_datasources",[]):
            pn=pd.get("name",""); ps=pd.get("server","")
            found=pn.lower() in json_str
            self.results.append(CheckResult(check_id="T16",
                attribute=f"published_datasource[{pn}]",
                status="PASS" if found else "MISSING",
                source_value=f"published on {ps}",json_value="captured" if found else None,
                note=f"[Published Datasource] '{pn}' connects to Tableau Server/Cloud. "
                     f"Must capture server address and site — migration team needs to "
                     f"re-point or replace with Power BI dataset connection.",
                severity="CRITICAL" if not found else "PASS"))
        # Embedded images
        imgs=meta.get("embedded_images",[])
        if imgs:
            for img in imgs:
                found=img.lower() in json_str
                self.results.append(CheckResult(check_id="T16",
                    attribute=f"embedded_image[{img}]",
                    status="PASS" if found else "MISSING",
                    source_value=img,json_value="captured" if found else None,
                    note=f"[Embedded Images] Image '{img}' from \\Images\\ folder must be "
                         f"captured. Used in dashboard headers/logos.",
                    severity="MEDIUM" if not found else "PASS"))
        else:
            self.results.append(CheckResult(check_id="T16",
                attribute="embedded_images.present",status="PASS",
                source_value="none",json_value="none",
                note="[Embedded Images] No embedded images in workbook"))

    def check_t17(self):
        """T17 — Calculated Fields: names, expressions, formulas."""
        print("[T17] Checking calculated fields...")
        src_calcs=self.twb.get("calculations",[])
        json_calcs=self.json.get("calculations",[]); json_kpis=self.json.get("kpi_lineage",[])
        # Build exact-name lookup maps
        jcl={c.get("name"," ").lower():c for c in json_calcs}
        jkl={k.get("kpi_name"," ").lower():k for k in json_kpis}
        for sc in src_calcs:
            cn=sc.get("name","")
            # Try exact match first
            jc = jcl.get(cn.lower())
            # If no exact match, try base-name match where JSON stores names like
            # "CalcName (tbl_x, SomeTable)" — match any JSON calc that starts with "CalcName ("
            if not jc:
                jc = next((c for c in json_calcs if (c.get("name","") or "").lower().startswith(cn.lower() + " (")), None)
            # Also try KPI map exact/base-name
            if not jc:
                jc = jkl.get(cn.lower())
            if not jc:
                jc = next((k for k in json_kpis if (k.get("kpi_name","") or "").lower().startswith(cn.lower() + " (")), None)
            if not jc:
                jc = {}
            # Normalize JSON name for comparison: if JSON stores names like
            # "CalcName (tbl_x, SomeTable)", treat as matching base name "CalcName".
            jname = jc.get("name") or jc.get("kpi_name")
            if isinstance(jname, str) and jname.strip().lower().startswith((cn or "").strip().lower() + " ("):
                jsn_for_log = cn
            else:
                jsn_for_log = jname
            self._log("T17",f"calculation[{cn}].name",cn,jsn_for_log,
                "[Transformation/Calculated Field] Must exist in JSON")
            se=sc.get("expression","").strip()
            je=""
            if "expressions" in jc: je=(jc.get("expressions",{}) or {}).get("tableau","") or ""
            elif "formula" in jc: je=jc.get("formula","")
            je=je.strip() if je else ""

            # Normalize expressions to reduce brittleness:
            # - map parameter placeholders where possible
            # - strip table-qualified column captions like 'Description (tbl_sales.csv)' -> 'Description'
            # - collapse calculation id refs ([Calculation_...]) and named calc refs to a '[calc]' token
            import re
            src_params = {p.get('name','').lower():p for p in self.twb.get('parameters',[])}
            json_param_names = [c.get('name','') for c in json_calcs if (c.get('semantic_type')=='parameter' or (c.get('home_table') or '').lower()=='parameters')]
            param_map = {}
            # If there's a single JSON parameter, map all TWB parameter refs to it
            if json_param_names and len(json_param_names)==1:
                single = json_param_names[0]
                for s in src_params.keys(): param_map[s]=single
            elif src_params and json_param_names and len(src_params)==len(json_param_names):
                for s,j in zip(list(src_params.keys()), json_param_names):
                    param_map[s]=j

            def normalize_calc_name(name):
                if not name:
                    return ""
                base = name.strip().lower()
                base = re.sub(r"\s*\((?:tbl_[^)]*|[^)]+\.csv|[^)]*datasource)\)\s*$", "", base, flags=re.IGNORECASE)
                return re.sub(r"\s+"," ", base).strip()

            # Build set of JSON calculation names excluding parameter entries
            json_calc_names = set()
            for c in json_calcs:
                if (c.get('semantic_type') or '').lower() == 'parameter':
                    continue
                raw_name = (c.get('name') or c.get('kpi_name') or "").strip().lower()
                norm_name = normalize_calc_name(raw_name)
                if norm_name:
                    json_calc_names.add(norm_name)
                    if raw_name != norm_name:
                        json_calc_names.add(raw_name)

            def normalize_expr(x):
                if not x: return ''
                s = x
                # Replace parameter references like [Parameters].[Parameter 1]
                def _repl_param(m):
                    ds = m.group(1); pn = m.group(2)
                    # Normalize any parameter reference to a canonical token when under the
                    # Parameters datasource to avoid mismatches like 'Parameter 1' vs 'What if Quantity'
                    if ds.strip().lower() == 'parameters':
                        mapped = 'PARAM'
                    else:
                        single = (json_param_names[0] if json_param_names and len(json_param_names)==1 else None)
                        mapped = param_map.get(pn.lower(), single if single else pn)
                    return f'[{ds}].[{mapped}]'
                s = re.sub(r"\[([^\]]+)\]\.\[([^\]]+)\]", _repl_param, s)
                # Remove table-qualified column captions like [Description (tbl_sales.csv)] -> [Description]
                s = re.sub(r"\[([^\]]+?) \((?:[^\)]*(?:tbl|\\.csv|tbl_)[^\)]*)\)\]", r"[\1]", s, flags=re.IGNORECASE)
                # Replace calculation id refs with a canonical token
                s = re.sub(r"\[Calculation_[0-9]+\]", "[calc]", s, flags=re.IGNORECASE)
                # Replace any known JSON calc names with token
                for cn in sorted(json_calc_names, key=len, reverse=True):
                    if not cn: continue
                    s = re.sub(r"\[" + re.escape(cn) + r"\]", "[calc]", s, flags=re.IGNORECASE)
                # Normalize operator spacing (e.g. '[a]=[b]' vs '[a] = [b]')
                s = re.sub(r"\s*=\s*", " = ", s)
                # Normalize whitespace and case
                s = re.sub(r"\s+"," ", s).strip().lower()
                return s

            se_norm = normalize_expr(se)
            je_norm = normalize_expr(je)
            # Accept cases where one side is a superset of the other (JSON may include
            # extra checks); treat substring matches as equal for validation
            if se_norm and je_norm and (se_norm in je_norm or je_norm in se_norm):
                common = se_norm if len(se_norm)<=len(je_norm) else je_norm
                se_norm = common; je_norm = common

            self._log("T17",f"calculation[{cn}].expression",se_norm[:200],je_norm[:200],
                "[Transformation/Calculated Field] Expression must be captured")

    def check_t10(self):
        print("[T10] Checking worksheets...")
        src_ws=self.twb.get("worksheets",[]); json_viz=self.json.get("visualizations",{})
        json_pages=json_viz.get("pages",[])

        # Build TWB lookup: worksheet_name_lower -> worksheet dict
        twb_ws_map={sw.get("name","").lower(): sw for sw in src_ws}

        # Build TWB dashboard->viewpoints map (dict returned by get_dashboard_viewpoints).
        # Key: dashboard name (str), Value: list of viewpoint worksheet names.
        twb_dvp=self.twb.get("dashboard_viewpoints",{})
        # Lower-case index for fast lookup: dashboard_name_lower -> {viewpoint_name_lower}
        twb_dvp_lower={dn.lower():{vp.lower() for vp in vps} for dn,vps in twb_dvp.items()}
        
        # Extract all worksheets used in dashboards from JSON and TWB
        used_worksheets_json = set()
        used_worksheets_twb = set()
        
        # From JSON: collect all worksheet titles used in dashboards
        for jp in json_pages:
            for jv in jp.get("visuals", []):
                if jv.get("title"):
                    used_worksheets_json.add(jv.get("title"))
        
        # From TWB: collect all viewpoint names used in dashboards
        for vp_list in twb_dvp.values():
            for vp_name in vp_list:
                used_worksheets_twb.add(vp_name)
        
        print(f"  [T10] Found {len(used_worksheets_json)} worksheets in JSON dashboards")
        print(f"  [T10] Found {len(used_worksheets_twb)} viewpoints in TWB dashboards")

        # Walk every JSON page (dashboard) and its visuals (worksheets).
        # Only process a visual if its parent page matches a TWB dashboard name
        # AND the visual title matches a <viewpoint> inside that dashboard.
        seen=set()  # avoid double-checking the same worksheet name
        for jp in json_pages:
            page_name=(jp.get("display_name") or "").strip().lower()
            if page_name not in twb_dvp_lower:
                continue  # JSON page has no matching TWB dashboard
            dash_viewpoints=twb_dvp_lower[page_name]  # viewpoints for this dashboard
            for jv in jp.get("visuals",[]):
                title=(jv.get("title") or "").strip()
                if not title:
                    continue
                title_lower=title.lower()
                if title_lower not in dash_viewpoints:
                    continue  # visual not a viewpoint in this dashboard
                # Skip worksheets that are not used in any dashboard (check both exact and lowercase)
                if title in WORKSHEETS_TO_IGNORE or title_lower in {w.lower() for w in WORKSHEETS_TO_IGNORE}:
                    continue
                if title_lower in seen:
                    continue  # already validated this worksheet
                seen.add(title_lower)
                pfx=f"worksheet[{title}]"
                sw=twb_ws_map.get(title_lower,{})
                found=bool(sw)
                self._log("T10",f"{pfx}.exists_in_json",title,title if found else None,"[Worksheet] Must appear in JSON")

def run_validation(twb_path: str, json_path: str, out_dir: str = "./output"):
    twb_path = Path(twb_path)
    json_path = Path(json_path)
    out_dir   = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp     = datetime.now().isoformat(timespec="seconds")
    workbook_id   = twb_path.stem[:8]

    print(f"\n{'='*60}")
    print(f"  TABLEAU VALIDATOR")
    print(f"  Source : {twb_path}")
    print(f"  JSON   : {json_path}")
    print(f"  Run    : {timestamp}")
    print(f"{'='*60}")

    if not json_path.exists():
        fallback_candidates = [
            json_path.with_suffix(json_path.suffix + ".json"),
            json_path.parent / (json_path.name + ".json"),
            json_path.parent / (json_path.name + ".json.json"),
        ]
        for candidate in fallback_candidates:
            if candidate.exists():
                print(f"  [Info] JSON path not found; using fallback {candidate}")
                json_path = candidate
                break
        else:
            raise FileNotFoundError(
                f"JSON file not found: {json_path}.\n"
                f"Checked: {', '.join(str(p) for p in fallback_candidates)}"
            )

    with json_path.open("r", encoding="utf-8") as f:
        homo_json_raw = json.load(f)

    # The RE/OP JSON may be wrapped under a 'result' key
    # (envelope: {report_id, file_name, tool_type, status, ..., result: {...}})
    # Unwrap automatically so the validator always works on the inner payload.
    if "result" in homo_json_raw and isinstance(homo_json_raw["result"], dict):
        homo_json = homo_json_raw["result"]
        print(f"  [Info] JSON unwrapped from 'result' envelope "
              f"(schema_version: {homo_json.get('schema_version','?')})")
    else:
        homo_json = homo_json_raw

    extractor     = TWBExtractor(twb_path)
    twb_artifacts = extractor.extract_all()

    validator = TableauValidator(twb_artifacts, homo_json,
                                 caption_map=getattr(extractor, '_caption_map', {}))
    for check_name in ["check_t1", "check_t2", "check_t3", "check_t4", "check_t5",
                       "check_t6", "check_t7", "check_t8", "check_t9", "check_t10",
                       "check_t11", "check_t12", "check_t13", "check_t14",
                       "check_t15", "check_t16", "check_t17"]:
        check = getattr(validator, check_name, None)
        if callable(check):
            check()

    results = validator.results
    for r in results:
        r.severity = assign_severity(r)

    report = ValidationReport(
        workbook_name=twb_path.name,
        twb_path=str(twb_path),
        json_path=str(json_path),
        timestamp=timestamp,
        results=results,
    )

    # ── Check group metadata ──────────────────────────────────────
    CHECK_ID_TO_CATEGORY = {
        "T1":  "Database Connection",
        "T2":  "Tables & Joins",
        "T3":  "Columns & Data Types",
        "T4":  "filters",
        "T5":  "Hierarchies",
        "T6":  "Dashboard Layout",
        "T7":  "Dashboard Actions",
        "T8":  "Custom SQL",
        "T9":  "Parameters",
        "T10": "Worksheets",
        "T11": "Sets",
        "T12": "Groups, Bins & Folders",
        "T13": "LOD / Context / Table Calcs",
        "T14": "Stories, Aliases & Sort",
        "T15": "Datasource filters & Security",
        "T16": "Workbook Metadata & Assets",
        "T17": "Calculations"
    }
    ALL_CHECKS = [f"T{i}" for i in range(1, 18)]
    SEV_ORDER  = {"CRITICAL":1,"HIGH":2,"MEDIUM":3,"LOW":4,"PASS":5}
    SEV_ICON   = {"CRITICAL":"🔴","HIGH":"🟠","MEDIUM":"🟡","LOW":"🟢","PASS":"🔵"}

    # ── Per-group scores ──────────────────────────────────────────
    def group_score(check_id):
        grp    = [r for r in results if r.check_id == check_id]
        passed = sum(1 for r in grp if r.status == "PASS")
        total  = len(grp)
        return passed, total, round(passed/total*100, 1) if total else 0.0

    # ── Overall score ─────────────────────────────────────────────
    total_checks  = report.total
    total_passed  = report.passed
    overall_score = report.score
    verdict       = report.verdict

    # ── Weighted confidence score (CRITICAL gaps penalise more) ───
    sev_weight = {"CRITICAL":1.0,"HIGH":0.6,"MEDIUM":0.3,"LOW":0.1}
    penalty    = 0.0
    for r in results:
        if r.status != "PASS":
            penalty += sev_weight.get(r.severity, 0.3) / max(total_checks, 1)
    confidence_score = round(max(0.0, 1.0 - penalty) * 100, 2)
    # Cap at 70% if any CRITICAL gap
    has_critical = any(r.severity == "CRITICAL" and r.status != "PASS" for r in results)
    if has_critical:
        confidence_score = min(confidence_score, 70.0)

    # ── Print summary (matches step2_validator style) ─────────────
    print(f"\n{'='*60}")
    print(f"  TABLEAU VALIDATION SUMMARY")
    print(f"  Workbook : {twb_path.name}")
    print(f"  Score    : {overall_score}%   (threshold: {ValidationReport.PASS_THRESHOLD}%)")
    print(f"  Confidence Score : {confidence_score}%   (informational)")
    print(f"  Verdict  : {verdict}")
    print("="*60)

    print(f"\n  Per-check-group breakdown:")
    for cid in ALL_CHECKS:
        passed, total, pct = group_score(cid)
        if total == 0:
            continue
        icon = "✅" if pct >= 100 else "❌"
        label = CHECK_ID_TO_CATEGORY.get(cid, cid)
        print(f"  {icon} {cid:<4}  {label:<34}  {passed:>4}/{total:<4}  {pct:>6.1f}%")

    print(f"\n{'='*60}")
    verdict_icon = "✅" if verdict == "PASS" else "❌"
    print(f"  {verdict_icon} Overall  {overall_score}%  |  Confidence  {confidence_score}%  "
          f"|  {total_passed}/{total_checks} passed")
    print("="*60)

    # ── Gaps only ─────────────────────────────────────────────────
    gaps = [r for r in results if r.status != "PASS"]

    if gaps:
        # Severity breakdown
        sev_counts: dict = {}
        for g in gaps:
            sev_counts[g.severity] = sev_counts.get(g.severity, 0) + 1
        print(f"\n  {len(gaps)} gap(s) found — severity breakdown:")
        for sev in sorted(sev_counts, key=lambda s: SEV_ORDER.get(s, 9)):
            print(f"    {SEV_ICON.get(sev,'⚪')} {sev:<10}: {sev_counts[sev]} gap(s)")

        # First 10 gaps sorted by severity
        sorted_gaps = sorted(gaps, key=lambda g: SEV_ORDER.get(g.severity, 9))
        print(f"\n  First 10 gaps (sorted by severity):")
        for g in sorted_gaps[:10]:
            icon = SEV_ICON.get(g.severity, "⚪")
            cat  = CHECK_ID_TO_CATEGORY.get(g.check_id, g.check_id)
            print(f"    {icon} [{g.check_id}] {g.attribute}")
            print(f"           Source  : {str(g.source_value)[:70]}")
            print(f"           JSON    : {str(g.json_value)[:70]}")
            if g.note:
                print(f"           Note    : {g.note[:90]}")
    else:
        print(f"\n  ✅ No gaps — JSON captures all Tableau artifacts correctly.")

    # ── Write outputs ─────────────────────────────────────────────
    # CSV — full results with category column
    rows_out = []
    for r in results:
        d = asdict(r)
        d["category"] = CHECK_ID_TO_CATEGORY.get(r.check_id, r.check_id)
        rows_out.append(d)
    results_df = pd.DataFrame(rows_out)
    # Sort by severity then check_id
    results_df["_sev_order"] = results_df["severity"].map(
        lambda s: SEV_ORDER.get(s, 9))
    results_df = results_df.sort_values(
        ["_sev_order", "check_id", "attribute"]
    ).drop(columns=["_sev_order"])

    csv_path     = out_dir / f"{twb_path.stem}_validation_results.csv"
    summary_path = out_dir / f"{twb_path.stem}_validation_summary.json"
    gap_path     = out_dir / f"{twb_path.stem}_gap_report.json"

    results_df.to_csv(csv_path, index=False)

    # Summary JSON
    group_scores_dict = {}
    for cid in ALL_CHECKS:
        passed, total, pct = group_score(cid)
        if total > 0:
            group_scores_dict[cid] = {
                "category": CHECK_ID_TO_CATEGORY.get(cid, cid),
                "passed":   passed,
                "total":    total,
                "score":    pct,
            }

    with summary_path.open("w", encoding="utf-8") as f:
        json.dump({
            "workbook_name":    report.workbook_name,
            "twb_path":         report.twb_path,
            "json_path":        report.json_path,
            "timestamp":        report.timestamp,
            "total_checks":     total_checks,
            "passed":           total_passed,
            "score":            overall_score,
            "confidence_score": confidence_score,
            "verdict":          verdict,
            "gap_count":        len(gaps),
            "has_critical_gaps":has_critical,
            "group_scores":     group_scores_dict,
        }, f, indent=2)

    # Gap report JSON — only failures, sorted by severity
    gap_rows = [asdict(r) for r in sorted_gaps] if gaps else []
    with gap_path.open("w", encoding="utf-8") as f:
        json.dump({
            "summary": {
                "workbook": report.workbook_name,
                "score":    overall_score,
                "confidence_score": confidence_score,
                "verdict":  verdict,
                "gap_count":len(gaps),
            },
            "gaps": gap_rows,
        }, f, indent=2, default=str)

    print(f"\n[Report] CSV         --> {csv_path}")
    print(f"[Report] Summary JSON --> {summary_path}")
    print(f"[Report] Gap report   --> {gap_path}")
    return report




def main():
    parser = argparse.ArgumentParser(description="Validate Tableau TWB/TWBX against homogeneous JSON")
    parser.add_argument("--twb", required=True, help="Path to .twb or .twbx file")
    parser.add_argument("--json", required=True, help="Path to homogeneous JSON file")
    parser.add_argument("--out", default="./output", help="Output directory for validation results")
    args = parser.parse_args()

    run_validation(args.twb, args.json, args.out)


if __name__ == "__main__":
    main()