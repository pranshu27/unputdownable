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
