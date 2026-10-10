---
tags: [book, track-a]
chapter: 02
prev: "[[Ch 01 - The Problem]]"
next: "[[Ch 03 - Chunking]]"
---
# Ch 2 — Parsing: five formats walk into a pipeline

Native PDFs with text layers. Scanned PDFs that are pure photographs. Markdown from the wiki. DOCX
from legal. SEC filings wearing inline XBRL like scaffolding. And legal just sent an email saying
slides are coming next quarter.

My first instinct - and I stood up in a mock interview and proposed this, so I own it - was a
**Parser class with a method per format**. Modular, right? One method away from PPTX? No. It is a
trap with a friendly face: adding a format means editing the class every format shares. Merge
conflicts. Every parser dependency in one place. One bad regression breaks them all.

The shape that actually survives: **a Strategy Pattern with one uniform output**.

- One interface: `DocumentParser.parse(source, title) -> ParsedDocument`
- One output shape: ordered **typed blocks** - `HEADING`, `PARAGRAPH`, `TABLE` - each carrying its
  `section_path`, and for tables the **structured rows**, not just flattened text
- One seam: a registry dict keyed by format. A new format is a new file plus one registration line.
  Existing code does not change. Not one line.

And the failure story matters as much as the happy path: when a parser dies on a malformed document,
it is caught, flagged as `parse_failed`, and the batch moves on. In a 4,000-document day, one bad
file is a statistic - measured - never a fire alarm.

The honest limits are part of the design story: stdlib `HTMLParser` is not a full HTML5 parser (fine -
SEC files are machine-generated), DOCX is a placeholder, real PDF extraction is a future strategy,
and the OCR engine sits behind a swappable seam because that vendor contract is literally still open.

> **Walk off stage with:** "One protocol, one registry, uniform typed blocks - a new format is a
> file, not a refactor."