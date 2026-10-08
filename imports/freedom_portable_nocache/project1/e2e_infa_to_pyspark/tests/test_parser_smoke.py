"""Smoke tests for the agentic codegen package.

These tests exercise the deterministic, non-LLM parts of the pipeline (XML parsing,
folder pre-processing, barrier state) so CI can run without Azure credentials.
"""

import asyncio
import json
from pathlib import Path

from app.agents.result_collector_agent import CollectorState
from app.utils.pc_file_processor import flatten_mapping_to_nodes, get_export_type
from app.utils.xml_parser import parse_powercenter_xml

XML_PATH = (
    Path(__file__).resolve().parents[2]
    / "app_CALCULATE_EINTERACTION"
    / "wf_4202_fnd_rltinteraction.XML"
)
FOCUS_MAPPING = "m_4202_dt_chn_rltinteractionagreement"


def test_export_type_detected() -> None:
    assert get_export_type(str(XML_PATH)) == "powercenter"


def test_parse_focus_mapping() -> None:
    parsed = parse_powercenter_xml(str(XML_PATH), focus_mapping=FOCUS_MAPPING)
    assert parsed["sources"]
    assert parsed["targets"]
    assert any(m["name"] == FOCUS_MAPPING for m in parsed["mappings"])


def test_flatten_produces_json_serializable_nodes() -> None:
    parsed = parse_powercenter_xml(str(XML_PATH), focus_mapping=FOCUS_MAPPING)
    nodes = flatten_mapping_to_nodes(parsed)
    assert len(nodes) > 0
    for node in nodes:
        json.dumps(node)
    assert {n["node_class"] for n in nodes} & {"SOURCE", "TRANSFORMATION", "TARGET"}


def test_collector_barrier_releases() -> None:
    async def _run() -> int:
        state = CollectorState()
        state.set_expected_count(2)
        state.results.append({"ok": 1})
        state.response_counter += 1
        state.results.append({"ok": 2})
        state.response_counter += 1
        if state.response_counter >= state.expected_count:
            state.event.set()
        return len(await state.wait_for_results(timeout=2))

    assert asyncio.new_event_loop().run_until_complete(_run()) == 2
