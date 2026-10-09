---
tags: [book, track-a]
chapter: 03
prev: "[[Ch 02 - Parsing]]"
next: "[[Ch 04 - Embeddings]]"
---
# Ch 3 — Chunking: semantic units, self-describing chunks

Chunking is where retrieval quality is won or lost. Three contracts (ADR-001):

1. **Semantic packing** - paragraphs packed to ~250 tokens; oversized ones split on **sentence
   boundaries** (never mid-thought); 50 tokens of overlap carried across seams.
2. **Self-describing chunks** - every chunk carries `title > section_path...`. A chunk that says
   "operating expenses rose 3%" is meaningless without it. The header is also **prepended to the
   embedding text**, not just stored.
3. **Tables are atomic** - a table is emitted as its own single chunk, never merged with prose,
   never split. The structured rows survive in the payload too (for exact queries).

**The proof:** a corruption check asserts every source cell survives into exactly one chunk.
Measured across 75 tables (merged headers, parenthesised negatives, XBRL): **0 corrupted**.

> **Interview line:** "Semantic chunking with contextual headers and an atomicity contract for
> tables - and I prove it with a corruption metric, not vibes."