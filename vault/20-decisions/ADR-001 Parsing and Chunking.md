---
tags: [decision, adr, summary]
created: 2026-09-29
up: "[[Home]]"
source: "adr/001-parsing-chunking-pipeline.md"
related: "[[Chunking]]"
---
# ADR-001 — Parsing + Chunking Pipeline (summary)

> [!info] Full record lives in the repo: `adr/001-parsing-chunking-pipeline.md`.
> This note is the memorizable digest + interview framing.

## Context
Track A ingests heterogeneous documents — native PDFs, Markdown, Word, SEC 10-K filings
(incl. scanned pages, multi-column layouts, financial tables). Retrieved chunks must be
semantically coherent, self-describing, and faithful to source structure.

## Decision (4 contracts)
1. **Strategy Pattern parsing** — `DocumentParser` interface; Markdown / SEC-HTML /
   plain-text strategies; uniform `Block` stream out.
2. **Semantic chunking** — target-token packing with sentence-boundary splits + overlap.
3. **Contextual headers** — every chunk carries `Title > Section > Subsection`.
4. **Table-aware rules** — tables detected at parse time, kept atomic, never split.

## Rejected alternatives (be able to argue these)
- **Fixed-size character splitting** — destroys tables & context; cheapest, rejected.
- **Full rewrite to a canonical intermediate format** — big-bang migration risk; rejected.
- **Pure LLM layout parsing for everything** — highest fidelity but slow/costly at ingest
  scale; deferred to the scanned-PDF path only.

## Trade-offs admitted
- Latency: layout-aware chunking slower than naive → mitigated by async workers/batching.
- Complexity: Strategy Pattern + table rules = more code surface → mitigated by shared
  `Chunk` schema + per-strategy unit tests.

## Success metrics (→ [[Measurement Harness]])
- Quality: parse-failure + table-corruption < 5% → **actual: 0%** (75 tables)
- Latency: p95 < 2 s/doc, ≥ 0.5 docs/s → **missed on the 10-K** (embed-bound; Week-2 fix)
- Cost: embedding + storage per 1k pages → baseline captured

## Interview soundbite
> "ADR-001's load-bearing decision is table atomicity plus contextual headers. I
> rejected pure-LLM parsing for cost reasons but kept it as the escape hatch for
> scanned pages — that's a scoped trade-off, not an all-or-nothing bet."
