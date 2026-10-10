---
tags: [book, track-a, mind-map]
created: 2026-10-08
updated: 2026-10-08
---
# 📖 The Track A Book — a talk in seventeen chapters

> [!info] How to read This is a **story**, not a manual: every chapter opens on a real moment from the build, shows the wrong turn, and lands on the measured number that fixed it. **Full pass:** Ch1 -> Ch9 (30 minutes). **3-minute recall before an interview:** Ch1 + Ch6 + Ch7. Chapters 10-16 are teasers - each gets written the week that component ships, so the book never drifts from reality.

## The one-diagram mind map

```text
                         THE FLOW
 docs -> parse -> chunk -> embed (dense+sparse) -> index (Qdrant)
                                                        |
 question -> embed -> dense || sparse -> RRF fuse -> [rerank] -> top-k -> answer

 quality / latency / cost measured at every arrow
```

| Ch | Chapter | The moment |
| :-- | :--- | :--- |
| 1 | [[Ch 01 - The Problem]] | the answer that was confidently wrong |
| 2 | [[Ch 02 - Parsing]] | five formats walk into a pipeline |
| 3 | [[Ch 03 - Chunking]] | the half balance sheet |
| 3b | [[Ch 03b - The Chunk Catalog]] | every chunk shape, with real output |
| 4 | [[Ch 04 - Embeddings]] | the number the vector could not see |
| 5 | [[Ch 05 - Indexing]] | the tie that taught me something |
| 5b | [[Ch 05b - Qdrant Primer]] | the database under the pipeline (first-timer) |
| 6 | [[Ch 06 - Retrieval & RRF]] | two witnesses and a judge |
| 7 | [[Ch 07 - Measurement]] | the two times I lied to myself |
| 8 | [[Ch 08 - Serving]] | what happens when the store dies at 3 a.m. |
| 9 | [[Ch 09 - Guardrails]] | the test that polluted production |
| 10 | [[Ch 10 - Reranking (W2)]] | stub - precision on top of recall |
| 11 | [[Ch 11 - Query Rewriting & Self-RAG (W3)]] | stub - fix the question first |
| 12 | [[Ch 12 - Caching & Streaming (W4)]] | stub - stop paying twice |
| 13 | [[Ch 13 - Agents (W5-6)]] | stub - the graph, the gate |
| 14 | [[Ch 14 - vLLM Serving (W7)]] | stub - own the generator |
| 15 | [[Ch 15 - Track B Enterprise (W9-12)]] | stub - the enterprise story |
| 16 | [[Ch 16 - Evals & Observability (W13-14)]] | stub - make regression visible |
| 17 | [[Ch 17 - Appendix - Prior Evidence]] | before Track A, there was this |
