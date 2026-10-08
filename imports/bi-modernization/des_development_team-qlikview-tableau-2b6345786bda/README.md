# Power BI → Databricks Pipeline

End-to-end pipeline that:
1. Pushes `.pbix` data into Databricks as Delta tables
2. Creates `_tmp` versions of those tables (with optional dummy columns)
3. Generates modified PBIP output files where every real table has a `_tmp` companion

---

## Folder Structure

```
qlikview-tableau/
├── input_files/              ← .pbix files (source for push_pbix_to_databricks.py)
├── pbib_input_files/         ← PBIP project folders (source for pbip_tmp_generator.py)
│   ├── report.SemanticModel/
│   ├── Insurance Analysis/
│   ├── INSURANCE DATA PROJECT/
│   ├── Data Analyst (Project 2[Insurance])/
│   └── Insurance_Cliam_Power Bi/
├── pbip_output_files/        ← Generated PBIP files (created by pbip_tmp_generator.py)
│
├── push_pbix_to_databricks.py    ← Script 1: push .pbix tables to Databricks
├── create_databricks_tmp_tables.py ← Script 2: create _tmp tables in Databricks
├── pbip_tmp_generator.py         ← Script 3: generate modified PBIP output files
├── run_batch.sh                  ← Bash batch runner (parallel .pbix processing)
└── requirements.txt
```

---

## Prerequisites

### Python version
```bash
python --version    # requires Python 3.9+
```

### Install dependencies
```bash
pip install -r requirements.txt
```

Key packages installed:
| Package | Used by |
|---------|---------|
| `databricks-sql-connector` | All DB scripts |
| `pbixray` | `push_pbix_to_databricks.py` |
| `pandas` | `push_pbix_to_databricks.py` |

---

## Run Order

> **Always run in this exact order.** Each step depends on the previous one.

```
Step 1 → push_pbix_to_databricks.py      (creates real source tables in Databricks)
Step 2 → create_databricks_tmp_tables.py  (creates _tmp tables from those source tables)
Step 3 → pbip_tmp_generator.py            (generates PBIP output files pointing to _tmp)
```

---

## Step 1 — Push `.pbix` data to Databricks

**Script:** `push_pbix_to_databricks.py`
**Input:** All `.pbix` files inside `input_files/`
**Output:** One schema per `.pbix` file created inside `genai_demo` catalog in Databricks

```bash
python push_pbix_to_databricks.py
```

**What it does:**
- Reads every `.pbix` in `input_files/`
- Skips Power BI system tables (`DateTableTemplate_*`, `LocalDateTable_*`)
- For each real table → `CREATE OR REPLACE TABLE` + inserts all rows (500 rows per batch)
- Enables `delta.columnMapping.mode = name` so column names with spaces work

**Expected output:**
```
Found 3 .pbix file(s) in input_files/
Connecting to Databricks: dbc-9064b591-ac6c.cloud.databricks.com

======================================================================
FILE   : report.pbix
CATALOG: genai_demo  |  SCHEMA: report
======================================================================
  Total tables found by pbixray : 5
  Real source tables            : 2
  System tables (skipped)       : 3
  Schema `genai_demo`.`report` ready.

  Table: 'claims'  =>  `claims`
    Rows: 1,000  |  Cols: 12
    Table created/replaced.
    Inserted 1,000 rows. OK
...
FINAL SUMMARY
  [OK]  report.pbix  =>  schema: report  |  pushed: 2  |  failed: 0  |  sys-skipped: 3
```

---

## Step 2 — Create `_tmp` tables in Databricks

**Script:** `create_databricks_tmp_tables.py`
**Input:** Existing source tables in Databricks (created in Step 1)
**Output:** 13 `_tmp` tables created in Databricks

```bash
python create_databricks_tmp_tables.py
```

**What it does:**
- Creates `_tmp` copy of every real source table
- 4 tables get **extra dummy columns** added:

| Table | `_tmp` Table | Dummy Columns Added |
|-------|-------------|---------------------|
| `report.claims` | `report.claims_tmp` | `claims_test_flag`, `claims_dummy_amount` |
| `report.policies` | `report.policies_tmp` | `policies_test_flag`, `policies_dummy_category`, `policies_dummy_score` |
| `insurance_data_project.insurancedata` | `insurancedata_tmp` | `insurancedata_test_flag`, `insurancedata_review_score`, `insurancedata_batch_id` |
| `insurance_data_project.sheet1` | `sheet1_tmp` | `sheet1_test_flag`, `sheet1_source_tag` |

- 9 tables are **simple copies** (no extra columns): `brokerage`, `fees`, `individual_budge`, `invoice`, `meeting_list`, `opportunity`, `placed_achivement`, `insurance`, `insurancedata` (data analyst project)

**Expected output:**
```
======================================================================
Databricks _tmp Table Creator
======================================================================
Host    : dbc-9064b591-ac6c.cloud.databricks.com
Catalog : genai_demo

Total _tmp tables to create: 13

  [report]  claims -> claims_tmp
    Creating `report`.`claims_tmp` (2 dummy col(s)) ...
    OK -- `report`.`claims_tmp` created.
    Verified: 1,000 rows

  [report]  policies -> policies_tmp
    ...
======================================================================
SUMMARY
======================================================================
  Created  : 13
  Failed   : 0
```

---

## Step 3 — Generate PBIP output files

**Script:** `pbip_tmp_generator.py`
**Input:** PBIP project folders in `pbib_input_files/`
**Output:** Modified PBIP files in `pbip_output_files/`

```bash
python pbip_tmp_generator.py
```

**What it does:**
- Reads all 5 PBIP projects from `pbib_input_files/`
- For every real source table in each project:
  - Writes original `<Table>.tmdl` → M source redirected to `_tmp` in Databricks (dummy columns stripped from view)
  - Writes `<Table>_tmp.tmdl` → renamed table + `_tmp` source + dummy column definitions
- Skips system tables and DAX calculated tables (copied as-is)
- Clears `pbip_output_files/` on every run (always a fresh output)

**Expected output:**
```
Found 5 PBIP project(s) in pbib_input_files/
Output -> pbip_output_files/

======================================================================
PROJECT: report.SemanticModel
  SemanticModel  : ...report.SemanticModel
  Fallback schema: report
  Non-table files copied.
    [DAX CALC]  calculations.tmdl  (copied as-is, no _tmp)
    [REAL]      claims.tmdl  +  claims_tmp.tmdl  (schema: report)
    [REAL]      policies.tmdl  +  policies_tmp.tmdl  (schema: report)
  Tables copied as-is : 1
  _tmp tables created : 2

======================================================================
PROJECT: Insurance Analysis
  ...
Done.  Modified PBIP files are in: pbip_output_files/
```

---

## Opening the Output in Power BI Desktop

1. Close any previously open PBIP project in Power BI Desktop
2. Navigate to `pbip_output_files/<project-name>/`
3. Open the `.pbip` file
4. Power BI will connect to Databricks and load data

**What you will see in the field list:**
- `InsuranceData` — original columns only, data comes from `insurancedata_tmp` in Databricks
- `InsuranceData_tmp` — all columns including dummy ones, data also from `insurancedata_tmp`

Both tables read from the same `_tmp` table in Databricks. The original table strips dummy columns so you can compare.

---

## Bash Batch Runner (parallel `.pbix` processing)

**Script:** `run_batch.sh`
Runs `create_databricks_tables.py` + `parallel_runner.py` together.

```bash
# Default run (auto-detect worker count)
bash run_batch.sh

# Override number of parallel workers
bash run_batch.sh --workers 3

# Custom input directory
bash run_batch.sh --input-dir ./my_pbix_folder

# Custom input dir + worker count
bash run_batch.sh --input-dir ./my_pbix_folder --workers 3

# Change ETL tool (default: powerbi)
bash run_batch.sh --etltool powerbi
```

**Steps inside `run_batch.sh`:**
1. Runs `python create_databricks_tables.py --drop-recreate` (cleans 17 managed tables)
2. Runs `python parallel_runner.py --input-dir <dir> --etltool <tool>` (parallel `.pbix` push)

---

## Databricks Connection Details

All three Python scripts use these connection constants (set at the top of each file or via environment variables):

| Setting | Value | Env Variable |
|---------|-------|--------------|
| Host | `dbc-9064b591-ac6c.cloud.databricks.com` | `DATABRICKS_WORKSPACE_URL` |
| HTTP Path | `/sql/protocolv1/o/0/0206-091900-f4nnmzzq` | `DATABRICKS_HTTP_PATH` |
| Token | `dapi862b5...` | `DATABRICKS_ACCESS_TOKEN` |
| Cluster ID | `0206-091900-f4nnmzzq` | `DATABRICKS_CLUSTER_ID` |
| Catalog | `genai_demo` | — |

To override via environment variables instead of editing the scripts:
```bash
export DATABRICKS_WORKSPACE_URL="dbc-xxxx.cloud.databricks.com"
export DATABRICKS_ACCESS_TOKEN="dapiXXXXXXXX"
export DATABRICKS_CLUSTER_ID="XXXX-XXXXXX-XXXXXXXX"

python push_pbix_to_databricks.py
python create_databricks_tmp_tables.py
python pbip_tmp_generator.py
```

---

## Common Errors and Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `PermissionError: [WinError 32]` | Power BI Desktop has the output folder open | Close the PBIP project in Power BI Desktop, then re-run |
| `lineage-tag already exists` | Old output files still in `pbip_output_files/` | Script clears output on every run — make sure PBI is closed |
| `Variation relationship must be defined on current table` | Variation blocks left in `_tmp` TMDL | Already handled by `strip_variation_blocks()` — re-run generator |
| `DELTA_INVALID_CHARACTERS_IN_COLUMN_NAMES` | Column names with spaces in Databricks | Already handled — Delta Column Mapping is always enabled |
| `cannot load <table>_tmp` | `_tmp` table doesn't exist in Databricks yet | Run Step 2 (`create_databricks_tmp_tables.py`) first |
| `No .pbix files found in input_files/` | Wrong directory or missing files | Check that `.pbix` files are inside `input_files/` folder |
| `No PBIP projects found in pbib_input_files/` | Wrong directory or missing `.SemanticModel` folders | Check that PBIP folders are inside `pbib_input_files/` |
