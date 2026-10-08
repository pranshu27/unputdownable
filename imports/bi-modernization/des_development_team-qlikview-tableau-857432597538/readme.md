# Linker Agent

**Linker Agent** automatically connects BI report assets — DAX calculations, columns, and tables from Power BI, Tableau, or Qlik — to their matching business glossary terms in Alation. Every asset receives a context-aware business definition ready to write back to the catalog.

---

## The Problem It Solves

When a BI developer builds a Power BI report they create assets like `CAGR (%)`, `Loan Eligible`, or `FCT Insurance_Policy_Table`. These names mean something to the developer, but a business user browsing the Alation catalog sees a technical label with no business context.

At the same time, the data governance team has spent time writing glossary terms like **Compound Annual Growth Rate** and **Loan Eligibility Indicator** — but those terms are not linked to the actual report columns, so neither side of the catalog is useful.

Linker Agent closes this gap automatically:

1. It reads the structured model JSON produced by the RE (Reverse Engineering) pipeline — a description of every asset in a report.
2. It runs each asset through a three-tier matching engine to find the correct glossary term in Alation.
3. It generates a catalog-ready, context-aware business definition for each asset — incorporating the matched term's meaning, the report name, the pages the asset appears on, and the visual types it powers.
4. It makes results available for write-back to Alation via REST API.

---

## How It Works — The Three Tiers

Every asset is processed in sequence through three tiers, stopping as soon as a match is found.

| Tier | Name | What happens | When it fires |
|------|------|--------------|---------------|
| **1** | Direct Link | Asset already has a Data Asset field in Alation pointing directly to a glossary term. Instant match, no LLM call. | Only when the catalog has pre-existing links |
| **2** | Semantic Match | The LLM receives the full asset context (name, type, DAX expression, page usage, visual types) and the complete glossary. It identifies the closest matching term and simultaneously writes a context-enriched definition. | Most assets — 93 of 97 in the sample run |
| **3** | Term Generation | No existing term is a good fit. The LLM generates three ranked candidate business terms for a data steward to review and select. | Assets genuinely absent from the glossary |

**Validated run results** on the Tru Secure CreDebit Dashboard (97 assets, 42 glossary terms):

| Metric | Result |
|--------|--------|
| Match rate | 100% (97 / 97) |
| Average confidence | 93.4% |
| Tier 2 semantic matches | 93 — all with enriched definitions |
| Tier 3 generated terms | 4 — each with 3 ranked recommendations |
| Total run time | ~4.2 minutes (concurrent processing) |

---

## A Real Example: CAGR (%)

**Input** (from `input1.json`):
```
name: "CAGR (%)"
semantic_type: growth_rate
aggregation_behavior: non_additive
expression: (POWER(DIVIDE(Maturity, TotalPremium), 1/Years) - 1)
pages: Summary, Insurance Overview, Investment Amount Vs Maturity Amount
```

**Pipeline result:**
- **Tier 1** → miss (no Data Asset link set)
- **Tier 2** → matched to **Compound Annual Growth Rate** (98% confidence)
- **Business definition written to catalog:**
  > The compound annual growth rate (CAGR) measures the mean annual growth rate of premium or investment value across the Tru Secure CreDebit portfolio over the policy term. It is displayed as a percentage on the Summary, Insurance Overview, Investment Amount Vs Maturity Amount, and Annual Premium Vs Protection Value pages in card, table, and combo chart visuals. It is calculated by comparing total premium paid to the policy maturity amount over the policy tenure in years and is a non-additive ratio metric that must not be summed across segments.

The enriched definition combines the glossary term's meaning with the specific report name, formula, pages, and visual types — ready for a data steward to approve and publish.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                         Clients                                   │
│   Alation Agent Studio (MCP) port 8001  │  REST API port 3005    │
└─────────────────────┬────────────────────────────────────────────┘
                      │
┌─────────────────────▼────────────────────────────────────────────┐
│                    Ingestion Layer                                 │
│  model_parser.py — parses RE Common Model JSON → AssetRecord[]    │
│  context_builder.py — assembles asset-type-aware LLM context      │
└─────────────────────┬────────────────────────────────────────────┘
                      │
┌─────────────────────▼────────────────────────────────────────────┐
│                    Service Layer                                   │
│  AssetMatcherService (orchestration, concurrency, event logging)  │
└─────────────────────┬────────────────────────────────────────────┘
                      │
┌─────────────────────▼────────────────────────────────────────────┐
│                    Core Matching Engine                            │
│  ColumnMetadataLookup — Tier 1 / Tier 2 / Tier 3                 │
└─────────────────────┬────────────────────────────────────────────┘
                      │
┌─────────────────────▼────────────────────────────────────────────┐
│                   External Systems                                 │
│    Alation (data catalog)    │    Azure OpenAI (LLM)              │
└──────────────────────────────────────────────────────────────────┘
```

---

## Asset Types Supported

| Type | Description | Example |
|------|-------------|---------|
| `calculation` | DAX measure, Tableau calc field, Qlik expression | `CAGR (%)`, `Annual ROI` |
| `column` | Standard table column | `Customer ID`, `Policy Number` |
| `dimension` | Column with a group-by / filter role | `Gender`, `Policy Type` |
| `measure` | Column with an aggregation role | `Total Premium Amount` |
| `table` | Logical table in the report model | `FCT Insurance_Policy_Table` |

---

## Output Fields (per asset)

| Field | Description |
|-------|-------------|
| `asset_id` | Stable synthetic ID (`powerbi::dashboard::type::name`) |
| `asset_type` | `calculation`, `column`, `dimension`, `measure`, `table` |
| `term_title` | Matched glossary term name (e.g., "Compound Annual Growth Rate") |
| `term_id` | Alation glossary term ID — used for write-back |
| `confidence_score` | Match confidence 0–100 |
| `linkage_type` | `direct`, `semantic`, `generated`, or `no_match` |
| `business_definition` | Context-enriched definition ready for catalog write-back |
| `description_enriched` | `true` when the definition was LLM-enhanced beyond the glossary text |
| `purpose_statement` | Where and how the asset is used in visuals |
| `metric_classification` | `kpi`, `measure`, `ratio`, `dimension`, `identifier`, `date` |
| `tier3_recommendations` | (Tier 3 only) 3 ranked candidate terms for steward review |
| `matching_rationale` | LLM explanation of why this term was selected |

---

## Enrichment vs. Write-back

The pipeline produces enrichment results automatically. **Write-back to Alation is a separate, explicit step** — this is intentional so that data stewards can review results before they are published.

See [WRITE_CAPABILITIES.md](WRITE_CAPABILITIES.md) for the full write-back API reference and workflow.

---

## Project Structure

```
linker_agent/
├── api/
│   ├── main.py                      # FastAPI app, lifespan, CORS, route registration
│   └── routes/
│       ├── assets.py                # POST /assets/ingest-model, /match, /batch-match
│       ├── alation_route.py         # GET /alation/*
│       ├── column_route.py          # GET|POST /columns/* (backward-compatible)
│       └── curation_route.py        # PUT /curation/* (write-back endpoints)
├── ingestion/
│   ├── model_parser.py              # RE Common Model JSON → AssetRecord[]
│   └── context_builder.py           # Asset-type-aware LLM context assembly
├── clients/
│   └── alation_client.py            # Async HTTP wrapper for all Alation API calls
├── core/
│   ├── asset_matcher_service.py     # Orchestration: concurrent batch + event logging
│   ├── column_metadata_lookup.py    # Tier 1 / 2 / 3 engine + description enrichment
│   ├── event_log_service.py         # Append-only event log (in-memory + JSONL)
│   └── tier2_semantic_matcher.py    # Pipeline B: term → column direction
├── models/
│   ├── asset_record.py              # AssetRecord, AssetLinkResult, enums
│   ├── event_log.py                 # AssetEvent, EventAction
│   └── curation_models.py           # Request/response models for write-back
├── services/
│   ├── curation_service.py          # Write-back orchestration + error mapping
│   └── enrichment_service.py        # Pipeline B orchestrator
├── utils/
│   ├── llm_factory.py               # Azure OpenAI client builder
│   └── html_cleaner.py              # Strips HTML from Alation descriptions
├── tests/
│   └── run_pipeline_showcase.py     # End-to-end showcase script
├── input1.json                      # Sample RE Common Model (Power BI insurance dashboard)
├── mock_glossary.json               # 42-term mock glossary (no live Alation required)
└── config.py                        # Environment-based configuration

output/                              # Written at runtime
├── enrichment_results.json          # Full AssetLinkResult list
├── event_log.jsonl                  # Audit trail — one JSON event per asset per run
├── showcase_summary.json            # Tier breakdown and statistics
└── showcase_terminal_output.txt     # Plain-text copy of terminal run
```

---

## Quick Links

- **Setup and running the pipeline:** [SETUP_AND_RUN.md](SETUP_AND_RUN.md)
- **Write-back to Alation:** [WRITE_CAPABILITIES.md](WRITE_CAPABILITIES.md)
- **Visual pipeline flow diagram:** [PIPELINE_FLOW.md](PIPELINE_FLOW.md)
- **Full API reference:** `http://localhost:3005/docs` (when running locally)
