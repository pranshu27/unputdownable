from pathlib import Path

import pytest

from rag_system.eval.ragas_eval import _extract_ragas_scores, _load_dataset


class _FakeEvalResult:
    def __init__(self, data):
        self._data = data

    def __getitem__(self, item):
        return self._data[item]


def test_extract_ragas_scores_from_dict_like_result():
    fake = _FakeEvalResult({"faithfulness": 0.81, "answer_relevancy": 0.72})
    out = _extract_ragas_scores(fake)
    assert out["faithfulness"] == pytest.approx(0.81)
    assert out["answer_relevancy"] == pytest.approx(0.72)


def test_load_dataset_requires_query_and_ground_truth(tmp_path: Path):
    ds = tmp_path / "answer_eval.jsonl"
    ds.write_text(
        '{"id":"q1","query":"How is InteractionEvent_Id used?","ground_truth":"It is traced through mappings."}\n',
        encoding="utf-8",
    )

    rows = _load_dataset(
        dataset_path=ds,
        default_k=6,
        default_mode="hybrid",
        rerank=False,
    )

    assert len(rows) == 1
    assert rows[0].id == "q1"
    assert rows[0].mode == "hybrid"
    assert rows[0].k == 6


def test_load_dataset_rejects_empty_query(tmp_path: Path):
    ds = tmp_path / "bad_eval.jsonl"
    ds.write_text('{"id":"q1","query":"","ground_truth":"x"}\n', encoding="utf-8")

    with pytest.raises(ValueError):
        _load_dataset(
            dataset_path=ds,
            default_k=6,
            default_mode="hybrid",
            rerank=False,
        )
