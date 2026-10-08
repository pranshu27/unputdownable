"""Production-grade evaluation strategies for generated PySpark.

`metrics.py` covers deterministic, offline reference-overlap metrics (ROUGE / token-F1 /
structural checks) — perfect for fast CI gates. In production you also want *semantic* and
*behavioural* signals. This module collects those strategies. They are written to be
optional and side-effect-light: the embedding metric reuses the RAG embedder; the
execution-parity and LLM-judge strategies are scaffolds you point at a Spark session / a
judge model.

Strategy catalogue
------------------
1. Embedding cosine similarity (semantic) — `embedding_similarity`.
   Two snippets can be lexically different but semantically equivalent
   (`F.col('a') - F.col('b')` vs `expr('a - b')`). Cosine of their embeddings captures that.
2. Execution-based parity (behavioural, the gold standard) — `execution_parity`.
   Run the generated PySpark and the legacy output on the SAME sample input and diff row
   counts, schema, and per-column checksums. If the data matches, the code is correct
   regardless of how it is written. Requires a Spark session + sample data, so it is a
   scaffold here.
3. LLM-as-a-judge (rubric scoring) — `llm_judge`.
   A strong model scores correctness / fidelity / safety against a rubric. Catches issues
   that overlap metrics miss; pair with a confidence threshold and human review.
4. CodeBLEU (AST + dataflow aware) — noted; plug in `codebleu` package in CI if desired.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# --------------------------------------------------------------------------- #
# 1. Semantic similarity via embeddings
# --------------------------------------------------------------------------- #


def embedding_similarity(generated: str, reference: str, embedder=None) -> float:
    """Cosine similarity of embedding vectors for two code snippets.

    Uses the RAG embedding provider by default (Azure when configured, hashing offline).
    """
    if embedder is None:
        from app.rag.embeddings import get_embedding_provider

        embedder = get_embedding_provider()
    g_vec, r_vec = embedder.embed([generated, reference])
    # vectors are L2-normalized, so dot product == cosine similarity
    return round(sum(a * b for a, b in zip(g_vec, r_vec)), 4)


# --------------------------------------------------------------------------- #
# 2. Execution-based parity (behavioural)
# --------------------------------------------------------------------------- #


@dataclass
class ParityResult:
    matched: bool
    row_count_generated: int = 0
    row_count_reference: int = 0
    schema_match: bool = False
    column_checksums_match: bool = False
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "matched": self.matched,
            "row_count_generated": self.row_count_generated,
            "row_count_reference": self.row_count_reference,
            "schema_match": self.schema_match,
            "column_checksums_match": self.column_checksums_match,
            "details": self.details,
        }


def execution_parity(generated_df, reference_df) -> ParityResult:
    """Compare two Spark DataFrames for behavioural equivalence.

    Pass the DataFrame produced by the generated PySpark and the legacy/golden DataFrame
    (both already computed in a Spark session). Compares row count, schema, and a
    per-column checksum so column order / naming differences are caught.

    This is the strongest correctness signal: if the data matches on representative input,
    the translation is correct regardless of code style.
    """
    from pyspark.sql import functions as F  # local import; only when actually executing

    gen_count = generated_df.count()
    ref_count = reference_df.count()
    schema_match = sorted(generated_df.columns) == sorted(reference_df.columns)

    checksums_match = False
    details: Dict[str, Any] = {}
    if schema_match:
        cols = sorted(generated_df.columns)
        gen_sum = generated_df.select(
            [F.sum(F.hash(F.col(c)).cast("long")).alias(c) for c in cols]
        ).collect()[0].asDict()
        ref_sum = reference_df.select(
            [F.sum(F.hash(F.col(c)).cast("long")).alias(c) for c in cols]
        ).collect()[0].asDict()
        checksums_match = gen_sum == ref_sum
        details = {"generated_checksums": gen_sum, "reference_checksums": ref_sum}

    matched = (gen_count == ref_count) and schema_match and checksums_match
    return ParityResult(
        matched=matched,
        row_count_generated=gen_count,
        row_count_reference=ref_count,
        schema_match=schema_match,
        column_checksums_match=checksums_match,
        details=details,
    )


# --------------------------------------------------------------------------- #
# 3. LLM-as-a-judge
# --------------------------------------------------------------------------- #

LLM_JUDGE_SYSTEM_PROMPT = """
You are a strict code-review judge for Informatica->PySpark migrations. Score the GENERATED
PySpark against the REFERENCE and the stated intent. Return ONLY JSON:
{"correctness":0-1,"sql_fidelity":0-1,"safety":0-1,"readability":0-1,
 "overall":0-1,"issues":[str],"rationale":str}
Be conservative: penalize silent column drops, altered SQL overrides, and nondeterminism.
""".strip()


async def llm_judge(
    generated: str,
    reference: str,
    model_client,
    intent: str = "",
) -> Dict[str, Any]:
    """Score a snippet with a judge model. Returns the parsed JSON verdict (soft-fails)."""
    from autogen_core.models import SystemMessage, UserMessage

    user = (
        f"INTENT:\n{intent}\n\nREFERENCE:\n{reference}\n\nGENERATED:\n{generated}\n\n"
        "Return only the JSON verdict."
    )
    try:
        resp = await model_client.create(
            [SystemMessage(content=LLM_JUDGE_SYSTEM_PROMPT), UserMessage(content=user, source="user")]
        )
        text = str(resp.content).strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(text)
    except Exception as exc:  # soft-fail: never break a CI run on the judge
        return {"overall": 0.0, "issues": [f"judge_error: {exc}"], "rationale": ""}


# --------------------------------------------------------------------------- #
# Aggregator: combine offline metrics + production signals
# --------------------------------------------------------------------------- #


def production_scorecard(
    generated: str,
    reference: str,
    expected_symbols: Optional[List[str]] = None,
    embedder=None,
) -> Dict[str, Any]:
    """Offline metrics + semantic similarity in one dict (no Spark / no LLM needed)."""
    from app.evaluation.metrics import evaluate

    result = evaluate(generated, reference, expected_symbols=expected_symbols)
    scorecard = result.to_dict()
    scorecard["embedding_similarity"] = embedding_similarity(
        generated, reference, embedder=embedder
    )
    scorecard["overall_f1"] = result.overall_f1
    return scorecard
