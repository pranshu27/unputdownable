"""Unit tests for writer.py — no LLM needed. Tests the TMDL-based PBIP output."""
import json, os, sys, tempfile, pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from skills.json_to_pbip.src.writer import write_pbip

SAMPLE_MAPPED = {
    "reportName": "TestReport",
    "originalName": "Test Report",
    "source": "tableau",
    "tables": [
        {
            "name": "Sales",
            "columns": [
                {"name": "Region",  "dataType": "string",  "sourceColumn": "Region",  "nullable": True},
                {"name": "Revenue", "dataType": "decimal", "sourceColumn": "Revenue", "nullable": True},
            ],
            "measures": [
                {"name": "Total Revenue", "expression": "SUM(Sales[Revenue])", "formatString": "#,##0.00"},
            ],
        }
    ],
    "relationships": [
        {
            "fromTable": "Sales", "fromColumn": "RegionID",
            "toTable":   "Sales", "toColumn":   "RegionID",
        }
    ],
    "pages": [
        {
            "name": "Overview",
            "width": 1280,
            "height": 720,
            "visuals": [
                {
                    "visualType": "barChart",
                    "title": "Revenue by Region",
                    "position": {"x": 0, "y": 0, "w": 400, "h": 300, "z": 0},
                    "fields": [
                        {"role": "Axis",   "table": "Sales", "column": "Region",  "aggregation": ""},
                        {"role": "Values", "table": "Sales", "column": "Revenue", "aggregation": "Sum"},
                    ],
                }
            ],
        }
    ],
}


@pytest.fixture
def output_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


# ── .pbip entry point ─────────────────────────────────────────────────────────

def test_writes_pbip_entry(output_dir):
    write_pbip(SAMPLE_MAPPED, output_dir)
    assert os.path.exists(os.path.join(output_dir, "TestReport.pbip"))


def test_pbip_entry_json_valid(output_dir):
    write_pbip(SAMPLE_MAPPED, output_dir)
    with open(os.path.join(output_dir, "TestReport.pbip")) as f:
        data = json.load(f)
    assert "artifacts" in data
    assert data["artifacts"][0]["report"]["path"] == "TestReport.Report"


# ── Report folder ─────────────────────────────────────────────────────────────

def test_writes_definition_pbir(output_dir):
    write_pbip(SAMPLE_MAPPED, output_dir)
    path = os.path.join(output_dir, "TestReport.Report", "definition.pbir")
    assert os.path.exists(path)
    data = json.load(open(path))
    assert data["datasetReference"]["byPath"]["path"] == "../TestReport.SemanticModel"


def test_writes_report_json(output_dir):
    write_pbip(SAMPLE_MAPPED, output_dir)
    assert os.path.exists(os.path.join(output_dir, "TestReport.Report", "definition", "report.json"))


def test_writes_version_json(output_dir):
    write_pbip(SAMPLE_MAPPED, output_dir)
    assert os.path.exists(os.path.join(output_dir, "TestReport.Report", "definition", "version.json"))


def test_writes_pages_json(output_dir):
    write_pbip(SAMPLE_MAPPED, output_dir)
    path = os.path.join(output_dir, "TestReport.Report", "definition", "pages", "pages.json")
    assert os.path.exists(path)
    pj = json.load(open(path))
    assert "pageOrder" in pj
    assert len(pj["pageOrder"]) == 1


def test_writes_page_json(output_dir):
    write_pbip(SAMPLE_MAPPED, output_dir)
    pages_dir = os.path.join(output_dir, "TestReport.Report", "definition", "pages")
    page_folders = [d for d in os.listdir(pages_dir) if os.path.isdir(os.path.join(pages_dir, d))]
    assert len(page_folders) == 1
    pg = json.load(open(os.path.join(pages_dir, page_folders[0], "page.json")))
    assert pg["displayName"] == "Overview"
    assert pg["width"] == 1280


def test_writes_visual_json(output_dir):
    write_pbip(SAMPLE_MAPPED, output_dir)
    pages_dir = os.path.join(output_dir, "TestReport.Report", "definition", "pages")
    page_folder = next(d for d in os.listdir(pages_dir) if os.path.isdir(os.path.join(pages_dir, d)))
    visuals_dir = os.path.join(pages_dir, page_folder, "visuals")
    assert os.path.exists(visuals_dir)
    visual_folders = os.listdir(visuals_dir)
    assert len(visual_folders) == 1
    v = json.load(open(os.path.join(visuals_dir, visual_folders[0], "visual.json")))
    assert v["visual"]["visualType"] == "barChart"


# ── SemanticModel (TMDL) ──────────────────────────────────────────────────────

def test_writes_semantic_model_folder(output_dir):
    write_pbip(SAMPLE_MAPPED, output_dir)
    assert os.path.isdir(os.path.join(output_dir, "TestReport.SemanticModel"))


def test_writes_model_tmdl(output_dir):
    write_pbip(SAMPLE_MAPPED, output_dir)
    path = os.path.join(output_dir, "TestReport.SemanticModel", "definition", "model.tmdl")
    assert os.path.exists(path)
    content = open(path).read()
    assert "model Model" in content
    assert "ref table" in content


def test_writes_database_tmdl(output_dir):
    write_pbip(SAMPLE_MAPPED, output_dir)
    path = os.path.join(output_dir, "TestReport.SemanticModel", "definition", "database.tmdl")
    assert os.path.exists(path)


def test_writes_table_tmdl(output_dir):
    write_pbip(SAMPLE_MAPPED, output_dir)
    tables_dir = os.path.join(output_dir, "TestReport.SemanticModel", "definition", "tables")
    assert os.path.exists(tables_dir)
    tmdls = [f for f in os.listdir(tables_dir) if f.endswith(".tmdl")]
    assert len(tmdls) == 1
    content = open(os.path.join(tables_dir, tmdls[0])).read()
    assert "table Sales" in content
    assert "measure" in content
    assert "Total Revenue" in content


def test_writes_relationships_tmdl(output_dir):
    write_pbip(SAMPLE_MAPPED, output_dir)
    path = os.path.join(output_dir, "TestReport.SemanticModel", "definition", "relationships.tmdl")
    assert os.path.exists(path)
    assert "relationship" in open(path).read()


def test_writes_platform_files(output_dir):
    write_pbip(SAMPLE_MAPPED, output_dir)
    assert os.path.exists(os.path.join(output_dir, "TestReport.Report", ".platform"))
    assert os.path.exists(os.path.join(output_dir, "TestReport.SemanticModel", ".platform"))
