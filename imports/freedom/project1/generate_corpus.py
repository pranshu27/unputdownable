#!/usr/bin/env python3
"""Generate synthetic Informatica PowerMart XML files for the infa -> pyspark migration corpus.

Creates 10 domain files x 12 mappings = 120 mappings (>100), mirroring the exact element
and attribute vocabulary of informatica_powermart_comprehensive.xml (POWERMART 10.4,
REP_DEV, Oracle + SQL Server sources, INSTANCE/CONNECTOR wiring, EXPRESSION locals).
The original file is left untouched.

Patterns per domain folder (all mirror shapes harvested from the original):
  P1  SQ -> EXP(derive)                                -> TGT
  P2  SQ1,SQ2 -> JNR -> FIL -> EXP                     -> TGT
  P3  SQ -> AGG -> EXP                                 -> TGT
  P4  SQ -> SRT -> EXP(stateful window emulation)      -> TGT
  P5  SQ -> RTR -> EXP(group A) -> TGT (+ group B feed)
  P6  SQ -> LKP -> EXP -> UPS(update strategy)         -> TGT
  P7  SQ -> FIL -> RNK(top-N) -> EXP                   -> TGT
  P8  SQ -> NRM(unpivot) -> EXP                        -> TGT
  P9  SQ1 -> AGG -> JNR(agg=detail, SQ2=master) -> EXP -> TGT
  P10 SQ -> MPL(domain mapplet) -> EXP                 -> TGT

Usage:  python3 generate_corpus.py            # writes + validates the 10 files
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path

HERE = Path(__file__).resolve().parent

# SOURCEFIELD datatype -> TRANSFORMFIELD datatype (mirrors the original's mapping quirk)
SRC2TF = {
    "varchar2": "string", "varchar": "string", "char": "string",
    "number": "decimal", "decimal": "decimal",
    "integer": "integer", "bigint": "bigint",
    "date": "date/time", "datetime": "date/time",
}

PRETTY_INDENT = "\n        "


def E(tag: str, **attrs) -> ET.Element:
    el = ET.Element(tag)
    for k, v in attrs.items():
        el.set(k, str(v))
    return el


def fld(name, datatype, porttype, prec, scale, expression=None, **extra) -> ET.Element:
    attrs = {"DATATYPE": datatype, "NAME": name, "PORTTYPE": porttype,
             "PRECISION": prec, "SCALE": scale}
    if expression is not None:
        attrs["EXPRESSION"] = expression
    attrs.update(extra)
    return E("TRANSFORMFIELD", **attrs)


def attr(name, value) -> ET.Element:
    return E("TABLEATTRIBUTE", NAME=name, VALUE=value)


def tf_fields_for_source(src: dict) -> list[ET.Element]:
    """SQ/chain ports: SOURCEFIELDs converted to TRANSFORMFIELD datatypes (INPUT/OUTPUT)."""
    out = []
    for f in src["fields"]:
        name, dt, p, s = f[0], f[1], f[2], f[3]
        out.append(fld(name, SRC2TF[dt], "INPUT/OUTPUT", p, s))
    return out


def source_field_names(src: dict) -> list[str]:
    return [f[0] for f in src["fields"]]


def master_ports(fields: list[ET.Element]) -> list[ET.Element]:
    """Joiner master-side ports: same fields, porttype + '/MASTER' (mirrors JNR_CUST_ORDERS)."""
    out = []
    for f in fields:
        c = deepcopy(f)
        c.set("PORTTYPE", f.get("PORTTYPE") + "/MASTER")
        out.append(c)
    return out


def wire(prev_name, prev_type, next_name, next_type, fields, map_from=None) -> list[ET.Element]:
    """Connectors: same-named fields from prev instance to next (map_from renames)."""
    out = []
    for f in fields:
        src_f = f if map_from is None else map_from
        out.append(E("CONNECTOR", FROMFIELD=src_f, FROMINSTANCE=prev_name,
                     FROMINSTANCETYPE=prev_type, TOFIELD=f, TOINSTANCE=next_name,
                     TOINSTANCETYPE=next_type))
    return out


def target_wires(exp_name, target_name, pairs) -> list[ET.Element]:
    """Connectors from an Expression's O_* outputs into target fields."""
    return [E("CONNECTOR", FROMFIELD=of, FROMINSTANCE=exp_name, FROMINSTANCETYPE="Expression",
              TOFIELD=tf, TOINSTANCE=target_name, TOINSTANCETYPE="Target Definition")
            for of, tf in pairs]

# ---------------------------------------------------------------- transform builders

def build_sq(name: str, src: dict, extra_filter: str | None = None) -> ET.Element:
    tfo = E("TRANSFORMATION", NAME=name, TYPE="Source Qualifier", REUSABLE="NO",
            OBJECTVERSION="1", VERSIONNUMBER="1")
    for f in tf_fields_for_source(src):
        tfo.append(f)
    tfo.append(attr("Source Filter", extra_filter or ""))
    tfo.append(attr("User Defined Join", ""))
    return tfo


def build_expression(name: str, pass_fields: list[ET.Element], locals_: list[dict],
                     outputs: list[dict]) -> ET.Element:
    """Expression: pass-through INPUT/OUTPUT ports + LOCAL VARIABLE ports (EXPRESSION,
    variables first, outputs last - mirrors EXP_STATEFUL_WINDOW_EMULATION)."""
    tfo = E("TRANSFORMATION", NAME=name, TYPE="Expression", REUSABLE="NO",
            OBJECTVERSION="1", VERSIONNUMBER="1")
    for f in pass_fields:
        tfo.append(deepcopy(f))
    for spec in locals_:
        tfo.append(fld(spec["name"], spec["dtype"], "LOCAL VARIABLE", spec["prec"],
                       spec["scale"], expression=spec["expr"]))
    for spec in outputs:
        tfo.append(fld(spec["name"], spec["dtype"], "OUTPUT", spec["prec"],
                       spec["scale"], expression=spec["expr"]))
    return tfo


def build_filter(name: str, fields: list[ET.Element], condition: str) -> ET.Element:
    tfo = E("TRANSFORMATION", NAME=name, TYPE="Filter", REUSABLE="NO",
            OBJECTVERSION="1", VERSIONNUMBER="1")
    for f in fields:
        tfo.append(deepcopy(f))
    tfo.append(attr("Filter Condition", condition))
    return tfo


def build_joiner(name: str, detail_fields: list[ET.Element], master_fields: list[ET.Element],
                 join_type: str, condition: str) -> ET.Element:
    tfo = E("TRANSFORMATION", NAME=name, TYPE="Joiner", REUSABLE="NO",
            OBJECTVERSION="1", VERSIONNUMBER="1")
    for f in detail_fields:
        tfo.append(deepcopy(f))
    for f in master_fields:
        tfo.append(deepcopy(f))
    tfo.append(attr("Case Sensitive String Comparison", "YES"))
    tfo.append(attr("Join Condition", condition))
    tfo.append(attr("Join Type", join_type))
    tfo.append(attr("Null ordering in master", "Null Is Highest Value"))
    tfo.append(attr("Null ordering in detail", "Null Is Highest Value"))
    tfo.append(attr("Sorted Input", "NO"))
    return tfo


def build_aggregator(name: str, group_fields: list[ET.Element], agg_inputs: list[ET.Element],
                     aggregates: list[dict]) -> ET.Element:
    """Group-by ports keep INPUT/OUTPUT + identity EXPRESSION; aggregates are OUTPUT ports."""
    tfo = E("TRANSFORMATION", NAME=name, TYPE="Aggregator", REUSABLE="NO",
            OBJECTVERSION="1", VERSIONNUMBER="1")
    for f in group_fields:
        c = deepcopy(f)
        c.set("EXPRESSION", c.get("NAME"))
        tfo.append(c)
    for f in agg_inputs:
        tfo.append(E("TRANSFORMFIELD", DATATYPE=f.get("DATATYPE"), NAME=f.get("NAME"),
                     PORTTYPE="INPUT", PRECISION=f.get("PRECISION"), SCALE=f.get("SCALE")))
    for spec in aggregates:
        tfo.append(fld(spec["name"], spec["dtype"], "OUTPUT", spec["prec"], spec["scale"],
                       expression=spec["expr"]))
    tfo.append(attr("Sorted Input", "NO"))
    return tfo


def build_sorter(name: str, fields: list[ET.Element], sort_keys: list[str]) -> ET.Element:
    tfo = E("TRANSFORMATION", NAME=name, TYPE="Sorter", REUSABLE="NO",
            OBJECTVERSION="1", VERSIONNUMBER="1")
    for f in fields:
        c = deepcopy(f)
        c.set("ISSORTKEY", "YES" if c.get("NAME") in sort_keys else "NO")
        c.set("SORTDIRECTION", "ASCENDING")
        tfo.append(c)
    tfo.append(attr("Case Sensitive", "YES"))
    tfo.append(attr("Distinct", "NO"))
    tfo.append(attr("Null Treated Low", "YES"))
    return tfo


def build_router(name: str, in_fields: list[ET.Element], groups: list[dict]) -> ET.Element:
    """GROUP='INPUT' pass-through + one output set per group (field names suffixed 1/2)."""
    tfo = E("TRANSFORMATION", NAME=name, TYPE="Router", REUSABLE="NO",
            OBJECTVERSION="1", VERSIONNUMBER="1")
    for f in in_fields:
        c = deepcopy(f)
        c.set("GROUP", "INPUT")
        tfo.append(c)
    for gi, g in enumerate(groups, start=1):
        gname = g["name"] if isinstance(g, dict) else g[0]
        for f in in_fields:
            c = deepcopy(f)
            c.set("GROUP", gname)
            c.set("PORTTYPE", "INPUT")
            c.set("NAME", c.get("NAME") + str(gi))
            tfo.append(c)
    return tfo



def build_lookup(name: str, lkp_src: dict, in_fields: list[ET.Element],
                 lkp_condition: str, return_specs: list[dict]) -> ET.Element:
    """Non-reusable connected lookup: IN_* inputs, LOOKUP keys, LOOKUP/OUTPUT/RETURN values."""
    tfo = E("TRANSFORMATION", NAME=name, TYPE="Lookup Procedure", REUSABLE="NO",
            OBJECTVERSION="1", VERSIONNUMBER="1")
    for f in in_fields:
        c = deepcopy(f)
        c.set("PORTTYPE", "INPUT")
        c.set("NAME", "IN_" + c.get("NAME"))
        tfo.append(c)
    lkp_cols = source_field_names(lkp_src)
    dt_by_name = {f[0]: f[1] for f in lkp_src["fields"]}
    for n in lkp_cols:
        tfo.append(fld(n, SRC2TF[dt_by_name[n]], "LOOKUP", 50, 0))
    for spec in return_specs:
        tfo.append(fld(spec["name"], spec["dtype"], "LOOKUP/OUTPUT/RETURN",
                       spec["prec"], spec["scale"]))
    cols = ", ".join(f"{n} AS {n}" for n in lkp_cols + [s["name"] for s in return_specs])
    tfo.append(attr("Lookup Sql Override",
                    f"SELECT {cols} FROM {lkp_src['dbd']}.{lkp_src['name']} --"))
    tfo.append(attr("Lookup table name", lkp_src["name"]))
    tfo.append(attr("Lookup Source Filter", ""))
    tfo.append(attr("Lookup caching enabled", "YES"))
    tfo.append(attr("Lookup policy on multiple match", "Use First Value"))
    tfo.append(attr("Lookup condition", lkp_condition))
    tfo.append(attr("Connection Information", "$Source"))
    tfo.append(attr("Source Type", "Database"))
    return tfo


def build_update_strategy(name: str, fields: list[ET.Element], expr: str) -> ET.Element:
    tfo = E("TRANSFORMATION", NAME=name, TYPE="Update Strategy", REUSABLE="NO",
            OBJECTVERSION="1", VERSIONNUMBER="1")
    for f in fields:
        tfo.append(deepcopy(f))
    tfo.append(attr("Update Strategy Expression", expr))
    return tfo


def build_rank(name: str, fields: list[ET.Element], topn: int, topbottom: str = "Top") -> ET.Element:
    tfo = E("TRANSFORMATION", NAME=name, TYPE="Rank", REUSABLE="NO",
            OBJECTVERSION="1", VERSIONNUMBER="1")
    tfo.append(fld("RANKINDEX", "integer", "OUTPUT", 10, 0, expression="RANKINDEX"))
    for f in fields:
        c = deepcopy(f)
        c.set("EXPRESSION", c.get("NAME"))
        tfo.append(c)
    tfo.append(attr("Top/Bottom", topbottom))
    tfo.append(attr("Number of Ranks", topn))
    tfo.append(attr("Case Sensitive String Comparison", "YES"))
    return tfo


def build_normalizer(name: str, base_cols: list[tuple], pivot_specs: list[dict]) -> ET.Element:
    """Unpivot: '<col>_in<i>' inputs -> '<col>' outputs + GENERATED KEY/COLUMN ID ports."""
    tfo = E("TRANSFORMATION", NAME=name, TYPE="Normalizer", REUSABLE="NO",
            OBJECTVERSION="1", VERSIONNUMBER="1")
    for name_, dtype, prec, scale in base_cols:
        tfo.append(fld(name_ + "_in", dtype, "INPUT", prec, scale))
    for spec in pivot_specs:
        for i in range(1, spec["occurrences"] + 1):
            tfo.append(fld(f"{spec['name']}_in{i}", spec["dtype"], "INPUT",
                           spec["prec"], spec["scale"]))
    for name_, dtype, prec, scale in base_cols:
        tfo.append(fld(name_, dtype, "OUTPUT", prec, scale))
    for spec in pivot_specs:
        tfo.append(fld(spec["name"], spec["dtype"], "OUTPUT", spec["prec"], spec["scale"]))
        tfo.append(fld("GK_" + spec["name"], "bigint", "GENERATED KEY/OUTPUT", 19, 0))
        tfo.append(fld("GCID_" + spec["name"], "integer", "GENERATED COLUMN ID/OUTPUT", 10, 0))
    return tfo


def build_sequence(name: str, start: int = 100000, reusable: str = "NO") -> ET.Element:
    tfo = E("TRANSFORMATION", NAME=name, TYPE="Sequence", REUSABLE=reusable,
            OBJECTVERSION="1", VERSIONNUMBER="1")
    tfo.append(fld("NEXTVAL", "bigint", "OUTPUT", 19, 0))
    tfo.append(fld("CURRVAL", "bigint", "OUTPUT", 19, 0))
    tfo.append(attr("Start Value", start))
    tfo.append(attr("Increment By", 1))
    tfo.append(attr("End Value", 9223372036854775807))
    tfo.append(attr("Current Value", start))
    tfo.append(attr("Cycle", "NO"))
    tfo.append(attr("Number of Cached Values", 1000))
    tfo.append(attr("Reset", "NO"))
    return tfo



# ---------------------------------------------------------------- domain corpus specs
# Field tuple: (NAME, SRC_DATATYPE, PRECISION, SCALE, KEYTYPE, NULLABLE)
# mkbank auto-derives generic expressions from the primary source; per-domain overrides
# inject the flavor (dim / m1 / attr / filter / router conditions).

def mkbank(s1, **fl) -> dict:
    key_field = s1["fields"][0][0]
    measures = [f[0] for f in s1["fields"] if f[1] == "number"]
    measure, measure2 = measures[0], (measures[1] if len(measures) > 1 else measures[0])
    dim_f = next((f[0] for f in s1["fields"] if f[1] in ("varchar2", "varchar") and f[4] != "PRIMARY KEY"), key_field)
    date_f = next((f[0] for f in s1["fields"] if f[1] in ("date", "datetime")), "SESSSTARTTIME")
    return dict(
        key_field=key_field, measure=measure, measure2=measure2,
        dim=fl.get("dim", f"UPPER({dim_f})"),
        m1=fl.get("m1", f"IIF(ISNULL({measure}), 0, {measure})"),
        m2=fl.get("m2", f"IIF(ISNULL({measure2}), 0, {measure2})"),
        attr=fl.get("attr", f"'{date_f}=' || TO_CHAR({date_f}, 'YYYY-MM-DD')"),
        key_derive=fl.get("key_derive", f"TO_DECIMAL(SUBSTR({key_field}, 2, 9))"),
        filter_cond=fl.get("filter_cond", f"{measure} IS NOT NULL AND {measure} > 0"),
        join_type=fl.get("join_type", "Detail Outer Join"),
        rtr_groups=fl.get("rtr_groups", [("GRP_ACTIVE", f"{measure} > 0"), ("GRP_NULL", f"{measure} IS NULL")]),
        lkp_cond=fl.get("lkp_cond"),
        ups_expr=fl.get("ups_expr", "DD_INSERT"),
        mpl_net=fl.get("mpl_net", "ROUND(IIF(ISNULL(IN_M1), 0, IN_M1) - IIF(ISNULL(IN_M2), 0, IN_M2), 2)"),
        mpl_ratio=fl.get("mpl_ratio", "IIF(ISNULL(IN_M1) OR IN_M1 = 0, 0, ROUND(IN_M2 / IN_M1, 4))"),
    )


def src(name, biz, dbd, fields) -> dict:
    return dict(name=name, biz=biz, dbd=dbd, fields=fields)


def flavor(**kw) -> dict:
    """Per-domain expression overrides; the full bank is built lazily against the source."""
    return kw


def dom(key, folder, s1, s2, flav, stories) -> dict:
    return dict(key=key, folder=folder, s1=s1, s2=s2, flavor=flav, stories=stories)


V = "varchar2"
D = "number"
DT = "date"

DOMAINS = []

DOMAINS.append(dom("finance_ledger", "MIGRATION_FINANCE_LEDGER",
    src("SRC_GL_JOURNAL_LINES", "General Ledger Journal Lines", "ORA_FIN", [
        ("JOURNAL_ID", V, 30, 0, "PRIMARY KEY", "NOTNULL"), ("LINE_NO", D, 5, 0, "NOT A KEY", "NOTNULL"),
        ("ACCOUNT_CD", V, 10, 0, "FOREIGN KEY", "NOTNULL"), ("COST_CENTER", V, 10, 0, "NOT A KEY", "NULL"),
        ("ENTRY_TYPE", V, 3, 0, "NOT A KEY", "NOTNULL"), ("DEBIT_AMT", D, 18, 2, "NOT A KEY", "NULL"),
        ("CREDIT_AMT", D, 18, 2, "NOT A KEY", "NULL"), ("POST_DT", DT, 19, 0, "NOT A KEY", "NULL")]),
    src("SRC_GL_ACCOUNTS", "Chart of Accounts", "ORA_FIN", [
        ("ACCOUNT_CD", V, 10, 0, "PRIMARY KEY", "NOTNULL"), ("ACCOUNT_NAME", V, 100, 0, "NOT A KEY", "NOTNULL"),
        ("ACCOUNT_TYPE", V, 10, 0, "NOT A KEY", "NOTNULL"), ("IS_PL_IND", V, 1, 0, "NOT A KEY", "NULL")]),
    flavor(
        dim="UPPER(ACCOUNT_CD) || '-' || ENTRY_TYPE",
        m1="IIF(ENTRY_TYPE = 'DR', IIF(ISNULL(DEBIT_AMT), 0, DEBIT_AMT), -1 * IIF(ISNULL(CREDIT_AMT), 0, CREDIT_AMT))",
        m2="IIF(ISNULL(DEBIT_AMT), 0, DEBIT_AMT) - IIF(ISNULL(CREDIT_AMT), 0, CREDIT_AMT)",
        attr="'POSTED:' || TO_CHAR(POST_DT, 'YYYY-MM-DD') || ':CC=' || COST_CENTER",
        filter_cond="ENTRY_TYPE IN ('DR', 'CR') AND POST_DT >= ADD_TO_DATE(SESSSTARTTIME, 'MM', -24)",
        rtr_groups=[("GRP_DEBIT", "ENTRY_TYPE = 'DR'"), ("GRP_CREDIT", "ENTRY_TYPE = 'CR'")],
        lkp_cond="IN_ACCOUNT_CD = ACCOUNT_CD",
        ups_expr="IIF(ENTRY_TYPE = 'DR', DD_INSERT, DD_UPDATE)"),
    ["gl_period_balances", "journal_line_enrichment", "account_rolling_totals",
     "dr_cr_running_ledger", "debit_credit_split", "account_master_enrich_upsert",
     "top_accounts_by_volume", "quarterly_unpivot_gl", "ratio_to_total_by_account",
     "mapplet_net_entry_math", "journal_exception_feed", "cost_center_rollup", "consolidated_daily_load"]))

DOMAINS.append(dom("treasury_fx", "MIGRATION_TREASURY_FX",
    src("SRC_TREASURY_POSITIONS", "Treasury Positions", "ORA_TRE", [
        ("POSITION_ID", V, 30, 0, "PRIMARY KEY", "NOTNULL"), ("BOOK_CD", V, 10, 0, "NOT A KEY", "NOTNULL"),
        ("CURRENCY_CD", V, 3, 0, "NOT A KEY", "NOTNULL"), ("INSTRUMENT_TYPE", V, 20, 0, "NOT A KEY", "NOTNULL"),
        ("FACE_AMT", D, 18, 2, "NOT A KEY", "NULL"), ("MTM_AMT", D, 18, 4, "NOT A KEY", "NULL"),
        ("TRADE_DT", DT, 19, 0, "NOT A KEY", "NULL")]),
    src("SRC_FX_TICKETS", "FX Tickets", "ORA_TRE", [
        ("TICKET_ID", V, 30, 0, "PRIMARY KEY", "NOTNULL"), ("CURRENCY_CD", V, 3, 0, "NOT A KEY", "NOTNULL"),
        ("RATE", D, 18, 6, "NOT A KEY", "NOTNULL"), ("TICKET_DT", DT, 19, 0, "NOT A KEY", "NULL")]),
    flavor(
        dim="BOOK_CD || '-' || CURRENCY_CD || '-' || INSTRUMENT_TYPE",
        m1="IIF(ISNULL(FACE_AMT), 0, FACE_AMT) * IIF(ISNULL(RATE_LKP), 1, RATE_LKP)",
        attr="'BOOK=' || BOOK_CD || ':TRADED=' || TO_CHAR(TRADE_DT, 'YYYY-MM-DD')",
        filter_cond="INSTRUMENT_TYPE IN ('FX_FORWARD', 'FX_SPOT') AND TRADE_DT >= ADD_TO_DATE(SESSSTARTTIME, 'DD', -90)",
        join_type="Master Outer Join",
        rtr_groups=[("GRP_LONG", "MTM_AMT >= 0"), ("GRP_SHORT", "MTM_AMT < 0")],
        lkp_cond="IN_CURRENCY_CD = CURRENCY_CD",
        ups_expr="IIF(MTM_AMT > 0, DD_INSERT, DD_UPDATE)",
        mpl_net="ROUND(IIF(ISNULL(IN_M1), 0, IN_M1) * IIF(ISNULL(IN_M2), 1, IN_M2), 4)"),
    ["position_mtm_snapshot", "position_fx_enrichment", "book_exposure_totals",
     "mtm_running_by_book", "long_short_split", "position_ticket_upsert",
     "top_positions_by_face", "tenor_unpivot_treasury", "ratio_to_book_total",
     "mapplet_position_math", "stale_position_feed", "currency_rollup", "consolidated_daily_load"]))

DOMAINS.append(dom("receivables", "MIGRATION_RECEIVABLES",
    src("SRC_AR_INVOICES", "AR Invoices", "ORA_AR", [
        ("INVOICE_ID", V, 30, 0, "PRIMARY KEY", "NOTNULL"), ("CUSTOMER_ID", V, 50, 0, "FOREIGN KEY", "NOTNULL"),
        ("INVOICE_AMT", D, 18, 2, "NOT A KEY", "NULL"), ("PAID_AMT", D, 18, 2, "NOT A KEY", "NULL"),
        ("CURRENCY_CD", V, 3, 0, "NOT A KEY", "NULL"), ("DUE_DT", DT, 19, 0, "NOT A KEY", "NULL"),
        ("OPEN_IND", V, 1, 0, "NOT A KEY", "NULL")]),
    src("SRC_AR_PAYMENTS", "AR Payments", "ORA_AR", [
        ("PAYMENT_ID", V, 30, 0, "PRIMARY KEY", "NOTNULL"), ("INVOICE_ID", V, 30, 0, "FOREIGN KEY", "NOTNULL"),
        ("PAYMENT_AMT", D, 18, 2, "NOT A KEY", "NULL"), ("PAYMENT_DT", DT, 19, 0, "NOT A KEY", "NULL")]),
    flavor(
        dim="CUSTOMER_ID || '-' || CURRENCY_CD",
        m1="IIF(ISNULL(INVOICE_AMT), 0, INVOICE_AMT) - IIF(ISNULL(PAID_AMT), 0, PAID_AMT)",
        attr="'DUE=' || TO_CHAR(DUE_DT, 'YYYY-MM-DD') || ':OPEN=' || OPEN_IND",
        filter_cond="OPEN_IND = 'Y' AND INVOICE_AMT > 0",
        rtr_groups=[("GRP_OVERDUE", "DUE_DT < TRUNC(SESSSTARTTIME)"), ("GRP_CURRENT", "DUE_DT >= TRUNC(SESSSTARTTIME)")],
        lkp_cond="IN_INVOICE_ID = INVOICE_ID",
        ups_expr="IIF(OPEN_IND = 'Y', DD_UPDATE, DD_INSERT)"),
    ["open_ar_snapshot", "invoice_payment_enrichment", "customer_ar_totals",
     "aging_running_balance", "overdue_current_split", "invoice_status_upsert",
     "top_open_invoices", "month_bucket_unpivot", "paid_ratio_by_customer",
     "mapplet_open_balance", "writeoff_candidate_feed", "currency_ar_rollup", "consolidated_daily_load"]))

DOMAINS.append(dom("payables", "MIGRATION_PAYABLES",
    src("SRC_AP_BILLS", "AP Bills", "ORA_AP", [
        ("BILL_ID", V, 30, 0, "PRIMARY KEY", "NOTNULL"), ("VENDOR_ID", V, 50, 0, "FOREIGN KEY", "NOTNULL"),
        ("BILL_AMT", D, 18, 2, "NOT A KEY", "NULL"), ("TAX_AMT", D, 18, 2, "NOT A KEY", "NULL"),
        ("APPROVAL_STATUS", V, 20, 0, "NOT A KEY", "NOTNULL"), ("BILL_DT", DT, 19, 0, "NOT A KEY", "NULL")]),
    src("SRC_AP_PAYMENTS", "AP Payments", "ORA_AP", [
        ("PAYMENT_ID", V, 30, 0, "PRIMARY KEY", "NOTNULL"), ("BILL_ID", V, 30, 0, "FOREIGN KEY", "NOTNULL"),
        ("PAID_AMT", D, 18, 2, "NOT A KEY", "NULL"), ("PAYMENT_DT", DT, 19, 0, "NOT A KEY", "NULL")]),
    flavor(
        dim="VENDOR_ID || '-' || APPROVAL_STATUS",
        m1="IIF(ISNULL(BILL_AMT), 0, BILL_AMT) - IIF(ISNULL(TAX_AMT), 0, TAX_AMT)",
        attr="'STATUS=' || APPROVAL_STATUS || ':BILLED=' || TO_CHAR(BILL_DT, 'YYYY-MM-DD')",
        filter_cond="APPROVAL_STATUS <> 'REJECTED'",
        rtr_groups=[("GRP_APPROVED", "APPROVAL_STATUS = 'APPROVED'"), ("GRP_PENDING", "APPROVAL_STATUS = 'PENDING'")],
        lkp_cond="IN_BILL_ID = BILL_ID",
        ups_expr="IIF(APPROVAL_STATUS = 'APPROVED', DD_INSERT, DD_REJECT)",
        mpl_net="ROUND(IIF(ISNULL(IN_M1), 0, IN_M1) + IIF(ISNULL(IN_M2), 0, IN_M2), 2)",
        mpl_ratio="IIF(ISNULL(IN_M1) OR IN_M1 = 0, 0, ROUND(IN_M2 / IN_M1, 4))"),
    ["payables_snapshot", "bill_vendor_enrichment", "vendor_liability_totals",
     "approval_running_queue", "approved_pending_split", "bill_payment_upsert",
     "top_bills_by_amount", "period_unpivot_ap", "tax_ratio_by_vendor",
     "mapplet_gross_math", "stale_bill_feed", "vendor_rollup", "consolidated_daily_load"]))

DOMAINS.append(dom("risk_credit", "MIGRATION_RISK_CREDIT",
    src("SRC_LOAN_APPLICATIONS", "Loan Applications", "MSSQL_RISK", [
        ("APPLICATION_ID", "varchar", 30, 0, "PRIMARY KEY", "NOTNULL"), ("APPLICANT_ID", "varchar", 50, 0, "FOREIGN KEY", "NOTNULL"),
        ("PRODUCT_CD", "varchar", 10, 0, "NOT A KEY", "NOTNULL"), ("REQUESTED_AMT", "number", 18, 2, "NOT A KEY", "NULL"),
        ("TERM_MONTHS", "number", 5, 0, "NOT A KEY", "NULL"), ("APR", "number", 8, 4, "NOT A KEY", "NULL"),
        ("APPLICATION_DT", "datetime", 19, 0, "NOT A KEY", "NULL")]),
    src("SRC_CREDIT_SCORES", "Credit Scores", "MSSQL_RISK", [
        ("APPLICANT_ID", "varchar", 50, 0, "PRIMARY KEY", "NOTNULL"), ("BUREAU_CD", "varchar", 10, 0, "NOT A KEY", "NOTNULL"),
        ("SCORE", "number", 5, 0, "NOT A KEY", "NOTNULL"), ("SCORE_DT", "datetime", 19, 0, "NOT A KEY", "NULL")]),
    flavor(
        dim="APPLICANT_ID || '-' || PRODUCT_CD",
        m1="IIF(ISNULL(REQUESTED_AMT), 0, REQUESTED_AMT) * IIF(ISNULL(APR), 0, APR) / 100",
        attr="'TERM=' || TO_CHAR(TERM_MONTHS) || ':APPLIED=' || TO_CHAR(APPLICATION_DT, 'YYYY-MM-DD')",
        filter_cond="REQUESTED_AMT > 0 AND TERM_MONTHS BETWEEN 6 AND 84",
        join_type="Full Outer Join",
        rtr_groups=[("GRP_PRIME", "APR < 10"), ("GRP_SUBPRIME", "APR >= 10")],
        lkp_cond="IN_APPLICANT_ID = APPLICANT_ID",
        ups_expr="IIF(APR < 10, DD_INSERT, DD_UPDATE)",
        mpl_net="ROUND(IIF(ISNULL(IN_M1), 0, IN_M1) * IIF(ISNULL(IN_M2), 1, IN_M2), 2)",
        mpl_ratio="IIF(ISNULL(IN_M1) OR IN_M1 = 0, 0, ROUND(IN_M2 / IN_M1, 4))"),
    ["applications_snapshot", "applicant_score_enrichment", "product_request_totals",
     "decision_running_queue", "prime_subprime_split", "application_score_upsert",
     "top_applications_by_amount", "term_bucket_unpivot", "apr_ratio_by_product",
     "mapplet_interest_math", "incomplete_application_feed", "product_rollup", "consolidated_daily_load"]))

DOMAINS.append(dom("market_risk", "MIGRATION_MARKET_RISK",
    src("SRC_TRD_TRADES", "Trading Positions", "ORA_TRD", [
        ("TRADE_ID", V, 30, 0, "PRIMARY KEY", "NOTNULL"), ("BOOK_CD", V, 10, 0, "NOT A KEY", "NOTNULL"),
        ("INSTRUMENT_ID", V, 20, 0, "FOREIGN KEY", "NOTNULL"), ("TRADE_TYPE", V, 10, 0, "NOT A KEY", "NOTNULL"),
        ("QUANTITY", D, 18, 4, "NOT A KEY", "NULL"), ("TRADE_PRICE", D, 18, 6, "NOT A KEY", "NULL"),
        ("TRADE_DT", DT, 19, 0, "NOT A KEY", "NULL")]),
    src("SRC_MARKET_PRICES", "Market Prices", "ORA_TRD", [
        ("INSTRUMENT_ID", V, 20, 0, "PRIMARY KEY", "NOTNULL"), ("CLOSE_PRICE", D, 18, 6, "NOT A KEY", "NOTNULL"),
        ("PRICE_DT", DT, 19, 0, "NOT A KEY", "NULL")]),
    flavor(
        dim="BOOK_CD || '-' || INSTRUMENT_ID",
        m1="IIF(ISNULL(QUANTITY), 0, QUANTITY) * IIF(ISNULL(CLOSE_PRICE_LKP), 0, CLOSE_PRICE_LKP)",
        attr="'TYPE=' || TRADE_TYPE || ':TRADED=' || TO_CHAR(TRADE_DT, 'YYYY-MM-DD')",
        filter_cond="TRADE_TYPE IN ('BUY', 'SELL')",
        rtr_groups=[("GRP_BUY", "TRADE_TYPE = 'BUY'"), ("GRP_SELL", "TRADE_TYPE = 'SELL'")],
        lkp_cond="IN_INSTRUMENT_ID = INSTRUMENT_ID",
        ups_expr="IIF(TRADE_TYPE = 'BUY', DD_INSERT, DD_UPDATE)",
        mpl_net="ROUND(IIF(ISNULL(IN_M1), 0, IN_M1) * IIF(ISNULL(IN_M2), 1, IN_M2), 4)",
        mpl_ratio="IIF(ISNULL(IN_M1) OR IN_M1 = 0, 0, ROUND(IN_M2 / IN_M1, 4))"),
    ["trade_snapshot", "trade_price_enrichment", "book_notional_totals",
     "pnl_running_by_book", "buy_sell_split", "trade_price_upsert",
     "top_trades_by_notional", "strike_unpivot_trades", "price_ratio_by_instrument",
     "mapplet_notional_math", "orphan_trade_feed", "instrument_rollup", "consolidated_daily_load"]))

DOMAINS.append(dom("inventory_supply", "MIGRATION_INVENTORY_SUPPLY",
    src("SRC_INV_MOVEMENTS", "Inventory Movements", "ORA_SCM", [
        ("MOVEMENT_ID", V, 30, 0, "PRIMARY KEY", "NOTNULL"), ("ITEM_CD", V, 20, 0, "FOREIGN KEY", "NOTNULL"),
        ("WAREHOUSE_CD", V, 10, 0, "NOT A KEY", "NOTNULL"), ("MOVEMENT_TYPE", V, 10, 0, "NOT A KEY", "NOTNULL"),
        ("QTY", D, 12, 3, "NOT A KEY", "NULL"), ("UNIT_COST", D, 18, 4, "NOT A KEY", "NULL"),
        ("MOVE_DT", DT, 19, 0, "NOT A KEY", "NULL")]),
    src("SRC_PO_LINES", "Purchase Order Lines", "ORA_SCM", [
        ("PO_ID", V, 30, 0, "PRIMARY KEY", "NOTNULL"), ("LINE_NO", D, 5, 0, "NOT A KEY", "NOTNULL"),
        ("ITEM_CD", V, 20, 0, "FOREIGN KEY", "NOTNULL"), ("ORDERED_QTY", D, 12, 3, "NOT A KEY", "NULL"),
        ("UNIT_PRICE", D, 18, 4, "NOT A KEY", "NULL")]),
    flavor(
        dim="ITEM_CD || '-' || WAREHOUSE_CD",
        m1="IIF(ISNULL(QTY), 0, QTY) * IIF(ISNULL(UNIT_COST), 0, UNIT_COST)",
        attr="'MVT=' || MOVEMENT_TYPE || ':MOVED=' || TO_CHAR(MOVE_DT, 'YYYY-MM-DD')",
        filter_cond="QTY <> 0 AND MOVEMENT_TYPE IN ('RECEIPT', 'ISSUE')",
        rtr_groups=[("GRP_RECEIPT", "MOVEMENT_TYPE = 'RECEIPT'"), ("GRP_ISSUE", "MOVEMENT_TYPE = 'ISSUE'")],
        lkp_cond="IN_ITEM_CD = ITEM_CD",
        ups_expr="IIF(MOVEMENT_TYPE = 'RECEIPT', DD_INSERT, DD_UPDATE)",
        mpl_net="ROUND(IIF(ISNULL(IN_M1), 0, IN_M1) * IIF(ISNULL(IN_M2), 0, IN_M2), 4)"),
    ["movements_snapshot", "movement_po_enrichment", "warehouse_value_totals",
     "stock_running_balance", "receipt_issue_split", "movement_cost_upsert",
     "top_items_by_value", "period_unpivot_inventory", "cost_ratio_by_item",
     "mapplet_valuation_math", "negative_stock_feed", "warehouse_rollup", "consolidated_daily_load"]))

DOMAINS.append(dom("sales_pipeline", "MIGRATION_SALES_PIPELINE",
    src("SRC_OPPORTUNITIES", "Sales Opportunities", "MSSQL_CRM", [
        ("OPPORTUNITY_ID", "varchar", 30, 0, "PRIMARY KEY", "NOTNULL"), ("ACCOUNT_ID", "varchar", 50, 0, "FOREIGN KEY", "NOTNULL"),
        ("STAGE_CD", "varchar", 20, 0, "NOT A KEY", "NOTNULL"), ("PROBABILITY", "number", 8, 4, "NOT A KEY", "NULL"),
        ("DEAL_AMT", "number", 18, 2, "NOT A KEY", "NULL"), ("CLOSE_DT", "datetime", 19, 0, "NOT A KEY", "NULL")]),
    src("SRC_SALES_ACTIVITIES", "Sales Activities", "MSSQL_CRM", [
        ("ACTIVITY_ID", "varchar", 30, 0, "PRIMARY KEY", "NOTNULL"), ("OPPORTUNITY_ID", "varchar", 30, 0, "FOREIGN KEY", "NOTNULL"),
        ("ACTIVITY_TYPE", "varchar", 20, 0, "NOT A KEY", "NOTNULL"), ("ACTIVITY_DT", "datetime", 19, 0, "NOT A KEY", "NULL")]),
    flavor(
        dim="ACCOUNT_ID || '-' || STAGE_CD",
        m1="IIF(ISNULL(DEAL_AMT), 0, DEAL_AMT) * IIF(ISNULL(PROBABILITY), 0, PROBABILITY)",
        attr="'STAGE=' || STAGE_CD || ':CLOSE=' || TO_CHAR(CLOSE_DT, 'YYYY-MM-DD')",
        filter_cond="STAGE_CD NOT IN ('LOST', 'CANCELLED')",
        rtr_groups=[("GRP_COMMIT", "STAGE_CD = 'COMMIT'"), ("GRP_FORECAST", "STAGE_CD IN ('PIPELINE', 'BEST_CASE')")],
        lkp_cond="IN_OPPORTUNITY_ID = OPPORTUNITY_ID",
        ups_expr="IIF(STAGE_CD = 'COMMIT', DD_INSERT, DD_UPDATE)"),
    ["pipeline_snapshot", "opp_activity_enrichment", "stage_pipeline_totals",
     "probability_running_weight", "commit_forecast_split", "opp_stage_upsert",
     "top_opps_by_deal", "stage_unpivot_pipeline", "prob_ratio_by_stage",
     "mapplet_weighted_math", "stalled_opp_feed", "account_rollup", "consolidated_daily_load"]))

DOMAINS.append(dom("compliance_aml", "MIGRATION_COMPLIANCE_AML",
    src("SRC_TXN_ALERTS", "Transaction Alerts", "ORA_CML", [
        ("ALERT_ID", V, 30, 0, "PRIMARY KEY", "NOTNULL"), ("CUSTOMER_ID", V, 50, 0, "FOREIGN KEY", "NOTNULL"),
        ("TXN_ID", V, 30, 0, "NOT A KEY", "NOTNULL"), ("ALERT_TYPE", V, 20, 0, "NOT A KEY", "NOTNULL"),
        ("SEVERITY", V, 10, 0, "NOT A KEY", "NOTNULL"), ("ALERT_AMT", D, 18, 2, "NOT A KEY", "NULL"),
        ("ALERT_DT", DT, 19, 0, "NOT A KEY", "NULL")]),
    src("SRC_KYC_CUSTOMERS", "KYC Customer Profiles", "ORA_CML", [
        ("CUSTOMER_ID", V, 50, 0, "PRIMARY KEY", "NOTNULL"), ("KYC_STATUS", V, 10, 0, "NOT A KEY", "NOTNULL"),
        ("RISK_RATING", V, 10, 0, "NOT A KEY", "NOTNULL"), ("COUNTRY_ISO", V, 10, 0, "NOT A KEY", "NULL")]),
    flavor(
        dim="CUSTOMER_ID || '-' || ALERT_TYPE",
        attr="'SEV=' || SEVERITY || ':ALERTED=' || TO_CHAR(ALERT_DT, 'YYYY-MM-DD')",
        filter_cond="SEVERITY IN ('HIGH', 'CRITICAL') AND ALERT_DT >= ADD_TO_DATE(SESSSTARTTIME, 'DD', -30)",
        rtr_groups=[("GRP_CRITICAL", "SEVERITY = 'CRITICAL'"), ("GRP_HIGH", "SEVERITY = 'HIGH'")],
        lkp_cond="IN_CUSTOMER_ID = CUSTOMER_ID",
        ups_expr="IIF(SEVERITY = 'CRITICAL', DD_INSERT, DD_UPDATE)"),
    ["alert_snapshot", "alert_kyc_enrichment", "customer_alert_totals",
     "severity_running_queue", "critical_high_split", "alert_kyc_upsert",
     "top_alerts_by_amount", "type_bucket_unpivot", "amount_ratio_by_rating",
     "mapplet_risk_math", "aged_alert_feed", "country_rollup", "consolidated_daily_load"]))

DOMAINS.append(dom("hr_payroll", "MIGRATION_HR_PAYROLL",
    src("SRC_PAYROLL_RUNS", "Payroll Runs", "MSSQL_HR", [
        ("RUN_ID", "varchar", 30, 0, "PRIMARY KEY", "NOTNULL"), ("EMP_ID", "varchar", 20, 0, "FOREIGN KEY", "NOTNULL"),
        ("GROSS_PAY", "number", 18, 2, "NOT A KEY", "NULL"), ("NET_PAY", "number", 18, 2, "NOT A KEY", "NULL"),
        ("PAY_DT", "datetime", 19, 0, "NOT A KEY", "NULL")]),
    src("SRC_EMP_MASTER", "Employee Master", "MSSQL_HR", [
        ("EMP_ID", "varchar", 20, 0, "PRIMARY KEY", "NOTNULL"), ("DEPT_CD", "varchar", 10, 0, "NOT A KEY", "NOTNULL"),
        ("GRADE_CD", "varchar", 10, 0, "NOT A KEY", "NOTNULL"), ("BASE_SALARY", "number", 18, 2, "NOT A KEY", "NULL"),
        ("HIRE_DT", "datetime", 19, 0, "NOT A KEY", "NULL")]),
    flavor(
        dim="EMP_ID || '-' || DEPT_LKP",
        m1="IIF(ISNULL(GROSS_PAY), 0, GROSS_PAY) - IIF(ISNULL(NET_PAY), 0, NET_PAY)",
        attr="'GRADED=' || GRADE_LKP || ':PAID=' || TO_CHAR(PAY_DT, 'YYYY-MM-DD')",
        join_type="Detail Outer Join",
        rtr_groups=[("GRP_EXEMPT", "GRADE_LKP IN ('E1', 'E2', 'E3')"), ("GRP_NONEXEMPT", "GRADE_LKP NOT IN ('E1', 'E2', 'E3')")],
        lkp_cond="IN_EMP_ID = EMP_ID",
        ups_expr="IIF(NET_PAY >= 0, DD_INSERT, DD_REJECT)"),
    ["payroll_snapshot", "payroll_dept_enrichment", "dept_payroll_totals",
     "deduction_running_delta", "exempt_nonexempt_split", "payroll_emp_upsert",
     "top_earners_by_gross", "period_unpivot_payroll", "deduction_ratio_by_dept",
     "mapplet_netpay_math", "anomaly_payroll_feed", "grade_rollup", "consolidated_daily_load"]))


# ---------------------------------------------------------------- pattern (mapping) builders

TGT_FIELDS = [("SUMMARY_KEY", "decimal", 15, 0), ("DIMENSION_1", "string", 100, 0),
              ("METRIC_PRIMARY", "decimal", 18, 4), ("METRIC_SECONDARY", "decimal", 18, 4),
              ("ATTRIBUTES_TEXT", "string", 1000, 0), ("PROCESSED_DT", "date/time", 29, 9)]
TGT_WIRE = [("O_KEY", "SUMMARY_KEY"), ("O_DIM", "DIMENSION_1"), ("O_M1", "METRIC_PRIMARY"),
            ("O_M2", "METRIC_SECONDARY"), ("O_ATTR", "ATTRIBUTES_TEXT"), ("O_DT", "PROCESSED_DT")]

LKP_DOMAINS = {"treasury_fx": ("RATE_LKP", True), "market_risk": ("CLOSE_PRICE_LKP", True),
               "hr_payroll": ("DEPT_LKP", False), "sales_pipeline": ("LASTACT_LKP", False)}

_IDENT = re.compile(r"\b[A-Z][A-Z0-9_]{1,}\b")
_SQLKW = {"IIF", "ISNULL", "UPPER", "TO_CHAR", "TO_DECIMAL", "TO_INTEGER", "TO_DATE", "SUBSTR",
          "TRUNC", "SESSSTARTTIME", "SYSDATE", "SUM", "COUNT", "AVG", "DECODE", "ADD_TO_DATE",
          "AND", "OR", "NOT", "IN", "THEN", "ELSE", "END", "NULL", "DD_INSERT", "DD_UPDATE",
          "DD_REJECT", "ROUND", "HASH"}


def ports_ok(expr: str, available: set) -> bool:
    """True when every port identifier the expression references exists upstream."""
    ids = {x for x in _IDENT.findall(expr) if x not in _SQLKW}
    return ids <= set(available)


def final_exp(name, pass_fields, bank, with_seq, has_lkp=False, lkp_return=None,
              ret_is_numeric=True, extra_locals=None, extra_outputs=None) -> ET.Element:
    """The terminal Expression: pass-through ports + v_* locals + O_* final outputs.
    Any flavor expression referencing a port this pattern does not carry falls back to a
    safe generic built from the ports that DO exist (keeps mappings import-valid)."""
    m, m2, kf = bank["measure"], bank["measure2"], bank["key_field"]
    local_names = {s["name"] for s in (extra_locals or [])}
    avail = {f.get("NAME") for f in pass_fields} | local_names
    if with_seq:
        avail.add("SEQ_NEXTVAL")
    if lkp_return:
        avail.add(lkp_return)

    def base_port(*candidates):
        for c in candidates:
            if c in avail:
                return c
        return sorted(avail)[0]

    bp1, bp2 = base_port(m, kf), base_port(m2, m, kf)
    m1 = bank["m1"] if ports_ok(bank["m1"], avail) else f"IIF(ISNULL({bp1}), 0, {bp1})"
    m2e = bank["m2"] if ports_ok(bank["m2"], avail) else f"IIF(ISNULL({bp2}), 0, {bp2})"
    if lkp_return and ret_is_numeric:
        m2e = f"IIF(ISNULL({lkp_return}), 0, {lkp_return})"
    dim = bank["dim"] if ports_ok(bank["dim"], avail) else f"UPPER({kf if kf in avail else min(avail)})"
    attr_e = bank["attr"] if ports_ok(bank["attr"], avail) else f"'GROUP=' || {kf if kf in avail else min(avail)}"
    key_out = "IIF(SEQ_NEXTVAL > 0, SEQ_NEXTVAL, 0)" if with_seq else bank["key_derive"]
    if not ports_ok(key_out, avail):
        key_out = f"TO_DECIMAL(SUBSTR({kf}, 2, 9))" if kf in avail else "IIF(v_VALID = 1, 1, 0)"
    locals_ = [dict(name="v_VALID", dtype="integer", prec=10, scale=0,
                    expr=f"IIF(ISNULL({kf}), 0, 1)" if kf in avail else "1")]
    if extra_locals:
        locals_ = extra_locals + locals_
    outputs = [dict(name="O_KEY", dtype="decimal", prec=15, scale=0, expr=key_out),
               dict(name="O_DIM", dtype="string", prec=100, scale=0, expr=dim),
               dict(name="O_M1", dtype="decimal", prec=18, scale=4, expr="v_M1"),
               dict(name="O_M2", dtype="decimal", prec=18, scale=4, expr="v_M2"),
               dict(name="O_ATTR", dtype="string", prec=1000, scale=0, expr=attr_e),
               dict(name="O_DT", dtype="date/time", prec=29, scale=9, expr="SESSSTARTTIME")]
    if extra_outputs:
        outputs = outputs + extra_outputs
    return build_expression(name, pass_fields, locals_, outputs)


def inst(name, ttype, kind="TRANSFORMATION", reusable=None) -> ET.Element:
    a = dict(NAME=name, TRANSFORMATION_NAME=name, TRANSFORMATION_TYPE=ttype, TYPE=kind)
    if reusable:
        a["REUSABLE"] = reusable
    return E("INSTANCE", **a)


def conn(from_i, from_t, from_f, to_i, to_t, to_f=None) -> ET.Element:
    return E("CONNECTOR", FROMFIELD=from_f, FROMINSTANCE=from_i, FROMINSTANCETYPE=from_t,
             TOFIELD=to_f or from_f, TOINSTANCE=to_i, TOINSTANCETYPE=to_t)


def mk_mapping(d: dict, i: int) -> ET.Element:
    """Dispatch: mapping i (1..12) -> pattern; story names come from the domain spec."""
    bank = mkbank(d["s1"], **d["flavor"])
    story = d["stories"][i - 1]
    s1, s2 = d["s1"], d["s2"]
    sq1_fields = tf_fields_for_source(s1)
    sq2_fields = tf_fields_for_source(s2)
    lkp_ret, ret_num = LKP_DOMAINS.get(d["key"], (None, True))
    has_lkp = lkp_ret is not None
    m, m2f, kf = bank["measure"], bank["measure2"], bank["key_field"]
    tfs, ins, conns = [], [], []

    def add_sq(sx, tag):
        sq_name = f"SQ_{tag}"
        tfs.append(build_sq(sq_name, sx))
        ins.append(inst(sx["name"], "Source Definition", kind="SOURCE"))
        ins.append(inst(sq_name, "Source Qualifier"))
        for f in tf_fields_for_source(sx):
            conns.append(conn(sx["name"], "Source Definition", f.get("NAME"), sq_name, "Source Qualifier"))
        return sq_name

    def add_target(tgt_name):
        ins.append(inst(tgt_name, "Target Definition", kind="TARGET"))
        return tgt_name

    tgt = f"TGT_{d['key'].upper()}_SUMMARY"
    add_target(tgt)

    # pattern id from mapping number
    pid = (i - 1) % 12 + 1

    if pid in (1, 11):  # SQ -> EXP(final) -> TGT  (1: with sequence, 11: derived key)
        sq = add_sq(s1, "SRC1")
        exp_name = "EXP_FINAL_DERIVE" if pid == 11 else "EXP_FINAL_ENRICH"
        pass_ports = [deepcopy(f) for f in sq1_fields]
        if pid == 1:
            pass_ports.append(fld("SEQ_NEXTVAL", "bigint", "INPUT/OUTPUT", 19, 0))
        tfs.append(final_exp(exp_name, pass_ports, bank, with_seq=(pid == 1)))
        ins.append(inst(exp_name, "Expression"))
        for f in sq1_fields:
            conns.append(conn(sq, "Source Qualifier", f.get("NAME"), exp_name, "Expression"))
        if pid == 1:
            seq_name = f"SEQ_{d['key'].upper()}_KEY"
            ins.append(inst(seq_name, "Sequence", reusable="YES"))
            conns.append(conn(seq_name, "Sequence", "NEXTVAL", exp_name, "Expression", to_f="SEQ_NEXTVAL"))
        # only O_* outputs are wired into the target (pass-through ports are not)
        for of, tf in TGT_WIRE:
            conns.append(conn(exp_name, "Expression", of, tgt, "Target Definition", to_f=tf))
        desc = f"Pattern {'P1 (sequence key)' if pid == 1 else 'P11 (derived key)'}: source -> final expression -> summary target. Story: {story}."

    elif pid in (2, 12):  # SQ1,SQ2 -> JNR -> (FIL) -> EXP -> TGT
        sq1 = add_sq(s1, "SRC1")
        sq2 = add_sq(s2, "SRC2")
        jnr = f"JNR_{d['key'][:4].upper()}"
        jk = bank["key_field"] if pid == 2 else next(f[0] for f in s2["fields"] if f[4] == "PRIMARY KEY")
        master_fields = [deepcopy(f) for f in sq2_fields]
        for mf in master_fields:
            mf.set("NAME", mf.get("NAME") + "_M")
            mf.set("PORTTYPE", mf.get("PORTTYPE") + "/MASTER")
        tfs.append(build_joiner(jnr, sq1_fields, master_fields, bank["join_type"],
                                f"{jk} = {jk}_M" if pid == 2 else f"{jk}_M = {jk}_M2" if False else f"{kf} = {jk}_M"))
        ins.append(inst(jnr, "Joiner"))
        for f in sq1_fields:
            conns.append(conn(sq1, "Source Qualifier", f.get("NAME"), jnr, "Joiner"))
        for mf in master_fields:
            conns.append(conn(sq2, "Source Qualifier", mf.get("NAME")[:-2], jnr, "Joiner", to_f=mf.get("NAME")))
        jnr_fields = [deepcopy(f) for f in sq1_fields] + [deepcopy(f) for f in master_fields]
        if pid == 2:
            fil = "FIL_VALID"
            tfs.append(build_filter(fil, jnr_fields, bank["filter_cond"]))
            ins.append(inst(fil, "Filter"))
            for f in jnr_fields:
                conns.append(conn(jnr, "Joiner", f.get("NAME"), fil, "Filter"))
            up_fields = [deepcopy(f) for f in jnr_fields]
            up_name, up_type = fil, "Filter"
        else:
            up_fields, up_name, up_type = jnr_fields, jnr, "Joiner"
        exp_name = "EXP_FINAL_ENRICH"
        tfs.append(final_exp(exp_name, up_fields, bank, with_seq=False, has_lkp=True))
        ins.append(inst(exp_name, "Expression"))
        for f in up_fields:
            conns.append(conn(up_name, up_type, f.get("NAME"), exp_name, "Expression"))
        for of, tf in TGT_WIRE:
            conns.append(conn(exp_name, "Expression", of, tgt, "Target Definition", to_f=tf))
        desc = f"Pattern {'P2 (join+filter+enrich)' if pid == 2 else 'P12 (join+enrich)'}: two sources joined on {kf}. Story: {story}."

    elif pid == 3:  # SQ -> AGG -> EXP -> TGT (rollup)
        sq = add_sq(s1, "SRC1")
        gname, gfield = "AGG_ROLLUP", next(f for f in sq1_fields if f.get("NAME") == kf)
        measure_field = next(f for f in sq1_fields if f.get("NAME") == m)
        aggs = [dict(name="O_TOTAL", dtype="decimal", prec=18, scale=4, expr=f"SUM({m})"),
                dict(name="O_CNT", dtype="integer", prec=10, scale=0, expr=f"COUNT({kf})"),
                dict(name="O_AVG", dtype="decimal", prec=18, scale=4, expr=f"AVG({m})")]
        tfs.append(build_aggregator(gname, [gfield], [measure_field], aggs))
        ins.append(inst(gname, "Aggregator"))
        conns.append(conn(sq, "Source Qualifier", kf, gname, "Aggregator"))
        conns.append(conn(sq, "Source Qualifier", m, gname, "Aggregator"))
        agg_outs = [deepcopy(gfield)] + [fld(a["name"], a["dtype"], "INPUT/OUTPUT", a["prec"], a["scale"]) for a in aggs]
        exp_name = "EXP_FINAL_ROLLUP"
        tfs.append(final_exp(exp_name, agg_outs, bank, with_seq=False))
        # O_KEY without seq: derived key from the group field
        ins.append(inst(exp_name, "Expression"))
        conns.append(conn(gname, "Aggregator", kf, exp_name, "Expression"))
        for a in aggs:
            conns.append(conn(gname, "Aggregator", a["name"], exp_name, "Expression"))
        for of, tf in TGT_WIRE:
            conns.append(conn(exp_name, "Expression", of, tgt, "Target Definition", to_f=tf))
        desc = f"Pattern P3 (rollup): group by {kf}, SUM/COUNT/AVG({m}). Story: {story}."

    elif pid == 4:  # SQ -> SRT -> EXP(stateful window emulation) -> TGT
        sq = add_sq(s1, "SRC1")
        srt = "SRT_BY_KEY_DATE"
        date_f = next((f[0] for f in s1["fields"] if f[1] in ("date", "datetime")), kf)
        tfs.append(build_sorter(srt, sq1_fields, [kf, date_f]))
        ins.append(inst(srt, "Sorter"))
        for f in sq1_fields:
            conns.append(conn(sq, "Source Qualifier", f.get("NAME"), srt, "Sorter"))
        exp_name = "EXP_STATEFUL_WINDOW_EMULATION"
        stateful = [
            dict(name="v_IS_SAME_KEY", dtype="integer", prec=10, scale=0,
                 expr=f"IIF({kf} = v_PREV_KEY, 1, 0)"),
            dict(name="v_SEQ_NUM", dtype="integer", prec=10, scale=0,
                 expr="IIF(v_IS_SAME_KEY = 1, v_SEQ_NUM + 1, 1)"),
            dict(name="v_RUNNING_TOTAL", dtype="decimal", prec=18, scale=4,
                 expr=f"IIF(v_IS_SAME_KEY = 1, v_RUNNING_TOTAL + {m}, {m})"),
            dict(name="v_DELTA_FROM_PREV", dtype="decimal", prec=18, scale=4,
                 expr=f"IIF(v_IS_SAME_KEY = 1, {m} - v_PREV_AMT, 0)"),
            dict(name="v_PREV_KEY", dtype="string", prec=50, scale=0, expr=kf),
            dict(name="v_PREV_AMT", dtype="decimal", prec=18, scale=4, expr=m)]
        extras = [dict(name="O_RUNNING_TOTAL", dtype="decimal", prec=18, scale=4, expr="v_RUNNING_TOTAL"),
                  dict(name="O_DELTA_FROM_PREV", dtype="decimal", prec=18, scale=4, expr="v_DELTA_FROM_PREV"),
                  dict(name="O_WINDOW_DESC", dtype="string", prec=1000, scale=0,
                       expr="'SEQ=' || TO_CHAR(v_SEQ_NUM)")]
        tfs.append(final_exp(exp_name, [deepcopy(f) for f in sq1_fields], bank, with_seq=False,
                             extra_locals=stateful, extra_outputs=extras))
        ins.append(inst(exp_name, "Expression"))
        for f in sq1_fields:
            conns.append(conn(srt, "Sorter", f.get("NAME"), exp_name, "Expression"))
        wire4 = [("O_KEY", "SUMMARY_KEY"), ("O_DIM", "DIMENSION_1"),
                 ("O_RUNNING_TOTAL", "METRIC_PRIMARY"), ("O_DELTA_FROM_PREV", "METRIC_SECONDARY"),
                 ("O_WINDOW_DESC", "ATTRIBUTES_TEXT"), ("O_DT", "PROCESSED_DT")]
        for of, tf in wire4:
            conns.append(conn(exp_name, "Expression", of, tgt, "Target Definition", to_f=tf))
        desc = (f"Pattern P4 (stateful window emulation): variables emulate LAG()/SUM() OVER "
                f"(PARTITION BY {kf} ORDER BY {date_f}). Story: {story}.")

    elif pid == 5:  # SQ -> RTR -> EXP(group1) -> TGT (+ group2 direct to TGT)
        sq = add_sq(s1, "SRC1")
        rtr = "RTR_SPLIT"
        _rg = bank["rtr_groups"]
        g1 = {"name": _rg[0][0], "condition": _rg[0][1]}
        g2 = {"name": _rg[1][0], "condition": _rg[1][1]}
        tfs.append(build_router(rtr, sq1_fields, [g1, g2]))
        ins.append(inst(rtr, "Router"))
        for f in sq1_fields:
            conns.append(conn(sq, "Source Qualifier", f.get("NAME"), rtr, "Router"))
        g1_fields = [fld(f.get("NAME") + "1", f.get("DATATYPE"), "INPUT",
                         f.get("PRECISION"), f.get("SCALE")) for f in sq1_fields]
        exp_name = "EXP_FINAL_GROUP1"
        tfs.append(final_exp(exp_name, g1_fields, bank, with_seq=False))
        ins.append(inst(exp_name, "Expression"))
        for gf in g1_fields:
            conns.append(conn(rtr, "Router", gf.get("NAME"), exp_name, "Expression",
                              to_f=gf.get("NAME")))
        for of, tf in TGT_WIRE:
            conns.append(conn(exp_name, "Expression", of, tgt, "Target Definition", to_f=tf))
        # group 2 feeds the target directly (a second pipeline into the same target)
        for j, f in enumerate(sq1_fields):
            if j >= len(TGT_WIRE):
                break
            conns.append(conn(rtr, "Router", f.get("NAME") + "2", tgt, "Target Definition",
                              to_f=TGT_WIRE[j][1]))
        desc = f"Pattern P5 (router split): groups {g1['name']} / {g2['name']}. Story: {story}."

    elif pid == 6:  # SQ -> LKP + SQ -> EXP -> UPS -> TGT
        sq = add_sq(s1, "SRC1")
        s2pk = next(f[0] for f in s2["fields"] if f[4] == "PRIMARY KEY")
        cond = bank["lkp_cond"] or f"IN_{s2pk} = {s2pk}"
        numerics = [f for f in s2["fields"] if f[1] == "number"]
        if d["key"] == "hr_payroll":
            ret_specs = [dict(name="DEPT_LKP", dtype="string", prec=10, scale=0),
                         dict(name="GRADE_LKP", dtype="string", prec=10, scale=0)]
        elif numerics:
            r = numerics[0]
            ret_specs = [dict(name=lkp_ret or r[0] + "_LKP", dtype="decimal", prec=r[2], scale=r[3])]
        else:
            ret_specs = [dict(name=lkp_ret or "LKP_VAL", dtype="string", prec=50, scale=0)]
        lkp = f"LKP_{s2['name']}"
        tfs.append(build_lookup(lkp, s2, sq1_fields, cond, ret_specs))
        ins.append(inst(lkp, "Lookup Procedure"))
        for f in sq1_fields:
            conns.append(conn(sq, "Source Qualifier", f.get("NAME"), lkp, "Lookup Procedure",
                              to_f="IN_" + f.get("NAME")))
        exp_ports = [deepcopy(f) for f in sq1_fields]
        for spec in ret_specs:
            exp_ports.append(fld(spec["name"], spec["dtype"], "INPUT/OUTPUT", spec["prec"], spec["scale"]))
        exp_name = "EXP_FINAL_ENRICH"
        tfs.append(final_exp(exp_name, exp_ports, bank, with_seq=False, has_lkp=True,
                             lkp_return=ret_specs[0]["name"],
                             ret_is_numeric=ret_specs[0]["dtype"] == "decimal"))
        ins.append(inst(exp_name, "Expression"))
        for f in sq1_fields:
            conns.append(conn(sq, "Source Qualifier", f.get("NAME"), exp_name, "Expression"))
        for spec in ret_specs:
            conns.append(conn(lkp, "Lookup Procedure", spec["name"], exp_name, "Expression"))
        ups_name = "UPD_UPSERT"
        ups_fields = [fld("O_KEY", "decimal", "INPUT/OUTPUT", 15, 0),
                      fld("O_DIM", "string", "INPUT/OUTPUT", 100, 0),
                      fld("O_M1", "decimal", "INPUT/OUTPUT", 18, 4),
                      fld("O_M2", "decimal", "INPUT/OUTPUT", 18, 4),
                      fld("O_ATTR", "string", "INPUT/OUTPUT", 1000, 0),
                      fld("O_DT", "date/time", "INPUT/OUTPUT", 29, 9)]
        tfs.append(build_update_strategy(ups_name, ups_fields, bank["ups_expr"]))
        ins.append(inst(ups_name, "Update Strategy"))
        tw = dict(TGT_WIRE)
        for f in ups_fields:
            conns.append(conn(exp_name, "Expression", f.get("NAME"), ups_name, "Update Strategy"))
            conns.append(conn(ups_name, "Update Strategy", f.get("NAME"), tgt,
                              "Target Definition", to_f=tw[f.get("NAME")]))
        desc = (f"Pattern P6 (lookup enrich + update strategy): lookup {s2['name']}, "
                f"{bank['ups_expr']}. Story: {story}.")

    elif pid == 7:  # SQ -> FIL -> RNK(top-N) -> EXP -> TGT
        sq = add_sq(s1, "SRC1")
        fil = "FIL_MEASURE"
        tfs.append(build_filter(fil, sq1_fields, bank["filter_cond"]))
        ins.append(inst(fil, "Filter"))
        for f in sq1_fields:
            conns.append(conn(sq, "Source Qualifier", f.get("NAME"), fil, "Filter"))
        rnk = "RNK_TOP_N"
        tfs.append(build_rank(rnk, sq1_fields, 100))
        ins.append(inst(rnk, "Rank"))
        for f in sq1_fields:
            conns.append(conn(fil, "Filter", f.get("NAME"), rnk, "Rank"))
        exp_ports = [deepcopy(f) for f in sq1_fields]
        exp_ports.append(fld("RANKINDEX", "integer", "INPUT/OUTPUT", 10, 0))
        exp_name = "EXP_FINAL_RANK"
        tfs.append(final_exp(exp_name, exp_ports, bank, with_seq=False))
        ins.append(inst(exp_name, "Expression"))
        for f in sq1_fields:
            conns.append(conn(rnk, "Rank", f.get("NAME"), exp_name, "Expression"))
        conns.append(conn(rnk, "Rank", "RANKINDEX", exp_name, "Expression"))
        wire7 = list(TGT_WIRE)
        wire7[3] = ("RANKINDEX", "METRIC_SECONDARY")
        for of, tf in wire7:
            conns.append(conn(exp_name, "Expression", of, tgt, "Target Definition", to_f=tf))
        desc = f"Pattern P7 (filter + top-N rank): rank on {m}, RANKINDEX carried as metric. Story: {story}."

    elif pid == 8:  # SQ -> NRM (unpivot) -> EXP -> TGT
        sq = add_sq(s1, "SRC1")
        dim_f = next((f[0] for f in s1["fields"] if f[1] in ("varchar2", "varchar") and f[4] != "PRIMARY KEY"), kf)
        dt_by_name = {f[0]: f for f in s1["fields"]}
        base = [(kf, SRC2TF[dt_by_name[kf][1]], dt_by_name[kf][2], 0),
                (dim_f, SRC2TF[dt_by_name[dim_f][1]], dt_by_name[dim_f][2], 0)]
        pivots = [dict(name=m, dtype="decimal", prec=18, scale=4, occurrences=2),
                  dict(name=m2f, dtype="decimal", prec=18, scale=4, occurrences=2)]
        nrm = "NRM_UNPIVOT"
        tfs.append(build_normalizer(nrm, base, pivots))
        ins.append(inst(nrm, "Normalizer"))
        conns.append(conn(sq, "Source Qualifier", kf, nrm, "Normalizer", to_f=kf + "_in"))
        conns.append(conn(sq, "Source Qualifier", dim_f, nrm, "Normalizer", to_f=dim_f + "_in"))
        conns.append(conn(sq, "Source Qualifier", m, nrm, "Normalizer", to_f=m + "_in1"))
        conns.append(conn(sq, "Source Qualifier", m2f, nrm, "Normalizer", to_f=m + "_in2"))
        conns.append(conn(sq, "Source Qualifier", m2f, nrm, "Normalizer", to_f=m2f + "_in1"))
        conns.append(conn(sq, "Source Qualifier", m, nrm, "Normalizer", to_f=m2f + "_in2"))
        exp_ports = [fld(kf, SRC2TF[dt_by_name[kf][1]], "INPUT/OUTPUT", dt_by_name[kf][2], 0),
                     fld(dim_f, SRC2TF[dt_by_name[dim_f][1]], "INPUT/OUTPUT", dt_by_name[dim_f][2], 0),
                     fld(m, "decimal", "INPUT/OUTPUT", 18, 4),
                     fld(m2f, "decimal", "INPUT/OUTPUT", 18, 4)]
        exp_name = "EXP_FINAL_UNPIVOT"
        tfs.append(final_exp(exp_name, exp_ports, bank, with_seq=False))
        ins.append(inst(exp_name, "Expression"))
        for n in (kf, dim_f, m, m2f):
            conns.append(conn(nrm, "Normalizer", n, exp_name, "Expression"))
        for of, tf in TGT_WIRE:
            conns.append(conn(exp_name, "Expression", of, tgt, "Target Definition", to_f=tf))
        desc = f"Pattern P8 (normalizer unpivot): pivots {m}/{m2f} x2 occurrences. Story: {story}."

    elif pid == 9:  # SQ1 -> AGG -> JNR(agg=detail, SQ2=master) -> EXP -> TGT
        sq1 = add_sq(s1, "SRC1")
        sq2 = add_sq(s2, "SRC2")
        s2pk = next(f[0] for f in s2["fields"] if f[4] == "PRIMARY KEY")
        s2fk = next((f[0] for f in s2["fields"] if f[4] == "FOREIGN KEY"), s2pk)
        g9 = s2fk if s2fk in {f[0] for f in s1["fields"]} else kf
        g9_field = next(f for f in sq1_fields if f.get("NAME") == g9)
        measure_field = next(f for f in sq1_fields if f.get("NAME") == m)
        aggs = [dict(name="O_TOTAL", dtype="decimal", prec=18, scale=4, expr=f"SUM({m})"),
                dict(name="O_CNT", dtype="integer", prec=10, scale=0, expr=f"COUNT({g9})")]
        agg = "AGG_BY_KEY"
        tfs.append(build_aggregator(agg, [g9_field], [measure_field], aggs))
        ins.append(inst(agg, "Aggregator"))
        conns.append(conn(sq1, "Source Qualifier", g9, agg, "Aggregator"))
        conns.append(conn(sq1, "Source Qualifier", m, agg, "Aggregator"))
        master_fields = [deepcopy(f) for f in sq2_fields]
        for mf in master_fields:
            mf.set("NAME", mf.get("NAME") + "_M")
            mf.set("PORTTYPE", mf.get("PORTTYPE") + "/MASTER")
        jnr = f"JNR_{d['key'][:4].upper()}_BACK"
        agg_detail = [deepcopy(g9_field)] + [fld(a["name"], a["dtype"], "INPUT/OUTPUT", a["prec"], a["scale"]) for a in aggs]
        tfs.append(build_joiner(jnr, agg_detail, master_fields, "Normal Join", f"{g9} = {s2fk}_M"))
        ins.append(inst(jnr, "Joiner"))
        conns.append(conn(agg, "Aggregator", g9, jnr, "Joiner"))
        for a in aggs:
            conns.append(conn(agg, "Aggregator", a["name"], jnr, "Joiner"))
        for mf in master_fields:
            conns.append(conn(sq2, "Source Qualifier", mf.get("NAME")[:-2], jnr, "Joiner", to_f=mf.get("NAME")))
        jnr_out = [fld(g9, g9_field.get("DATATYPE"), "INPUT/OUTPUT", g9_field.get("PRECISION"), 0)]
        jnr_out += [fld(a["name"], a["dtype"], "INPUT/OUTPUT", a["prec"], a["scale"]) for a in aggs]
        jnr_out += [deepcopy(f) for f in master_fields]
        exp_name = "EXP_FINAL_RATIO"
        tfs.append(final_exp(exp_name, jnr_out, bank, with_seq=False))
        ins.append(inst(exp_name, "Expression"))
        for f in jnr_out:
            conns.append(conn(jnr, "Joiner", f.get("NAME"), exp_name, "Expression"))
        for of, tf in TGT_WIRE:
            conns.append(conn(exp_name, "Expression", of, tgt, "Target Definition", to_f=tf))
        desc = f"Pattern P9 (ratio-to-total): aggregate by {g9}, join back to {s2['name']}. Story: {story}."

    else:  # pid == 10: SQ -> MPL(domain mapplet) -> EXP -> TGT
        sq = add_sq(s1, "SRC1")
        mpl = f"MPL_{d['key'].upper()}_CALC"
        ins.append(inst(mpl, "Mapplet", kind="MAPPLET"))
        dim_f = next((f[0] for f in s1["fields"] if f[1] in ("varchar2", "varchar") and f[4] != "PRIMARY KEY"), kf)
        conns.append(conn(sq, "Source Qualifier", m, mpl, "Mapplet", to_f="IN_M1"))
        conns.append(conn(sq, "Source Qualifier", m2f, mpl, "Mapplet", to_f="IN_M2"))
        conns.append(conn(sq, "Source Qualifier", dim_f, mpl, "Mapplet", to_f="IN_CODE"))
        mpl_outs = [fld("NET_VALUE", "decimal", "INPUT/OUTPUT", 18, 4),
                    fld("RATIO_VALUE", "decimal", "INPUT/OUTPUT", 10, 4),
                    fld("SEQ_NEXTVAL", "bigint", "INPUT/OUTPUT", 19, 0)]
        exp_name = "EXP_FINAL_MPLET"
        tfs.append(final_exp(exp_name, mpl_outs, bank, with_seq=True))
        ins.append(inst(exp_name, "Expression"))
        conns.append(conn(mpl, "Mapplet", "OUT_NET_VALUE", exp_name, "Expression", to_f="NET_VALUE"))
        conns.append(conn(mpl, "Mapplet", "OUT_RATIO_VALUE", exp_name, "Expression", to_f="RATIO_VALUE"))
        seq_name = f"SEQ_{d['key'].upper()}_KEY"
        ins.append(inst(seq_name, "Sequence", reusable="YES"))
        conns.append(conn(seq_name, "Sequence", "NEXTVAL", exp_name, "Expression", to_f="SEQ_NEXTVAL"))
        for of, tf in TGT_WIRE:
            conns.append(conn(exp_name, "Expression", of, tgt, "Target Definition", to_f=tf))
        desc = f"Pattern P10 (mapplet reuse): {mpl} computes domain math; EXP finalizes. Story: {story}."

    mapping = E("MAPPING", DESCRIPTION=desc, ISVALID="YES",
                NAME=f"m_{i:02d}_{PATTERNS[(i - 1) % len(PATTERNS)]}_{story}", OBJECTVERSION="1", VERSIONNUMBER="1")
    for t in tfs:
        mapping.append(t)
    for e in ins:
        mapping.append(e)
    for c in conns:
        mapping.append(c)
    return mapping


PATTERNS = ["SQ_EXP_ENRICH", "SQ_SQ_JNR_FIL_EXP", "AGG_EXP_ROLLUP", "SRT_EXP_WINDOW",
            "RTR_SPLIT_EXP", "LKP_EXP_UPS", "FIL_RNK_EXP", "NRM_EXP",
            "AGG_JNR_RATIO", "MPL_EXP", "SQ_EXP_DERIVE", "SQ_SQ_JNR_EXP"]


# ---------------------------------------------------------------- folder assembly

def build_source_el(s: dict) -> ET.Element:
    el = E("SOURCE", BUSINESSNAME=s["biz"], DATABASETYPE="Oracle", DBDNAME=s["dbd"],
           NAME=s["name"], OBJECTVERSION="1", VERSIONNUMBER="1")
    for i, (n, dt, p, sc, key, nullable) in enumerate(s["fields"], start=1):
        a = dict(DATATYPE=dt, FIELDNUMBER=i, FIELDTYPE="E", KEYTYPE=key, NAME=n,
                 NULLABLE=nullable, PRECISION=p, SCALE=sc)
        if key == "FOREIGN KEY":
            a["REFERENCEDDBD"] = s["dbd"]
            a["REFERENCEDTABLE"] = "SRC_" + n.rsplit("_", 1)[0]  # best-effort ref table
            a["REFERENCEDFIELD"] = n
        el.append(E("SOURCEFIELD", **a))
    return el


def build_target_el(key: str) -> ET.Element:
    el = E("TARGET", BUSINESSNAME=f"{key.replace('_', ' ').title()} Summary",
           DATABASETYPE="Oracle", NAME=f"TGT_{key.upper()}_SUMMARY",
           OBJECTVERSION="1", VERSIONNUMBER="1")
    specs = [("SUMMARY_KEY", "number", 15, 0, "PRIMARY KEY", "NOTNULL"),
             ("DIMENSION_1", "varchar2", 100, 0, "NOT A KEY", "NULL"),
             ("METRIC_PRIMARY", "number", 18, 4, "NOT A KEY", "NULL"),
             ("METRIC_SECONDARY", "number", 18, 4, "NOT A KEY", "NULL"),
             ("ATTRIBUTES_TEXT", "varchar2", 1000, 0, "NOT A KEY", "NULL"),
             ("PROCESSED_DT", "date", 19, 0, "NOT A KEY", "NULL")]
    for i, (n, dt, p, sc, key, nullable) in enumerate(specs, start=1):
        el.append(E("TARGETFIELD", DATATYPE=dt, FIELDNUMBER=i, KEYTYPE=key, NAME=n,
                    NULLABLE=nullable, PRECISION=p, SCALE=sc))
    return el


def build_mapplet_el(d: dict) -> ET.Element:
    bank = mkbank(d["s1"], **d["flavor"])
    mpl = E("MAPPLET", DESCRIPTION=f"Reusable domain math for {d['key']}",
            ISVALID="YES", NAME=f"MPL_{d['key'].upper()}_CALC", OBJECTVERSION="1", VERSIONNUMBER="1")
    tin = E("TRANSFORMATION", NAME="MPL_IN", TYPE="Input Transformation", REUSABLE="NO",
            OBJECTVERSION="1", VERSIONNUMBER="1")
    tin.append(fld("IN_M1", "decimal", "OUTPUT", 18, 4))
    tin.append(fld("IN_M2", "decimal", "OUTPUT", 18, 4))
    tin.append(fld("IN_CODE", "string", "OUTPUT", 50, 0))
    mex = E("TRANSFORMATION", NAME="EXP_MPL_MATH", TYPE="Expression", REUSABLE="NO",
            OBJECTVERSION="1", VERSIONNUMBER="1")
    mex.append(fld("IN_M1", "decimal", "INPUT", 18, 4))
    mex.append(fld("IN_M2", "decimal", "INPUT", 18, 4))
    mex.append(fld("IN_CODE", "string", "INPUT", 50, 0))
    mex.append(fld("v_NET", "decimal", "LOCAL VARIABLE", 18, 4, expression=bank["mpl_net"]))
    mex.append(fld("v_RATIO", "decimal", "LOCAL VARIABLE", 10, 4, expression=bank["mpl_ratio"]))
    mex.append(fld("O_NET_VALUE", "decimal", "OUTPUT", 18, 4, expression="v_NET"))
    mex.append(fld("O_RATIO_VALUE", "decimal", "OUTPUT", 10, 4, expression="v_RATIO"))
    tout = E("TRANSFORMATION", NAME="MPL_OUT", TYPE="Output Transformation", REUSABLE="NO",
             OBJECTVERSION="1", VERSIONNUMBER="1")
    tout.append(fld("OUT_NET_VALUE", "decimal", "INPUT", 18, 4))
    tout.append(fld("OUT_RATIO_VALUE", "decimal", "INPUT", 10, 4))
    for t in (tin, mex, tout):
        mpl.append(t)
    for nm, tt in [("MPL_IN", "Input Transformation"), ("EXP_MPL_MATH", "Expression"),
                   ("MPL_OUT", "Output Transformation")]:
        mpl.append(E("INSTANCE", NAME=nm, TRANSFORMATION_NAME=nm, TRANSFORMATION_TYPE=tt, TYPE="TRANSFORMATION"))
    for f in ("IN_M1", "IN_M2", "IN_CODE"):
        mpl.append(E("CONNECTOR", FROMFIELD=f, FROMINSTANCE="MPL_IN",
                     FROMINSTANCETYPE="Input Transformation", TOFIELD=f,
                     TOINSTANCE="EXP_MPL_MATH", TOINSTANCETYPE="Expression"))
    for of, ofo in [("O_NET_VALUE", "OUT_NET_VALUE"), ("O_RATIO_VALUE", "OUT_RATIO_VALUE")]:
        mpl.append(E("CONNECTOR", FROMFIELD=of, FROMINSTANCE="EXP_MPL_MATH",
                     FROMINSTANCETYPE="Expression", TOFIELD=ofo, TOINSTANCE="MPL_OUT",
                     TOINSTANCETYPE="Output Transformation"))
    return mpl


def build_workflow_shels(d: dict, mapping_names: list[str]) -> list[ET.Element]:
    """CONFIG + WORKLET + WORKFLOW (mirrors the original folder tail)."""
    cfg = E("CONFIG", NAME=f"cfg_default_{d['key']}", VERSIONNUMBER="1")
    for n, v in [("Commit Interval", "10000"), ("Commit Type", "Target"),
                 ("Commit On End Of File", "YES"), ("Rollback Transactions on Errors", "NO"),
                 ("Stop on errors", "1"), ("Override tracing", "None"),
                 ("Save session log by", "Session runs"), ("Save session log for these runs", "10")]:
        cfg.append(E("ATTRIBUTE", NAME=n, VALUE=v))

    wklt = E("WORKLET", DESCRIPTION=f"{d['key']} dimension and DQ prep", ISVALID="YES",
             NAME=f"wklt_{d['key'].upper()}_PREP", REUSABLE="NO", VERSIONNUMBER="1")
    wklt.append(E("TASK", DESCRIPTION="Start Task", NAME="Start", REUSABLE="NO",
                  TYPE="Start", VERSIONNUMBER="1"))
    cmd = E("TASK", DESCRIPTION="Archive Old Logs Command", NAME="cmd_ARCHIVE_OLD_LOGS",
            REUSABLE="NO", TYPE="Command", VERSIONNUMBER="1")
    cmd.append(E("ATTRIBUTE", NAME="Fail task if any command fails", VALUE="YES"))
    cmd.append(E("VALUEPAIR", EXECORDER="1", NAME="ArchiveCmd", REVERSEASSIGNMENT="NO",
                 VALUE="sh /opt/informatica/scripts/archive_logs.sh $$ENV_NAME"))
    wklt.append(cmd)
    s1 = mapping_names[0]
    sess = E("SESSION", DESCRIPTION=f"Run {s1}", ISVALID="YES", MAPPINGNAME=s1,
             NAME=f"s_{s1}", REUSABLE="NO", SORTORDER="Binary", VERSIONNUMBER="1")
    sess.append(E("CONFIGREFERENCE", REFOBJECTNAME=f"cfg_default_{d['key']}", TYPE="Session config"))
    wklt.append(sess)
    for tn, tt in [("Start", "Start"), ("cmd_ARCHIVE_OLD_LOGS", "Command"), (f"s_{s1}", "Session")]:
        wklt.append(E("TASKINSTANCE", DESCRIPTION=tt, FAIL_PARENT_IF_INSTANCE_DID_NOT_RUN="NO",
                      FAIL_PARENT_IF_INSTANCE_FAILS="YES", ISENABLED="YES", NAME=tn,
                      REUSABLE="NO", TASKNAME=tn, TASKTYPE=tt))
    wklt.append(E("WORKFLOWLINK", CONDITION="", FROMTASK="Start", TOTASK="cmd_ARCHIVE_OLD_LOGS"))
    wklt.append(E("WORKFLOWLINK", CONDITION="$cmd_ARCHIVE_OLD_LOGS.Status = SUCCEEDED",
                  FROMTASK="cmd_ARCHIVE_OLD_LOGS", TOTASK=f"s_{s1}"))
    return [cfg, wklt]  # the WORKFLOW is built inline in build_domain_tree


def build_workflow_el(d: dict, mapping_names: list[str]) -> ET.Element:
    wf = E("WORKFLOW", DESCRIPTION=f"Master migration workflow for {d['key']}", ISVALID="YES",
           NAME=f"wf_MASTER_{d['folder']}", REUSABLE="NO", VERSIONNUMBER="1")
    sch = E("SCHEDULER", DESCRIPTION="Daily Nightly Schedule", NAME="Scheduler",
            REUSABLE="NO", VERSIONNUMBER="1")
    sch.append(E("SCHEDULEINFO", SCHEDULETYPE="ONDEMAND"))
    wf.append(sch)
    wf.append(E("TASK", DESCRIPTION="Workflow Start", NAME="Start", REUSABLE="NO",
                TYPE="Start", VERSIONNUMBER="1"))
    asg = E("TASK", DESCRIPTION="Assign Workflow Timestamp Variables", NAME="asgn_SET_WF_VARS",
            REUSABLE="NO", TYPE="Assignment", VERSIONNUMBER="1")
    asg.append(E("VALUEPAIR", EXECORDER="1", NAME="$$WF_RUN_DATE", REVERSEASSIGNMENT="NO",
                 VALUE="TO_CHAR(SYSDATE, 'YYYY-MM-DD')"))
    wf.append(asg)
    dec = E("TASK", DESCRIPTION="Decision Gate on Row Counts", NAME="dec_CHECK_ROWS",
            REUSABLE="NO", TYPE="Decision", VERSIONNUMBER="1")
    dec.append(E("ATTRIBUTE", NAME="Decision Name",
                 VALUE=f"$s_{mapping_names[0]}.TgtSuccessRows > 0"))
    wf.append(dec)
    eml = E("TASK", DESCRIPTION="Failure Alert Email", NAME="eml_ON_FAILURE_ALERT",
            REUSABLE="NO", TYPE="Email", VERSIONNUMBER="1")
    eml.append(E("ATTRIBUTE", NAME="Email User Name", VALUE="data-engineering-alerts@example.com"))
    eml.append(E("ATTRIBUTE", NAME="Email Subject", VALUE=f"[ALERT] {d['folder']} workflow failed"))
    eml.append(E("ATTRIBUTE", NAME="Email Text", VALUE="Session failure detected."))
    wf.append(eml)
    tasks = [("Start", "Start"), ("asgn_SET_WF_VARS", "Assignment"),
             ("dec_CHECK_ROWS", "Decision"), ("eml_ON_FAILURE_ALERT", "Email")]
    for mn in mapping_names[:3]:
        s = E("SESSION", DESCRIPTION=f"Session for {mn}", ISVALID="YES", MAPPINGNAME=mn,
              NAME=f"s_{mn}", REUSABLE="NO", SORTORDER="Binary", VERSIONNUMBER="1")
        s.append(E("CONFIGREFERENCE", REFOBJECTNAME=f"cfg_default_{d['key']}", TYPE="Session config"))
        wf.append(s)
        tasks.append((f"s_{mn}", "Session"))
    for tn, tt in tasks:
        wf.append(E("TASKINSTANCE", DESCRIPTION=tt, FAIL_PARENT_IF_INSTANCE_DID_NOT_RUN="NO",
                    FAIL_PARENT_IF_INSTANCE_FAILS="YES", ISENABLED="YES", NAME=tn,
                    REUSABLE="NO", TASKNAME=tn, TASKTYPE=tt))
    wf.append(E("WORKFLOWLINK", CONDITION="", FROMTASK="Start", TOTASK="asgn_SET_WF_VARS"))
    wf.append(E("WORKFLOWLINK", CONDITION="$asgn_SET_WF_VARS.Status = SUCCEEDED",
                FROMTASK="asgn_SET_WF_VARS", TOTASK=f"s_{mapping_names[0]}"))
    wf.append(E("WORKFLOWLINK", CONDITION="$s_" + mapping_names[0] + ".Status = SUCCEEDED",
                FROMTASK=f"s_{mapping_names[0]}", TOTASK="dec_CHECK_ROWS"))
    wf.append(E("WORKFLOWLINK", CONDITION="$dec_CHECK_ROWS.ConditionResult = FALSE",
                FROMTASK="dec_CHECK_ROWS", TOTASK="eml_ON_FAILURE_ALERT"))
    for vn, dv in [("$$WF_RUN_DATE", ""), ("$$ENV_NAME", "PROD")]:
        wf.append(E("WORKFLOWVARIABLE", DATATYPE="string", DEFAULTVALUE=dv,
                    DESCRIPTION="Workflow variable", ISNULL="NO", ISPERSISTENT="NO",
                    NAME=vn, USERDEFINED="YES"))
    return wf


def build_domain_tree(d: dict) -> ET.Element:
    root = E("POWERMART", CREATION_DATE="10/14/2026 13:30:00", REPOSITORY_VERSION="10.4")
    repo = E("REPOSITORY", NAME="REP_DEV", VERSION="181", CODEPAGE="UTF-8", DATABASETYPE="Oracle")
    root.append(repo)
    folder = E("FOLDER", NAME=d["folder"], GROUP="", OWNER="Administrator", SHARED="NOTSHARED",
               DESCRIPTION=f"Synthetic migration corpus for {d['key']}",
               PERMISSIONS="rwxr-x", UUID=f"0000{abs(hash(d['key'])) % 10**12:012d}")
    repo.append(folder)
    folder.append(build_source_el(d["s1"]))
    folder.append(build_source_el(d["s2"]))
    folder.append(build_target_el(d["key"]))
    folder.append(build_sequence(f"SEQ_{d['key'].upper()}_KEY", reusable="YES"))
    folder.append(build_mapplet_el(d))
    mapping_names = []
    for i in range(1, 14):
        m = mk_mapping(d, i)
        folder.append(m)
        mapping_names.append(m.get("NAME"))
    for el in (*build_workflow_shels(d, mapping_names), build_workflow_el(d, mapping_names)):
        folder.append(el)
    return root


# ---------------------------------------------------------------- main + validation

def lint_tree(root: ET.Element, fname: str) -> list[str]:
    problems = []
    folder = root.find("./REPOSITORY/FOLDER")
    ports: dict[str, set] = {}
    for s in folder.findall("SOURCE"):
        ports[s.get("NAME")] = {f.get("NAME") for f in s.findall("SOURCEFIELD")}
    for t in folder.findall("TARGET"):
        ports[t.get("NAME")] = {f.get("NAME") for f in t.findall("TARGETFIELD")}
    for t in folder.findall("TRANSFORMATION"):
        ports[t.get("NAME")] = {f.get("NAME") for f in t.findall("TRANSFORMFIELD")}
    mapplet_ports = {}
    for mp in folder.findall("MAPPLET"):
        mapplet_ports[mp.get("NAME")] = {
            f.get("NAME") for t in mp.findall("TRANSFORMATION") for f in t.findall("TRANSFORMFIELD")}
    for m in folder.findall("MAPPING"):
        local_ports = dict(ports)
        for t in m.findall("TRANSFORMATION"):
            local_ports[t.get("NAME")] = {f.get("NAME") for f in t.findall("TRANSFORMFIELD")}
        mpl_inst = next((e for e in m.findall("INSTANCE") if e.get("TYPE") == "MAPPLET"), None)
        if mpl_inst is not None:
            local_ports[mpl_inst.get("NAME")] = mapplet_ports[mpl_inst.get("TRANSFORMATION_NAME")]
        for e in m.findall("INSTANCE"):
            nm = e.get("NAME")
            if nm not in local_ports:
                problems.append(f"{fname}:{m.get('NAME')}: instance {nm} has no port definitions")
        for c in m.findall("CONNECTOR"):
            fi, ti = c.get("FROMINSTANCE"), c.get("TOINSTANCE")
            if fi not in local_ports or c.get("FROMFIELD") not in local_ports[fi]:
                problems.append(f"{fname}:{m.get('NAME')}: FROM {fi}.{c.get('FROMFIELD')} unresolved")
            if ti not in local_ports or c.get("TOFIELD") not in local_ports[ti]:
                problems.append(f"{fname}:{m.get('NAME')}: TO {ti}.{c.get('TOFIELD')} unresolved")
    return problems


def main() -> None:
    total_maps = 0
    all_problems = []
    summary = []
    for d in DOMAINS:
        fname = f"informatica_powermart_{d['key']}.xml"
        tree = build_domain_tree(d)
        ET.indent(tree, space="    ")
        path = HERE / fname
        path.write_bytes(ET.tostring(tree, encoding="utf-8", xml_declaration=True))
        back = ET.parse(path).getroot()  # parse-back: well-formedness check
        problems = lint_tree(back, fname)
        all_problems += problems
        n_maps = len(back.findall("./REPOSITORY/FOLDER/MAPPING"))
        n_tfs = len(back.findall(".//TRANSFORMATION"))
        total_maps += n_maps
        summary.append((fname, n_maps, n_tfs, len(problems)))
    print(f"{'file':48s} {'mappings':>8s} {'transforms':>10s} {'lint':>6s}")
    for fn, nm, nt, np_ in summary:
        print(f"{fn:48s} {nm:8d} {nt:10d} {np_:6d}")
    print(f"\nTOTAL mappings: {total_maps} (target: >100)")
    if all_problems:
        print(f"\nLINT PROBLEMS ({len(all_problems)}):")
        for p in all_problems[:15]:
            print("  -", p)
    else:
        print("LINT: all connectors resolve; all instances have port definitions")


if __name__ == "__main__":
    main()














