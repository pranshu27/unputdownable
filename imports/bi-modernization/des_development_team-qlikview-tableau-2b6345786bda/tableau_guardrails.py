"""
tableau_guardrails.py — Reliability + output-contract enforcement for the
**Tableau** reverse-engineering flow ONLY.

Nothing in this module is imported by the PowerBI or QlikView flows; it exists
purely to make the Tableau flow (sequentialworkflow.py) produce a predictable,
fully-formed common-model envelope on every run, regardless of what the LLM
returns.

It centralises four concerns:

  1. robust_llm_parse(...)   — call the LLM and parse its JSON with bounded
     retry + error feedback. Replaces the old "swallow the exception and
     publish {} / {'pages': []}" behaviour that silently produced empty
     tables / visuals when a single response was malformed.

  2. QualityReport           — accumulates per-stage warnings / errors / repairs.
     Emitted on the final JSON as `quality_report` so a degraded run is
     explicit and auditable instead of looking like a clean empty result.

  3. validate_common_model / validate_visualizations
                             — deterministic shape + enum repair aligned EXACTLY
     with what the downstream pbip-converter-skill parser reads
     (skills/json_to_pbip/src/parser.py). In particular the converter accesses
     tables[].name, tables[].columns[].name and calculations[].name with
     bracket access — a missing name raises KeyError and crashes the converter.
     These validators guarantee those invariants (dropping unusable, nameless
     entries) and normalise the constrained vocabularies (cardinality,
     relationship_type, filter_direction). They NEVER raise — they only repair
     and record. The orchestrator decides whether to hard-fail.

  4. finalize_tableau_envelope(...)
                             — stamps the top-level `tool_type` ("tableau") that
     the converter's detect_source() REQUIRES, plus the accumulated
     `quality_report`. Without tool_type the converter raises
     "Unknown or missing tool_type" before it reads anything else.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Marker key an agent attaches to its published dict when it could not produce
# valid JSON even after retries. The orchestrator detects this, records it, and
# decides whether the failure is fatal (core model) or tolerable (visuals /
# technical). Stripped from the final output by finalize_tableau_envelope.
EXTRACTION_ERROR_KEY = "__extraction_error__"
AGENT_QUALITY_KEY = "__quality__"

# ── Constrained vocabularies the downstream converter understands ─────────────
# Mirrors skills/json_to_pbip/src/parser.py + mapper.py. Anything outside these
# sets is coerced to a safe default so the converter never sees an unknown value.
_VALID_CARDINALITY = {"one_to_one", "one_to_many", "many_to_one", "many_to_many"}
_VALID_REL_TYPE = {"dimension_lookup", "auto_date_relationship", "blend"}
_VALID_FILTER_DIRECTION = {"single", "bidirectional"}


def _short(err: Any, limit: int = 300) -> str:
    s = str(err)
    return s if len(s) <= limit else s[:limit] + "…"


# ─────────────────────────────────────────────────────────────────────────────
# Quality report
# ─────────────────────────────────────────────────────────────────────────────
class QualityReport:
    """Accumulates the health of a single Tableau extraction run.

    `errors`  — a stage produced nothing usable (e.g. extraction agent failed
                all retries). These drive the orchestrator's hard-fail decision.
    `warnings`— a recoverable hiccup (retry succeeded, a section degraded).
    `repairs` — a deterministic fix the validator applied to LLM output.
    """

    def __init__(self) -> None:
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.repairs: List[str] = []
        self.counts: Dict[str, int] = {}

    def error(self, stage: str, msg: str) -> None:
        self.errors.append(f"{stage}: {msg}")
        logger.error("[Tableau][quality] ERROR %s: %s", stage, msg)

    def warn(self, stage: str, msg: str) -> None:
        self.warnings.append(f"{stage}: {msg}")
        logger.warning("[Tableau][quality] WARN %s: %s", stage, msg)

    def repair(self, stage: str, msg: str) -> None:
        self.repairs.append(f"{stage}: {msg}")
        logger.info("[Tableau][quality] repair %s: %s", stage, msg)

    def set_count(self, key: str, value: int) -> None:
        self.counts[key] = value

    def merge_agent_quality(self, entries: Optional[List[Dict[str, str]]]) -> None:
        """Fold an agent's locally-collected quality entries into this report.

        Each entry is {"level": "warn"|"error"|"repair", "stage": str, "msg": str}.
        """
        for e in entries or []:
            level = (e.get("level") or "warn").lower()
            stage = e.get("stage") or "agent"
            msg = e.get("msg") or ""
            if level == "error":
                self.error(stage, msg)
            elif level == "repair":
                self.repair(stage, msg)
            else:
                self.warn(stage, msg)

    def to_list(self) -> List[Dict[str, str]]:
        """Flat, transport-friendly form used to ship an agent-local report back
        to the orchestrator through the result queue."""
        out: List[Dict[str, str]] = []
        out += [{"level": "error", "stage": "", "msg": m} for m in self.errors]
        out += [{"level": "warn", "stage": "", "msg": m} for m in self.warnings]
        out += [{"level": "repair", "stage": "", "msg": m} for m in self.repairs]
        return out

    def status(self) -> str:
        if self.errors:
            return "degraded"
        if self.warnings or self.repairs:
            return "ok_with_repairs"
        return "ok"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status(),
            "counts": dict(self.counts),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "repairs": list(self.repairs),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Robust LLM call + parse with bounded retry and error feedback
# ─────────────────────────────────────────────────────────────────────────────
async def robust_llm_parse(
    model_client: Any,
    system_prompt: str,
    user_content: str,
    parser: Any,
    *,
    label: str,
    quality: QualityReport,
    sanitize: Optional[Callable[[str], str]] = None,
    max_attempts: int = 3,
    repair_directive: str = "",
) -> Optional[dict]:
    """Call ``model_client`` and parse its reply with ``parser``.

    On a parse failure the model is re-prompted with the exact error and a
    snippet of its own bad output, up to ``max_attempts`` times. Returns the
    parsed dict, or ``None`` if every attempt failed. NEVER raises — failures
    are recorded on ``quality`` and surfaced to the caller as ``None`` so the
    orchestrator (not this helper) decides whether the failure is fatal.
    """
    # Imported lazily so this module has no hard dependency on autogen when its
    # pure-Python validators are used in isolation (e.g. unit tests).
    from autogen_core.models import SystemMessage, UserMessage

    messages: List[Any] = [
        SystemMessage(content=system_prompt),
        UserMessage(content=user_content, source="user"),
    ]
    last_err: Any = None

    for attempt in range(1, max_attempts + 1):
        try:
            resp = await model_client.create(messages=messages)
        except Exception as e:  # network / rate-limit / client error
            last_err = e
            quality.warn(label, f"llm_call_failed_attempt_{attempt}: {_short(e)}")
            continue

        raw = resp.content if isinstance(resp.content, str) else str(resp.content)
        if sanitize:
            try:
                raw = sanitize(raw)
            except Exception:  # sanitiser must never block parsing
                pass

        try:
            parsed = parser.parse(raw)
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
            if not isinstance(parsed, dict):
                raise ValueError(f"parsed result is {type(parsed).__name__}, expected object")
            if attempt > 1:
                quality.warn(label, f"recovered_on_attempt_{attempt}")
            return parsed
        except Exception as e:
            last_err = e
            quality.warn(label, f"parse_failed_attempt_{attempt}: {_short(e)}")
            # Feed the error + a snippet of the bad output back so the model can
            # self-correct. Multiple consecutive user turns are valid for chat
            # completion APIs.
            snippet = (raw or "")[:1500]
            messages.append(
                UserMessage(
                    content=(
                        "Your previous reply could not be parsed as JSON.\n"
                        f"Error: {_short(e)}\n"
                        "Here is the start of what you returned (truncated):\n"
                        f"{snippet}\n\n"
                        f"{repair_directive}\n"
                        "Return ONLY one complete, valid JSON object that conforms "
                        "to the required schema. No markdown code fences, no prose."
                    ),
                    source="user",
                )
            )

    quality.error(label, f"all_{max_attempts}_attempts_failed: {_short(last_err)}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic common-model validation / repair
# ─────────────────────────────────────────────────────────────────────────────
def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _clean_name(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def validate_common_model(model: dict, quality: QualityReport) -> dict:
    """Repair the extraction agent's output in place so it always satisfies the
    downstream converter's hard invariants, then return it.

    Hard invariants enforced (converter uses bracket access on these):
      * tables[].name, tables[].columns[].name, calculations[].name present.
        Entries without a usable name are DROPPED (and recorded) — a nameless
        entity is unusable downstream and would crash the converter.
    Soft repairs:
      * Top-level data_sources / tables / relationships / calculations are lists.
      * columns / ingestion.steps / hierarchies are lists; columns get a
        data_type default of "string".
      * relationships: cardinality / relationship_type / filter_direction
        coerced into the converter's constrained vocabularies.
      * calculations: expressions is a dict; depends_on_* are lists.
    """
    if not isinstance(model, dict):
        quality.error("validate_model", f"model is {type(model).__name__}, expected object")
        return {"data_sources": [], "tables": [], "relationships": [], "calculations": []}

    # ── top-level collections ────────────────────────────────────────────────
    for key in ("data_sources", "tables", "relationships", "calculations"):
        if not isinstance(model.get(key), list):
            if key in model:
                quality.repair("validate_model", f"{key} was not a list — reset to []")
            model[key] = []

    # ── tables + columns ─────────────────────────────────────────────────────
    clean_tables: List[dict] = []
    for t in model["tables"]:
        if not isinstance(t, dict):
            quality.repair("validate_model", "dropped a non-object table entry")
            continue
        name = _clean_name(t.get("name"))
        if not name:
            quality.repair("validate_model", "dropped a table with no usable name")
            continue
        t["name"] = name

        cols = _as_list(t.get("columns"))
        clean_cols: List[dict] = []
        for c in cols:
            if not isinstance(c, dict):
                continue
            cname = _clean_name(c.get("name"))
            if not cname:
                quality.repair("validate_model", f"dropped a nameless column in table '{name}'")
                continue
            c["name"] = cname
            if not _clean_name(c.get("data_type")):
                c["data_type"] = "string"
            clean_cols.append(c)
        t["columns"] = clean_cols

        # ingestion.steps must be a list
        ing = t.get("ingestion")
        if not isinstance(ing, dict):
            ing = {"steps": []}
        if not isinstance(ing.get("steps"), list):
            ing["steps"] = []
        t["ingestion"] = ing

        if not isinstance(t.get("hierarchies"), list):
            t["hierarchies"] = []

        clean_tables.append(t)
    model["tables"] = clean_tables

    # ── calculations ─────────────────────────────────────────────────────────
    clean_calcs: List[dict] = []
    for calc in model["calculations"]:
        if not isinstance(calc, dict):
            continue
        cname = _clean_name(calc.get("name"))
        if not cname:
            quality.repair("validate_model", "dropped a calculation with no usable name")
            continue
        calc["name"] = cname
        if not isinstance(calc.get("expressions"), dict):
            # Preserve any bare 'expression' so the converter's fallback
            # (exprs.get('tableau') or calc.get('expression')) still resolves.
            calc["expressions"] = {}
        for dk in ("depends_on_columns", "depends_on_measures"):
            if calc.get(dk) is not None and not isinstance(calc.get(dk), list):
                calc[dk] = []
        clean_calcs.append(calc)
    model["calculations"] = clean_calcs

    # ── relationships: normalise constrained vocabularies ────────────────────
    for r in model["relationships"]:
        if not isinstance(r, dict):
            continue
        card = (r.get("cardinality") or "")
        if isinstance(card, str) and card:
            norm = card.lower().replace("-", "_").replace(" ", "_")
            r["cardinality"] = norm if norm in _VALID_CARDINALITY else None
            if r["cardinality"] is None:
                quality.repair("validate_model", f"reset unknown cardinality '{card}' to null")

        rtype = r.get("relationship_type")
        if isinstance(rtype, str) and rtype:
            norm = rtype.lower().replace("-", "_").replace(" ", "_")
            if norm not in _VALID_REL_TYPE:
                quality.repair(
                    "validate_model",
                    f"coerced relationship_type '{rtype}' -> 'dimension_lookup'",
                )
                r["relationship_type"] = "dimension_lookup"
            else:
                r["relationship_type"] = norm

        fdir = r.get("filter_direction")
        if isinstance(fdir, str) and fdir:
            norm = fdir.lower()
            if norm not in _VALID_FILTER_DIRECTION:
                r["filter_direction"] = None

    quality.set_count("data_sources", len(model["data_sources"]))
    quality.set_count("tables", len(model["tables"]))
    quality.set_count("relationships", len(model["relationships"]))
    quality.set_count("calculations", len(model["calculations"]))
    quality.set_count(
        "columns", sum(len(t.get("columns", [])) for t in model["tables"])
    )
    return model


def validate_visualizations(viz: Any, quality: QualityReport) -> dict:
    """Repair the visuals agent's output so visualizations.pages[] is always a
    well-formed list the converter can iterate. Returns a dict with a `pages`
    list. NEVER raises."""
    if not isinstance(viz, dict):
        quality.warn("validate_visuals", f"visualizations was {type(viz).__name__} — reset")
        return {"pages": []}

    pages = viz.get("pages")
    if not isinstance(pages, list):
        if pages is not None:
            quality.repair("validate_visuals", "pages was not a list — reset to []")
        viz["pages"] = []
        return viz

    total_visuals = 0
    for pg in pages:
        if not isinstance(pg, dict):
            continue
        visuals = pg.get("visuals")
        if not isinstance(visuals, list):
            pg["visuals"] = []
            visuals = pg["visuals"]
        kept: List[dict] = []
        for v in visuals:
            if not isinstance(v, dict):
                continue
            if not isinstance(v.get("fields"), list):
                v["fields"] = []
            if not isinstance(v.get("position"), dict):
                v["position"] = {}
            kept.append(v)
        pg["visuals"] = kept
        total_visuals += len(kept)

    quality.set_count("pages", len([p for p in pages if isinstance(p, dict)]))
    quality.set_count("visuals", total_visuals)
    return viz


# ─────────────────────────────────────────────────────────────────────────────
# Envelope finalisation
# ─────────────────────────────────────────────────────────────────────────────
def strip_agent_private_keys(model: dict) -> List[Dict[str, str]]:
    """Pop the private agent markers off a parsed model and return the merged
    agent-quality list. Safe to call on any dict."""
    if not isinstance(model, dict):
        return []
    entries = model.pop(AGENT_QUALITY_KEY, None) or []
    err = model.pop(EXTRACTION_ERROR_KEY, None)
    if err:
        entries = list(entries) + [{"level": "error", "stage": "extraction", "msg": str(err)}]
    return entries


def finalize_tableau_envelope(final_parsed: dict, quality: QualityReport) -> dict:
    """Stamp the converter-required `tool_type` and the `quality_report`.

    `tool_type="tableau"` is the value the converter's detect_source() matches;
    without it the converter raises before reading anything else. Returns the
    same dict (mutated) for convenience.
    """
    if not isinstance(final_parsed, dict):
        return final_parsed
    final_parsed["tool_type"] = "tableau"
    final_parsed["quality_report"] = quality.to_dict()
    return final_parsed
