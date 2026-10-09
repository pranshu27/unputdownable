---
tags: [book, track-a]
chapter: 09
prev: "[[Ch 08 - Serving]]"
next: "[[Ch 10 - Reranking (W2)]]"
---
# Ch 9 — Guardrails: tests, fuzz and fidelity checks

The test map (30 passing):

- **Per strategy:** block extraction for markdown / HTML / plain text (`test_parsers.py`)
- **Invariants:** chunk packing, overlap, headers, table atomicity (`test_chunker.py`)
- **Fusion maths:** RRF ordering and k-damping (`test_rrf.py`)
- **Boundaries:** schema validation rejects bad input (`test_schemas.py`)
- **Config:** dense dims + sparse IDF collection config (`test_qdrant_config.py`)
- **Live integration:** auto-skip when Qdrant is down; writes go to a **scratch collection
  (`documents-tests`)** dropped on teardown - never the production collection (`test_qdrant_integration.py`)
- **End-to-end:** ingest -> hybrid search on the scratch collection (`test_services.py`)

**Beyond pytest, the harnesses:** quality claims are fuzzed against reference implementations (200-500
cases with negatives and edge cases), and the table-corruption check asserts every source cell
survives into exactly one chunk.

> **Interview line:** "Per-strategy unit tests, invariants as assertions, fuzz against reference
> implementations, and live integration tests that can never pollute production data."