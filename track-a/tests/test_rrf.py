"""RRF (reciprocal rank fusion) tests — algorithm implemented from scratch."""

from app.core.rrf import reciprocal_rank_fusion


def test_single_list_preserves_order():
    fused = reciprocal_rank_fusion([["a", "b", "c"]], k=60)
    assert [item for item, _ in fused] == ["a", "b", "c"]
    assert fused[0][1] > fused[1][1] > fused[2][1]


def test_item_in_both_lists_beats_item_in_one():
    fused = reciprocal_rank_fusion([["a", "b"], ["x", "a"]], k=60)
    assert fused[0][0] == "a"
    a_score = fused[0][1]
    b_score = dict(fused)["b"]
    x_score = dict(fused)["x"]
    assert a_score == 1 / (60 + 1) + 1 / (60 + 2)
    assert a_score > b_score and a_score > x_score


def test_k_dampening():
    top_of_one_list = reciprocal_rank_fusion([["a"]], k=60)[0][1]
    assert abs(top_of_one_list - 1 / 61) < 1e-12


def test_duplicates_within_list_deduplicated():
    fused = reciprocal_rank_fusion([["a", "a", "b"]], k=60)
    assert [i for i, _ in fused] == ["a", "b"]


def test_disjoint_lists_merged():
    fused = reciprocal_rank_fusion([["a", "b"], ["c", "d"]], k=60)
    order = [i for i, _ in fused]
    assert order[0] in {"a", "c"}
    assert set(order) == {"a", "b", "c", "d"}


def test_weighted_rank_fusion_matches_uniform_when_weights_equal():
    from app.core.rrf import reciprocal_rank_fusion, weighted_rank_fusion

    lists = [["a", "b", "c"], ["b", "a"]]
    assert weighted_rank_fusion(lists, k=60) == reciprocal_rank_fusion(lists, k=60)


def test_weighted_rank_fusion_respects_weights():
    from app.core.rrf import weighted_rank_fusion

    # x tops list 0, y tops list 1; doubling list 0's weight must lift x above y
    out = dict(weighted_rank_fusion([["x"], ["y"]], k=60, weights=[2.0, 1.0]))
    assert out["x"] > out["y"]
    # and with equal weights they tie in first-seen order (x wins by insertion)
    out2 = dict(weighted_rank_fusion([["x"], ["y"]], k=60))
    assert out2["x"] == out2["y"]


def test_weighted_rank_fusion_validates():
    from app.core.rrf import weighted_rank_fusion

    import pytest

    with pytest.raises(ValueError):
        weighted_rank_fusion([["a"]], weights=[1.0, 2.0])
    with pytest.raises(ValueError):
        weighted_rank_fusion([["a"]], weights=[-1.0])
