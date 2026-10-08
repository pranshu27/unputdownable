"""
Tests covering the helpers introduced/modified during SonarQube fixes.

Files covered:
  - postgres_dedup.py        : _get_match_reason, _build_fuzzy_pair,
                               _compare_table_pair, _level2_fuzzy_duplicates,
                               _jaccard, _normalize_col
  - pbip_tmp_generator.py   : _strip_sm_suffix, _make_project_entry,
                               _find_nested_sm, find_pbip_projects
  - sequentialworkflow.py   : _select_model_client, _build_table_columns_map,
                               _deduplicate_calculated_columns,
                               _inject_metadata_and_reorder,
                               _collect_visuals_result (error path)
  - generate_mapping_report.py : get_status, _NOT_FOUND constant,
                                  _find_header_row

Run with:
    python -m pytest tests/test_sonarqube_fixes.py -v
"""

import sys
import os
import json
import asyncio
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("POSTGRES_URL", "postgresql://test:test@localhost:5432/test")

# ---------------------------------------------------------------------------
# Mock heavy dependencies before importing project modules
# ---------------------------------------------------------------------------
_HEAVY = [
    "config",
    "autogen_core", "autogen_core.models",
    "autogen_core._default_subscription", "autogen_core._default_topic",
    "autogen_ext", "autogen_ext.models", "autogen_ext.models.openai",
    "autogen_agentchat",
    "semantic_kernel",
    "semantic_kernel.connectors", "semantic_kernel.connectors.ai",
    "semantic_kernel.connectors.ai.google",
    "semantic_kernel.connectors.ai.google.google_ai",
    "semantic_kernel.connectors.ai.google.google_ai.services",
    "semantic_kernel.connectors.ai.google.google_ai.services.google_ai_chat_completion",
    "semantic_kernel.memory", "semantic_kernel.memory.null_memory",
    "semantic_kernel.kernel_pydantic",
    "AWSSecretsManager",
    "databricks", "databricks.sql",
    "agents_qlikview", "agents_powerbi", "agents_tableau",
    "powerbi_extractor", "layout_mapper",
    "prompts_powerbi", "prompts_qlikview", "extraction_schema",
    "openpyxl", "openpyxl.styles",
]
for _m in _HEAVY:
    if _m not in sys.modules:
        sys.modules[_m] = MagicMock()


# ===========================================================================
# postgres_dedup.py
# ===========================================================================

class TestJaccardAndNormalizeCol:
    def test_jaccard_identical_sets(self):
        from postgres_dedup import _jaccard
        assert _jaccard({"a", "b"}, {"a", "b"}) == 1.0

    def test_jaccard_disjoint_sets(self):
        from postgres_dedup import _jaccard
        assert _jaccard({"a"}, {"b"}) == 0.0

    def test_jaccard_partial_overlap(self):
        from postgres_dedup import _jaccard
        result = _jaccard({"a", "b", "c"}, {"b", "c", "d"})
        # intersection=2, union=4 → 0.5
        assert abs(result - 0.5) < 1e-9

    def test_jaccard_both_empty(self):
        from postgres_dedup import _jaccard
        assert _jaccard(set(), set()) == 1.0

    def test_normalize_col_strips_spaces(self):
        from postgres_dedup import _normalize_col
        assert _normalize_col("  My Column  ") == "mycolumn"

    def test_normalize_col_removes_underscores_and_hyphens(self):
        from postgres_dedup import _normalize_col
        assert _normalize_col("my_col-name") == "mycolname"

    def test_normalize_col_lowercases(self):
        from postgres_dedup import _normalize_col
        assert _normalize_col("PolicyID") == "policyid"


class TestGetMatchReason:
    def test_combined_above_fuzzy_threshold_returns_name_columns(self):
        from postgres_dedup import _get_match_reason
        assert _get_match_reason(0.70, 0.50) == "name+columns"

    def test_combined_at_fuzzy_threshold_returns_name_columns(self):
        from postgres_dedup import _get_match_reason
        assert _get_match_reason(0.65, 0.50) == "name+columns"

    def test_col_jaccard_above_column_only_threshold(self):
        from postgres_dedup import _get_match_reason
        # combined below 0.65 but col_jaccard >= 0.85
        assert _get_match_reason(0.60, 0.90) == "columns_only"

    def test_col_jaccard_at_column_only_threshold(self):
        from postgres_dedup import _get_match_reason
        assert _get_match_reason(0.50, 0.85) == "columns_only"

    def test_both_below_threshold_returns_none(self):
        from postgres_dedup import _get_match_reason
        assert _get_match_reason(0.30, 0.40) is None

    def test_zero_scores_returns_none(self):
        from postgres_dedup import _get_match_reason
        assert _get_match_reason(0.0, 0.0) is None


class TestBuildFuzzyPair:
    def _tbl(self, tid, name, tool, fname):
        return {"table_id": tid, "table_name": name, "tool_type": tool, "file_name": fname}

    def test_returns_correct_keys(self):
        from postgres_dedup import _build_fuzzy_pair
        a = self._tbl("t1", "Sales", "tableau", "sales.twb")
        b = self._tbl("t2", "Sales", "powerbi", "sales.pbix")
        pair = _build_fuzzy_pair(a, b, 0.756, 1.0, 0.593, "name+columns")
        assert pair["table_a_id"] == "t1"
        assert pair["table_b_id"] == "t2"
        assert pair["match_reason"] == "name+columns"
        assert pair["combined_score"] == 0.756
        assert pair["table_name_similarity"] == 1.0
        assert pair["column_jaccard"] == 0.593

    def test_scores_are_rounded_to_3_dp(self):
        from postgres_dedup import _build_fuzzy_pair
        a = self._tbl("x", "T", "t", "f")
        b = self._tbl("y", "T", "t", "g")
        pair = _build_fuzzy_pair(a, b, 0.666666, 1.0, 0.444444, "name+columns")
        assert pair["combined_score"] == 0.667
        assert pair["column_jaccard"] == 0.444


class TestCompareTablePair:
    def _tbl(self, name, cols, sig="", tool="tableau", fname="f.twb", tid="1"):
        return {
            "table_id": tid, "table_name": name, "tool_type": tool,
            "file_name": fname, "column_signature": sig,
            "column_names": cols,
        }

    def test_returns_none_when_tbl_b_has_no_columns(self):
        from postgres_dedup import _compare_table_pair
        a = self._tbl("Sales", ["id", "amount"])
        b = self._tbl("Sales", [])
        assert _compare_table_pair(a, {"id", "amount"}, b, set()) is None

    def test_skips_exact_duplicate_already_in_signatures(self):
        from postgres_dedup import _compare_table_pair
        sig = "abc123"
        a = self._tbl("T", ["id"], sig=sig)
        b = self._tbl("T", ["id"], sig=sig)
        assert _compare_table_pair(a, {"id"}, b, {sig}) is None

    def test_identical_name_and_columns_triggers_name_columns(self):
        from postgres_dedup import _compare_table_pair
        cols = ["policy_id", "claim_id", "amount", "date", "status"]
        a = self._tbl("Claims", cols, tid="1")
        b = self._tbl("Claims", cols, tid="2")
        result = _compare_table_pair(a, set(cols), b, set())
        assert result is not None
        assert result["match_reason"] == "name+columns"

    def test_high_column_overlap_triggers_columns_only(self):
        from postgres_dedup import _compare_table_pair
        # different names, high column overlap: 16 shared / 18 total → jaccard ≈ 0.889 ≥ 0.85
        # combined = 0*0.4 + 0.889*0.6 ≈ 0.533 < 0.65, so reason is "columns_only" not "name+columns"
        cols_a = [f"col{i}" for i in range(16)] + ["only_in_a"]
        cols_b = [f"col{i}" for i in range(16)] + ["only_in_b"]
        a = self._tbl("TableAlpha", cols_a, tid="1")
        b = self._tbl("TableBeta", cols_b, tid="2")
        result = _compare_table_pair(a, set(cols_a), b, set())
        assert result is not None
        assert result["match_reason"] == "columns_only"

    def test_low_overlap_returns_none(self):
        from postgres_dedup import _compare_table_pair
        a = self._tbl("TableA", ["x", "y"], tid="1")
        b = self._tbl("TableB", ["p", "q"], tid="2")
        assert _compare_table_pair(a, {"x", "y"}, b, set()) is None


class TestLevel2FuzzyDuplicates:
    def _tbl(self, name, cols, sig="", tool="tableau", fname="f.twb", tid=None):
        return {
            "table_id": tid or name,
            "table_name": name, "tool_type": tool,
            "file_name": fname, "column_signature": sig,
            "column_names": cols,
        }

    def test_returns_empty_for_empty_list(self):
        from postgres_dedup import _level2_fuzzy_duplicates
        assert _level2_fuzzy_duplicates([], set()) == []

    def test_skips_tables_with_no_columns(self):
        from postgres_dedup import _level2_fuzzy_duplicates
        tables = [self._tbl("A", []), self._tbl("B", [])]
        assert _level2_fuzzy_duplicates(tables, set()) == []

    def test_detects_identical_pair(self):
        from postgres_dedup import _level2_fuzzy_duplicates
        cols = ["id", "name", "amount", "date", "status"]
        tables = [
            self._tbl("Claims", cols, tid="1"),
            self._tbl("Claims", cols, tid="2"),
        ]
        result = _level2_fuzzy_duplicates(tables, set())
        assert len(result) == 1
        assert result[0]["match_reason"] == "name+columns"

    def test_excludes_exact_duplicates(self):
        from postgres_dedup import _level2_fuzzy_duplicates
        cols = ["id", "name"]
        sig = "exactsig"
        tables = [
            self._tbl("T", cols, sig=sig, tid="1"),
            self._tbl("T", cols, sig=sig, tid="2"),
        ]
        # Both have same sig in exact_signatures → skipped by level2
        result = _level2_fuzzy_duplicates(tables, {sig})
        assert result == []

    def test_single_table_produces_no_pairs(self):
        from postgres_dedup import _level2_fuzzy_duplicates
        tables = [self._tbl("Only", ["a", "b", "c"], tid="1")]
        assert _level2_fuzzy_duplicates(tables, set()) == []

    def test_three_tables_produces_correct_number_of_matching_pairs(self):
        from postgres_dedup import _level2_fuzzy_duplicates
        # All three have identical name+columns → 3 pairs
        cols = ["col_a", "col_b", "col_c", "col_d", "col_e"]
        tables = [
            self._tbl("Policy", cols, tid="1"),
            self._tbl("Policy", cols, tid="2"),
            self._tbl("Policy", cols, tid="3"),
        ]
        result = _level2_fuzzy_duplicates(tables, set())
        assert len(result) == 3


# ===========================================================================
# pbip_tmp_generator.py
# ===========================================================================

class TestStripSmSuffix:
    def test_strips_databricks_sm_suffix(self):
        from pbip_tmp_generator import _strip_sm_suffix
        assert _strip_sm_suffix("MyReport_databricks.SemanticModel") == "MyReport"

    def test_strips_plain_sm_suffix(self):
        from pbip_tmp_generator import _strip_sm_suffix
        assert _strip_sm_suffix("MyReport.SemanticModel") == "MyReport"

    def test_returns_name_unchanged_when_no_suffix(self):
        from pbip_tmp_generator import _strip_sm_suffix
        assert _strip_sm_suffix("SomeName") == "SomeName"

    def test_prefers_longer_databricks_suffix(self):
        # "_databricks.SemanticModel" ends with ".SemanticModel" too —
        # the longer suffix should be stripped first, leaving no residue.
        from pbip_tmp_generator import _strip_sm_suffix
        result = _strip_sm_suffix("Report_databricks.SemanticModel")
        assert result == "Report"


class TestMakeProjectEntry:
    def test_schema_name_is_sanitized(self):
        from pbip_tmp_generator import _make_project_entry
        entry = _make_project_entry("/sm", "/root", "output", "Insurance Analysis")
        # sanitize_identifier should convert spaces/special chars
        assert " " not in entry["schema_name"]

    def test_all_keys_present(self):
        from pbip_tmp_generator import _make_project_entry
        entry = _make_project_entry("/sm", "/root", "output", "Sales")
        assert set(entry.keys()) == {"semantic_model_dir", "project_root", "output_name", "schema_name"}

    def test_paths_stored_correctly(self):
        from pbip_tmp_generator import _make_project_entry
        entry = _make_project_entry("/a/sm", "/a", "myoutput", "Sales")
        assert entry["semantic_model_dir"] == "/a/sm"
        assert entry["project_root"] == "/a"
        assert entry["output_name"] == "myoutput"


class TestFindNestedSm:
    def test_returns_none_when_no_sm_subfolder(self, tmp_path):
        from pbip_tmp_generator import _find_nested_sm
        (tmp_path / "subfolder").mkdir()
        assert _find_nested_sm(str(tmp_path), "parent") is None

    def test_returns_none_when_sm_is_a_file_not_dir(self, tmp_path):
        from pbip_tmp_generator import _find_nested_sm
        (tmp_path / "Report.SemanticModel").write_text("")
        assert _find_nested_sm(str(tmp_path), "parent") is None

    def test_finds_plain_sm_subfolder(self, tmp_path):
        from pbip_tmp_generator import _find_nested_sm
        sm_dir = tmp_path / "MyReport.SemanticModel"
        sm_dir.mkdir()
        result = _find_nested_sm(str(tmp_path), "parent")
        assert result is not None
        assert result["output_name"] == "parent"
        assert result["semantic_model_dir"] == str(sm_dir)

    def test_finds_databricks_sm_subfolder(self, tmp_path):
        from pbip_tmp_generator import _find_nested_sm
        sm_dir = tmp_path / "Report_databricks.SemanticModel"
        sm_dir.mkdir()
        result = _find_nested_sm(str(tmp_path), "proj")
        assert result is not None
        assert str(sm_dir) == result["semantic_model_dir"]


class TestFindPbipProjects:
    def test_case_a_direct_sm_folder(self, tmp_path):
        from pbip_tmp_generator import find_pbip_projects
        sm = tmp_path / "Sales.SemanticModel"
        sm.mkdir()
        projects = find_pbip_projects(str(tmp_path))
        assert len(projects) == 1
        assert projects[0]["output_name"] == "Sales.SemanticModel"

    def test_case_b_nested_sm_folder(self, tmp_path):
        from pbip_tmp_generator import find_pbip_projects
        proj = tmp_path / "Insurance Analysis"
        proj.mkdir()
        sm = proj / "Insurance Analysis_databricks.SemanticModel"
        sm.mkdir()
        projects = find_pbip_projects(str(tmp_path))
        assert len(projects) == 1
        assert projects[0]["output_name"] == "Insurance Analysis"
        assert projects[0]["project_root"] == str(proj)

    def test_skips_non_directory_entries(self, tmp_path):
        from pbip_tmp_generator import find_pbip_projects
        (tmp_path / "README.txt").write_text("hello")
        projects = find_pbip_projects(str(tmp_path))
        assert projects == []

    def test_skips_outer_folder_with_no_sm_inside(self, tmp_path):
        from pbip_tmp_generator import find_pbip_projects
        (tmp_path / "SomeFolder").mkdir()
        assert find_pbip_projects(str(tmp_path)) == []

    def test_mixed_case_a_and_case_b(self, tmp_path):
        from pbip_tmp_generator import find_pbip_projects
        # Case A
        (tmp_path / "Direct.SemanticModel").mkdir()
        # Case B
        proj = tmp_path / "Nested"
        proj.mkdir()
        (proj / "Nested.SemanticModel").mkdir()
        projects = find_pbip_projects(str(tmp_path))
        assert len(projects) == 2

    def test_empty_input_dir(self, tmp_path):
        from pbip_tmp_generator import find_pbip_projects
        assert find_pbip_projects(str(tmp_path)) == []


# ===========================================================================
# sequentialworkflow.py — pure helpers (no runtime/agent needed)
# ===========================================================================
# conftest.py mocks 'sequentialworkflow' before collection; we need the real
# module.  Pop the mock, import the real one, then restore the mock so other
# tests (which expect a mock) are unaffected.
_sw_conftest_mock = sys.modules.pop("sequentialworkflow", None)
try:
    import sequentialworkflow as _real_sw
except Exception:
    _real_sw = None  # type: ignore
if _sw_conftest_mock is not None:
    sys.modules["sequentialworkflow"] = _sw_conftest_mock

class TestSelectModelClient:
    def test_gpt4o_returns_azure_client(self):
        if _real_sw is None:
            pytest.skip("sequentialworkflow could not be imported")
        mock_client = MagicMock()
        sys.modules["config"].azure_client = mock_client
        result = _real_sw._select_model_client("gpt4o")
        assert result is mock_client

    def test_gemini_returns_google_client(self):
        if _real_sw is None:
            pytest.skip("sequentialworkflow could not be imported")
        mock_client = MagicMock()
        sys.modules["config"].google_client = mock_client
        result = _real_sw._select_model_client("gemini_1.5_pro")
        assert result is mock_client

    def test_unsupported_model_raises_value_error(self):
        if _real_sw is None:
            pytest.skip("sequentialworkflow could not be imported")
        with pytest.raises(ValueError, match="Unsupported model"):
            _real_sw._select_model_client("gpt3")


class TestBuildTableColumnsMap:
    def test_excludes_calculated_column_names(self):
        if _real_sw is None:
            pytest.skip("sequentialworkflow could not be imported")
        data = {
            "tables": [
                {
                    "id": "t1",
                    "columns": [
                        {"name": "base_col"},
                        {"name": "calc_col"},
                    ]
                }
            ]
        }
        result = _real_sw._build_table_columns_map(data, calc_names={"calc_col"})
        assert "base_col" in result["t1"]
        assert "calc_col" not in result["t1"]

    def test_empty_tables_returns_empty_map(self):
        if _real_sw is None:
            pytest.skip("sequentialworkflow could not be imported")
        assert _real_sw._build_table_columns_map({"tables": []}, set()) == {}

    def test_multiple_tables_mapped_by_id(self):
        if _real_sw is None:
            pytest.skip("sequentialworkflow could not be imported")
        data = {
            "tables": [
                {"id": "t1", "columns": [{"name": "a"}, {"name": "b"}]},
                {"id": "t2", "columns": [{"name": "x"}]},
            ]
        }
        result = _real_sw._build_table_columns_map(data, set())
        assert "a" in result["t1"] and "b" in result["t1"]
        assert "x" in result["t2"]


class TestDeduplicateCalculatedColumns:
    def test_no_calculations_leaves_columns_unchanged(self):
        if _real_sw is None:
            pytest.skip("sequentialworkflow could not be imported")
        data = {
            "calculations": [],
            "tables": [{"id": "t1", "columns": [{"name": "amount"}]}],
        }
        _real_sw._deduplicate_calculated_columns(data)
        assert data["tables"][0]["columns"] == [{"name": "amount"}]

    def test_removes_calc_col_from_table_without_dependency(self):
        if _real_sw is None:
            pytest.skip("sequentialworkflow could not be imported")
        # calc "Total" depends on "base_amt" but table t1 doesn't have "base_amt"
        data = {
            "calculations": [{"name": "Total", "depends_on_columns": ["base_amt"]}],
            "tables": [
                {
                    "id": "t1",
                    "columns": [{"name": "id"}, {"name": "Total"}],
                }
            ],
        }
        _real_sw._deduplicate_calculated_columns(data)
        col_names = [c["name"] for c in data["tables"][0]["columns"]]
        assert "Total" not in col_names

    def test_keeps_calc_col_in_table_that_owns_dependency(self):
        if _real_sw is None:
            pytest.skip("sequentialworkflow could not be imported")
        data = {
            "calculations": [{"name": "Total", "depends_on_columns": ["base_amt"]}],
            "tables": [
                {
                    "id": "t1",
                    "columns": [{"name": "base_amt"}, {"name": "Total"}],
                }
            ],
        }
        _real_sw._deduplicate_calculated_columns(data)
        col_names = [c["name"] for c in data["tables"][0]["columns"]]
        assert "Total" in col_names
        assert "base_amt" in col_names

    def test_calc_with_no_deps_is_removed(self):
        if _real_sw is None:
            pytest.skip("sequentialworkflow could not be imported")
        # depends_on_columns is empty → deps is falsy → removed
        data = {
            "calculations": [{"name": "EmptyCalc", "depends_on_columns": []}],
            "tables": [
                {"id": "t1", "columns": [{"name": "EmptyCalc"}]}
            ],
        }
        _real_sw._deduplicate_calculated_columns(data)
        col_names = [c["name"] for c in data["tables"][0]["columns"]]
        assert "EmptyCalc" not in col_names

    def test_non_calc_columns_always_kept(self):
        if _real_sw is None:
            pytest.skip("sequentialworkflow could not be imported")
        data = {
            "calculations": [{"name": "Calc", "depends_on_columns": ["other"]}],
            "tables": [
                {"id": "t1", "columns": [{"name": "id"}, {"name": "name"}]}
            ],
        }
        _real_sw._deduplicate_calculated_columns(data)
        col_names = [c["name"] for c in data["tables"][0]["columns"]]
        assert "id" in col_names
        assert "name" in col_names


class TestInjectMetadataAndReorder:
    def test_injects_all_required_keys(self):
        if _real_sw is None:
            pytest.skip("sequentialworkflow could not be imported")
        result = _real_sw._inject_metadata_and_reorder({}, "MyWorkbook")
        for k in ("schema_version", "model_id", "name", "extracted_at"):
            assert k in result

    def test_does_not_overwrite_existing_values(self):
        if _real_sw is None:
            pytest.skip("sequentialworkflow could not be imported")
        result = _real_sw._inject_metadata_and_reorder(
            {"model_id": "existing-id", "name": "existing-name"}, "new-name"
        )
        assert result["model_id"] == "existing-id"
        assert result["name"] == "existing-name"

    def test_schema_version_defaults_to_1_0(self):
        if _real_sw is None:
            pytest.skip("sequentialworkflow could not be imported")
        result = _real_sw._inject_metadata_and_reorder({}, "wb")
        assert result["schema_version"] == "1.0"

    def test_top_keys_appear_first(self):
        if _real_sw is None:
            pytest.skip("sequentialworkflow could not be imported")
        data = {"extra_key": "val", "another": 123}
        result = _real_sw._inject_metadata_and_reorder(data, "wb")
        keys = list(result.keys())
        top = ["schema_version", "model_id", "name", "extracted_at"]
        # All top keys must precede non-top keys
        last_top_idx = max(keys.index(k) for k in top if k in keys)
        first_extra_idx = keys.index("extra_key")
        assert last_top_idx < first_extra_idx

    def test_name_set_from_filename_when_missing(self):
        if _real_sw is None:
            pytest.skip("sequentialworkflow could not be imported")
        result = _real_sw._inject_metadata_and_reorder({}, "My Tableau Report")
        assert result["name"] == "My Tableau Report"


class TestCollectVisualsResultErrorPath:
    def test_returns_none_and_zero_on_exception(self):
        if _real_sw is None:
            pytest.skip("sequentialworkflow could not be imported")
        original_queue = _real_sw.queue_visuals
        mock_queue = MagicMock()
        mock_queue.get = AsyncMock(side_effect=RuntimeError("queue error"))
        _real_sw.queue_visuals = mock_queue
        try:
            parsed, elapsed = asyncio.run(_real_sw._collect_visuals_result())
            assert parsed is None
            assert elapsed == 0.0
        finally:
            _real_sw.queue_visuals = original_queue

    def test_returns_dict_when_content_is_json_string(self):
        if _real_sw is None:
            pytest.skip("sequentialworkflow could not be imported")
        original_queue = _real_sw.queue_visuals
        mock_msg = MagicMock()
        mock_msg.content = json.dumps({"pages": []})
        mock_queue = MagicMock()
        mock_queue.get = AsyncMock(return_value=mock_msg)
        _real_sw.queue_visuals = mock_queue
        try:
            parsed, elapsed = asyncio.run(_real_sw._collect_visuals_result())
            assert isinstance(parsed, dict)
            assert "pages" in parsed
            assert elapsed >= 0.0
        finally:
            _real_sw.queue_visuals = original_queue

    def test_returns_dict_when_content_is_already_dict(self):
        if _real_sw is None:
            pytest.skip("sequentialworkflow could not be imported")
        original_queue = _real_sw.queue_visuals
        mock_msg = MagicMock()
        mock_msg.content = {"pages": [{"name": "Page1"}]}
        mock_queue = MagicMock()
        mock_queue.get = AsyncMock(return_value=mock_msg)
        _real_sw.queue_visuals = mock_queue
        try:
            parsed, elapsed = asyncio.run(_real_sw._collect_visuals_result())
            assert parsed == {"pages": [{"name": "Page1"}]}
        finally:
            _real_sw.queue_visuals = original_queue


# ===========================================================================
# generate_mapping_report.py
# ===========================================================================

class TestNotFoundConstant:
    def test_constant_value(self):
        from generate_mapping_report import _NOT_FOUND
        assert _NOT_FOUND == "Not Found"


class TestGetStatus:
    def test_found_when_key_exists_and_new_src_nonempty(self):
        from generate_mapping_report import get_status
        lookup = {("claims", "PolicyID"): "policy_id_new"}
        new_src, status = get_status("claims.xlsx", "claims", "PolicyID", lookup)
        assert status == "Found"
        assert new_src == "policy_id_new"

    def test_not_found_when_key_missing(self):
        from generate_mapping_report import get_status, _NOT_FOUND
        new_src, status = get_status("f.xlsx", "claims", "MissingCol", {})
        assert status == _NOT_FOUND
        assert new_src == ""

    def test_not_found_when_new_source_column_empty(self):
        from generate_mapping_report import get_status, _NOT_FOUND
        lookup = {("claims", "PolicyID"): ""}
        new_src, status = get_status("f.xlsx", "claims", "PolicyID", lookup)
        assert status == _NOT_FOUND
        assert new_src == ""

    def test_not_found_when_new_source_column_is_none(self):
        from generate_mapping_report import get_status, _NOT_FOUND
        lookup = {("claims", "PolicyID"): None}
        new_src, status = get_status("f.xlsx", "claims", "PolicyID", lookup)
        assert status == _NOT_FOUND

    def test_lookup_key_uses_table_name_and_col(self):
        from generate_mapping_report import get_status
        lookup = {("tableA", "col1"): "new_col1", ("tableB", "col1"): "other"}
        _, status_a = get_status("f.xlsx", "tableA", "col1", lookup)
        _, status_b = get_status("f.xlsx", "tableB", "col1", lookup)
        assert status_a == "Found"
        assert status_b == "Found"

    def test_file_name_parameter_not_used_in_lookup(self):
        # file_name is in the signature but not used in the key — should not affect result
        from generate_mapping_report import get_status
        lookup = {("t", "c"): "v"}
        _, s1 = get_status("file_a.xlsx", "t", "c", lookup)
        _, s2 = get_status("file_b.xlsx", "t", "c", lookup)
        assert s1 == s2 == "Found"


class TestFindHeaderRow:
    def test_finds_row_with_source_column(self):
        from generate_mapping_report import _find_header_row
        rows = [
            ("Title", None, None),
            ("Source Schema", "Source Column", "New Source Column"),
        ]
        assert _find_header_row(rows) == 1

    def test_returns_none_when_no_header_found(self):
        from generate_mapping_report import _find_header_row
        rows = [("foo", "bar"), ("baz", "qux")]
        assert _find_header_row(rows) is None

    def test_finds_header_at_first_row(self):
        from generate_mapping_report import _find_header_row
        rows = [("source column", "new source column")]
        assert _find_header_row(rows) == 0

    def test_case_insensitive_match(self):
        from generate_mapping_report import _find_header_row
        rows = [("SOURCE COLUMN", "OTHER")]
        assert _find_header_row(rows) == 0

    def test_handles_none_cells_gracefully(self):
        from generate_mapping_report import _find_header_row
        rows = [(None, None, None), (None, "source column", None)]
        assert _find_header_row(rows) == 1

    def test_returns_none_for_empty_rows(self):
        from generate_mapping_report import _find_header_row
        assert _find_header_row([]) is None
