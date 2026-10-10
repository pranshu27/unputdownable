---
tags: [book, track-a]
chapter: 03
prev: "[[Ch 02 - Parsing]]"
next: "[[Ch 04 - Embeddings]]"
---
# Ch 3 — Chunking: the half balance sheet

Remember the demo that opened this talk? Here is exactly how it happens. A chunker cuts text every
N characters, and a balance sheet straddles the cut. The top half goes into one chunk, the bottom
half into another. Both are retrieved. The model - fluent, confident - averages a truth with a
fragment and presents a lie.

So chunking got three contracts, not settings:

1. **Semantic packing.** Paragraphs are packed to ~250 tokens, and when a paragraph is too big it
   splits on **sentence boundaries** - a chunk ends where an idea ends. Fifty tokens of overlap
   cross every seam, so context is never amputated.
2. **Self-describing chunks.** Every chunk carries `title > section > subsection` - and that header
   is *embedded with the text*, not merely stored. Retrieval sees the context, not just the reader.
3. **Tables are atomic.** A table is its own chunk. Never merged with prose. Never split. Ever. The
   structured rows travel in the payload too, so an exact query can hit them directly.

Then the part I care about most: **I did not take my own word for it.** I wrote a corruption check -
for every source table, every cell must appear, intact, inside exactly one chunk - and ran it over
75 tables: merged header cells, parenthesised negatives like `(921)`, inline XBRL tags, a scanned
lease with OCR noise. The result: **0 corrupted.** Across all eight documents: 0 parse failures.

That zero is the point of this chapter. Anyone can write a chunker. Very few can *prove* theirs.

> **Walk off stage with:** "Semantic chunking, contextual headers, an atomicity contract for tables -
> and a corruption metric of 0 out of 75 to prove it."