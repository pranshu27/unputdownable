# ADR 001: Parsing & Chunking Pipeline

## Status
Proposed (Sep 28, 2026)

## Context
Track A ingests heterogeneous documents — native PDFs, Markdown, Word, and SEC 10-K filings
(including scanned and multi-column pages with financial tables). Retrieved chunks must be
semantically coherent, self-describing, and faithful to source structure so the hybrid retriever
(ADR 002) returns the right context. Naive fixed-size character splitting breaks tables, splits
clauses across columns, and discards document hierarchy — all of which degrade retrieval quality
and answer faithfulness.

## Decision
Build the ingestion pipeline as an extensible parser + chunker with four contracts:

1. **Strategy Pattern for parsing** — a `DocumentParser` interface with pluggable strategies:
   `PdfParser`, `MarkdownParser`, `DocxParser`. The file type routes to the correct strategy;
   adding a format adds a strategy without touching the pipeline.
2. **Semantic chunking** — split on paragraph/section boundaries with a target chunk size and
   overlap, not fixed character windows. Chunks align to complete semantic units (paragraphs,
   list items, table cells).
3. **Contextual headers** — prepend each chunk with its document title + section hierarchy
   (e.g. `10-K > Item 7 > MD&A > Liquidity`), so a chunk is self-describing even out of context.
4. **Table-aware rules for 10-Ks** — detect tabular regions (balance sheets, income statements)
   and keep each table as an atomic unit; convert to markdown and serialize as structured rows
   with row headers. Never split mid-table. Multi-column/scanned pages route to a layout-aware path.

## Alternatives Considered
1. **Fixed-size character chunking (512 tokens, 10% overlap)** — simple, but corrupts tables and
   splits clauses; rejected for poor retrieval quality.
2. **Single monolithic PDF parser** — fastest to build, but cannot extend to Word/Markdown without
   a rewrite; rejected for maintainability.
3. **Pure LLM layout parsing for everything** — highest fidelity on scanned pages, but slow and
   costly at ingest scale; deferred to the scanned-PDF path only.

## Trade-offs
- **Latency:** semantic + layout-aware chunking is slower than naive splitting; mitigated by async
  ingest workers and batching.
- **Complexity:** Strategy Pattern + table rules add code surface; mitigated by a shared `Chunk`
  schema and per-strategy unit tests.
- **Cost:** contextual header generation (and the vision path for scanned pages) adds tokens/compute;
  capped to header generation only in v1.

## Expected Measurements (Validation on Day 3)
- **Quality:** parse failure + table-corruption rate (Target: < 5% corruption across a mixed batch
  incl. one 10-K).
- **Latency:** ingest p95 latency + throughput in docs/sec (Target: p95 < 2s/doc, throughput ≥ 0.5
  docs/sec single worker).
- **Cost:** embedding + index storage cost per 1k pages (Target: baseline captured on Day 3).
