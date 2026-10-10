---
tags: [book, track-a]
chapter: 09
prev: "[[Ch 08 - Serving]]"
next: "[[Ch 10 - Reranking (W2)]]"
---
# Ch 9 — Guardrails: the test that polluted production

Confession time again, and this one is my favourite, because I caught it showing the system off. I opened the collection to demo what was inside and found strangers living there: a `hello world` point, four `Smoke Doc` chunks, four `Quarterly Report` chunks. **My own live tests had been writing into the production collection** - every pytest run with Qdrant up, quietly leaking.

Nine stray points. Small blast radius, huge lesson: integration tests need the same production hygiene as production code. Now they run against a **scratch collection** that is created on demand and dropped on teardown, and the round-trip test *asserts* it is not writing into `documents`. The pollution can never happen again - there is a guardrail where the bug used to live.

The full guardrail stack around the pipeline:

- **Per-strategy unit tests** - markdown tables, HTML headings, plain text, each parser on its own
- **Invariants as assertions** - chunk packing, overlap, headers, and table atomicity
- **Fuzz against references** - 200 to 500 randomised cases, negatives included, compared to a boring correct implementation, on every quality claim I make
- **The corruption check** - every source table cell must survive into exactly one chunk
- **Live tests that auto-skip** - CI stays green without infrastructure

> **Walk off stage with:** "The guardrail I am proudest of is the one that caught me - my tests now cannot write into production, because there is a lock where the bug used to be."
