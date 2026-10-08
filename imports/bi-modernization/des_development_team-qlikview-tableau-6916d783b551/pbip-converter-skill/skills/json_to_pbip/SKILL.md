# PBIP Converter Skill

## What this skill does
Converts Tableau or Power BI JSON exports (common-model format) to Power BI .pbip folder structure that can be opened directly in Power BI Desktop.

## Trigger conditions
Use this skill when the user:
- Provides a Tableau or Power BI export JSON and wants it converted to .pbip
- Uploads a JSON file and asks to "convert to Power BI" or "generate a .pbip"
- Pastes JSON content from a BI tool export
- Says "delete cache" or "clear cache" → call run_json_to_pbip with skip_cache=true

## Required environment variables
```
AZURE_OPENAI_ENDPOINT=https://genaigpt5x.openai.azure.com/
AZURE_OPENAI_KEY=<your-key>
AZURE_OPENAI_DEPLOYMENT=gpt-5-mini
AZURE_OPENAI_API_VERSION=2024-12-01-preview
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
```python
from skills.json_to_pbip.src.parser import parse_common_model, detect_source
intermediate = parse_common_model(input_data, source, db_rows=None)
```
Expected: intermediate dict with keys: source, tables, relationships, pages, all_measures

### Step 2 — Map (LLM)
```python
from skills.json_to_pbip.src.mapper import map_intermediate
mapped = map_intermediate(intermediate)
```
Expected: mapped dict with DAX measures and PBIP visual types
Uses Azure OpenAI gpt-5-mini via AutoGen Core agents:
- DaxConverterAgent: converts raw calc expressions → valid DAX
- VisualMapperAgent: maps unknown visual types → PBIP strings
- TypeInferenceAgent: normalises Power BI data types

### Step 3 — Write
```python
from skills.json_to_pbip.src.writer import write_pbip
files = write_pbip(mapped, output_dir)
```
Expected: complete .pbip folder structure

### Step 4 — Validate
```python
from skills.json_to_pbip.src.validator import validate
errors = validate(output_dir)
```
Expected: empty errors list for "VALIDATION PASSED"

### Step 5 — Cache save
Automatically handled by skill.run() on success.

### Step 6 — Return to user
Provide:
- List of files created
- Path to the .pbip entry file (e.g. `outputs/MyReport/MyReport.pbip`)
- Validation result
- Instructions: "Open Power BI Desktop → File → Open → select the .pbip file"

## Cache management
```
User says: "delete cache" or "clear cache"
→ call run_json_to_pbip(skip_cache=true)
→ runs fresh conversion and updates cache
```

## Error handling
| Error | Action |
|-------|--------|
| Cannot detect source | Ask user to specify source_override = "tableau" or "powerbi" |
| Azure OpenAI call fails | Log which measure failed, use raw expression as fallback |
| writer.py fails | Show exact file path that failed to write |
| validator.py finds errors | Show missing keys, suggest which step to re-run |
| Python import error | Run `pip install autogen-core autogen-ext openai` |

## What NOT to do
- Do not invent DAX expressions without calling mapper
- Do not skip the cache check
- Do not modify files in examples/ or assets/ during conversion
- Do not write to the input JSON files

## Output structure produced
```
outputs/{ReportName}/
  {ReportName}.pbip                    ← Open this in Power BI Desktop
  {ReportName}.Report/
    .platform
    definition.pbir
    definition/
      version.json
      report.json
      pages/{PageId}/
        page.json
        visuals/{VisualId}/
          visual.json
  {ReportName}.SemanticModel/
    .platform
    definition.pbism
    definition/
      model.tmdl
      database.tmdl
      relationships.tmdl
      tables/*.tmdl
      cultures/en-US.tmdl
```
