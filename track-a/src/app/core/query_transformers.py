"""Query transformation pipeline - ADR 003 (pluggable, config-driven).

A chain of QueryTransformer strategies applied before retrieval. Everything here is
LLM-FREE by design in Week 3: decomposition and rewrite are deterministic rules; HyDE
ships as an interface with a pluggable Generator that degrades to a no-op until the
generation LLM lands (Week 7).
"""

from __future__ import annotations

import re
from typing import Callable, Protocol

from ..config import Settings, get_settings


class QueryTransformer(Protocol):
    """One strategy in the transformation pipeline."""

    name: str

    def transform(self, query: str) -> list[str]:
        """Return 0..n transformed variants (empty = strategy did not apply)."""
        ...


class SubQueryDecomposer:
    """Split compound questions into focused sub-queries (LLM-free).

    Splits on coordinating conjunctions and separators, strips interrogative filler
    AND leading articles from each fragment. Only fires when the query actually
    splits into more than one fragment (a simple query yields no variants).
    'What is the fee schedule and the latency budget?' -> ['fee schedule', 'latency budget'].
    """

    name = "subquery"

    _SPLIT_RE = re.compile(r"\b(?:and|also|plus|;|and then)\b", re.IGNORECASE)
    _FILLER_RE = re.compile(
        r"^(?:what|which|who|where|when|why|how)\s+(?:is|are|was|were|does|do|did)\b\s*",
        re.IGNORECASE,
    )
    _ARTICLE_RE = re.compile(r"^(?:the|a|an|our|their)\s+", re.IGNORECASE)

    def transform(self, query: str) -> list[str]:
        fragments = [f.strip(" ?.,!") for f in self._SPLIT_RE.split(query)]
        if len(fragments) <= 1:
            return []  # not compound -> no decomposition (a query is not its own variant)
        variants: list[str] = []
        for frag in fragments:
            frag = self._FILLER_RE.sub("", frag)
            frag = self._ARTICLE_RE.sub("", frag).strip()
            if len(frag.split()) >= 2:  # skip trivial one-word fragments
                variants.append(frag)
        return variants


class RewriteTransformer:
    """Deterministic cleanup rewrite (LLM-free): strip interrogative filler, trailing
    punctuation and leading articles, apply a small domain synonym map."""

    name = "rewrite"

    _FILLER_RE = re.compile(
        r"^(?:please\s+)?(?:tell me about|explain|describe|what is|what was|which|show me)\b\s*",
        re.IGNORECASE,
    )
    _ARTICLE_RE = re.compile(r"^(?:the|a|an|our|their)\s+", re.IGNORECASE)
    _SYNONYMS = {
        "revenue": "net sales",
        "profit": "net income",
        "cash": "cash and cash equivalents",
        "debt": "term loan",
    }

    def transform(self, query: str) -> list[str]:
        cleaned = self._FILLER_RE.sub("", query.strip())
        cleaned = cleaned.strip(" ?.!,")
        cleaned = self._ARTICLE_RE.sub("", cleaned).strip()
        for term, replacement in self._SYNONYMS.items():
            if term in cleaned.lower():
                cleaned = re.sub(re.escape(term), replacement, cleaned, flags=re.IGNORECASE)
                break
        if not cleaned or cleaned.lower() == query.strip().lower():
            return []
        return [cleaned]


class HydeTransformer:
    """Hypothetical Document Embeddings - NEEDS a generator (LLM). Until the
    generation LLM lands (Week 7), the default generator returns nothing and the
    strategy degrades to a no-op; the seam is the point."""

    name = "hyde"

    def __init__(self, generator: Callable[[str], str] | None = None) -> None:
        self.generator = generator  # Callable: query -> hypothetical passage text

    def transform(self, query: str) -> list[str]:
        if self.generator is None:
            return []  # graceful no-op until Week 7
        return [self.generator(query)]


def build_pipeline(settings: Settings | None = None, generator=None) -> list[QueryTransformer]:
    """Assemble the enabled transformation chain (config-driven)."""
    settings = settings or get_settings()
    chain: list[QueryTransformer] = []
    if "subquery" in settings.query_transform_pipeline:
        chain.append(SubQueryDecomposer())
    if "rewrite" in settings.query_transform_pipeline:
        chain.append(RewriteTransformer())
    if "hyde" in settings.query_transform_pipeline:
        chain.append(HydeTransformer(generator))
    return chain


def apply_pipeline(query: str, chain: list[QueryTransformer]) -> list[str]:
    """Run the chain; return every variant (order: strategy order, then original last
    is added by the caller - variants only ADD candidates, the original keeps its vote)."""
    variants: list[str] = []
    seen = {query.lower()}
    for strategy in chain:
        for v in strategy.transform(query):
            if v.lower() not in seen:
                seen.add(v.lower())
                variants.append(v)
    return variants
