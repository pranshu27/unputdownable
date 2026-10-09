"""Evaluation harness for generated PySpark / artifacts.

Why evaluation
--------------
"Is the agent working fine?" needs a measurable answer. We compare generated output against
a reference (golden) output and compute similarity + structural metrics. This enables
regression testing, prompt A/B comparison, and CI gates.

Metrics implemented (dependency-free, deterministic)
----------------------------------------------------
- ROUGE-N (N=1,2): n-gram recall/precision/F1 overlap with the reference.
- ROUGE-L: longest-common-subsequence based F1 (good for code line order).
- Token F1 / exact-match.
- Structural code checks: does generated PySpark reference expected DataFrames, preserve
  the SQL override, and parse as Python (ast.parse)?

For production you would also add: BLEU, CodeBLEU (AST + dataflow aware), embedding cosine
(semantic), execution-based parity (run both pipelines on sample data and diff row counts /
checksums), and LLM-as-a-judge scoring.
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[^\sA-Za-z0-9]")


def _tokenize(text: str) -> List[str]:
    return _WORD_RE.findall(text or "")


def _ngrams(tokens: Sequence[str], n: int) -> Counter:
    return Counter(tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1))


def _prf(overlap: int, gen_total: int, ref_total: int) -> Dict[str, float]:
    precision = overlap / gen_total if gen_total else 0.0
    recall = overlap / ref_total if ref_total else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def rouge_n(generated: str, reference: str, n: int = 1) -> Dict[str, float]:
    g = _ngrams(_tokenize(generated), n)
    r = _ngrams(_tokenize(reference), n)
    overlap = sum((g & r).values())
    return _prf(overlap, sum(g.values()), sum(r.values()))


def _lcs_length(a: Sequence[str], b: Sequence[str]) -> int:
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[-1][-1]


def rouge_l(generated: str, reference: str) -> Dict[str, float]:
    g, r = _tokenize(generated), _tokenize(reference)
    lcs = _lcs_length(g, r)
    return _prf(lcs, len(g), len(r))


def token_f1(generated: str, reference: str) -> Dict[str, float]:
    g, r = Counter(_tokenize(generated)), Counter(_tokenize(reference))
    overlap = sum((g & r).values())
    return _prf(overlap, sum(g.values()), sum(r.values()))


def exact_match(generated: str, reference: str) -> float:
    return 1.0 if (generated or "").strip() == (reference or "").strip() else 0.0


# --------------------------------------------------------------------------- #
# Structural code checks
# --------------------------------------------------------------------------- #


def is_parseable_python(code: str) -> bool:
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


def references_expected(code: str, expected_symbols: Sequence[str]) -> Dict[str, bool]:
    return {sym: (sym in (code or "")) for sym in expected_symbols}


# --------------------------------------------------------------------------- #
# Aggregate report
# --------------------------------------------------------------------------- #


@dataclass
class EvaluationResult:
    rouge_1: Dict[str, float]
    rouge_2: Dict[str, float]
    rouge_l: Dict[str, float]
    token_f1: Dict[str, float]
    exact_match: float
    structural: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rouge_1": self.rouge_1,
            "rouge_2": self.rouge_2,
            "rouge_l": self.rouge_l,
            "token_f1": self.token_f1,
            "exact_match": self.exact_match,
            "structural": self.structural,
        }

    @property
    def overall_f1(self) -> float:
        return round(
            (self.rouge_1["f1"] + self.rouge_2["f1"] + self.rouge_l["f1"]) / 3, 4
        )


def evaluate(
    generated: str,
    reference: str,
    expected_symbols: Optional[Sequence[str]] = None,
) -> EvaluationResult:
    """Compute the full metric suite for one generated/reference pair."""
    structural: Dict[str, Any] = {"parseable_python": is_parseable_python(generated)}
    if expected_symbols:
        structural["references"] = references_expected(generated, expected_symbols)
    return EvaluationResult(
        rouge_1=rouge_n(generated, reference, 1),
        rouge_2=rouge_n(generated, reference, 2),
        rouge_l=rouge_l(generated, reference),
        token_f1=token_f1(generated, reference),
        exact_match=exact_match(generated, reference),
        structural=structural,
    )


def evaluate_batch(
    pairs: List[Dict[str, str]],
) -> Dict[str, Any]:
    """Evaluate a list of {"generated":..., "reference":...} pairs and average."""
    results = [evaluate(p["generated"], p["reference"]) for p in pairs]
    n = max(len(results), 1)
    avg = lambda key: round(sum(getattr(r, key)["f1"] for r in results) / n, 4)
    return {
        "count": len(results),
        "avg_rouge_1_f1": avg("rouge_1"),
        "avg_rouge_2_f1": avg("rouge_2"),
        "avg_rouge_l_f1": avg("rouge_l"),
        "avg_overall_f1": round(sum(r.overall_f1 for r in results) / n, 4),
        "per_item": [r.to_dict() for r in results],
    }
