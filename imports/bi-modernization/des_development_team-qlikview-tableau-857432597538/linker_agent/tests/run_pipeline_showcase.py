"""
Pipeline showcase — reads input1.json, runs the full 3-tier enrichment pipeline,
prints step-by-step progress, and saves results to output/.

Usage:
    # No live Alation needed — uses mock_glossary.json for Tier 2 matching
    python -m linker_agent.tests.run_pipeline_showcase --use-mock-glossary

    # Dry run — parse and build context only, no LLM/Alation calls
    python -m linker_agent.tests.run_pipeline_showcase --dry-run

    # Process only calculations (11 assets — fastest meaningful demo)
    python -m linker_agent.tests.run_pipeline_showcase --use-mock-glossary --asset-type calculation

    # Full run against live Alation (requires ALATION_BASE_URL + ALATION_API_TOKEN in .env)
    python -m linker_agent.tests.run_pipeline_showcase --glossary-id 2 --confidence 70

Output files written to ./output/:
    enrichment_results.json       — full AssetLinkResult list (one object per asset)
    event_log.jsonl               — append-only audit trail (one JSON event per line)
    showcase_summary.json         — tier breakdown and key statistics
    dry_run_asset_records.json    — (dry-run only) parsed assets with LLM context
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re as _re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Resolve paths so the script works from any working directory
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_PKG_ROOT = _REPO_ROOT / "linker_agent"
_INPUT_PATH = _PKG_ROOT / "input1.json"
_MOCK_GLOSSARY_PATH = _PKG_ROOT / "mock_glossary.json"
_OUTPUT_DIR = _REPO_ROOT / "output"

sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(_REPO_ROOT / ".env")

from linker_agent.ingestion.model_parser import parse_common_model
from linker_agent.ingestion.context_builder import build_context
from linker_agent.models.asset_record import AssetRecord, AssetType


# ---------------------------------------------------------------------------
# TeeOutput — write all print() output to file while keeping terminal colour
# ---------------------------------------------------------------------------

_ANSI_RE = _re.compile(r"\x1b\[[0-9;]*m")

class TeeOutput:
    """Wraps sys.stdout so every write goes to the terminal AND to a plain-text file."""

    def __init__(self, path: Path):
        self._terminal = sys.stdout
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(path, "w", encoding="utf-8")

    def write(self, text: str) -> int:
        self._terminal.write(text)
        self._file.write(_ANSI_RE.sub("", text))
        return len(text)

    def flush(self):
        self._terminal.flush()
        self._file.flush()

    def close(self):
        self._file.close()

    # Forward attribute lookups to the real stdout (isatty, fileno, etc.)
    def __getattr__(self, name):
        return getattr(self._terminal, name)


# ---------------------------------------------------------------------------
# Colour helpers (graceful fallback if terminal doesn't support ANSI)
# ---------------------------------------------------------------------------

def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m"

def green(t):  return _c(str(t), "32")
def yellow(t): return _c(str(t), "33")
def cyan(t):   return _c(str(t), "36")
def bold(t):   return _c(str(t), "1")
def dim(t):    return _c(str(t), "2")
def red(t):    return _c(str(t), "31")
def blue(t):   return _c(str(t), "34")

TIER_COLOUR = {
    "direct":    green,
    "semantic":  cyan,
    "generated": yellow,
    "suggested": yellow,
    "no_match":  dim,
    "error":     red,
}

TIER_LABEL = {
    "direct":    "TIER 1  Direct Link   ",
    "semantic":  "TIER 2  Semantic Match",
    "generated": "TIER 3  Generated Term",
    "suggested": "TIER 3  Suggestion    ",
    "no_match":  "No Match              ",
    "error":     "Error                 ",
}


def _header(title: str, width: int = 72) -> None:
    print()
    print(bold("=" * width))
    print(bold(f"  {title}"))
    print(bold("=" * width))


def _subheader(title: str, width: int = 72) -> None:
    print()
    print(dim("-" * width))
    print(f"  {title}")
    print(dim("-" * width))


# ---------------------------------------------------------------------------
# MockAlationClient — reads terms from mock_glossary.json, no HTTP calls
# ---------------------------------------------------------------------------

class MockAlationClient:
    """
    Drop-in replacement for SwaggerAPIClient that serves terms from a local
    mock_glossary.json file instead of hitting a live Alation instance.

    Tier 1 (direct links) always misses — no Data Asset fields are set in the
    mock, so every asset goes through Tier 2 semantic matching or Tier 3 generation.
    """

    def __init__(self, glossary_path: Path = _MOCK_GLOSSARY_PATH):
        with open(glossary_path, encoding="utf-8") as f:
            data = json.load(f)
        self._terms: List[Dict[str, Any]] = data["terms"]
        self._glossary_name: str = data.get("glossary_name", "Mock Glossary")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def get_terms(
        self,
        glossary_id: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        terms = self._terms
        if limit:
            terms = terms[:limit]
        return terms

    async def get_all_columns(self, **kwargs) -> List[Dict[str, Any]]:
        return []

    async def get_column_by_id(self, column_id: int) -> Dict[str, Any]:
        return {}

    async def get_complete_glossary_with_technical_details(self, **kwargs) -> Dict[str, Any]:
        return {"terms": self._terms, "linked_terms": [], "unlinked_terms": self._terms, "columns": []}

    async def get_glossary_tree(self, **kwargs) -> Dict[str, Any]:
        return {"terms": self._terms}

    async def _get(self, *args, **kwargs) -> List:
        return []

    @staticmethod
    def clean_html_description(html: str) -> str:
        import re
        return re.sub(r"<[^>]+>", "", html).strip()

    def extract_data_asset_oid(self, term: Dict[str, Any]) -> Optional[int]:
        return None  # no direct links in mock

    def __repr__(self) -> str:
        return f"MockAlationClient(glossary='{self._glossary_name}', terms={len(self._terms)})"


# ---------------------------------------------------------------------------
# Phase 1: Parse input1.json
# ---------------------------------------------------------------------------

def phase_parse(filter_type: Optional[str]) -> List[AssetRecord]:
    _header("PHASE 1 — PARSE COMMON MODEL  (input1.json)")

    if not _INPUT_PATH.exists():
        print(red(f"  ERROR: input1.json not found at {_INPUT_PATH}"))
        sys.exit(1)

    with open(_INPUT_PATH, encoding="utf-8") as f:
        model = json.load(f)

    print(f"  Model:      {bold(model.get('name', 'unknown'))}")
    print(f"  Model ID:   {model.get('model_id', 'n/a')}")
    print(f"  Extracted:  {model.get('extracted_at', 'n/a')}")

    records = parse_common_model(model)

    by_type: dict[str, list] = {}
    for r in records:
        by_type.setdefault(str(r.asset_type), []).append(r)

    print()
    print(f"  {bold('Parsed assets:')}")
    for asset_type, group in sorted(by_type.items()):
        print(f"    {asset_type:<14}  {len(group):>3}")
    print(f"    {'TOTAL':<14}  {len(records):>3}")

    ids = [r.asset_id for r in records]
    if len(set(ids)) == len(ids):
        print(f"\n  {green('✓')} All {len(ids)} asset IDs are unique")
    else:
        print(f"\n  {red('✗')} {len(ids) - len(set(ids))} duplicate IDs detected")

    if filter_type:
        before = len(records)
        records = [r for r in records if str(r.asset_type) == filter_type]
        print(f"\n  Filter --asset-type {filter_type}: {before} → {len(records)} assets")

    return records


# ---------------------------------------------------------------------------
# Phase 2: Show context building (sample — one of each type)
# ---------------------------------------------------------------------------

def phase_context(records: List[AssetRecord]) -> None:
    _header("PHASE 2 — CONTEXT BUILDING  (LLM prompt assembly per asset type)")

    seen: set[str] = set()
    samples: list[AssetRecord] = []
    for r in records:
        t = str(r.asset_type)
        if t not in seen:
            seen.add(t)
            samples.append(r)
        if len(samples) >= 4:
            break

    for asset in samples:
        ctx = build_context(asset)
        _subheader(f"{str(asset.asset_type).upper()}  ·  {asset.name}")
        print(f"  {bold('Asset ID:')}   {dim(asset.asset_id)}")
        print(f"  {bold('Technical:')}  {ctx.technical_description[:200]}")
        print(f"  {bold('Context:')}    {ctx.business_context}")
        if ctx.usage_context and ctx.usage_context != "Usage across report pages not available.":
            print(f"  {bold('Usage:')}      {ctx.usage_context}")
        print(f"  {bold('LLM hint:')}   {ctx.enrichment_hint}")
        print(f"  {bold('Pre-class:')}  {ctx.suggested_classification}")


# ---------------------------------------------------------------------------
# Phase 3: Glossary preview (mock mode)
# ---------------------------------------------------------------------------

def phase_glossary_preview(client: MockAlationClient) -> None:
    _header("PHASE 3 — MOCK GLOSSARY  (target terms for Tier 2 matching)")

    print(f"  Source: {bold(str(_MOCK_GLOSSARY_PATH.relative_to(_REPO_ROOT)))}")
    print(f"  Terms:  {bold(str(len(client._terms)))} business terms loaded")
    print()
    print(f"  {bold('Sample terms (first 8):')}")
    for term in client._terms[:8]:
        import re
        desc_clean = re.sub(r"<[^>]+>", "", term.get("description", "")).strip()
        print(f"    [{term['id']:>4}]  {term['title']:<40}  {dim(desc_clean[:60])}")
    print(f"    {dim('... and')} {len(client._terms) - 8} {dim('more terms')}")
    print()
    print(f"  {yellow('▸')} Tier 1 (direct links):  always misses — no Data Asset fields set in mock")
    print(f"  {cyan('▸')} Tier 2 (semantic match): LLM scores each asset against all {len(client._terms)} terms")
    print(f"  {yellow('▸')} Tier 3 (generation):    fires for any asset the LLM cannot match above threshold")


# ---------------------------------------------------------------------------
# Phase 4: Enrichment (LLM + mock/live client)
# ---------------------------------------------------------------------------

async def phase_enrich(
    records: List[AssetRecord],
    client,
    glossary_id: int,
    confidence: int,
    use_mock: bool,
    max_concurrent: int = 5,
) -> list:
    from linker_agent.core.asset_matcher_service import AssetMatcherService

    source = f"mock glossary ({len(client._terms)} terms)" if use_mock else f"Alation glossary {glossary_id}"
    _header(f"PHASE 4 — ENRICHMENT  ({len(records)} assets · {source} · threshold {confidence}% · {max_concurrent} concurrent)")

    service = AssetMatcherService(
        swagger_client=client,
        glossary_id=glossary_id,
        confidence_threshold=confidence,
    )

    total = len(records)
    done_count = 0
    t0 = time.time()

    # ── Live progress counter ────────────────────────────────────────────────
    # enrich_batch() processes assets concurrently so we can't print inline
    # per-asset rows while they're in flight.  Instead we show a spinner that
    # updates every second, then print the full results table afterwards.

    spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    spinner_stop = asyncio.Event()

    async def _spinner():
        i = 0
        while not spinner_stop.is_set():
            elapsed = round(time.time() - t0, 1)
            frame   = spinner_frames[i % len(spinner_frames)]
            # \r rewrites the line; end="" keeps cursor there
            print(
                f"\r  {cyan(frame)}  Processing {total} assets concurrently "
                f"({max_concurrent} parallel LLM calls) … {elapsed}s",
                end="", flush=True,
            )
            await asyncio.sleep(1)
            i += 1
        # Clear the spinner line
        print("\r" + " " * 80 + "\r", end="", flush=True)

    spinner_task = asyncio.create_task(_spinner())

    try:
        results = await service.enrich_batch(records, max_concurrent=max_concurrent)
    finally:
        spinner_stop.set()
        await spinner_task

    elapsed_total = round(time.time() - t0, 1)

    # ── Results table (printed after all assets are done) ───────────────────
    print(f"  {'#':<5} {'TYPE':<14} {'ASSET NAME':<38} {'RESULT':<26} {'CONF':>5}  {'MATCHED TERM'}")
    print(dim("  " + "-" * 110))

    for i, (asset, result) in enumerate(zip(records, results), 1):
        asset_label = asset.name[:36]
        asset_type  = str(asset.asset_type)[:13]
        linkage     = result.linkage_type or "no_match"
        colour_fn   = TIER_COLOUR.get(linkage, dim)
        label       = TIER_LABEL.get(linkage, linkage)
        score       = f"{result.confidence_score}%" if result.confidence_score else " — "
        term        = (result.term_title or result.business_name or "")[:35]
        enriched    = "✦" if getattr(result, "description_enriched", False) else " "
        print(f"  {i:<5} {dim(asset_type):<14} {asset_label:<38} {colour_fn(label)}  {score:>5}  {enriched} {term}")

    print(dim(f"\n  {'─' * 110}"))
    print(f"  {green('✓')} Completed {total} assets in {bold(str(elapsed_total) + 's')}  "
          f"(was ~20 min sequential → now {elapsed_total}s concurrent)")

    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_asset_detail(r) -> None:
    """Print full detail for one result — tier, linkage, original vs enriched definition, Tier 3 recommendations."""
    colour_fn  = TIER_COLOUR.get(r.linkage_type or "no_match", dim)
    tier_str   = colour_fn(TIER_LABEL.get(r.linkage_type, r.linkage_type or "no_match").strip())
    enriched   = getattr(r, "description_enriched", False)
    enriched_badge = f"  {green('✦ enriched')}" if enriched else ""

    print(f"\n  {bold(r.asset_name)}  {dim(f'({r.asset_type})')}")
    print(f"    Tier:              {tier_str}  ({r.confidence_score}% confidence)")
    if r.term_title:
        print(f"    Glossary term:     {cyan(r.term_title)}{enriched_badge}")
    if r.metric_classification and r.metric_classification != "unclassified":
        print(f"    Classification:    {r.metric_classification}")
    if r.purpose_statement:
        print(f"    Purpose:           {r.purpose_statement}")

    if r.business_definition:
        label = green("Definition (enriched):") if enriched else dim("Definition:")
        print(f"    {label}")
        print(f"      {r.business_definition[:280]}")

    if r.matching_rationale:
        print(f"    Rationale:         {dim(r.matching_rationale[:160])}")

    # Tier 3 recommendations
    recs = getattr(r, "tier3_recommendations", None)
    if recs:
        rank_labels = {1: green("★ Best fit"), 2: cyan("  2nd     "), 3: yellow("  3rd     ")}
        print(f"    {bold('Tier 3 recommendations')} ({len(recs)} options for data steward):")
        for rec in recs:
            rank      = rec.get("rank", 0)
            label     = rank_labels.get(rank, dim(f"  #{rank}    "))
            conf      = rec.get("confidence", 0)
            title     = rec.get("term_title", "")
            desc      = rec.get("term_description", "")[:180]
            rationale = rec.get("rationale", "")[:120]
            print(f"      {label}  [{conf}%]  {bold(title)}")
            print(f"                 {dim(desc)}")
            if rationale:
                print(f"                 {dim('why: ' + rationale)}")


# ---------------------------------------------------------------------------
# Phase 5: Results summary + save
# ---------------------------------------------------------------------------

def phase_results(results: list, records: List[AssetRecord]) -> None:
    from linker_agent.core.event_log_service import get_all_events

    _header("PHASE 5 — RESULTS & SAVED OUTPUT")

    tier_counts: dict[str, int] = {}
    by_type: dict[str, dict[str, int]] = {}
    confidences: list[float] = []
    enriched_count = 0

    for r in results:
        lt = r.linkage_type or "no_match"
        tier_counts[lt] = tier_counts.get(lt, 0) + 1
        at = str(r.asset_type)
        by_type.setdefault(at, {})
        by_type[at][lt] = by_type[at].get(lt, 0) + 1
        if r.confidence_score:
            confidences.append(r.confidence_score)
        if getattr(r, "description_enriched", False):
            enriched_count += 1

    total    = len(results)
    matched  = sum(v for k, v in tier_counts.items() if k not in ("no_match", "error"))
    rate     = round(matched / total * 100, 1) if total else 0
    avg_conf = round(sum(confidences) / len(confidences), 1) if confidences else 0

    # Summary table
    print(f"\n  {bold('Overall:')}")
    print(f"    Total assets         {total}")
    print(f"    Matched              {matched}  ({rate}%)")
    print(f"    Unmatched            {total - matched}")
    print(f"    Avg confidence       {avg_conf}%")
    print(f"    Descriptions enriched {green(str(enriched_count))}  (Tier 2 context-enhanced definitions)")

    print(f"\n  {bold('By tier:')}")
    for tier, count in sorted(tier_counts.items(), key=lambda x: -x[1]):
        colour_fn = TIER_COLOUR.get(tier, dim)
        label     = TIER_LABEL.get(tier, tier).strip()
        bar       = "█" * count
        print(f"    {colour_fn(f'{label:<22}')}  {count:>3}  {dim(bar)}")

    print(f"\n  {bold('By asset type:')}")
    for at, tiers in sorted(by_type.items()):
        parts = "  ".join(
            f"{TIER_COLOUR.get(t, dim)(t[:3].upper())}:{n}"
            for t, n in sorted(tiers.items(), key=lambda x: -x[1])
        )
        print(f"    {at:<14}  {parts}")

    # Calculation spotlight (most business-critical)
    calcs = [r for r in results if str(r.asset_type) in ("calculation", "kpi")]
    if calcs:
        _subheader("Calculation & KPI spotlight")
        for r in calcs:
            _print_asset_detail(r)

    # Tier 3 generated-term spotlight
    generated_assets = [r for r in results if r.linkage_type == "generated"]
    if generated_assets:
        _subheader(f"Tier 3 — Generated Term Recommendations  ({len(generated_assets)} assets)")
        for r in generated_assets:
            _print_asset_detail(r)

    # Save outputs
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results_path = _OUTPUT_DIR / "enrichment_results.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump([r.model_dump() for r in results], f, indent=2)

    events = get_all_events()
    event_log_path = _OUTPUT_DIR / "event_log.jsonl"
    with open(event_log_path, "w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")

    summary = {
        "total_assets": total,
        "matched": matched,
        "match_rate_pct": rate,
        "avg_confidence": avg_conf,
        "tier_breakdown": tier_counts,
        "by_asset_type": by_type,
        "event_count": len(events),
    }
    summary_path = _OUTPUT_DIR / "showcase_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\n  {green('✓')} enrichment_results.json      → {results_path}  ({total} assets)")
    print(f"  {green('✓')} event_log.jsonl              → {event_log_path}  ({len(events)} events)")
    print(f"  {green('✓')} showcase_summary.json        → {summary_path}")
    print(f"  {green('✓')} showcase_terminal_output.txt → {_OUTPUT_DIR / 'showcase_terminal_output.txt'}")


# ---------------------------------------------------------------------------
# Dry-run: parse + context only
# ---------------------------------------------------------------------------

def dry_run(records: List[AssetRecord]) -> None:
    _header("DRY RUN — Parse and Context Building Only  (no LLM / Alation calls)")

    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for asset in records:
        ctx = build_context(asset)
        out.append({
            "asset_id":                asset.asset_id,
            "asset_type":              str(asset.asset_type),
            "name":                    asset.name,
            "source_tool":             asset.context.source_tool,
            "model_name":              asset.context.model_name,
            "technical_description":   ctx.technical_description,
            "business_context":        ctx.business_context,
            "usage_context":           ctx.usage_context,
            "enrichment_hint":         ctx.enrichment_hint,
            "suggested_classification":ctx.suggested_classification,
            "pages_used_on":           ctx.pages_used_on,
        })

    dry_path = _OUTPUT_DIR / "dry_run_asset_records.json"
    with open(dry_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    print(f"  Parsed {len(records)} AssetRecords from input1.json")
    print(f"  {green('✓')} LLM context for each asset saved → {dry_path}")
    print()
    print(f"  {bold('Sample (first 3):')}")
    for item in out[:3]:
        print()
        print(f"    {bold(item['name'])}  ({item['asset_type']})")
        print(f"    ID:   {dim(item['asset_id'])}")
        print(f"    Desc: {item['technical_description'][:160]}...")
        print(f"    Hint: {item['enrichment_hint']}")

    print()
    print(f"  Run with {bold('--use-mock-glossary')} to add LLM enrichment (no Alation needed).")
    print(f"  Run without flags for full live-Alation pipeline.")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Linker Agent pipeline showcase — input1.json → enriched output"
    )
    p.add_argument("--dry-run",          action="store_true",
                   help="Parse and build context only. No LLM or Alation calls.")
    p.add_argument("--use-mock-glossary", action="store_true",
                   help="Use mock_glossary.json instead of a live Alation instance.")
    p.add_argument("--asset-type",
                   choices=["table", "column", "dimension", "measure", "calculation", "kpi"],
                   default=None,
                   help="Process only this asset type (default: all 97 assets).")
    p.add_argument("--glossary-id",  type=int, default=2,
                   help="Alation glossary ID (live mode only, default: 2).")
    p.add_argument("--confidence",   type=int, default=60,
                   help="Minimum Tier 2 confidence threshold (default: 60).")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def _main() -> None:
    args = _parse_args()

    # Tee stdout → terminal + plain-text file
    _tee = TeeOutput(_OUTPUT_DIR / "showcase_terminal_output.txt")
    sys.stdout = _tee

    print()
    print(bold("╔══════════════════════════════════════════════════════════════════════╗"))
    print(bold("║            LINKER AGENT — PIPELINE SHOWCASE                          ║"))
    print(bold("║  input1.json  →  parse  →  enrich  →  output/                        ║"))
    if args.use_mock_glossary:
        print(bold("║  Mode: mock glossary  (no live Alation required)                     ║"))
    elif args.dry_run:
        print(bold("║  Mode: dry run  (parse + context only)                               ║"))
    else:
        print(bold("║  Mode: live Alation                                                  ║"))
    print(bold("╚══════════════════════════════════════════════════════════════════════╝"))

    # Phase 1 — Parse
    records = phase_parse(args.asset_type)

    if args.dry_run:
        phase_context(records)
        dry_run(records)
        return

    # Phase 2 — Context building preview
    phase_context(records)

    if args.use_mock_glossary:
        # Mock mode — no Alation connection needed
        if not _MOCK_GLOSSARY_PATH.exists():
            print(red(f"\n  ERROR: mock_glossary.json not found at {_MOCK_GLOSSARY_PATH}"))
            sys.exit(1)

        client = MockAlationClient(_MOCK_GLOSSARY_PATH)

        # Phase 3 — Glossary preview
        phase_glossary_preview(client)

        # Phase 4 — Enrich
        results = await phase_enrich(
            records, client, args.glossary_id, args.confidence, use_mock=True
        )
    else:
        # Live mode — real Alation connection
        from linker_agent.clients.alation_client import SwaggerAPIClient, SwaggerAPIConfig
        from linker_agent.config import get_config
        cfg = get_config()
        api_config = SwaggerAPIConfig(
            base_url=cfg.alation_base,
            api_token=cfg.alation_api_token,
        )
        async with SwaggerAPIClient(api_config) as client:
            results = await phase_enrich(
                records, client, args.glossary_id, args.confidence, use_mock=False
            )

    # Phase 5 — Results + save
    phase_results(results, records)

    print()
    print(bold("╔══════════════════════════════════════════════════════════════════════╗"))
    print(bold("║  SHOWCASE COMPLETE — results saved to output/                        ║"))
    print(bold("╚══════════════════════════════════════════════════════════════════════╝"))
    print()

    # Restore stdout and close log file
    sys.stdout = _tee._terminal
    _tee.close()
    print(f"Terminal output saved → {_OUTPUT_DIR / 'showcase_terminal_output.txt'}")


if __name__ == "__main__":
    asyncio.run(_main())
