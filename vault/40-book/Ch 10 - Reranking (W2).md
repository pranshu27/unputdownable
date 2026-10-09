---
tags: [book, track-a]
chapter: 10
prev: "[[Ch 09 - Guardrails]]"
next: "[[Ch 11 - Query Rewriting & Self-RAG (W3)]]"
---
# Ch 10 — Reranking: precision on top of recall (W2) - STUB

**Status:** stub - written the week the cross-encoder lands.

**Why it is next:** hybrid retrieval produces *candidates* (top-50); a cross-encoder reads query and candidate together and produces *precision* (top-5). Recall first, precision second - that is the standard two-stage shape.

**What this chapter will contain:** BGE-Reranker-Large integration, the top-50 -> top-5 budget, the measured Delta Recall@5 on the lexical-hard goldens (where dense fails on exact identifiers), rerank latency as a span, and $/1k queries.

**Interview angle:** "fusion is cheap (0.08 ms); the reranker is where the latency budget goes - here is the measured delta it buys."
