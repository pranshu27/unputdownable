from rag_system.eval.quality_gate import evaluate_drop_gate


def _report(faithfulness: float) -> dict:
    return {"scores": {"faithfulness": faithfulness}}


def test_gate_passes_when_drop_is_below_threshold():
    passed, stats = evaluate_drop_gate(
        baseline_report=_report(0.40),
        current_report=_report(0.39),
        metric="faithfulness",
        max_drop=0.02,
    )

    assert passed is True
    assert round(stats["drop"], 6) == 0.01


def test_gate_passes_when_drop_equals_threshold():
    passed, stats = evaluate_drop_gate(
        baseline_report=_report(0.40),
        current_report=_report(0.38),
        metric="faithfulness",
        max_drop=0.02,
    )

    assert passed is True
    assert round(stats["drop"], 6) == 0.02


def test_gate_fails_when_drop_exceeds_threshold():
    passed, stats = evaluate_drop_gate(
        baseline_report=_report(0.40),
        current_report=_report(0.379),
        metric="faithfulness",
        max_drop=0.02,
    )

    assert passed is False
    assert stats["drop"] > 0.02
