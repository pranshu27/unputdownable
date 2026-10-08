from rag_system.eval.retrieval_eval import (
    Matcher,
    evaluate_hits,
    matcher_matches,
    ndcg_at_k,
    summarize_by_bucket,
)


def test_matcher_matches_core_fields():
    hit = {
        "node_class": "TRANSFORMATION",
        "source_file": "wf_4201_calculate_interaction_facts.XML",
        "name": "SQ_SQL_Override_InteractionEvent",
        "text": "SQL_OVERRIDE: select * from foo",
        "metadata": {"type": "Source Qualifier"},
    }
    matcher = Matcher(
        score=3,
        node_class="TRANSFORMATION",
        source_file_contains="wf_4201",
        name_contains="SQ_SQL_Override",
        text_contains="SQL_OVERRIDE",
        metadata_contains={"type": "Source"},
    )
    assert matcher_matches(hit, matcher)


def test_ndcg_perfect_order_is_one():
    assert ndcg_at_k([3, 2, 1], [3, 2, 1], 3) == 1.0


def test_ndcg_worse_order_is_lower():
    perfect = ndcg_at_k([3, 2, 1], [3, 2, 1], 3)
    worse = ndcg_at_k([1, 2, 3], [3, 2, 1], 3)
    assert worse < perfect


def test_evaluate_hits_recall_coverage():
    hits = [
        {"name": "A", "node_class": "TRANSFORMATION", "text": "alpha"},
        {"name": "B", "node_class": "SOURCE", "text": "beta"},
    ]
    matchers = [
        Matcher(score=3, node_class="TRANSFORMATION", text_contains="alpha"),
        Matcher(score=2, node_class="TARGET", text_contains="gamma"),
    ]

    out = evaluate_hits(hits, matchers, k=5)
    assert out["matched_matchers"] == 1
    assert out["total_matchers"] == 2
    assert out["recall_at_k"] == 0.5


def test_evaluate_hits_ndcg_is_bounded_with_duplicate_matches():
    hits = [
        {"name": "A1", "node_class": "TRANSFORMATION", "text": "SQL_OVERRIDE"},
        {"name": "A2", "node_class": "TRANSFORMATION", "text": "SQL_OVERRIDE"},
        {"name": "A3", "node_class": "TRANSFORMATION", "text": "SQL_OVERRIDE"},
    ]
    matchers = [
        Matcher(score=3, node_class="TRANSFORMATION", text_contains="SQL_OVERRIDE"),
    ]

    out = evaluate_hits(hits, matchers, k=3)
    assert out["ndcg_at_k"] == 1.0


def test_summarize_by_bucket_aggregates_metrics():
    rows = [
        {"bucket": "identifier", "metrics": {"recall_at_k": 1.0, "ndcg_at_k": 0.8}},
        {"bucket": "identifier", "metrics": {"recall_at_k": 0.5, "ndcg_at_k": 0.2}},
        {"bucket": "lineage", "metrics": {"recall_at_k": 0.25, "ndcg_at_k": 0.1}},
    ]

    out = summarize_by_bucket(rows)
    assert out["identifier"]["query_count"] == 2
    assert out["identifier"]["avg_recall_at_k"] == 0.75
    assert out["identifier"]["avg_ndcg_at_k"] == 0.5
    assert out["lineage"]["query_count"] == 1
    assert out["lineage"]["avg_recall_at_k"] == 0.25
