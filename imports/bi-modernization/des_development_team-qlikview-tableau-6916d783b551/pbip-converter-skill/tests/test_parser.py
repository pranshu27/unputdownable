"""Unit tests for parser.py — no LLM, no Postgres needed."""
import json, sys, os, pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from skills.json_to_pbip.src.parser import detect_source, parse_common_model


# ── fixtures ──────────────────────────────────────────────────────────────────
EXAMPLES = os.path.join(os.path.dirname(__file__), "..", "examples")


def _load(name):
    with open(os.path.join(EXAMPLES, name)) as f:
        return json.load(f)


# ── source detection ──────────────────────────────────────────────────────────
def test_detect_tableau_via_id():
    data = {"data_sources": [{"id": "tableau(toolname)$some.twb(filename)"}]}
    assert detect_source(data) == "tableau"


def test_detect_powerbi_via_id():
    data = {"data_sources": [{"id": "powerbi(toolname)$some.pbix(filename)"}]}
    assert detect_source(data) == "powerbi"


def test_detect_via_root_keys():
    assert detect_source({"workbook": {}}) == "tableau"


def test_detect_unknown_raises():
    with pytest.raises(ValueError):
        detect_source({"random_key": {}})


# ── tableau sample ────────────────────────────────────────────────────────────
def test_tableau_tables_extracted():
    data = _load("tableau_sample.json")
    result = parse_common_model(data, "tableau")
    assert len(result["tables"]) > 0
    assert "columns" in result["tables"][0]


def test_tableau_pages_extracted():
    data = _load("tableau_sample.json")
    result = parse_common_model(data, "tableau")
    assert len(result["pages"]) > 0


def test_tableau_relationships_extracted():
    data = _load("tableau_sample.json")
    result = parse_common_model(data, "tableau")
    # salesdata has at least 1 relationship
    assert "relationships" in result


def test_tableau_measures_in_all_measures():
    data = _load("tableau_sample.json")
    result = parse_common_model(data, "tableau")
    # "10% discount" calculation should be captured
    names = [m["name"] for m in result.get("all_measures", [])]
    assert any("discount" in n.lower() for n in names)


def test_tableau_visual_types_present():
    data = _load("tableau_sample.json")
    result = parse_common_model(data, "tableau")
    for page in result["pages"]:
        for visual in page["visuals"]:
            assert "visualType" in visual


# ── powerbi sample ────────────────────────────────────────────────────────────
def test_powerbi_tables_extracted():
    data = _load("pbi_sample.json")
    result = parse_common_model(data, "powerbi")
    assert len(result["tables"]) > 0


def test_powerbi_source_field():
    data = _load("pbi_sample.json")
    result = parse_common_model(data, "powerbi")
    assert result["source"] == "powerbi"


def test_powerbi_report_name():
    data = _load("pbi_sample.json")
    result = parse_common_model(data, "powerbi")
    assert result["report_name"]  # non-empty


# ── data-type normalisation ───────────────────────────────────────────────────
def test_column_types_normalised():
    data = _load("tableau_sample.json")
    result = parse_common_model(data, "tableau")
    valid = {"string", "int64", "decimal", "boolean", "dateTime", "date", "time"}
    for table in result["tables"]:
        for col in table["columns"]:
            assert col["dataType"] in valid, f"Bad type: {col['dataType']} for {col['name']}"
