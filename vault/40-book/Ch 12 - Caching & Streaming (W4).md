---
tags: [book, track-a]
chapter: 12
prev: "[[Ch 11 - Query Rewriting & Self-RAG (W3)]]"
next: "[[Ch 13 - Agents (W5-6)]]"
---
# Ch 12 — Caching & Streaming (W4) - STUB

**Status:** stub.

**Why it matters:** a semantic cache (Redis, cosine similarity on query embeddings, staleness rules)
saves double-paying for identical questions; SSE streaming with backpressure makes answers feel
instant. Both measured as cache hit-rate, latency delta and tokens avoided.