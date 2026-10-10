---
tags: [concept, chunking, adr-001]
created: 2026-09-29
up: "[[Home]]"
related: "[[RAG Overview]], [[ADR-001 Parsing and Chunking]]"
---
# Chunking — semantic chunks, contextual headers, atomic tables

> [!abstract] Soundbite "I never split tables. A chunk cut through a balance sheet is worse than no chunk — the model reasons on corrupted numbers. My corruption rate across 75 tables is 0%."

## The problem
Naive splitting = cut every 500 chars. A 10-K has headings, paragraphs, and financial tables; a blind cut splits a table mid-row and produces chunks that are *lies*.

## What we built (`track-a/src/app/core/`)
### 1. Uniform block stream (Strategy Pattern)
Every parser (`MarkdownParser`, `HtmlParser`, `PlainTextParser`) outputs the same thing: `Block(kind ∈ {HEADING, PARAGRAPH, TABLE}, text, level, section_path, table_rows)`. Downstream code never knows the source format. See `core/parsers.py::_PARSERS`.

### 2. Semantic chunking (`core/chunker.py`)
- Paragraphs are packed up to `target_tokens=250`.
- Oversized paragraphs split on **sentence boundaries** (`_split_long_paragraph`) — a chunk ends where an idea ends.
- `overlap_tokens=50`: the last sentence of chunk N re-appears at the start of N+1, so context isn't lost at the seam.

### 3. Contextual headers
Every chunk carries `"Apple FY2023 Form 10-K > Item 7 > MD&A > Liquidity"`. Headings mutate a `section_path` list AND act as hard chunk boundaries. Why: a chunk saying "operating expenses rose 3%…" is meaningless out of context; the header makes every chunk self-describing. (Measurable: contextual headers were explicitly credited in the Q3 transcript fixture.)

### 4. Tables are atomic (the testable contract)
In `chunk_document()`: a TABLE block calls `_emit_table_chunk` — one chunk, never merged with prose, never split. Verified by the corruption check in the benchmarks: for every source table, every cell must survive into exactly one chunk.

## Stress-tested by the complex batch (Sep 29)
| Doc | Stress | Result |
|---|---|---|
| acme-financials-10k.html | colspan/rowspan merged headers, `(921)` negatives, `<ix:nonFraction>` XBRL tags | 4/4 tables intact |
| scanned-lease-agreement.html | OCR noise: `Prem1ses`, broken hyphens, fax cruft | 0 parse failures |
| research-paper-two-column.html | CSS 2-column reading order | 0 parse failures |
| incident-postmortem.md | deep h1–h4, code fences, exact IDs | clean |

## Open limitations (be able to name them)
- `MarkdownParser` treats fenced code blocks as plain paragraphs; a line starting with `#` inside a fence would misparse as a heading.
- `HtmlParser` ignores `rowspan` continuation cells → ragged rows (rows still survive atomically).
- 1-row layout tables are dropped (<2 rows filter) — a real hazard with table-based layouts.

## Interview soundbite
> "Chunking is where RAG quality is won or lost. I use semantic chunking with sentence boundaries and overlap, contextual headers so chunks are self-describing, and an atomicity contract for tables — and I prove it with a corruption metric, not vibes."

---

## Contract deep-dive (2026-10-08)

**Contract 1 - semantic packing.** `count_tokens` = whitespace split (fast, approximate: 250 whitespace tokens ~ 300+ BPE). Oversized paragraphs pre-split on sentence boundaries (`(?<=[.!?])\s+`), then packed greedily so a chunk never exceeds target. Headings are hard boundaries -> chunk size varies by section, by design. *Follow-up:* "why 250?" -> header + 250 whitespace tokens stays inside the 512-token embedding window; it is a measured dial, not a constant.

**Contract 2 - self-describing chunks.** `section_path` is a stack mutated by headings; the header `title > section > subsection` is **embedded with the text** (steers the vector, not just the reader). Heading blocks emit no body - their words live in the header. Degradation: no headings -> header is title-only (the honest gap; scanned docs are the frontier).

**Contract 3 - tables atomic.** Parser emits `table_rows` (structure) + markdown `text` (searchability); chunker emits the table alone, never merged/split. Proof: corruption check 0/75. **Sharpest edge:** atomicity is unbounded - a 400-row table becomes one chunk whose dense vector is truncated at the embedder's 512-token window (payload complete, embedding amputated - the corruption check cannot see it). Mitigation: row-group splits repeating the header row, or a long-context embedder.

### Two limitations found in `chunker.py` while elaborating
1. **Overlap takes the head, not the tail:** `_word_window` = `text.split()[:max]` on the previous chunk's last paragraph - so the seam carries the *beginning* of the previous chunk, halving the intended benefit. One-line fix: `text.split()[-max_tokens:]`.
2. **`start_index`/`end_index` are offsets into the chunk body, not the source document** - provenance is coarse (no page/character traceability).
