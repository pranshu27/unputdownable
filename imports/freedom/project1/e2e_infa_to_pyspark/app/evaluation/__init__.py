"""Evaluation layer: ROUGE-N/L, token-F1, structural checks + production strategies."""

from app.evaluation.metrics import (  # noqa: F401
    EvaluationResult,
    evaluate,
    evaluate_batch,
    rouge_l,
    rouge_n,
    token_f1,
)
from app.evaluation.prod_strategies import (  # noqa: F401
    embedding_similarity,
    execution_parity,
    llm_judge,
    production_scorecard,
)
