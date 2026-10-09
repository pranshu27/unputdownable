---
tags: [book, track-a]
chapter: 11
prev: "[[Ch 10 - Reranking (W2)]]"
next: "[[Ch 12 - Caching & Streaming (W4)]]"
---
# Ch 11 — Query Rewriting & Self-RAG (W3) - STUB

**Status:** stub - written after ADR-003.

**Why it matters:** retrieval fails on the *question* as often as on the corpus. HyDE, sub-query decomposition and rewrite loops fix the query; Self-RAG reflection tokens verify context sufficiency before answering.

**What this chapter will contain:** the strategy-selection rules (when rewrite vs decompose vs HyDE), latency budget per strategy, the reflection loop, and measured precision deltas.
