---
tags: [book, track-a]
chapter: 07
prev: "[[Ch 06 - Retrieval & RRF]]"
next: "[[Ch 08 - Serving]]"
---
# Ch 7 — Measurement: quality, latency, cost - every week

Claims without numbers do not exist. Every INTEGRATE & MEASURE day captures the same three categories (`measurements.md`):

- **Quality:** parse-failure rate - table-corruption rate - Recall@5 (dense vs hybrid) on golden queries incl. lexical-hard ones
- **Latency:** ingest p95 by stage - search spans (embed / dense / sparse / fuse)
- **Cost:** $/1k pages embed + storage - $/1k queries

**The harness discipline:** quality claims come from benchmark scripts with **reference implementations** (fuzz 200-500 cases), never from assertions alone.

**The measured Week-1 baseline:** parse 96 ms but embed 60-95 s (bottleneck is CPU embedding, not parsing) - search p50 11-18 ms - 0/75 tables corrupted - $0.0025/1k pages embed, $0.088 storage.

**The benchmark honesty ledger (learned the hard way):** (1) brute force with a small alphabet is ~O(n x alphabet), not O(n^2) - name the regime; (2) slots savings differ 288 B vs 40 B per object depending on the measurement method - say "tens to hundreds of MB per million records".

> **Interview line:** "Three fixed categories, every week, with numbers - and the harness told me my bottleneck is CPU embedding, not parsing, and that hybrid doesn't win on a toy corpus."
