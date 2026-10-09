# RAG System — API Testing Guide

**Server**: `http://localhost:8000`  
**Swagger UI**: http://localhost:8000/docs  
**Corpus**: depends on latest ingest; includes canonical retrieval chunks plus semantic explanation artifact chunks  
**Backend**: pgvector on port 5433 · Embeddings: local sentence model (dim=768)

---

## Quick Start (every session)

```powershell
# 1. Start pgvector (if not already up)
cd rag-system
docker compose up -d

# 2. Start the API server
$env:PYTHONPATH = "src"
python -m uvicorn rag_system.api.app:app --host 0.0.0.0 --port 8000 --reload

# 3. Wire to existing pgvector data (run once after server starts)
Invoke-RestMethod http://localhost:8000/connect -Method POST
```

---

## Endpoints

### GET /health
Check server state and chunk count.

```powershell
Invoke-RestMethod http://localhost:8000/health | ConvertTo-Json
```
Expected when ready:
```json
{
  "status": "ok",
  "kb_built": true,
  "chunk_count": 812,
  "ingest": { "state": "connected" },
  "lineage_graph": { "available": true, "engine": "networkx" },
  "semantic_layer": { "available": true, "workflow_count": 7 }
}
```

Note: `chunk_count` varies by corpus and by whether explanation artifacts are generated.

---

### POST /connect
Wire the server to existing pgvector data **without re-parsing XMLs**.  
Use after every server restart when pgvector already has data.

```powershell
Invoke-RestMethod http://localhost:8000/connect -Method POST
```

If local model initialization appears stuck in background mode, use blocking connect:

```powershell
Invoke-RestMethod "http://localhost:8000/connect?background=false" -Method POST
```

---

### POST /ingest
Re-parse all 7 XML files and rebuild the index (requires XML files to be synced by OneDrive).

Current S10 behavior during ingest:
1. Build workflow graph first from connector + port relationships.
2. Derive deterministic lineage paths from graph traversal.
3. Persist semantic truth (`rag.semantic_*`) atomically per workflow.
4. Generate explanation artifact chunks (node/path definitions) from deterministic facts.
5. Embed and upsert retrieval + explanation chunks to vector store.

```powershell
# Background (returns immediately)
Invoke-RestMethod http://localhost:8000/ingest -Method POST

# Blocking (waits until done — good for scripting)
Invoke-RestMethod "http://localhost:8000/ingest?background=false" -Method POST
```

---

### GET /semantic/model — semantic snapshot + graph metadata

```powershell
Invoke-RestMethod "http://localhost:8000/semantic/model?max_workflows=5" | ConvertTo-Json -Depth 6
```

What to verify:
1. `semantic_layer.available = true`
2. Each workflow row includes `graph_hash`
3. `lineage_graph.available = true` when graph is hydrated

Example checks:

```powershell
$m = Invoke-RestMethod "http://localhost:8000/semantic/model?max_workflows=5"
$m.semantic_layer.workflows | Select-Object -First 3 source_file, graph_hash, lineage_path_count
$m.lineage_graph
```

---

### GET /answer — semantic-first with linked explanation artifacts

```powershell
$a = Invoke-RestMethod "http://localhost:8000/answer?q=Show%20lineage%20for%20INTERACTION_ID%20in%20wf_4202_fnd_rltinteraction.XML&k=4&llm=false"
$a | ConvertTo-Json -Depth 8
```

What to verify:
1. `orchestration_mode = semantic_primary` for lineage/impact intent.
2. First evidence rows are semantic (`evidence_source = semantic_layer`).
3. Secondary retrieval strategy prefers linked explanation vectors when present:
- `retrieval_plan.secondary_retrieval.strategy = semantic_explanation_vectors`
4. If linked artifacts are absent, strategy falls back to:
- `retrieval_plan.secondary_retrieval.strategy = generic_transformation_context`

Example checks:

```powershell
$a.orchestration_mode
$a.evidence | Select-Object -First 5 chunk_id, evidence_source, node_class
$a.retrieval_plan.secondary_retrieval
```

---

## Semantic Definition Generation Controls (S10)

These env vars control how explanation artifacts are generated during ingest:

| Env var | Default | Meaning |
|---|---|---|
| `SEMANTIC_DEFINITIONS_USE_LLM` | `false` | Enable LLM generation of node/path definitions |
| `SEMANTIC_DEFINITION_MODEL` | unset | Optional model/deployment override for definition generation |
| `SEMANTIC_DEFINITION_MAX_TOKENS` | `220` | Max completion tokens per generated definition |
| `SEMANTIC_DEFINITIONS_MAX_ITEMS` | `0` | Optional cap on total generated definition artifacts (`0` = no cap) |

Safety behavior:
1. If LLM config is missing or client init fails, ingest does not fail.
2. System falls back to deterministic template explanations.
3. Explanation artifacts remain non-authoritative (`authoritative=false`) in metadata.

---

## P3 Observability Integration (Two-Week Extension)

P3 is integrated into this same rag-system project. Use this section to validate observability outcomes as they are implemented.

### Week +1 Validation Targets

1. `/answer`, `/retrieve`, and semantic APIs return additive `trace` and `telemetry` blocks.
2. `trace` includes `request_id`, `endpoint`, `timestamp_utc`, plus routing context (`intent`, `workflow_hint`, `orchestration_mode`) when applicable.
3. `telemetry.timing_ms` includes stage-level timings:
   - `/answer`: `total_ms` + stage timings (semantic/retrieval/rerank/secondary_retrieval/generation as applicable)
   - `/retrieve`: `total_ms`, `retrieval_ms`, `rerank_ms`
   - `/semantic/*`: `total_ms`, `semantic_ms`
4. `/answer` includes `telemetry.usage` placeholder fields for token/cost observability wiring.

Suggested check command:

```powershell
$r = Invoke-RestMethod "http://localhost:8000/answer?q=Show%20lineage%20for%20INTERACTION_ID%20in%20wf_4202_fnd_rltinteraction.XML&k=4&llm=true"
$r.trace | ConvertTo-Json -Depth 6
$r.telemetry | ConvertTo-Json -Depth 8

$s = Invoke-RestMethod "http://localhost:8000/semantic/lineage?workflow=wf_4202_fnd_rltinteraction.XML&field=INTERACTION_ID&limit=5"
$s.trace | ConvertTo-Json -Depth 6
$s.telemetry | ConvertTo-Json -Depth 8
```

### Week +2 Validation Targets

1. Latency distribution artifacts are available (p50/p95/p99).
2. Refusal and LLM error rates are reportable by reason.
3. Alert thresholds and quality-gate checks enforce latency/cost regression budgets.

Suggested acceptance checklist:

1. Semantic guardrail behavior remains deterministic with observability enabled.
2. Observability fields are additive and do not break existing response contracts.
3. Smoke tests continue to pass after instrumentation changes.

---

### GET /retrieve — Core Retrieval

```
GET /retrieve?q=<query>&k=<int>&node_class=<SOURCE|TRANSFORMATION|TARGET>
```

| Param | Required | Default | Notes |
|---|---|---|---|
| `q` | Yes | — | Natural-language query |
| `k` | No | 5 | 1–50 results |
| `node_class` | No | all | `SOURCE`, `TRANSFORMATION`, or `TARGET` |

**Response shape:**
```json
{
  "query": "...",
  "k": 5,
  "node_class_filter": null,
  "hits": [
    {
      "chunk_id": "wf_4201...:SOURCE:...",
      "source_file": "wf_4201_calculate_interaction_facts.XML",
      "node_class": "SOURCE",
      "name": "SQ_CHNRLTINTERACTIONAGREEMENT",
      "score": 0.91,
      "text": "...",
      "metadata": { "source_db": "TERADATA", "has_sql_override": true, ... }
    }
  ]
}
```

---

## Retrieval Test Cases

Copy-paste into PowerShell. Each shows what to look for.

### 1 — Source tables from Teradata
```powershell
Invoke-RestMethod "http://localhost:8000/retrieve?q=Teradata+source+table&k=5&node_class=SOURCE" | ConvertTo-Json -Depth 4
```
**Expect**: hits from `SOURCE` nodes, `metadata.source_db = "TERADATA"`

---

### 2 — SQL overrides / custom SELECT logic
```powershell
Invoke-RestMethod "http://localhost:8000/retrieve?q=SQL+override+Source+Qualifier&k=5" | ConvertTo-Json -Depth 4
```
**Expect**: Source Qualifier transformations with `metadata.has_sql_override = true`

---

### 3 — Joiner logic between tables
```powershell
Invoke-RestMethod "http://localhost:8000/retrieve?q=join+between+interaction+tables&k=5" | ConvertTo-Json -Depth 4
```
**Expect**: Joiner transformation chunks with `metadata.has_join = true`

---

### 4 — Filter transformations
```powershell
Invoke-RestMethod "http://localhost:8000/retrieve?q=filter+condition+rows&k=5" | ConvertTo-Json -Depth 4
```
**Expect**: `TRANSFORMATION` nodes of type Filter, `metadata.has_filter = true`

---

### 5 — Target tables (output destinations)
```powershell
Invoke-RestMethod "http://localhost:8000/retrieve?q=target+table+output+interaction&k=5&node_class=TARGET" | ConvertTo-Json -Depth 4
```
**Expect**: TARGET node chunks, `metadata.primary_key_count >= 1`

---

### 6 — RLTInteraction mapping (wf_4202)
```powershell
Invoke-RestMethod "http://localhost:8000/retrieve?q=RLTInteraction+relationship+agreement&k=5" | ConvertTo-Json -Depth 4
```
**Expect**: hits from `wf_4202_fnd_rltinteraction.XML`

---

### 7 — Expression transformations with field calculations
```powershell
Invoke-RestMethod "http://localhost:8000/retrieve?q=expression+field+calculation+output+port&k=5" | ConvertTo-Json -Depth 4
```
**Expect**: Expression transformation chunks, `metadata.port_count > 0`

---

### 8 — Aggregator logic
```powershell
Invoke-RestMethod "http://localhost:8000/retrieve?q=aggregation+group+by+sum&k=5" | ConvertTo-Json -Depth 4
```
**Expect**: Aggregator transformation chunks

---

### 9 — Only TRANSFORMATION nodes
```powershell
Invoke-RestMethod "http://localhost:8000/retrieve?q=data+processing+pipeline&k=10&node_class=TRANSFORMATION" | ConvertTo-Json -Depth 4
```
**Expect**: All 10 hits have `node_class = "TRANSFORMATION"`, variety of types

---

### 10 — Broad corpus search (no filter)
```powershell
Invoke-RestMethod "http://localhost:8000/retrieve?q=calculate+interaction+facts+workflow&k=10" | ConvertTo-Json -Depth 4
```
**Expect**: Mix of SOURCE/TRANSFORMATION/TARGET from multiple wf_42xx files

---

## Batch Test Script

Run all 10 queries at once and print a summary:

```powershell
$base = "http://localhost:8000"
$queries = @(
  @{ q="Teradata source table"; node_class="SOURCE" },
  @{ q="SQL override Source Qualifier"; node_class=$null },
  @{ q="join between interaction tables"; node_class=$null },
  @{ q="filter condition rows"; node_class=$null },
  @{ q="target table output interaction"; node_class="TARGET" },
  @{ q="RLTInteraction relationship agreement"; node_class=$null },
  @{ q="expression field calculation output port"; node_class=$null },
  @{ q="aggregation group by sum"; node_class=$null },
  @{ q="data processing pipeline"; node_class="TRANSFORMATION" },
  @{ q="calculate interaction facts workflow"; node_class=$null }
)

foreach ($item in $queries) {
  $url = "$base/retrieve?q=$([uri]::EscapeDataString($item.q))&k=3"
  if ($item.node_class) { $url += "&node_class=$($item.node_class)" }
  $r = Invoke-RestMethod $url
  $top = $r.hits[0]
  Write-Host "`n[$($item.q)]"
  Write-Host "  Top: $($top.name) | $($top.node_class) | score=$($top.score) | $($top.source_file)"
}
```

---

## Swagger UI

Open **http://localhost:8000/docs** in your browser for an interactive UI — try any query without leaving the browser.

---

## Corpus Breakdown (for reference)

| File | Chunks |
|---|---|
| wf_0000_eintr_lmt_load_confirmation.XML | 3 |
| wf_4201_calculate_interaction_facts.XML | 211 |
| wf_4202_fnd_rltinteraction.XML | 32 |
| wf_4203_calculate_interaction_facts_fbl.XML | 63 |
| wf_4204_fnd_rltinteraction_fbl.XML | 14 |
| wf_4205_calculate_dm_facts.XML | 333 |
| wf_4206_calculate_facts_fcr.XML | 62 |
| **Total** | **703** |

| Node class | Count |
|---|---|
| SOURCE | 83 |
| TRANSFORMATION | 565 |
| TARGET | 70 |

Transformation types: Source Qualifier (288), Expression (121), Filter (58), Joiner (39), Lookup Procedure (24), Custom (15), Aggregator (8), Sorter (7), Update Strategy (4), Sequence (1)

---

## Retrieval Evaluation Harness

Golden dataset path:

`eval/golden_retrieval.jsonl`

Run evaluation across all retrieval modes:

```powershell
$env:PYTHONPATH = "src"
python -m rag_system.eval.retrieval_eval `
  --base-url http://localhost:8000 `
  --dataset eval/golden_retrieval.jsonl `
  --modes hybrid,vector,bm25 `
  --k 8 `
  --output eval/report_latest.json
```

Example with guardrail thresholds (non-zero exit code on failure):

```powershell
$env:PYTHONPATH = "src"
python -m rag_system.eval.retrieval_eval `
  --base-url http://localhost:8000 `
  --dataset eval/golden_retrieval.jsonl `
  --modes hybrid,vector,bm25 `
  --k 8 `
  --min-recall 0.60 `
  --min-ndcg 0.55
```

What this gives you:

- Average recall@k per mode
- Average nDCG@k per mode
- Per-query diagnostics and top hit preview in JSON report

---

## Week 3 Expanded Eval Runs

Run the expanded 53-query retrieval dataset at `k=10`:

```powershell
$env:PYTHONPATH = "src"
python -m rag_system.eval.retrieval_eval `
  --base-url http://localhost:8000 `
  --dataset eval/golden_retrieval_w3.jsonl `
  --modes hybrid,vector,bm25 `
  --k 10 `
  --output eval/report_w3_k10.json
```

Quick smoke run (8-query subset):

```powershell
$env:PYTHONPATH = "src"
python -m rag_system.eval.retrieval_eval `
  --base-url http://localhost:8000 `
  --dataset eval/golden_retrieval_w3_smoke.jsonl `
  --modes hybrid,vector,bm25 `
  --k 10 `
  --output eval/report_w3_smoke_k10.json
```

RAGAS answer-level evaluation (requires API key for judge model):

```powershell
$env:PYTHONPATH = "src"
$env:OPENAI_API_KEY = "<your-key>"
python -m rag_system.eval.ragas_eval `
  --base-url http://localhost:8000 `
  --dataset eval/golden_answer_eval.jsonl `
  --mode hybrid `
  --k 6 `
  --output eval/ragas_report_latest.json
```

Validate that answer-eval questions are grounded in real Informatica XML files:

```powershell
$env:PYTHONPATH = "src"
python -m rag_system.eval.validate_answer_dataset_grounding `
  --dataset eval/golden_answer_eval.jsonl
```

Grounding rules enforced:

- each row must declare `source_file`
- `source_file` must exist under `INFA_XML_FOLDER`
- each row must include `expected_entities`
- each expected entity must be present in the referenced XML file

If `OPENAI_API_KEY` is missing, the command exits with:

- `ERROR: RAGAS scoring requires an OpenAI API key for judge-model calls. Set OPENAI_API_KEY in your shell and retry.`

Week 4 faithfulness regression gate (fails when current run drops by more than 0.02 from baseline):

```powershell
$env:PYTHONPATH = "src"
python -m rag_system.eval.quality_gate `
  --baseline eval/ragas_baseline_w3.json `
  --current eval/ragas_report_latest.json `
  --metric faithfulness `
  --max-drop 0.02
```
