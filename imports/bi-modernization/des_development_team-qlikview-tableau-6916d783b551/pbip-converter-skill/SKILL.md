# PBIP Converter Skill

## What this skill does
Converts Tableau or Power BI JSON exports (common-model format) to Power BI .pbip folder structure that can be opened directly in Power BI Desktop.

## Trigger conditions
Use this skill when the user:
- Provides a Tableau or Power BI export JSON and wants it converted to .pbip
- Uploads a JSON file and asks to "convert to Power BI" or "generate a .pbip"
- Pastes JSON content from a BI tool export
- Says "delete cache" or "clear cache" → call run_full_pipeline with skip_cache=true, which removes the stale cache entry and output folder before re-running

## Required environment variables
```
AZURE_OPENAI_ENDPOINT=https://genaigpt5x.openai.azure.com/
AZURE_OPENAI_KEY=<your-key>
AZURE_OPENAI_DEPLOYMENT=gpt-5-mini
AZURE_OPENAI_API_VERSION=2024-12-01-preview
POSTGRES_URL=postgresql://LLM_DBAdmin_PostgreSQL:<pass>@<host>:4528/LLM
```

## Input format
Both Tableau and Power BI inputs share the same common-model JSON schema with these top-level keys:
- `schema_version`, `model_id`, `name`, `extracted_at`
- `data_sources[]` — source connections (id contains "tableau" or "powerbi")
- `tables[]` — tables with columns and ingestion steps
- `relationships[]` — join relationships between tables
- `calculations[]` — calculated fields/measures
- `visualizations.pages[]` — dashboard pages with visuals

## Execution steps — run in this exact order, stop on failure

### Step 0 — Cache check
```
hash_key = sha256(sort_keys(input_json))[:16]
Look up hash_key in cache/cache_store.json
If FOUND and path exists: return cached output path, skip to Step 5
```

### Step 1 — Parse
```bash
cd pbip-converter-skill
python src/parser.py --input <input_file> --output temp/intermediate.json [--use-postgres]
```
Expected: `temp/intermediate.json` with keys: source, tables, relationships, pages, all_measures

### Step 2 — Map (LLM)
```bash
python src/mapper.py --input temp/intermediate.json --output temp/mapped.json
```
Expected: `temp/mapped.json` with DAX measures and PBIP visual types
Uses Azure OpenAI gpt-5-mini via AutoGen Core agents:
- DaxConverterAgent: converts raw calc expressions → valid DAX
- VisualMapperAgent: maps unknown visual types → PBIP strings
- TypeInferenceAgent: normalises Power BI data types

### Step 3 — Write
```bash
python src/writer.py --input temp/mapped.json --output outputs/<report_name>/
```
Expected: complete .pbip folder structure

### Step 4 — Validate
```bash
python src/validator.py --input outputs/<report_name>/
```
Expected: "VALIDATION PASSED"

### Step 5 — Cache save
Automatically handled by pipeline.py on success.

### One-command full pipeline
```bash
python src/pipeline.py --input <input_file> --output-dir outputs/ [--report-name "My Report"] [--use-postgres]
```

### Step 6 — Return to user
Provide:
- List of files created
- Path to the .pbip entry file (e.g. `outputs/MyReport/MyReport.pbip`)
- Validation result
- Instructions: "Open Power BI Desktop → File → Open → select the .pbip file"

## Cache management

### Delete cache
```
User says: "delete cache" or "clear cache"
→ call run_full_pipeline(skip_cache=true)
→ this removes the stale cache entry from cache/cache_store.json,
  deletes the old output folder, and runs a fresh conversion
→ confirm result to user when done
```

## Error handling
| Error | Action |
|-------|--------|
| Cannot detect source | Ask user to specify `--source tableau` or `--source powerbi` |
| Azure OpenAI call fails | Log which measure failed, use raw expression as fallback |
| Postgres connection fails | Skip enrichment, continue with JSON data only |
| writer.py fails | Show exact file path that failed to write |
| validator.py finds errors | Show missing keys, suggest which step to re-run |
| Python import error | Run `pip install autogen-core autogen-ext openai sqlalchemy psycopg2-binary pandas` |

## What NOT to do
- Do not invent DAX expressions without calling mapper.py
- Do not skip the cache check
- Do not modify files in examples/ or schemas/ during conversion
- Do not write to the input JSON files

## Output structure produced
```
outputs/{ReportName}/
  {ReportName}.pbip                    ← Open this in Power BI Desktop
  {ReportName}.Report/
    definition.pbir
    report.json
    pages/{PageName}/
      page.json
      visuals/visual01/
        visual.json
  DataModel/
    model.bim                          ← Tables, columns, measures, relationships
    definition.pbidataset
```
