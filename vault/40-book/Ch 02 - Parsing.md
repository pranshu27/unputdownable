---
tags: [book, track-a]
chapter: 02
prev: "[[Ch 01 - The Problem]]"
next: "[[Ch 03 - Chunking]]"
---
# Ch 2 — Parsing: messy formats, one uniform shape

Five formats arrive: native PDFs, scanned/image-only PDFs, Markdown, DOCX and SEC HTML filings (with inline XBRL and page-like layout tables). New ones arrive roughly quarterly.

**The decision (ADR-001): a Strategy Pattern with one uniform output.**

- Interface: `DocumentParser.parse(source, title) -> ParsedDocument`
- Output: an ordered list of **typed blocks** - `HEADING` / `PARAGRAPH` / `TABLE` - each carrying a `section_path` (e.g. `Item 7 > MD&A > Liquidity`) and, for tables, the **structured rows**
- Dispatch: a registry dict keyed by format; **a new format = one new file + one registration line**
- Failure isolation: a broken document raises -> caught -> `parse_failed` stat; the batch continues

**Why not a class with a method per format?** Adding PPTX would edit code every format shares - merge conflicts, all parser dependencies in one class, no independent testing. Open/Closed wins.

**Honest limits (know them):** stdlib HTMLParser is not a full HTML5 parser (fine: SEC files are machine-generated); DOCX is a placeholder; real PDF text-layer extraction is a future strategy; the OCR engine is a swappable seam behind a `ScannedPdfParser`.

> **Interview line:** "One protocol, one registry, uniform typed blocks - a new format is a file, not a refactor."
