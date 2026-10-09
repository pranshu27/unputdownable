#!/usr/bin/env bash
# run_batch.sh
# ─────────────────────────────────────────────────────────────────────────────
# Batch pipeline runner:
#   Step 1 — Clean up and recreate ONLY the 17 managed Databricks tables
#             (genai_demo.jnj_bi_modernization). No other schemas touched.
#   Step 2 — Process all .pbix files in input_files/ in parallel.
#             Each thread pushes its results to Databricks as soon as it finishes.
#
# Usage:
#   bash run_batch.sh                        # auto-detect worker count
#   bash run_batch.sh --workers 6            # override worker count
#   bash run_batch.sh --input-dir ./my_dir   # custom input directory
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Configurable defaults ─────────────────────────────────────────────────────
INPUT_DIR="${INPUT_DIR:-./input_files}"
ETLTOOL="${ETLTOOL:-powerbi}"
WORKERS=""   # empty = auto-detect inside parallel_runner.py

# ── Parse optional CLI args ───────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --workers)      WORKERS="$2";    shift 2 ;;
        --input-dir)    INPUT_DIR="$2";  shift 2 ;;
        --etltool)      ETLTOOL="$2";    shift 2 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

# ── Move to the script's own directory so relative paths work ─────────────────
cd "$(dirname "$0")"

echo ""
echo "============================================================"
echo " BI Batch Pipeline"
echo "============================================================"
echo " Input dir : $INPUT_DIR"
echo " ETL tool  : $ETLTOOL"
echo " Workers   : ${WORKERS:-auto-detect}"
echo "============================================================"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Drop and recreate only the 17 managed Databricks tables
# ─────────────────────────────────────────────────────────────────────────────
echo "[Step 1] Cleaning up and recreating Databricks tables ..."
echo "         Scope: genai_demo.jnj_bi_modernization (17 tables only)"
echo "         No other schemas or tables will be touched."
echo ""

python create_databricks_tables.py --drop-recreate

echo ""
echo "[Step 1] Done."
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: Run all input files in parallel
# ─────────────────────────────────────────────────────────────────────────────
echo "[Step 2] Starting parallel batch processing ..."
echo ""

RUNNER_ARGS="--input-dir $INPUT_DIR --etltool $ETLTOOL"
if [[ -n "$WORKERS" ]]; then
    RUNNER_ARGS="$RUNNER_ARGS --workers $WORKERS"
fi

python parallel_runner.py $RUNNER_ARGS

echo ""
echo "[Step 2] Done."
echo ""
echo "============================================================"
echo " Batch pipeline complete."
echo "============================================================"
