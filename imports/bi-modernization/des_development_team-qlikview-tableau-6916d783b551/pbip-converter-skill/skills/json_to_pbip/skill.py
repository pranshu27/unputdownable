import os, sys, traceback
from pathlib import Path

# Ensure core and skills are importable when run standalone
_BASE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BASE))

from core.base_skill import BaseSkill


class JsonToPbipSkill(BaseSkill):
    """
    Converts Tableau or Power BI JSON exports (common-model format)
    to a Power BI .pbip folder structure openable in Power BI Desktop.
    """

    name          = "json_to_pbip"
    display       = "JSON → PBIP Converter"
    description   = (
        "Use when the user provides a Tableau or Power BI export JSON "
        "and wants a Power BI .pbip project folder."
    )
    input_type    = "json"
    skill_md_path = str(Path(__file__).parent / "SKILL.md")

    tool_params   = {}
    tool_required = []

    def __init__(self, output_base: str = None):
        _root = Path(__file__).resolve().parent.parent.parent
        self._output_base = output_base or str(_root / "outputs")

    def run(self, _input_data=None, **kwargs) -> dict:
        """
        _input_data is the already-parsed JSON dict injected by the agent.
        Source type and report name are auto-detected from the JSON.
        Returns: { "output_dir": str, "files": list, "errors": list }
        """
        if _input_data is None:
            return {"output_dir": "", "files": [], "errors": ["No JSON input loaded."]}

        from skills.json_to_pbip.src.parser    import parse_common_model, detect_source
        from skills.json_to_pbip.src.mapper    import map_intermediate
        from skills.json_to_pbip.src.writer    import write_pbip
        from skills.json_to_pbip.src.validator import validate
        from skills.json_to_pbip.src           import debug_collector as _dbg

        _debug_base = os.path.join(os.path.dirname(self._output_base), "debug")
        _debug_dir  = _dbg.init(_debug_base, "MyReport")

        try:
            # ── Step 2 — Parse ────────────────────────────────────────────────
            print("\n[2/4] Parsing input JSON")
            detected     = detect_source(_input_data)
            intermediate = parse_common_model(_input_data, detected, None)

            n_tables   = len(intermediate.get("tables", []))
            tbl_names  = ", ".join(t["name"] for t in intermediate.get("tables", []))
            n_visuals  = sum(len(p.get("visuals", [])) for p in intermediate.get("pages", []))
            n_pages    = len(intermediate.get("pages", []))
            n_measures = sum(len(t.get("measures", [])) for t in intermediate.get("tables", []))
            n_columns  = sum(len(t.get("columns", [])) for t in intermediate.get("tables", []))
            print(f"      ✓ Source detected: {detected}")
            print(f"      ✓ Tables: {n_tables} ({tbl_names})")
            print(f"      ✓ Columns: {n_columns}  |  Measures: {n_measures}")
            print(f"      ✓ Pages: {n_pages}  |  Visuals: {n_visuals}")

            # ── Step 3 — Map (LLM) ────────────────────────────────────────────
            print("\n[3/4] Mapping with AI (resolving Tableau IDs → Power BI names)")
            print("      … this may take 20-60s")
            mapped      = map_intermediate(intermediate)
            n_rels      = len(mapped.get("relationships", []))
            n_m_tables  = len(mapped.get("tables", []))
            n_m_meas    = sum(len(t.get("measures", [])) for t in mapped.get("tables", []))
            n_m_visuals = sum(len(p.get("visuals", [])) for p in mapped.get("pages", []))
            n_m_pages   = len(mapped.get("pages", []))
            print(f"      ✓ DAX measures generated: {n_m_meas}")
            print(f"      ✓ Relationships mapped: {n_rels}")
            print(f"      ✓ Report name: {mapped.get('reportName')}")

            # ── Step 4 — Write .pbip folder ───────────────────────────────────
            print("\n[4/4] Building Power BI project folder")
            report = mapped["reportName"]
            output_dir = os.path.join(self._output_base, report)
            files = write_pbip(mapped, output_dir)
            print(f"      ✓ Created Semantic Model folder: {report}.SemanticModel/")
            print(f"            • {n_m_tables} tables  •  {n_rels} relationships  •  {n_m_meas} measures")
            print(f"      ✓ Created Report folder: {report}.Report/")
            print(f"            • {n_m_pages} pages  •  {n_m_visuals} visuals")
            print(f"      ✓ Created .pbip entry file: {report}.pbip")
            print(f"      ✓ Total files written: {len(files)}")

            errors = validate(output_dir)

        except Exception as e:
            print(f"\n      ✗ Pipeline crashed: {e}")
            return {"output_dir": "", "files": [], "errors": [traceback.format_exc()],
                    "debug_dir": _debug_dir}

        return {
            "output_dir": output_dir,
            "debug_dir":  _debug_dir,
            "files":      files,
            "errors":     errors,
        }
