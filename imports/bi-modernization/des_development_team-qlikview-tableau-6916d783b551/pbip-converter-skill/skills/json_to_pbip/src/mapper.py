"""
mapper.py — Map intermediate.json → mapped.json using AutoGen Core + gpt-5-mini.

Four AutoGen agents:
  1. DaxConverterAgent   — converts raw calc expressions → valid DAX
  2. VisualMapperAgent   — maps unknown visual types → PBIP visualType strings
  3. TypeInferenceAgent  — infers Power BI data types from column metadata
  4. RelationshipAgent   — enriches/validates relationships

Results are collected, merged, and written to mapped.json.
"""
import asyncio, json, os, re, sys, argparse
from dataclasses import dataclass
from pathlib import Path

try:
    from skills.json_to_pbip.src import debug_collector as _dbg
except ImportError:
    _dbg = None

# ── DAX post-processing ───────────────────────────────────────────────────────
_BARE_COL_RE   = re.compile(r"('[^']+')\[([^\]]+)\]")
_DOUBLE_SUM_RE = re.compile(r"\bSUM\(SUM\(('[^']+'\[[^\]]+\])\)\)", re.IGNORECASE)
_AGG_PREFIX_RE = re.compile(r"(\w+)\s*\(\s*$")
# Match SUM('Table'[Column]) so we can detect cases where the LLM (or our own
# bare-ref wrapper) sums a text/date column. Power BI rejects `SUM(text)` at
# query time, and the writer's column-typing heuristic also treats this as
# evidence the column is numeric and rewrites its TMDL dataType to `double` —
# both wrong when the underlying CSV holds text. We rewrite to SELECTEDVALUE
# so the measure stays syntactically valid and the column keeps its real type.
_SUM_TABLECOL_RE = re.compile(r"\bSUM\(\s*'([^']+)'\[([^\]]+)\]\s*\)", re.IGNORECASE)
_TEXT_DTYPES_FOR_SUM_DEMOTE = {"string", "datetime", "date", "time", "boolean"}

# DAX functions where a bare Table[Column] argument is ALREADY valid and must
# NOT be wrapped in SUM() — wrapping produces invalid DAX (e.g. MAX(SUM(col))
# is rejected) or silently breaks semantics (SUM inside SELECTCOLUMNS ignores
# row context and returns the grand total for every row).
#
# Two groups:
#   * aggregation / scalar functions that take a column directly;
#   * table & row-context functions (FILTER, SELECTCOLUMNS, ADDCOLUMNS, set
#     operators, …) — these establish a row context in which a naked column
#     reference is the correct, intended form. The earlier omission of these
#     corrupted any LLM-authored measure that built an intermediate table
#     (e.g. a CORR/correlation measure using ADDCOLUMNS over an invoice set).
_AGG_FUNCS = {
    "SUM", "MIN", "MAX", "AVERAGE", "AVG",
    "COUNT", "COUNTA", "COUNTROWS", "COUNTBLANK", "DISTINCTCOUNT",
    "MEDIAN", "STDEV", "STDEVX", "VAR", "VARX",
    "GEOMEAN", "PRODUCT", "FIRSTNONBLANK", "LASTNONBLANK",
    "VALUES", "DISTINCT", "ALL", "ALLEXCEPT", "ALLSELECTED",
    "RELATED", "RELATEDTABLE", "USERELATIONSHIP",
    "MINX", "MAXX", "SUMX", "AVERAGEX", "COUNTX", "COUNTAX",
    # table / row-context functions — bare column refs inside these are valid
    "FILTER", "SELECTCOLUMNS", "ADDCOLUMNS", "SUMMARIZE", "SUMMARIZECOLUMNS",
    "GROUPBY", "INTERSECT", "UNION", "EXCEPT", "NATURALINNERJOIN",
    "NATURALLEFTOUTERJOIN", "CROSSJOIN", "GENERATE", "GENERATEALL",
    "CALCULATETABLE", "TOPN", "TREATAS", "ROW", "RANKX",
}


def _demote_sum_on_text(expr: str, col_dtype: dict) -> str:
    """Rewrite `SUM('T'[c])` → `SELECTEDVALUE('T'[c])` when c is non-numeric.

    The DAX-converter LLM sometimes translates Tableau row-level text logic
    like `IF [Description]="X" THEN "Y" ELSE [Description] END` into
    `IF(SUM('tbl'[Description]) = "X", ...)`. SUM on a text column is invalid
    DAX (the comparison `<number> = "X"` is always false) AND it convinces
    the writer's _is_summed_string heuristic that the column is numeric, so
    it rewrites the TMDL dataType to `double` and the M cast to `type
    number` — which then fails on real text data. Replacing with
    SELECTEDVALUE preserves the author's row-level intent in a measure
    context and stops the type-promotion cascade.
    """
    if not expr or not col_dtype:
        return expr

    def _sub(m: re.Match) -> str:
        tbl, col = m.group(1), m.group(2)
        dt = (col_dtype.get((tbl, col)) or "").lower()
        if dt in _TEXT_DTYPES_FOR_SUM_DEMOTE:
            return f"SELECTEDVALUE('{tbl}'[{col}])"
        return m.group(0)

    return _SUM_TABLECOL_RE.sub(_sub, expr)


def _enclosing_func_name(expr: str, pos: int) -> str | None:
    """Return the upper-case name of the function whose argument list directly
    contains `pos`, or None if `pos` is at top level. Walks backward tracking
    parenthesis depth so a column sitting in the 2nd+ argument of a call is
    correctly attributed to the OUTER function name (e.g. for
    `ALLEXCEPT('t', 't'[c])`, the column at the second-arg position resolves
    to `ALLEXCEPT`, not to `(` immediately before it). The previous "look at
    immediate prefix" check only saw `,` and concluded the column was bare,
    which broke ALLEXCEPT/ALL/USERELATIONSHIP/iterator-second-arg cases."""
    depth = 0
    i = pos - 1
    while i >= 0:
        c = expr[i]
        if c == ')':
            depth += 1
        elif c == '(':
            if depth == 0:
                j = i - 1
                while j >= 0 and expr[j] in ' \t\r\n':
                    j -= 1
                end = j + 1
                while j >= 0 and (expr[j].isalnum() or expr[j] == '_'):
                    j -= 1
                name = expr[j + 1:end]
                return name.upper() if name else None
            depth -= 1
        i -= 1
    return None


def _fix_bare_column_refs(expr: str) -> str:
    """Wrap bare Table[Column] refs in SUM(), but skip refs that are already
    sitting anywhere inside an aggregation/scalar function call (MAX, MIN,
    AVERAGE, ALLEXCEPT, SUMX, …). Also collapses any leftover SUM(SUM(...))
    as a safety net.
    """
    if not expr:
        return expr

    def _maybe_wrap(m: re.Match) -> str:
        fn = _enclosing_func_name(expr, m.start())
        if fn in _AGG_FUNCS:
            return m.group(0)
        return f"SUM({m.group(1)}[{m.group(2)}])"

    wrapped = _BARE_COL_RE.sub(_maybe_wrap, expr)
    while _DOUBLE_SUM_RE.search(wrapped):
        wrapped = _DOUBLE_SUM_RE.sub(lambda m: f"SUM({m.group(1)})", wrapped)
    return wrapped


# A DAX measure reference is always bare `[Name]` — never table-qualified and
# never nested. The LLM mis-emits both forms when the input's
# `depends_on_measures` carries a path form (e.g. a Tableau parameter
# reference `[Parameters].[What if Quantity]`):
#   [Parameters].[What if Quantity]   →  invalid `[T].[M]`
#   [Parameters.[What if Quantity]]   →  invalid nested `[T.[M]]`
# Both are syntax errors that produce #ERROR in Power BI and cascade to every
# dependent measure. `[T].[M]` and `[T.[M]]` are never valid DAX, so collapsing
# them to the bare `[M]` measure reference is always safe.
_MEASURE_NEST_RE = re.compile(r"\[[^\[\]]*\.\[([^\[\]]+)\]\]")   # [T.[M]]
_MEASURE_PATH_RE = re.compile(r"\[[^\[\]]+\]\.\[([^\[\]]+)\]")   # [T].[M]


def _fix_measure_path_refs(expr: str) -> str:
    """Collapse table-qualified / nested measure references to bare `[Name]`."""
    if not expr:
        return expr
    prev = None
    while prev != expr:
        prev = expr
        expr = _MEASURE_NEST_RE.sub(r"[\1]", expr)
        expr = _MEASURE_PATH_RE.sub(r"[\1]", expr)
    return expr

# Add pbip-converter-skill root to path so config.py is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from autogen_core import (
    RoutedAgent, SingleThreadedAgentRuntime, TopicId,
    MessageContext, message_handler, type_subscription,
    ClosureAgent, ClosureContext,
)
from autogen_core.models import SystemMessage, UserMessage
from autogen_core._default_subscription import DefaultSubscription
from autogen_core._default_topic import DefaultTopicId

from config import azure_client as _azure_client

# ── Hardcoded visual type map (no LLM needed for these) ──────────────────────
_VISUAL_MAP = {
    # Horizontal bar charts. `barChart` is PBIP's native visualType for
    # horizontal stacked bars. Previously remapped to clusteredColumnChart,
    # which flipped orientation (the bar became a vertical column) and
    # broke any source visual whose author chose horizontal bars.
    "bar": "barChart", "bar_chart": "barChart", "barchart": "barChart",
    "stacked_bar": "barChart", "stacked_bar_chart": "barChart",
    "clustered_bar": "clusteredBarChart", "clustered_bar_chart": "clusteredBarChart",
    "line": "lineChart", "line_chart": "lineChart",
    # Area chart spellings. Without these variants the mapper falls through
    # to the LLM agent which sometimes returns `lineChart`/`columnChart`
    # instead, and the visual renders with the wrong shape (or blank when
    # the result isn't a valid PBI visualType). Catch every common form.
    "area": "areaChart", "area_chart": "areaChart", "areachart": "areaChart",
    "stacked_area": "stackedAreaChart", "stacked_area_chart": "stackedAreaChart",
    "pie": "pieChart",
    "scatter": "scatterChart",
    "map": "map", "filled_map": "filledMap",
    "table": "tableEx", "text": "tableEx", "crosstab": "tableEx",
    "textbox": "textbox",
    "blank": "textbox",
    "slicer": "slicerVisual",
    "card": "card",
    "kpi": "kpi",
    # `kpi_card` is the Tableau RE alias for a single-scalar "BAN" tile,
    # which is a PBI `card` — NOT a PBI `kpi`. The `kpi` visualType needs
    # an Indicator + TrendLine pair to render; BANs only provide the
    # value, so PBI's KPI engine shows the title chrome with no figure.
    # `card` takes a single Values slot which is exactly what BANs carry.
    "kpi_card": "card", "kpicard": "card", "kpi-card": "card", "kpiCard": "card",
    "matrix": "pivotTable",
    "column": "columnChart", "column_chart": "columnChart",
    "stacked_column": "columnChart", "stacked_column_chart": "columnChart",
    "clustered_column": "clusteredColumnChart", "clustered_column_chart": "clusteredColumnChart",
    "treemap": "treemap",
    "waterfall": "waterfallChart",
    "funnel": "funnel",
    "gauge": "gauge",
    "donut": "donutChart",
    "ribbon": "ribbonChart",
}

# ── Message types ─────────────────────────────────────────────────────────────
@dataclass
class DaxRequest:
    measure_name: str
    expression_raw: str
    depends_on_columns: str    # JSON-encoded list from calc.depends_on_columns
    depends_on_measures: str   # JSON-encoded list from calc.depends_on_measures

@dataclass
class VisualRequest:
    visual_id: str
    raw_type: str
    fields: str          # JSON string of field list

@dataclass
class TypeRequest:
    col_name: str
    data_type: str
    description: str

@dataclass
class AgentResult:
    task: str            # "dax" | "visual" | "type"
    key: str             # measure_name | visual_id | col_name
    value: str           # converted expression / visualType / dataType

# ── Result queue ──────────────────────────────────────────────────────────────
_result_queue: asyncio.Queue[AgentResult] = asyncio.Queue()


async def _collect(_agent: ClosureContext, message: AgentResult, _ctx: MessageContext) -> None:
    await _result_queue.put(message)


# ── DAX Converter Agent ───────────────────────────────────────────────────────
@type_subscription(topic_type="DaxConverterAgent")
class DaxConverterAgent(RoutedAgent):
    def __init__(self):
        super().__init__("DAX Converter Agent")

    @message_handler
    async def handle(self, message: DaxRequest, ctx: MessageContext) -> None:
        system = """You translate Tableau calculations to Power BI DAX.
Return ONLY the DAX expression. No explanation, no backticks, no comments.

SYNTAX RULES:
- Column reference:  'TableName'[ColumnName]   (single-quote the table)
- Measure reference: [MeasureName]             (no table prefix)
- Division:          DIVIDE(a, b, 0)           (never use /)
- String concat:     a & b                     (never use + for strings)
- Logical:           && for AND, || for OR, NOT for !

TABLEAU -> DAX FUNCTION MAP:
  SUM([x])           -> SUM('T'[x])
  AVG([x])           -> AVERAGE('T'[x])
  MIN([x])           -> MIN('T'[x])
  MAX([x])           -> MAX('T'[x])
  COUNT([x])         -> COUNTA('T'[x])
  COUNTD([x])        -> DISTINCTCOUNT('T'[x])
  MEDIAN([x])        -> MEDIAN('T'[x])
  STDEV([x])         -> STDEV.S('T'[x])
  VAR([x])           -> VAR.S('T'[x])
  ATTR([x])          -> SELECTEDVALUE('T'[x])

  IIF(c, a, b)       -> IF(c, a, b)
  IFNULL(a, b)       -> COALESCE(a, b)
  ISNULL([x])        -> ISBLANK('T'[x])
  ZN([x])            -> IFERROR('T'[x], 0)
  NULL               -> BLANK()

  LEN, LEFT, RIGHT, MID, UPPER, LOWER, TRIM, REPLACE  -> same name
  CONTAINS([x], "y") -> SEARCH("y", 'T'[x], 1, 0) > 0
  STR([x])           -> 'T'[x] & ""
  INT([x])           -> INT('T'[x])
  FLOAT([x])         -> VALUE('T'[x])

  TODAY()            -> TODAY()
  NOW()              -> NOW()
  DATEPART('year',  [d]) -> YEAR('T'[d])
  DATEPART('month', [d]) -> MONTH('T'[d])
  DATEPART('day',   [d]) -> DAY('T'[d])
  DATEPART('quarter',[d])-> QUARTER('T'[d])
  DATEPART('week',  [d]) -> WEEKNUM('T'[d])
  DATEDIFF('day', a, b)  -> DATEDIFF(a, b, DAY)
  DATEDIFF('month', a,b) -> DATEDIFF(a, b, MONTH)
  DATEDIFF('year',  a,b) -> DATEDIFF(a, b, YEAR)
  DATEADD('year', n, [d])-> EDATE('T'[d], n*12)
  DATETRUNC('month',[d]) -> EOMONTH('T'[d], -1) + 1
  MAKEDATE(y, m, d)      -> DATE(y, m, d)

  ABS, ROUND, CEILING, FLOOR, EXP, LOG, POWER, SQRT -> same name

LOD EXPRESSIONS:
  {FIXED [dim] : agg([m])}    -> CALCULATE(agg('T'[m]), ALLEXCEPT('T', 'T'[dim]))
  {INCLUDE [dim] : agg([m])}  -> CALCULATE(agg('T'[m]), VALUES('T'[dim]))
  {EXCLUDE [dim] : agg([m])}  -> CALCULATE(agg('T'[m]), ALL('T'[dim]))
  {FIXED : agg([m])}          -> CALCULATE(agg('T'[m]), ALL('T'))

TABLE CALCULATIONS:
  WINDOW_SUM(SUM([m]))    -> CALCULATE(SUM('T'[m]), ALLSELECTED('T'))
  RUNNING_SUM(SUM([m]))   -> CALCULATE(SUM('T'[m]),
                              FILTER(ALL('T'[orderby]),
                                     'T'[orderby] <= MAX('T'[orderby])))
  RANK(agg(...))          -> RANKX(ALL('T'), agg('T'[col]), , DESC, Skip)
  RANK_DENSE(...)         -> RANKX(..., , DESC, Dense)
  PERCENT_OF_TOTAL(SUM([m])) -> DIVIDE(SUM('T'[m]), CALCULATE(SUM('T'[m]), ALLSELECTED('T')))

CORRELATION (Pearson):
  Tableau CORR has no DAX builtin. For a correlation of two per-key aggregates
  — e.g. CORR({INCLUDE [k]:SUM([a])}, {INCLUDE [k]:SUM([b])}) where a and b may
  live on DIFFERENT tables Ta and Tb joined on key k — emit this exact shape:
    VAR _keys = INTERSECT(VALUES('Ta'[k]), VALUES('Tb'[k]))
    VAR _data = ADDCOLUMNS(_keys,
        "x", CALCULATE(SUM('Ta'[a])),
        "y", CALCULATE(SUM('Tb'[b])))
    VAR _ax = AVERAGEX(_data, [x])
    VAR _ay = AVERAGEX(_data, [y])
    VAR _cov = SUMX(_data, ([x] - _ax) * ([y] - _ay))
    VAR _sx  = SUMX(_data, ([x] - _ax) ^ 2)
    VAR _sy  = SUMX(_data, ([y] - _ay) ^ 2)
    RETURN DIVIDE(_cov, SQRT(_sx * _sy), 0)
  Keep the column refs inside ADDCOLUMNS/SUMX bare (no extra SUM wrapping).

RESOLUTION RULES:
- The "Columns used" list below tells you each [col] reference and which table it belongs
  to (format: 'table.column'). Use that table name as the 'T' placeholder above when
  wrapping the column.
- The "Measures used" list below tells you which bracketed names are measure references.
  For those, emit [Name] directly — do NOT wrap in SUM and do NOT add a table prefix.
- A bare [col] used in arithmetic with no aggregation function should be wrapped in SUM
  (if numeric) or COUNTA (if text/date). Inside SUMX/AVERAGEX it stays as 'T'[col]."""

        user = f"""Translate to DAX.

Tableau expression : {message.expression_raw}
Columns used       : {message.depends_on_columns}
Measures used      : {message.depends_on_measures}

Return only the DAX expression."""

        resp = await _azure_client.create([
            SystemMessage(content=system),
            UserMessage(content=user, source="user"),
        ])
        dax = resp.content.strip().strip("`").strip()
        await self.publish_message(
            AgentResult(task="dax", key=message.measure_name, value=dax),
            topic_id=DefaultTopicId(),
        )


# ── Visual Mapper Agent ───────────────────────────────────────────────────────
@type_subscription(topic_type="VisualMapperAgent")
class VisualMapperAgent(RoutedAgent):
    def __init__(self):
        super().__init__("Visual Mapper Agent")

    @message_handler
    async def handle(self, message: VisualRequest, ctx: MessageContext) -> None:
        # Try hardcoded map first
        key = message.raw_type.lower().replace(" ", "_")
        if key in _VISUAL_MAP:
            mapped = _VISUAL_MAP[key]
        else:
            prompt = f"""You are a Power BI expert.
Map this visual type to the correct Power BI PBIP visualType string.
Return ONLY the visualType string. No explanation.

Source visual type : {message.raw_type}
Fields in visual   : {message.fields}
Valid values       : barChart, columnChart, lineChart, areaChart, pieChart, donutChart,
                     scatterChart, map, filledMap, tableEx, pivotTable, card, kpiVisual,
                     slicerVisual, textbox, treemap, waterfallChart, funnel, gauge, ribbonChart"""

            resp = await _azure_client.create([
                SystemMessage(content="You map BI visual types to Power BI PBIP visualType strings. Return only the string."),
                UserMessage(content=prompt, source="user"),
            ])
            mapped = resp.content.strip().strip('"').strip()

        await self.publish_message(
            AgentResult(task="visual", key=message.visual_id, value=mapped),
            topic_id=DefaultTopicId(),
        )


# ── Type Inference Agent ──────────────────────────────────────────────────────
@type_subscription(topic_type="TypeInferenceAgent")
class TypeInferenceAgent(RoutedAgent):
    def __init__(self):
        super().__init__("Type Inference Agent")

    @message_handler
    async def handle(self, message: TypeRequest, ctx: MessageContext) -> None:
        # Attempt to pass through if already valid PBI type. `double` is the
        # floating-point type the parser emits for any generic numeric input
        # — including the RE's `decimal` (which is almost always a percentage
        # or ratio, not currency). Without `double` in this set the agent
        # falls through to the LLM, which returns `decimal`, undoing the
        # parser's correct mapping and producing a TMDL/M type mismatch
        # that breaks the column at refresh.
        _valid = {"string", "int64", "double", "decimal", "boolean",
                  "dateTime", "date", "time", "binary"}
        if message.data_type in _valid:
            await self.publish_message(
                AgentResult(task="type", key=message.col_name, value=message.data_type),
                topic_id=DefaultTopicId(),
            )
            return

        prompt = f"""You are a Power BI data modeler.
Infer the Power BI data type for this column.
Return ONLY one of: string, int64, decimal, boolean, dateTime, date, time
No explanation.

Column name  : {message.col_name}
Source type  : {message.data_type}
Description  : {message.description}"""

        resp = await _azure_client.create([
            SystemMessage(content="You infer Power BI column data types. Return only one valid type string."),
            UserMessage(content=prompt, source="user"),
        ])
        inferred = resp.content.strip().strip('"')
        await self.publish_message(
            AgentResult(task="type", key=message.col_name, value=inferred),
            topic_id=DefaultTopicId(),
        )


# ── Runtime helpers ───────────────────────────────────────────────────────────
async def _drain_queue() -> list[AgentResult]:
    results = []
    while not _result_queue.empty():
        results.append(await _result_queue.get())
    return results


async def _run_pipeline(intermediate: dict) -> dict:
    runtime = SingleThreadedAgentRuntime()

    await DaxConverterAgent.register(runtime, "DaxConverterAgent", DaxConverterAgent)
    await VisualMapperAgent.register(runtime, "VisualMapperAgent", VisualMapperAgent)
    await TypeInferenceAgent.register(runtime, "TypeInferenceAgent", TypeInferenceAgent)
    await ClosureAgent.register_closure(
        runtime, "collector", _collect,
        subscriptions=lambda: [DefaultSubscription()],
    )

    runtime.start()

    source = intermediate.get("source", "tableau")

    # 1. DAX conversion tasks — only for measures that aren't already valid DAX.
    # When expression_is_dax is True (PowerBI extractor emitted pre-translated DAX),
    # we trust the input as-is and skip the LLM round-trip entirely.
    for measure in intermediate.get("all_measures", []):
        expr_raw = measure.get("expression_raw", "")
        if not expr_raw or measure.get("expression_is_dax"):
            continue
        await runtime.publish_message(
            DaxRequest(
                measure_name=measure["name"],
                expression_raw=expr_raw,
                depends_on_columns=json.dumps(measure.get("depends_on_columns", []), ensure_ascii=False),
                depends_on_measures=json.dumps(measure.get("depends_on_measures", []), ensure_ascii=False),
            ),
            topic_id=TopicId("DaxConverterAgent", source="default"),
        )

    # 2. Visual type mapping tasks (only for unknowns)
    for page in intermediate.get("pages", []):
        for visual in page.get("visuals", []):
            raw = visual.get("type_raw", "unknown")
            key = raw.lower().replace(" ", "_")
            if key not in _VISUAL_MAP and raw.lower() not in ("unknown", "automatic"):
                await runtime.publish_message(
                    VisualRequest(
                        visual_id=visual.get("id", visual.get("title", "")),
                        raw_type=raw,
                        fields=json.dumps(visual.get("fields", []), ensure_ascii=False),
                    ),
                    topic_id=TopicId("VisualMapperAgent", source="default"),
                )

    # 3. Type inference for columns that may need it
    seen_cols: set[str] = set()
    for table in intermediate.get("tables", []):
        for col in table.get("columns", []):
            key = f"{table['name']}.{col['name']}"
            if key not in seen_cols:
                seen_cols.add(key)
                await runtime.publish_message(
                    TypeRequest(
                        col_name=key,
                        data_type=col.get("dataType", "string"),
                        description=col.get("description", ""),
                    ),
                    topic_id=TopicId("TypeInferenceAgent", source="default"),
                )

    await runtime.stop_when_idle()
    return {r.task + ":" + r.key: r.value for r in await _drain_queue()}


def _apply_results(intermediate: dict, results: dict) -> dict:
    """Merge LLM results back into the intermediate structure to produce mapped.json."""
    report_name = intermediate.get("report_name", "MyReport")
    # Source tool ("tableau" / "powerbi"). Needed by the nested
    # _resolve_cardinality fallback when a Tableau relationship arrives
    # without any explicit cardinality and no metadata to infer from —
    # without this binding, the closure raised NameError at runtime and
    # crashed the whole mapper for Tableau inputs.
    source = intermediate.get("source", "tableau")

    # Collect the set of all measure names declared anywhere in the input so we
    # can validate measure-on-measure references and drop measures that point at
    # missing measures (which would cause #ERROR cascades when PBI loads the model).
    _all_measure_names = set()
    for _t in intermediate.get("tables", []):
        for _m in _t.get("measures", []):
            _all_measure_names.add(_m["name"])

    # (table, col) → input dataType. Used to demote SUM('T'[c]) → SELECTEDVALUE
    # when the LLM/post-processor mistakenly aggregates a text/date column.
    _col_dtype: dict[tuple[str, str], str] = {}
    for _t in intermediate.get("tables", []):
        for _c in _t.get("columns", []):
            _col_dtype[(_t["name"], _c["name"])] = (_c.get("dataType") or "string")

    # Build tables with enriched types and DAX measures
    tables_out = []
    for table in intermediate.get("tables", []):
        cols_out = []
        for col in table.get("columns", []):
            key = f"type:{table['name']}.{col['name']}"
            orig_type = col.get("dataType", "string")
            data_type = results.get(key, orig_type)
            llm_called = key in results
            if _dbg:
                _dbg.log_type_inf(f"{table['name']}.{col['name']}",
                                  orig_type, data_type, llm_called)
            col_entry = {
                "name": col["name"],
                "dataType": data_type,
                "nullable": col.get("nullable", True),
                # Propagate so downstream (seeder, writer) can make correct
                # decisions about PK/key columns.
                "semantic_role": col.get("semantic_role"),
                "distinct_count_high": col.get("distinct_count_high", False),
                # PBI data category (Latitude / Longitude / …). Writer reads
                # this to emit `dataCategory:` and force `summarizeBy: none`.
                "data_category": col.get("data_category"),
                # Auto date/time variation pointer — used by writer to emit
                # `variation Variation { … }` on date columns.
                "variations": col.get("variations") or [],
            }
            dax_expr = col.get("expression") or col.get("expression_raw")
            if dax_expr:
                col_entry["expression"] = dax_expr
            else:
                col_entry["sourceColumn"] = col["name"]
            if col.get("formatString"):
                col_entry["formatString"] = col["formatString"]
            cols_out.append(col_entry)

        measures_out = []
        for m in table.get("measures", []):
            # Drop measures whose declared dependencies don't exist in the model.
            # Emitting a measure that references a missing measure produces #ERROR
            # in PBI and blanks every visual that consumes the dependent measure.
            #
            # Only treat a dependency as "definitely missing" when it is a plain
            # measure name. Tableau RE emits parameter/external references in
            # path forms like `Parameters.[Parameter 1]` or `[Parameter 1]` —
            # these never resolve through the plain-name index, but they aren't
            # broken measure refs either. Using them as a drop signal cascades:
            # the parameter-bound measure is removed, then every downstream
            # measure that referenced it surfaces a "cannot be determined"
            # error at load time. So strip path/bracket decoration and only
            # drop when the cleaned name still doesn't resolve AND the original
            # didn't carry any path/bracket characters.
            deps = m.get("depends_on_measures") or []
            missing_deps = []
            for d in deps:
                if not d or not isinstance(d, str):
                    continue
                if d in _all_measure_names:
                    continue
                # Strip enclosing brackets + table-path prefix and retry.
                cleaned = d.strip()
                if "." in cleaned:
                    cleaned = cleaned.rsplit(".", 1)[-1]
                cleaned = cleaned.strip("[]")
                if cleaned in _all_measure_names:
                    continue
                # If the original carried path/bracket decoration, the ref is
                # almost certainly a parameter or external object that the
                # measure can still emit against; don't use it as drop evidence.
                if "." in d or "[" in d or "]" in d:
                    continue
                missing_deps.append(d)
            if missing_deps:
                if _dbg:
                    _dbg.log_dax(table["name"], m["name"],
                                 m.get("expression_raw", ""),
                                 f"SKIPPED: missing deps {missing_deps}", "")
                continue

            dax_key = f"dax:{m['name']}"
            raw_expr = m.get("expression_raw", "")
            if m.get("expression_is_dax"):
                # Pre-translated DAX from the extractor — pass through untouched.
                # _fix_bare_column_refs is built for LLM output and can corrupt
                # valid hand-authored DAX (e.g. measure refs like [Other Measure]).
                llm_out = raw_expr
                expression = raw_expr
            else:
                llm_out = results.get(dax_key, raw_expr)
                expression = _fix_bare_column_refs(llm_out)
                expression = _demote_sum_on_text(expression, _col_dtype)
                expression = _fix_measure_path_refs(expression)
            if _dbg:
                _dbg.log_dax(table["name"], m["name"], raw_expr, llm_out, expression)
            # Prefer the input's declared format_string; fall back to a sensible
            # default driven by data_type.
            fmt = m.get("format_string") or (
                "#,##0.00" if m.get("data_type") == "decimal" else ""
            )
            measures_out.append({
                "name": m["name"],
                "expression": expression,
                "formatString": fmt,
            })

        tables_out.append({
            "name": table["name"],
            "table_type": table.get("table_type"),   # propagate so the seeder & writer see it
            "dax_table_expression": table.get("dax_table_expression"),
            "powerquery_expression": table.get("powerquery_expression"),
            # Self-join / data-source alias link — writer resolves the partition
            # CSV from this base table instead of the alias name when set.
            "source_derived_from_table_id": table.get("source_derived_from_table_id"),
            "columns": cols_out,
            "measures": measures_out,
            # User- and auto-authored hierarchies (writer emits them inside the
            # owning table's TMDL).
            "hierarchies": table.get("hierarchies") or [],
        })

    # Relationships — resolve table IDs (e.g. tbl_fct_insurance_policy_table)
    # to actual display names (e.g. FCT Insurance_Policy_Table) using the tables list.
    import re as _re
    def _norm(s): return _re.sub(r'[^a-z0-9]', '', s.lower())
    _tbl_map = {_norm(_re.sub(r'^tbl_', '', t["name"])): t["name"]
                for t in intermediate.get("tables", [])}
    def _resolve_tbl(ref):
        if not ref:
            return ref
        return _tbl_map.get(_norm(_re.sub(r'^tbl_', '', ref)), ref)

    # Build column / table indices for null-cardinality inference.
    _columns_idx = {}
    for _t in intermediate.get("tables", []):
        for _c in _t.get("columns", []):
            _columns_idx[(_t["name"], _c["name"])] = _c
    _tables_idx = {_t["name"]: _t for _t in intermediate.get("tables", [])}

    def _column_exists(tbl_name, col_name):
        """True iff the column is defined on the table in the intermediate model."""
        return (tbl_name, col_name) in _columns_idx

    def _resolve_cardinality(rel_raw, from_tbl_resolved, to_tbl_resolved):
        """Resolve cardinality from input; for null, infer from column/table metadata.
        Returns one of: 'many_to_one', 'one_to_many', 'one_to_one', 'many_to_many'.
        """
        card_raw = (rel_raw.get("cardinality") or "").lower().replace("-", "_").replace(" ", "_")
        explicit = card_raw if card_raw in ("many_to_one", "one_to_many", "one_to_one", "many_to_many") else None

        from_meta = _columns_idx.get((from_tbl_resolved, rel_raw.get("from_col")), {})
        to_meta   = _columns_idx.get((to_tbl_resolved,   rel_raw.get("to_col")),   {})
        from_t = _tables_idx.get(from_tbl_resolved, {}).get("table_type")
        to_t   = _tables_idx.get(to_tbl_resolved,   {}).get("table_type")

        # SANITY OVERRIDE — only for clearly bogus cardinalities
        # (one_to_one, many_to_many) on dim<->fact joins. The RE picks
        # many_to_one / one_to_many based on actual column uniqueness
        # (customer_code -> one_to_many because it's unique in dim_customer;
        # Age -> many_to_one because Age repeats). Overriding those would
        # force fromCardinality:one on non-unique columns and trigger
        # PFE_TM_RELATIONSHIP_ONE_TO_MANY at load time.
        if explicit in ("one_to_one", "many_to_many"):
            if from_t == "dimension" and to_t == "fact":
                return "one_to_many"
            if from_t == "fact" and to_t == "dimension":
                return "many_to_one"

        if explicit:
            return explicit

        # Inference for null cardinality
        from_pk = from_meta.get("semantic_role") == "primary_key"
        to_pk   = to_meta.get("semantic_role")   == "primary_key"
        if from_pk and to_pk: return "one_to_one"
        if from_pk:           return "one_to_many"
        if to_pk:             return "many_to_one"

        if from_t == "dimension" and to_t == "fact":     return "one_to_many"
        if from_t == "fact"      and to_t == "dimension": return "many_to_one"

        from_uniq = bool(from_meta.get("distinct_count_high"))
        to_uniq   = bool(to_meta.get("distinct_count_high"))
        if from_uniq and not to_uniq: return "one_to_many"
        if to_uniq and not from_uniq: return "many_to_one"

        return "one_to_many" if source == "tableau" else "many_to_one"

    def _is_key_candidate(col_meta):
        """True iff the column could plausibly be the 'one' side of a join.

        IMPORTANT: PBI does NOT require the one-side column to be a declared
        primary key — only that values be unique at refresh time. Dimension
        columns like dim_customer.Age or dim_customer.'Age Group' are legitimate
        join targets even though their semantic_role is "dimension" (RE labels
        any non-PK column on a dim table as "dimension"). The user wires these
        in PBI Desktop deliberately, and ground-truth PBIP exports preserve
        them — so the FE must not silently drop them on a heuristic.

        Reject ONLY when there is STRONG evidence the column cannot be a key:
          - semantic_role == "measure"  → an aggregation, never a join key
          - otherwise accept (trust the input relationship).
        """
        if not col_meta:
            return False
        if col_meta.get("semantic_role") == "measure":
            return False
        return True

    # Track table-pair counts so we can mark extra parallel relationships inactive
    # (PBI rejects multiple active relationships between the same two tables).
    _pair_active_count = {}

    rels_out = []
    for i, r in enumerate(intermediate.get("relationships", [])):
        from_tbl = _resolve_tbl(r.get("from_table", ""))
        to_tbl   = _resolve_tbl(r.get("to_table", ""))
        from_col = r.get("from_col")
        to_col   = r.get("to_col")

        # COLUMN RECOVERY: when one endpoint's column is null but the other
        # side's column exists, attempt to recover by checking if the
        # null-side table has a same-named column. RE has been observed to
        # drop column names on some relationships (e.g. calc-table joins
        # like CustomerCountPerDay -> dim_date.date where the LEFT column
        # comes back as null). The recovery is conservative: only fires
        # when the inferred column actually exists on the table, so it
        # never invents a column that doesn't exist.
        if not from_col and to_col and from_tbl and from_tbl in _tables_idx:
            if _column_exists(from_tbl, to_col):
                from_col = to_col
        if not to_col and from_col and to_tbl and to_tbl in _tables_idx:
            if _column_exists(to_tbl, from_col):
                to_col = from_col

        # GUARD 1: any endpoint or column is null — skip.
        if not from_tbl or not to_tbl or not from_col or not to_col:
            if _dbg:
                _dbg.log_rel_res(r.get("from_table", ""), from_tbl or "",
                                 r.get("to_table", ""), to_tbl or "", True)
            continue

        # GUARD 2: phantom-table check. Either side must exist in intermediate.tables.
        # Catches DAX calculated tables (e.g. 'Revenue Daywise') referenced in
        # relationships but not present as table definitions.
        if from_tbl not in _tables_idx or to_tbl not in _tables_idx:
            if _dbg:
                _dbg.log_rel_res(r.get("from_table", ""), from_tbl,
                                 r.get("to_table", ""), to_tbl, True)
            continue

        # GUARD 3: column existence — both columns must be defined on their tables.
        if not _column_exists(from_tbl, from_col) or not _column_exists(to_tbl, to_col):
            if _dbg:
                _dbg.log_rel_res(r.get("from_table", ""), from_tbl,
                                 r.get("to_table", ""), to_tbl, True)
            continue

        cardinality_resolved = _resolve_cardinality(r, from_tbl, to_tbl)
        filter_dir = (r.get("filter_direction") or "").lower()
        if filter_dir == "bidirectional":
            cross_filter = "bothDirections"
        elif filter_dir == "single":
            cross_filter = "oneDirection"
        else:
            cross_filter = "bothDirections"

        # GUARD 4: the 'one' side column must look like a key candidate.
        # Without this, malformed relationships like dim.NonKey <-> fact.NonKey
        # produce TMDL that PBI rejects ("contains blank values / duplicates").
        from_meta = _columns_idx.get((from_tbl, from_col), {})
        to_meta   = _columns_idx.get((to_tbl,   to_col),   {})
        if cardinality_resolved == "many_to_one":
            one_meta = to_meta
        elif cardinality_resolved == "one_to_many":
            one_meta = from_meta
        else:
            # one_to_one and many_to_many: BOTH sides act as 'one' side
            one_meta = None
            if not (_is_key_candidate(from_meta) and _is_key_candidate(to_meta)):
                if _dbg:
                    _dbg.log_rel_res(r.get("from_table", ""), from_tbl,
                                     r.get("to_table", ""), to_tbl, True)
                continue
        if one_meta is not None and not _is_key_candidate(one_meta):
            if _dbg:
                _dbg.log_rel_res(r.get("from_table", ""), from_tbl,
                                 r.get("to_table", ""), to_tbl, True)
            continue

        # GUARD 6: drop "hallucinated" relationships where the RE matched
        # two plain-dimension columns by NAME alone.
        #
        # A legitimate relationship's "one" side is always a key — flagged
        # either as semantic_role primary_key / foreign_key / identifier,
        # OR with distinct_count_high=True (high-cardinality column likely
        # to be unique). When BOTH endpoints are tagged as plain `dimension`
        # AND both have distinct_count_high=False, the column pair is
        # categorical (e.g. `State`, `City`, `Region` as descriptive
        # attributes) — not a join key. The RE has been observed to emit
        # `dim.State -> agent.State many_to_one` purely because the column
        # names match across tables; the source PBI has no such relationship
        # (it joins via `Sales Agent Code`/`Agent Code` instead). PBI then
        # enforces the bogus uniqueness constraint at load and rejects the
        # whole model because the "one" side has repeating values (multiple
        # agents per state, etc.).
        #
        # Auto-date hidden links are exempt — their endpoints are
        # synthetically generated, not user-authored.
        def _is_key_or_high_cardinality(col_meta):
            if not col_meta:
                return True  # unknown metadata — trust the input, don't drop
            if col_meta.get("semantic_role") in ("primary_key", "foreign_key", "identifier"):
                return True
            if col_meta.get("distinct_count_high"):
                return True
            return False

        _is_auto_date_link = bool(r.get("is_auto_generated")) or any(
            (_tables_idx.get(t, {}).get("table_type") == "calculated"
             and (_tables_idx.get(t, {}).get("dax_table_expression") or "").lower().startswith("calendar"))
            for t in (from_tbl, to_tbl)
        )
        # This name-match "hallucination" heuristic only applies to flows where
        # relationships are INFERRED (the Tableau LLM can match two dimension
        # columns by name). For PowerBI/QlikView the relationships are read
        # straight from the source model and are authoritative, so dropping one
        # (e.g. a real Region→Region dimension lookup) is wrong — gate to Tableau.
        if source == "tableau" and not _is_auto_date_link:
            if not (_is_key_or_high_cardinality(from_meta)
                    or _is_key_or_high_cardinality(to_meta)):
                if _dbg:
                    _dbg.log_rel_res(r.get("from_table", ""), from_tbl,
                                     r.get("to_table", ""), to_tbl, True)
                continue

        # GUARD 5: parallel-relationship dedup. PBI allows only one ACTIVE
        # relationship between any two tables. Keep first as active; mark rest inactive.
        pair_key = tuple(sorted([from_tbl, to_tbl]))
        active_input = r.get("active", True)
        if active_input and _pair_active_count.get(pair_key, 0) >= 1:
            active_resolved = False
        else:
            active_resolved = active_input
        if active_resolved:
            _pair_active_count[pair_key] = _pair_active_count.get(pair_key, 0) + 1

        rels_out.append({
            # Stable input id, used by column variations to reference the
            # auto-date hidden relationship by handle (not by GUID).
            "input_id": r.get("id"),
            "name": f"{from_tbl}_{from_col}__{to_tbl}_{to_col}",
            "fromTable": from_tbl,
            "fromColumn": from_col,
            "toTable": to_tbl,
            "toColumn": to_col,
            "cardinality_resolved": cardinality_resolved,
            "crossFilteringBehavior": cross_filter,
            "joinOnDateBehavior": r.get("join_on_date_behavior"),
            "type": r.get("join_type", "inner"),
            "active": active_resolved,
            "is_hidden": r.get("is_hidden", False),
            "is_auto_generated": r.get("is_auto_generated", False),
        })

    # ── Visual-field resolution index ─────────────────────────────────────
    # A visual field whose (table, column) doesn't point at a real model
    # object makes Power BI fail to render the WHOLE visual. Build an index of
    # every emitted column/measure so each field can be (a) rebound to the
    # table that actually owns it (the RE often binds a field to the worksheet
    # table rather than the table the measure lives on), or (b) dropped when it
    # resolves nowhere (e.g. a Tableau calc that was skipped, or a phantom
    # `... (copy)_<digits>` field id). A measure landing on a true axis role
    # (Category/Axis/Rows/Columns/X) is also dropped — Power BI can't place a
    # measure on an axis, and one bad field breaks the entire visual.
    _idx_cols: dict = {}
    _idx_meas: dict = {}
    _col_owner: dict = {}
    _meas_owner: dict = {}
    for _t in tables_out:
        _idx_cols[_t["name"]] = {c["name"] for c in _t.get("columns", [])}
        _idx_meas[_t["name"]] = {m["name"] for m in _t.get("measures", [])}
        for _c in _t.get("columns", []):
            _col_owner.setdefault(_c["name"], _t["name"])
        for _m in _t.get("measures", []):
            _meas_owner.setdefault(_m["name"], _t["name"])

    _FIELD_JUNK_RE = re.compile(r"\s*\(copy\)_\d+\s*$")
    _AXIS_ROLES_LC = {"category", "axis", "rows", "columns", "x"}

    def _resolve_visual_field(role, tbl, col):
        """Rebind (tbl, col) to the real owning table, or return None to drop."""
        cands = [col]
        cleaned = _FIELD_JUNK_RE.sub("", col).strip()
        if cleaned and cleaned != col:
            cands.append(cleaned)
        role_lc = (role or "").lower()
        for cand in cands:
            if cand in _idx_cols.get(tbl, ()):
                return (tbl, cand)
            if cand in _idx_meas.get(tbl, ()):
                return None if role_lc in _AXIS_ROLES_LC else (tbl, cand)
        for cand in cands:
            if cand in _col_owner:
                return (_col_owner[cand], cand)
            if cand in _meas_owner:
                return None if role_lc in _AXIS_ROLES_LC else (_meas_owner[cand], cand)
        # Auto-date Variation / Date-Hierarchy path (PowerBI), e.g.
        # "Start Date.Variation.Date Hierarchy.Year". The bare path isn't a model
        # column, so the lookups above miss it and the field was DROPPED (empty
        # Year slicers, missing chart date axes — audit #24/#25). Keep the FULL
        # path bound to the table whose BASE column exists; the writer's
        # _parse_hierarchy turns it into a HierarchyLevel projection. Tableau
        # never emits these, so this is inert for the Tableau flow.
        if (".Variation." in col) or re.search(r"\.[Dd]ate [Hh]ierarchy\.", col):
            base = col.split(".", 1)[0]
            if base in _idx_cols.get(tbl, ()):
                return (tbl, col)
            if base in _col_owner:
                return (_col_owner[base], col)
            return (tbl, col)
        return None

    # Pages / Visuals
    pages_out = []
    for page in intermediate.get("pages", []):
        visuals_out = []
        for visual in page.get("visuals", []):
            raw = visual.get("type_raw", "unknown")
            key = raw.lower().replace(" ", "_")
            intermediate_vtype = visual.get("visualType", "")
            # Resolve visual type: hardcoded map → intermediate value (if valid) → LLM result → fallback
            vid = visual.get("id", visual.get("title", ""))
            if key in _VISUAL_MAP:
                vtype = _VISUAL_MAP[key]
                _vis_method = "hardcoded_map"
            elif intermediate_vtype and intermediate_vtype.lower() not in ("unknown", ""):
                # Parser already identified a valid PBI type — trust it.
                # LLM results are unreliable here because all visuals on a page share the same id.
                vtype = intermediate_vtype
                _vis_method = "intermediate_passthrough"
            else:
                llm_vtype = results.get(f"visual:{vid}")
                if llm_vtype:
                    vtype = llm_vtype
                    _vis_method = "llm"
                else:
                    vtype = "tableEx"
                    _vis_method = "fallback_tableEx"
            if _dbg:
                _dbg.log_visual_res(page["name"], vid, raw, vtype, _vis_method)

            # Build fields — resolve every binding against the real model so a
            # wrong-table or phantom reference can't break the whole visual.
            fields_out = []
            for f in visual.get("fields", []):
                if not (f.get("table") and f.get("column")):
                    continue
                # `_force_dimension` marks a Tableau group/string calc that the
                # upstream RE bound to a categorical role (Category/Rows/slicer).
                # Such a calc resolves as a measure in the model, so the normal
                # axis-role guard in _resolve_visual_field would DROP it — leaving
                # the chart with no category or a slicer showing a scalar list.
                # Honor the flag: keep the binding on its categorical role and
                # tell the writer to emit it as a Column (dimension), not a Measure.
                force_dim = bool(f.get("_force_dimension"))
                if force_dim:
                    resolved = (f["table"], f["column"])
                    rb = _resolve_visual_field(f.get("role", ""), f["table"], f["column"])
                    if rb is not None:
                        resolved = rb
                    elif f["column"] in _meas_owner:
                        resolved = (_meas_owner[f["column"]], f["column"])
                else:
                    resolved = _resolve_visual_field(
                        f.get("role", ""), f["table"], f["column"])
                if resolved is None:
                    continue
                entry = {
                    "role": f.get("role", "Values"),
                    "table": resolved[0],
                    "column": resolved[1],
                    "aggregation": f.get("aggregation", ""),
                }
                if f.get("display_name"):
                    entry["display_name"] = f["display_name"]
                if force_dim:
                    entry["force_dimension"] = True
                fields_out.append(entry)

            vis_out = {
                "visualType": vtype,
                "title": visual.get("title", ""),
                "position": visual.get("position", {"x": 0, "y": 0, "w": 400, "h": 300, "z": 0}),
                "fields": fields_out,
            }
            # Carry the RE's visual id through so the writer can build the
            # {RE id → generated name} map for edit interactions (section 8)
            # and bookmark references (section 7).
            if visual.get("id"):
                vis_out["id"] = visual["id"]
            # Carry the original source visual id so the writer can remap captured
            # bookmarks (section 7) onto the regenerated visuals.
            if visual.get("source_visual_id"):
                vis_out["source_visual_id"] = visual["source_visual_id"]
            # Carry field-parameter bindings so the writer re-binds the slicer to
            # the visual it reconfigures.
            if visual.get("field_parameters_by_role"):
                vis_out["field_parameters_by_role"] = visual["field_parameters_by_role"]
            # Carry image references through to the writer (image visuals).
            if visual.get("imageId"):
                vis_out["imageId"] = visual["imageId"]
            if visual.get("imageUrl"):
                vis_out["imageUrl"] = visual["imageUrl"]
            # Carry textbox body content through to the writer — the writer
            # emits it as the textbox's paragraphs property.
            if visual.get("content"):
                vis_out["content"] = visual["content"]
            # Carry style / colour metadata through UNTOUCHED. The mapper's job
            # is data (DAX, types, relationships); colours and fonts are
            # deterministic and must never be routed through an LLM. The writer
            # turns `formatting` into the PBIP visualContainerObjects / objects.
            if visual.get("formatting"):
                vis_out["formatting"] = visual["formatting"]
            # Ready-made PBIP from the RE (`style.raw`) — authoritative, emitted
            # by the writer as-is (this is where per-visual dataPoint colours,
            # legend, axes etc. come through for PowerBI and the Tableau flow).
            if visual.get("raw_objects"):
                vis_out["raw_objects"] = visual["raw_objects"]
            if visual.get("raw_vc_objects"):
                vis_out["raw_vc_objects"] = visual["raw_vc_objects"]
            visuals_out.append(vis_out)

        page_out = {
            "name": page["name"],
            "width": page.get("width", 1280),
            "height": page.get("height", 720),
            "visuals": visuals_out,
        }
        # Carry the original source page id so the writer can remap a bookmark's
        # activeSection / sections (keyed by that id) onto the generated page.
        if page.get("page_id"):
            page_out["page_id"] = page["page_id"]
        # Carry page-level image references (canvas background / wallpaper)
        # through to the writer.
        if page.get("background_image_id"):
            page_out["background_image_id"] = page["background_image_id"]
        if page.get("wallpaper_image_id"):
            page_out["wallpaper_image_id"] = page["wallpaper_image_id"]
        # Canvas & environment style metadata (section 1) — passed through
        # verbatim for the writer to emit as page.json objects + displayOption.
        if page.get("canvas"):
            page_out["canvas"] = page["canvas"]
        # Ready-made page PBIP (RE `styles.raw`) + page-level scalars.
        if page.get("raw_objects"):
            page_out["raw_objects"] = page["raw_objects"]
        if page.get("displayOption"):
            page_out["displayOption"] = page["displayOption"]
        if page.get("pageType"):
            page_out["pageType"] = page["pageType"]
        # Edit interactions / cross-filtering (section 8) — passed through.
        if page.get("interactions"):
            page_out["interactions"] = page["interactions"]
        # Filter pane filter definitions (section 1 locking/filterType) — verbatim.
        if page.get("filterConfig"):
            page_out["filterConfig"] = page["filterConfig"]
        pages_out.append(page_out)

    # Auto-detect field parameter tables from slicer visuals that reference a "*Parameter*" table.
    # Measures with reusable=True are the entries; their table attribute becomes sourcetable.
    _param_table_names: set[str] = set()
    for page in intermediate.get("pages", []):
        for visual in page.get("visuals", []):
            if visual.get("type_raw", "").lower() == "slicer":
                for f in visual.get("fields", []):
                    tbl = f.get("table") or ""
                    if "parameter" in tbl.lower():
                        _param_table_names.add(tbl)

    _reusable_measures = [
        m for m in intermediate.get("all_measures", []) if m.get("reusable")
    ]

    for param_tbl in sorted(_param_table_names):
        # Skip if already present (e.g. explicitly defined in input)
        if any(t["name"] == param_tbl for t in tables_out):
            continue
        fp_measures = [
            {
                "name": m["name"],
                "sourcetable": m["table"],
                "expression": m["name"],   # used as NAMEOF(table[name])
            }
            for m in _reusable_measures
        ]
        tables_out.append({
            "name": param_tbl,
            "type": "fieldParameter",
            "columns": [],
            "measures": fp_measures,
        })

    # ── What-if parameters (audit #16) ─────────────────────────────────────
    # A parameter with a NUMERIC range becomes a real Power BI what-if: a
    # GENERATESERIES table + the parameter measure rewritten to SELECTEDVALUE
    # (KEEPS its name so dependent measures still resolve) + the slicer rebound
    # to the table's value column. Generic — keyed on semantic_type=="parameter"
    # + a numeric parameter_config; no input-specific names/values/hardcoding.
    def _num(v):
        try:
            fv = float(v)
            return int(fv) if fv == int(fv) else fv
        except (TypeError, ValueError):
            return None
    _existing_tbls = {t["name"] for t in tables_out}
    for _t in intermediate.get("tables", []):
        for _m in _t.get("measures", []):
            if (_m.get("semantic_type") or "").lower() != "parameter":
                continue
            cfg = _m.get("parameter_config") or {}
            mn = _num(cfg.get("min_value", cfg.get("min")))
            mx = _num(cfg.get("max_value", cfg.get("max")))
            stp = _num(cfg.get("step_size", cfg.get("step"))) or 1
            if mn is None or mx is None:
                continue   # list/non-numeric parameter — leave as-is
            cur = _num(cfg.get("current_value", cfg.get("current")))
            if cur is None:
                cur = mn
            pname = _m["name"]
            ptable = f"{pname} Parameter"
            if ptable in _existing_tbls:
                continue
            _existing_tbls.add(ptable)
            is_int = all(isinstance(x, int) for x in (mn, mx, stp))
            tables_out.append({
                "name": ptable,
                "table_type": "calculated",
                "dax_table_expression": f"GENERATESERIES({mn}, {mx}, {stp})",
                "powerquery_expression": None,
                "source_derived_from_table_id": None,
                "columns": [{
                    # GENERATESERIES introduces a single column literally named
                    # [Value] — match it (PBI's native what-if does the same).
                    "name": "Value",
                    "dataType": "int64" if is_int else "double",
                    "nullable": False,
                    "semantic_role": None,
                    "distinct_count_high": False,
                    "data_category": None,
                    "variations": [],
                    "sourceColumn": "[Value]",
                    "formatString": "0" if is_int else "#,##0.00",
                }],
                "measures": [],
                "hierarchies": [],
            })
            # Rewrite the parameter measure -> selected value (keep its name so
            # dependent measures that reference [<pname>] still resolve).
            _sv = f"SELECTEDVALUE('{ptable}'[Value], {cur})"
            for _tt in tables_out:
                for _mm in _tt.get("measures", []):
                    if _mm.get("name") == pname:
                        _mm["expression"] = _sv
            # Rebind slicer fields referencing the parameter -> the table's Value
            # column. NOTE: at this (mapper) stage a slicer's visualType is still
            # "slicerVisual" (the writer renames it to "slicer" later).
            for _pg in pages_out:
                for _v in _pg.get("visuals", []):
                    if (_v.get("visualType") or "") not in (
                            "slicer", "slicerVisual", "advancedSlicerVisual", "listControl"):
                        continue
                    for _f in (_v.get("fields") or []):
                        if (_f.get("column") or "") == pname:
                            _f["table"], _f["column"] = ptable, "Value"

    # ── Dangling-reference safety net (audit #18/CORR) ─────────────────────────
    # A source calc with no Power BI equivalent (e.g. Tableau CORR / other
    # statistical functions) is dropped during DAX translation. Any visual that
    # still binds it is then left pointing at a phantom measure, which surfaces a
    # "can't find field" error and blanks the visual. For each visual field that
    # references a KNOWN source calc name which was NOT emitted, add a BLANK()
    # placeholder measure on the referenced table so the binding resolves and the
    # visual stays valid. Purely additive and generic: keyed on "referenced but
    # not emitted" + the name being a real source calc — never input-specific
    # names. PowerBI measures are pre-translated DAX and never dropped, so no
    # dangling refs arise there and this loop is a no-op for that flow.
    _emitted_meas = {m["name"] for t in tables_out for m in (t.get("measures") or [])}
    _emitted_cols = {(t["name"], c["name"]) for t in tables_out for c in (t.get("columns") or [])}
    _source_calc_names = {m.get("name") for m in intermediate.get("all_measures", []) if m.get("name")}
    _tbl_by_name = {t["name"]: t for t in tables_out}
    for _pg in pages_out:
        for _v in _pg.get("visuals", []):
            for _f in (_v.get("fields") or []):
                cn, tn = _f.get("column"), _f.get("table")
                if not cn or not tn:
                    continue
                if cn in _emitted_meas or (tn, cn) in _emitted_cols:
                    continue   # resolves against the final model
                if cn not in _source_calc_names:
                    continue   # not a known dropped calc — leave alone
                _host = _tbl_by_name.get(tn) or (tables_out[0] if tables_out else None)
                if _host is None:
                    continue
                _host.setdefault("measures", []).append({
                    "name": cn,
                    "expression": "BLANK()",
                    "formatString": "",
                })
                _emitted_meas.add(cn)

    result = {
        "reportName": report_name,
        "originalName": intermediate.get("original_name", report_name),
        "source": intermediate.get("source", "unknown"),
        "tables": tables_out,
        "relationships": rels_out,
        "pages": pages_out,
    }
    # Report-level theme / design tokens (section 10) — passed through verbatim
    # for the writer to emit as themeCollection.customTheme. Source-agnostic: the
    # parser populates `theme` for any flow that carries a palette (PowerBI and
    # Tableau both do), so the FE stays common-model driven (no source check).
    if intermediate.get("theme"):
        result["theme"] = intermediate["theme"]
    # Bookmarks (section 7) — passed through verbatim.
    if intermediate.get("bookmarks"):
        result["bookmarks"] = intermediate["bookmarks"]
    # Row-Level Security roles — passed through verbatim (security-critical DAX).
    if intermediate.get("roles"):
        result["roles"] = intermediate["roles"]
    if _dbg:
        _dbg.flush_map_dax()
        _dbg.flush_map_types()
        _dbg.flush_map_visuals()
        _dbg.flush_map_rels()
        _dbg.log_mapped(result)
    return result


def map_intermediate(intermediate: dict) -> dict:
    results = asyncio.run(_run_pipeline(intermediate))
    return _apply_results(intermediate, results)


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Map intermediate.json → mapped.json using gpt-5-mini agents")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    with open(args.input) as f:
        intermediate = json.load(f)

    print(f"[mapper] Processing {len(intermediate.get('all_measures', []))} measures, "
          f"{sum(len(p['visuals']) for p in intermediate.get('pages', []))} visuals ...")

    mapped = map_intermediate(intermediate)

    # UTF-8 + ensure_ascii=False — keep English and non-Latin text (Japanese,
    # etc.) intact through the mapped JSON. ASCII output is unchanged.
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(mapped, f, indent=2, ensure_ascii=False)
    print(f"[mapper] Written → {args.output}")
    print(f"  Tables: {len(mapped['tables'])}, Pages: {len(mapped['pages'])}, "
          f"Relationships: {len(mapped['relationships'])}")


if __name__ == "__main__":
    main()
