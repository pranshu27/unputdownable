# Linker Agent — UI Integration Guide

This guide is for the UI developer. It covers every API endpoint the frontend needs, the exact request and response shapes, and what to render for each field.

---

## Base URL & Headers

```
Base URL:  http://localhost:3005
Headers:   Content-Type: application/json
```

Full interactive docs (Swagger UI) are available at `http://localhost:3005/docs` while the server is running.

---

## The Bulk Enrichment Flow

This is the primary showcase flow — one button press enriches everything in the database.

```
1.  GET  /assets/jobs              → show available jobs to the user (optional preview step)
2.  POST /assets/ingest-all-jobs   → run enrichment on all jobs, stream back results
3.  Render the BatchEnrichmentResponse
```

---

## Endpoint Reference

### 1. `GET /assets/jobs`
Lists all rationalization jobs available in the Postgres catalog with asset counts. Use this to populate a preview panel or job selector before running enrichment.

**Request**
```
GET /assets/jobs
```
No body, no params.

**Response** — `200 OK`, array of job summaries
```json
[
  {
    "job_id":            "d27d8f5c-5547-4a99-b4da-a7adb8197b71",
    "total_assets":      114,
    "kpi_count":         13,
    "attribute_count":   101,
    "source_tool_count": 2,
    "sample_verdict":    "Keep",
    "latest_entry":      "ff3a9c..."
  }
]
```

| Field | What to display |
|---|---|
| `job_id` | Identifier — pass this to single-job endpoint |
| `total_assets` | "114 assets" |
| `kpi_count` | "13 KPIs" |
| `attribute_count` | "101 Attributes" |
| `source_tool_count` | "2 tools" |

**Error** — `503` if Postgres is unreachable.

---

### 2. `POST /assets/ingest-all-jobs` ← **Primary bulk endpoint**
Fetches all jobs from Postgres and runs the full 3-tier enrichment pipeline on every asset. This is the one call for the bulk showcase button.

**Request**
```
POST /assets/ingest-all-jobs
```
All params are optional query strings:

| Param | Type | Default | Description |
|---|---|---|---|
| `verdict_filter` | `string[]` | all | Repeat for each verdict to include: `Keep`, `Merge`, `Standardize`, `Retire`. Recommended: exclude `Retire`. |
| `item_type` | `string` | both | `KPI` or `Attribute`. Leave blank for both. |

**Recommended call for the showcase:**
```
POST /assets/ingest-all-jobs?verdict_filter=Keep&verdict_filter=Merge&verdict_filter=Standardize
```

**Response** — `200 OK`, `BatchEnrichmentResponse`
```json
{
  "total_jobs":              5,
  "total_assets_processed":  455,
  "overall_match_rate_pct":  94.3,
  "elapsed_seconds":         187.4,
  "jobs": [
    {
      "job_id":          "d27d8f5c-...",
      "total_assets":    86,
      "matched":         82,
      "match_rate_pct":  95.3,
      "elapsed_seconds": 41.2,
      "verdict_filter":  ["Keep", "Merge", "Standardize"],
      "results": [
        {
          "asset_id":            "powerbi(toolname)$Tru Secure CreDebit Dashboard...$CAGR (%)",
          "asset_type":          "kpi",
          "asset_name":          "CAGR (%)",
          "term_title":          "Compound Annual Growth Rate",
          "term_id":             1001,
          "confidence_score":    95,
          "linkage_type":        "semantic",
          "matching_rationale":  "Exact semantic match to 'Compound Annual Growth Rate'...",
          "business_definition": "The compound annual growth rate (CAGR) measures...",
          "description_enriched": true,
          "purpose_statement":   null,
          "metric_classification": "ratio",
          "tier3_recommendations": null,
          "enriched_at":         "2026-05-20T12:48:07Z",
          "model_id":            "d27d8f5c-..."
        }
      ]
    }
  ]
}
```

**Errors**
| Code | Meaning |
|---|---|
| `503` | Postgres is unreachable |
| `404` | No jobs found in the catalog |

> **Note on response time:** With 5 jobs and ~460 assets (excluding Retire), expect 3–7 minutes. Show a loading state with the elapsed time. Assets within each job run concurrently (5 parallel LLM calls); jobs run sequentially.

---

### 3. `POST /assets/ingest-from-postgres` — Single job
Run enrichment on one specific job. Use when the user selects a job from the job list.

**Request**
```
POST /assets/ingest-from-postgres?job_id=d27d8f5c-...&verdict_filter=Keep&verdict_filter=Merge&verdict_filter=Standardize
```

| Param | Required | Description |
|---|---|---|
| `job_id` | Yes | UUID from `GET /assets/jobs` |
| `verdict_filter` | No | Repeat param. Recommended: Keep, Merge, Standardize |
| `item_type` | No | `KPI` or `Attribute` |

**Response** — `200 OK`, `AssetLinkResult[]` (flat array, no wrapper)
Same `AssetLinkResult` objects as shown in the bulk response above.

**Errors** — `503` Postgres unreachable, `404` no assets match filters.

---

## Key Fields to Render

Every enriched asset returns an `AssetLinkResult`. Here's what matters for the UI:

### Asset identity
| Field | Value examples | Display as |
|---|---|---|
| `asset_name` | `"CAGR (%)"`, `"Customer ID"` | Row title |
| `asset_type` | `"kpi"`, `"calculation"`, `"column"`, `"dimension"`, `"measure"`, `"table"` | Badge/pill |
| `asset_id` | long stable string | Tooltip / copy button |

### Match result
| Field | Value examples | Display as |
|---|---|---|
| `linkage_type` | `"semantic"`, `"direct"`, `"generated"`, `"no_match"`, `"error"` | Coloured tier badge (see below) |
| `confidence_score` | `0`–`100` | Progress bar or `"95%"` |
| `term_title` | `"Compound Annual Growth Rate"` | Linked glossary term name |
| `term_id` | `1001` | Use for Alation write-back link |

### Tier badge colour guide
| `linkage_type` | Label | Suggested colour |
|---|---|---|
| `direct` | Tier 1 — Direct Link | Green |
| `semantic` | Tier 2 — Semantic Match | Blue |
| `generated` | Tier 3 — New Term | Amber |
| `no_match` | No Match | Grey |
| `error` | Error | Red |

### Enriched definition
| Field | Display rule |
|---|---|
| `business_definition` | Main definition text block. Always show when non-null. |
| `description_enriched` | Show a "✦ AI-enriched" badge when `true` |
| `matching_rationale` | Show in a collapsed detail / tooltip — explains why this term was chosen |
| `metric_classification` | Small label: `"kpi"`, `"ratio"`, `"dimension"`, `"measure"`, `"identifier"`, `"date"` |

### Tier 3 only — new term candidates
When `linkage_type === "generated"`, `tier3_recommendations` is an array of up to 3 ranked options for the data steward to choose from:
```json
[
  { "rank": 1, "term_title": "Ten Percent Discount", "confidence": 90, "term_description": "...", "rationale": "..." },
  { "rank": 2, "term_title": "Fixed Discount Rate",  "confidence": 75, "term_description": "...", "rationale": "..." },
  { "rank": 3, "term_title": "Line Item Discount",   "confidence": 60, "term_description": "...", "rationale": "..." }
]
```
Render these as a radio group labelled "Select the best term" with rank 1 pre-selected.

---

## Suggested UI Layout for Bulk Enrichment

```
┌────────────────────────────────────────────────────────┐
│  Bulk Enrichment                          [Run All Jobs]│
│  5 jobs · 568 assets · Exclude: Retire                 │
└────────────────────────────────────────────────────────┘

  While running:
  ┌──────────────────────────────────────────────────────┐
  │  ⟳  Processing job 2 of 5 — 41s elapsed              │
  │  ████████████░░░░░░░░  job 1 complete (86 assets)     │
  └──────────────────────────────────────────────────────┘

  Results panel (per job):
  ┌──────────────────────────────────────────────────────┐
  │  Job d27d8f5c · 86 assets · 95.3% match · 41s        │
  │  ─────────────────────────────────────────────────── │
  │  [kpi]  CAGR (%)          [Tier 2] 95%  ✦             │
  │          Compound Annual Growth Rate                  │
  │          The CAGR measures...                         │
  │  [kpi]  10% discount      [Tier 3] 90%               │
  │          ● Ten Percent Discount   ○ Fixed Discount... │
  │  [col]  Customer ID       [Tier 2] 88%               │
  │          Customer Identifier                          │
  └──────────────────────────────────────────────────────┘

  Summary bar:
  ┌──────────────────────────────────────────────────────┐
  │  Total: 455 assets · Matched: 430 (94.5%) · 187s     │
  │  Tier 2: 419  Tier 3: 11  No match: 25               │
  └──────────────────────────────────────────────────────┘
```

---

## Polling vs. Streaming

`POST /assets/ingest-all-jobs` is a **synchronous long-running call** — it holds the HTTP connection open until all jobs complete (3–7 minutes). The response arrives all at once.

Options for a good UX:
- **Simplest:** Call with `fetch` and show a spinner with a timer. Display results when the response resolves.
- **Better:** Call from a background job (e.g. a server-side task) and poll for results. The output file `output/enrichment_results_batch.json` is written when complete — the backend can serve a status endpoint against that.
- **Best for showcase:** Show the spinner + elapsed time during the call, then animate the results table in row-by-row once the full response arrives.

---

## Asset Type Values (for filtering/display)

```
kpi           → KPI
calculation   → Calculated Field
column        → Column
dimension     → Dimension
measure       → Measure
table         → Table
```

---

## Quick Reference — All Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/assets/jobs` | List all Postgres job IDs with counts |
| `POST` | `/assets/ingest-all-jobs` | **Bulk: enrich all jobs** |
| `POST` | `/assets/ingest-from-postgres` | Enrich a single job by `job_id` |
| `POST` | `/assets/ingest-model` | Enrich from a JSON file (existing flow) |
| `POST` | `/assets/match` | Enrich a single asset (body: AssetRecord) |
| `GET` | `/assets/events` | Full audit event log |
| `GET` | `/health` | Server health check |
