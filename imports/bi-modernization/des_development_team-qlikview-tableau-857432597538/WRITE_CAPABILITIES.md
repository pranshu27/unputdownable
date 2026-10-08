# Write Capabilities

Linker Agent reads from Alation during enrichment and writes back to Alation through explicit curation endpoints. Write-back is always a **separate, intentional step** — enrichment results are never automatically pushed to the catalog. This gives data stewards the opportunity to review generated definitions and Tier 3 recommendations before they are published.

---

## What Can Be Written to Alation

### 1. Glossary Term Description

Write or overwrite the description field of an existing Alation glossary term.

**When to use this:** After Tier 2 or Tier 3 enrichment, the `business_definition` field on each `AssetLinkResult` contains a catalog-ready, context-aware definition. Use this endpoint to push that definition back to the matched glossary term in Alation.

**Endpoint:** `PUT /curation/term-description`

**Request body:**
```json
{
  "term_id": 1001,
  "description": "The compound annual growth rate (CAGR) measures the mean annual growth rate of premium or investment value across the Tru Secure CreDebit portfolio over the policy term. It is a non-additive ratio metric that must not be summed across segments.",
  "template_id": null
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `term_id` | integer | Yes | Alation glossary term ID — available in `AssetLinkResult.term_id` |
| `description` | string | Yes | The business definition to write. Plain text or HTML. |
| `template_id` | integer | No | Alation template ID, if your glossary uses custom templates. Leave `null` to auto-resolve. |

**Success response:**
```json
{
  "success": true,
  "term_id": 1001,
  "detail": "Description updated successfully.",
  "alation_response": { ... }
}
```

**cURL example:**
```bash
curl -X PUT http://localhost:3005/curation/term-description \
  -H "Content-Type: application/json" \
  -d '{
    "term_id": 1001,
    "description": "The compound annual growth rate (CAGR) measures the mean annual growth rate of premium or investment value across the portfolio over the policy term."
  }'
```

---

### 2. Custom Field Values (Batch)

Write one or more custom field values on a glossary term in a single API call.

**When to use this:** Alation glossary terms often have custom fields beyond the standard description — for example, a "Business Owner" field, a "Data Classification" field, or a "Last Reviewed Date" field. This endpoint lets you populate any of those fields programmatically.

**Endpoint:** `PUT /curation/custom-field-values`

**Request body:**
```json
{
  "term_id": 1001,
  "field_updates": [
    {
      "field_id": 10020,
      "value": "Finance"
    },
    {
      "field_id": 10021,
      "value": "2026-05-07"
    }
  ],
  "template_id": null
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `term_id` | integer | Yes | Alation glossary term ID |
| `field_updates` | array | Yes | One or more `{field_id, value}` pairs |
| `field_updates[].field_id` | integer | Yes | Alation custom field ID |
| `field_updates[].value` | any | Yes | The value to write. Type must match the field's data type in Alation (string, date, pick-list value, etc.) |
| `template_id` | integer | No | Alation template ID. Leave `null` to auto-resolve. |

**Success response:**
```json
{
  "success": true,
  "term_id": 1001,
  "detail": "Custom field values updated successfully.",
  "alation_response": { ... }
}
```

**cURL example:**
```bash
curl -X PUT http://localhost:3005/curation/custom-field-values \
  -H "Content-Type: application/json" \
  -d '{
    "term_id": 1001,
    "field_updates": [
      { "field_id": 10020, "value": "Finance" },
      { "field_id": 10021, "value": "Approved" }
    ]
  }'
```

---

## The Recommended Write-back Workflow

```
1. Run enrichment
   python -m linker_agent.tests.run_pipeline_showcase --use-mock-glossary

2. Review output/enrichment_results.json
   Check linkage_type, confidence_score, and business_definition for each asset.
   For Tier 3 assets, review tier3_recommendations and select the preferred term.

3. Approve results for write-back
   Filter to assets with linkage_type = "semantic" or "generated" and confidence >= 80.

4. Write definitions back to Alation
   For each approved result:
     PUT /curation/term-description
       { "term_id": result.term_id, "description": result.business_definition }

5. Optionally update custom fields
   PUT /curation/custom-field-values
       { "term_id": ..., "field_updates": [{ "field_id": ..., "value": ... }] }
```

---

## Finding Field IDs

Custom field IDs are Alation-instance-specific. To find them:

1. In the Alation UI, navigate to **Settings → Custom Fields**.
2. Hover over a field name — the field ID appears in the URL or tooltip.
3. Alternatively, call `GET /alation/terms` and inspect the `custom_fields` array on any returned term object. Each entry has `field_id` and `field_name`.

```bash
curl http://localhost:3005/alation/terms?glossary_id=1
```

---

## Error Handling

All curation endpoints return structured error responses — they never throw unstructured 500 errors.

| HTTP Status | Meaning |
|-------------|---------|
| `200` | Write succeeded |
| `400` | Invalid request (empty description, empty field_updates) |
| `401` | Alation API token rejected |
| `404` | Term ID not found in Alation |
| `502` | Alation returned a 5xx error |
| `503` | Could not reach Alation (connection error or timeout) |

Error response body:
```json
{
  "success": false,
  "term_id": 1001,
  "detail": "Alation API error: Not Found",
  "status_code": 404
}
```

---

## Alation API Endpoints Called Internally

| Operation | Alation endpoint | HTTP method |
|-----------|-----------------|-------------|
| Update term description | `/integration/v2/term/` | `PUT` |
| Update custom field values | `/integration/v2/custom_field_value/` | `PUT` |
| Fetch glossary terms | `/integration/v2/term/` | `GET` |
| Fetch column details | `/integration/v2/attribute/` | `GET` |

The Alation client handles authentication (Bearer token from `ALATION_API_TOKEN`), retries on transient errors, and async connection pooling via `aiohttp`.

---

## What Is NOT Written Automatically

| Item | Written automatically? | Notes |
|------|----------------------|-------|
| Asset descriptions in Alation | No | Must call `PUT /curation/term-description` explicitly |
| Custom field values | No | Must call `PUT /curation/custom-field-values` explicitly |
| New glossary terms (Tier 3) | No | Tier 3 generates candidates for review; the steward creates the term in Alation and then calls the curation endpoints |
| Data Asset links (column → term) | No | Linking a column to a term in Alation requires a separate Data Asset field update, not currently exposed |
| `output/enrichment_results.json` | Yes | Written automatically at the end of every showcase run and `/assets/ingest-model` call |
| `output/event_log.jsonl` | Yes | Appended automatically for every asset processed |
