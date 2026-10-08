# Setup and Running the Pipeline

This guide covers everything needed to install, configure, and run Linker Agent — from local development to a full production run against live Alation.

---

## Prerequisites

| Requirement | Version / Notes |
|-------------|-----------------|
| Python | 3.12 or higher |
| Azure OpenAI | Deployed instance with a GPT-4 or GPT-4o deployment |
| Alation | API token with read access to the target glossary; write access for curation endpoints |
| pip | Latest recommended |

---

## 1. Installation

Clone the repository and install dependencies from the project root:

```bash
pip install -r requirements.txt
```

To install the `linker_agent` package itself in editable mode (so imports resolve correctly):

```bash
pip install -e ./linker_agent
```

---

## 2. Environment Configuration

Create a `.env` file in the project root (next to `requirements.txt`). All credentials are loaded from here — nothing is hardcoded.

```env
# ── Azure OpenAI ────────────────────────────────────────────────────────────
AZURE_OPENAI_API_BASE=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_DEPLOYMENT=gpt-4
AZURE_OPENAI_API_VERSION=2024-02-15-preview

# ── Alation ─────────────────────────────────────────────────────────────────
ALATION_BASE_URL=https://your-alation-instance.com
ALATION_API_TOKEN=your-api-token
ALATION_GLOSSARY_ID=1          # ID of the target glossary in Alation

# ── Pipeline behaviour ──────────────────────────────────────────────────────
LINKER_CONFIDENCE_THRESHOLD=60  # Minimum LLM confidence to accept a Tier 2 match (0–100)
LINKER_CACHE_HOURS=24           # How long to cache fetched Alation glossary data on disk
LINKER_CACHE_DIR=./cache
```

> For the mock/offline mode described below, only the Azure OpenAI variables are required — no Alation credentials needed.

---

## 3. Running the Pipeline Showcase

The showcase script is the primary way to run and validate the pipeline. It reads `linker_agent/input1.json` (the sample Power BI insurance dashboard model), runs all 97 assets through the 3-tier enrichment pipeline, and saves results to `output/`.

### Option A — Mock glossary (no live Alation required)

Uses `linker_agent/mock_glossary.json` (42 insurance domain terms). Tier 1 direct links always miss in this mode — every asset goes through Tier 2 semantic matching or Tier 3 generation. **This is the recommended starting point.**

```bash
python -m linker_agent.tests.run_pipeline_showcase --use-mock-glossary
```

Expected runtime: ~4–5 minutes (97 assets, 5 concurrent LLM calls).

### Option B — Live Alation glossary

```bash
python -m linker_agent.tests.run_pipeline_showcase --glossary-id 2
```

Requires `ALATION_BASE_URL` and `ALATION_API_TOKEN` in `.env`. The glossary at `--glossary-id` is fetched and cached locally for 24 hours (configurable via `LINKER_CACHE_HOURS`).

### Option C — Dry run (no LLM calls)

Parse the input model and build per-asset context without calling the LLM or Alation. Useful for verifying the model parses correctly and the context looks right.

```bash
python -m linker_agent.tests.run_pipeline_showcase --dry-run
```

Writes parsed assets with their LLM context to `output/dry_run_asset_records.json`.

### Option D — Filter by asset type

Process only a subset of asset types — useful for quick demos or targeted testing.

```bash
# Only the 11 DAX calculations
python -m linker_agent.tests.run_pipeline_showcase --use-mock-glossary --asset-type calculation

# Only columns
python -m linker_agent.tests.run_pipeline_showcase --use-mock-glossary --asset-type column
```

### All flags

| Flag | Description | Default |
|------|-------------|---------|
| `--use-mock-glossary` | Use local `mock_glossary.json` instead of live Alation | Off |
| `--dry-run` | Parse and build context only, no LLM/Alation calls | Off |
| `--asset-type TYPE` | Filter to one asset type (`calculation`, `column`, `dimension`, `measure`, `table`) | All types |
| `--glossary-id N` | Alation glossary ID to fetch | From `.env` |
| `--confidence N` | Confidence threshold override (0–100) | 60 |

---

## 4. Output Files

After a successful run, four files are written to `output/`:

### `enrichment_results.json`
The primary output — a JSON array with one `AssetLinkResult` object per asset.

```json
[
  {
    "asset_id": "powerbi::tru_secure_credebit_dashboard::calc::cagr",
    "asset_name": "CAGR (%)",
    "asset_type": "calculation",
    "term_title": "Compound Annual Growth Rate",
    "term_id": 1001,
    "confidence_score": 98,
    "linkage_type": "semantic",
    "business_definition": "The compound annual growth rate (CAGR) measures...",
    "description_enriched": true,
    "purpose_statement": "Used on Summary, Insurance Overview pages in card visuals...",
    "metric_classification": "ratio",
    "tier3_recommendations": null,
    "matching_rationale": "Exact semantic match to Compound Annual Growth Rate...",
    "enriched_at": "2026-05-07T00:38:16Z",
    "model_id": "23ae2cb4-ed9b-4dc0-a835-822f59b2a56c"
  }
]
```

`linkage_type` values:
- `direct` — Tier 1 match (pre-existing Data Asset link in Alation)
- `semantic` — Tier 2 match (LLM semantic match to existing glossary term)
- `generated` — Tier 3 match (LLM generated a new term; see `tier3_recommendations`)
- `no_match` — No match found above the confidence threshold
- `error` — Processing error (details in `matching_rationale`)

### `event_log.jsonl`
An append-only audit trail — one JSON object per line, one per asset. Records which tier fired and why.

```jsonl
{"event_id":"a1b2...","asset_id":"powerbi::...::calc::cagr","action":"tier2_semantic_match","confidence":98,"before_state":"extracted","after_state":"enriched","payload":{"term_title":"Compound Annual Growth Rate"},"timestamp":"2026-05-07T00:38:16Z"}
```

### `showcase_summary.json`
High-level statistics for dashboarding or reporting:

```json
{
  "total_assets": 97,
  "matched": 97,
  "match_rate_pct": 100.0,
  "avg_confidence": 93.4,
  "tier_breakdown": { "semantic": 93, "generated": 4 },
  "by_asset_type": {
    "calculation": { "semantic": 10, "generated": 1 },
    "column":      { "semantic": 29, "generated": 2 },
    "dimension":   { "semantic": 34, "generated": 1 },
    "measure":     { "semantic": 11 },
    "table":       { "semantic": 9 }
  }
}
```

### `showcase_terminal_output.txt`
Plain-text copy of the full terminal output (ANSI colour codes stripped). Useful for sharing a run result without needing a terminal.

---

## 5. Running the REST API

The REST API exposes the same pipeline over HTTP. It is built with FastAPI and serves interactive documentation at `/docs`.

```bash
python -m linker_agent.api.main
```

The server starts on **port 3005**. API docs: `http://localhost:3005/docs`

### Key endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/assets/ingest-model` | Send a full RE Common Model JSON; returns enriched results |
| `POST` | `/assets/batch-match` | Send a list of `AssetRecord` objects |
| `POST` | `/assets/match` | Enrich a single `AssetRecord` |
| `GET` | `/assets/events` | Full audit event log |
| `PUT` | `/curation/term-description` | Write a definition back to Alation |
| `PUT` | `/curation/custom-field-values` | Batch-update custom fields on a term |

Example — send the full model and receive enriched results:

```bash
curl -X POST http://localhost:3005/assets/ingest-model \
  -H "Content-Type: application/json" \
  -d @linker_agent/input1.json
```

---

## 6. Running the MCP Server (Alation Agent Studio)

The MCP server exposes 7 tools callable directly from Alation Agent Studio.

```bash
python -m linker_agent.mcp_server
```

Starts on **port 8001**. See the main [README.md](README.md) for the full tool list.

---

## 7. Running with Docker

Both the API and MCP server are containerised. From the project root:

```bash
docker-compose up --build
```

| Container | Port | Role |
|-----------|------|------|
| `linker-api` | 3005 | REST API |
| `linker-mcp` | 8001 | MCP server for Alation Agent Studio |

The `./cache` and `./output` directories are mounted into both containers, so glossary cache and enrichment results persist on the host.

Ensure `.env` is in the project root before running — Docker Compose picks it up automatically.

---

## 8. Running Tests

```bash
pytest linker_agent/tests/ -v
```

| File | What it tests |
|------|---------------|
| `test_curation_service.py` | All write-back paths, including HTTP error mapping |
| `test_alation_client.py` | The async aiohttp client layer |
| `test_all_three_tiers.py` | End-to-end 3-tier pipeline |
| `test_ingestion.py` | Model parser and context builder |

---

## Common Issues

**`ModuleNotFoundError: No module named 'linker_agent'`**
Run `pip install -e ./linker_agent` from the project root.

**`AuthenticationError` from Azure OpenAI**
Check `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_API_BASE`, and `AZURE_OPENAI_DEPLOYMENT` in `.env`. The deployment name must match exactly what is configured in the Azure portal.

**`aiohttp.ClientConnectorError` when connecting to Alation**
Check `ALATION_BASE_URL` (must include `https://`, no trailing slash) and confirm the API token has not expired.

**Pipeline runs but all results are `no_match`**
The confidence threshold may be too high for the glossary. Try lowering it: `--confidence 50`. Also check that `ALATION_GLOSSARY_ID` points to a glossary that contains terms.

**Run takes longer than expected**
The first run fetches and caches the full glossary from Alation. Subsequent runs use the disk cache (`./cache/`) and are significantly faster. Increase `--max-concurrent` (default 5) if the LLM deployment allows higher throughput.
