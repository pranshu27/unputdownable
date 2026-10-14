# LLD Drill — Extensible Document Parser

**Plan item:** Week 1 Thu · spoken LLD, 25 minutes, no code, no notes. **Prompt (say this to yourself, then design out loud):**

> *"Design the document-parsing component of a RAG ingestion service. It must handle native PDFs, scanned PDFs, Markdown, DOCX and SEC HTML filings. Tables must survive parsing intact. New formats will arrive later and must be addable without touching the ingestion pipeline."*

## Structure your spoken answer in these 6 beats (≈4 min each)

1. **Clarify** — functional + non-functional requirements, what's out of scope. (Ask: how many formats/year? scanned share? latency budget? who calls this?)
2. **Core abstractions** — the interfaces and data types, and *why* they're shaped that way.
3. **Extensibility mechanism** — how a new format gets added, and what the seam looks like.
4. **Failure modes + observability** — what happens when a parser fails or mangles a table, and how you'd detect it.
5. **Testing strategy** — what you unit-test per strategy vs integration-test end to end.
6. **Trade-offs + rejected alternatives** — the two-background candidates you'd compare in an interview.

## Rubric — did you cover these? (tick after speaking)

- [ ] Interface with a single method and a **uniform output type** (not format-specific returns)
- [ ] Output is a stream/sequence of **typed blocks** (heading / paragraph / table), not raw strings
- [ ] **Tables as first-class, atomic** units — never split downstream
- [ ] **Section hierarchy carried** on blocks (so chunks can be self-describing)
- [ ] **Registry / dispatch by format** — adding a format = adding a class + a registration line
- [ ] **Strategy Pattern named explicitly**, with the alternative (if/else ladder) rejected and why
- [ ] **Failure isolation** — one bad document can't kill the batch; failure rate is a measured metric
- [ ] **Fidelity checks** — a way to prove tables survived (a corruption metric, not vibes)
- [ ] Deferred intentionally: OCR/scanned path behind the same interface, confidence scores, plugin loading
- [ ] Two rejected alternatives stated with reasons (e.g. normalize-everything-to-one-format; LLM layout parsing for all)

## Reference: what your own implementation does (`track-a/src/app/core/parsers.py`)

| Rubric item | Where it lives |
| :--- | :--- |
| Single-method interface | `DocumentParser` Protocol → `parse(source, title) -> ParsedDocument` |
| Uniform output | `Block(kind, text, level, section_path, table_rows)`; `ParsedDocument(title, blocks)` |
| Tables first-class | `BlockKind.TABLE` + `table_rows`; serialized to markdown text so they're also searchable |
| Section hierarchy | `Block.section_path`, built as headings mutate a path list |
| Registry dispatch | `_PARSERS: dict[DocumentFormat, type]` + `get_parser(fmt)`; `_format_from_uri` routes `.htm/.html/.md/.txt` |
| Failure isolation | `IngestService.ingest` catches exceptions → `stats.parse_failed` (a measured quality metric) |
| Fidelity proof | `table_corruption_check` in both benchmarks (source rows/cells must survive into exactly one chunk) |
| Deferred | scanned/OCR strategy + real PDF strategy; DOCX currently routed to the plain-text parser |

**Extensions you should be able to discuss if pushed:** streaming parse for huge filings, per-parser confidence, page-level provenance, layout-table hazard (1-row tables get dropped), and where OCR would slot in (a `ScannedPdfParser` implementing the same interface).

## My verbal answer in 6 bullets (fill after speaking — your own words)

- Clarify:
- Abstractions:
- Extensibility:
- Failure/observability:
- Testing:
- Trade-offs:

---

## Session trace — 2026-10-08 (drill 1)

**Candidate clarifying questions:**
1. What formats need to be parsed?
2. What should the standard output format be?

**Interviewer answers:**
1. Five formats today: native (text-layer) PDFs ~70% of volume; scanned/image-only PDFs ~12%; Markdown exported from the internal wiki; DOCX from legal/ops; SEC HTML filings (10-K/10-Q, inline XBRL, page-like layout tables). A new source appears roughly once a quarter (last quarter: scanned contracts; next quarter: legal is threatening PPTX). Volume ~4,000 docs/day, bursts to ~40 docs/sec, average 60 pages, 10-Ks up to ~400. Latency budget: p95 <= 2 s/doc for text-layer docs; the scanned path may be 10-20x slower and is allowed to be asynchronous. Downstream consumer is the chunker -> embeddings -> hybrid search, and analysts query financial statements, so numeric tables must be queryable exactly.
2. **Handed back as a design decision, not a requirement:** "That's your proposal to make - I'll answer requirements questions and ask you to justify design ones." Interviewer expects: the interface signature, the return type, how tables are represented (structure preserved, not flattened), how section hierarchy is carried, and what metadata rides along (provenance, format, warnings/confidence).

**Rubric status at this point:** clarify ✅ (2 solid requirement questions) · abstractions ⬜ · extensibility ⬜ · failure/observability ⬜ · testing ⬜ · trade-offs ⬜

### Trace 2 — the design answer (verbatim summary)
1. "A class with several methods, one per format, so a new format is a method away."
2. "Return type is JSON with standard fields: document type, name, data, size in bytes — to preserve metadata."
3. "Tables stored as-is in Postgres; exact keyword match fetches exact details; Postgres has good JSON search."
4. "Semantic chunking so every section is preserved; chunk metadata via Postgres pgvector tells us where the chunk came from."

**Interviewer score:** clarify ✅ · abstractions ⚠️ (document metadata only, no content units) · extensibility ❌ (method-per-format in one class = Open/Closed violation; this is the rejected alternative in ADR-001) · failure/observability ❌ (not mentioned) · testing ❌ (not mentioned) · trade-offs ⚠️ (semantic-vs-fixed named, but at chunk level; also storage scope creep)

**Three issues that would sink it in a real loop:**
- God-class dispatch: adding PPTX means editing a shared class (merge conflicts, regression risk, one class accumulating every parser dependency). Fix: interface + one class per format + registry dispatch.
- Return type too thin: document-level metadata only; `data` unspecified. For a 400-page 10-K with 66 tables you need ordered typed blocks (heading/paragraph/table) with section path, table structure, page provenance, warnings. Size-in-bytes is not a retrieval-relevant number (tokens are).
- Scope creep into storage: Postgres/pgvector is the chunker+storage component's decision, not the parser's. Putting tables only in Postgres removes them from the retrieval stream (so hybrid search can never retrieve them) and creates two sources of truth. Tables must stay in the document stream as atomic blocks, with structured rows additionally retained in the payload.

**Follow-ups still owed by the candidate:** the PPTX diff question, failure isolation, testing strategy.

---

## MODEL ANSWER — memorize this (closes the drill at 6/6)

### The 6-beat spoken answer (≈4 min each, 25 min total)

**Beat 1 — Clarify (ask before designing).** "Before I design: three questions. One — format mix and growth: how many formats today, how often does a new one arrive? Two — quality bar: are tables numeric-financial (must round-trip exactly) or visual-only? Three — latency budget: is parsing synchronous in the request path or async in ingestion? Out of scope for me: OCR model choice (it lives behind the same interface), storage, chunking — I produce a parsed document; the chunker owns everything after." *(Given numbers: 5 formats, new source ~quarterly, 4k docs/day burst 40/sec, avg 60 pages, p95 ≤ 2 s text-layer, scanned async 10–20×.)*

**Beat 2 — Core abstractions (the beat that decides the interview).** "The contract: one interface, one method, and a **uniform output type**.

```python
class DocumentParser(Protocol):
    def parse(self, source: str, title: str) -> ParsedDocument: ...

@dataclass
class Block:                  # ONE ordered content unit
    kind: BlockKind           # HEADING | PARAGRAPH | TABLE
    text: str                 # markdown-serialized (tables included -> still searchable)
    level: int | None         # heading depth
    section_path: list[str]   # e.g. ["Item 8", "Liquidity", "Capital Resources"]
    table_rows: list[list[str]] | None   # structured rows when kind == TABLE
```

Why: the downstream chunker is format-agnostic — it must never learn what a PDF is; five formats reduce to one *stream of typed blocks*. Tables are **first-class and atomic**: structured rows in `table_rows` (exact cell access), markdown serialization keeps them in the searchable stream — one source of truth, two views. `section_path` rides on every block so chunks are self-describing."

**Beat 3 — Extensibility.** "Adding a format = **a class and a registration line**; the pipeline never edits:

```python
_PARSERS: dict[DocumentFormat, type] = {DocumentFormat.PDF: TextLayerPdfParser, ...}
def get_parser(fmt): return _PARSERS[fmt]()
```

This is the **Strategy Pattern**. The rejected alternative is the method-per-format god-class: adding PPTX then means editing a shared class — merge conflicts, regression risk on every format, one class importing every parser dependency. The registry lets the new parser ship in isolation; dispatch is one dict lookup."

**Beat 4 — Failure + observability.** "Two failure classes, handled differently. **Hard failure** (file corrupt, parser raises): the *batch* survives — the ingest service catches per document, marks `parse_failed`, moves on; one bad doc never kills the batch. Metric: parse-failure rate (0/8 on the stress corpus), alarm above 1%. **Soft failure** — the dangerous one: the parser *succeeds* but mangles a table. You cannot except-clause that; you need a **fidelity check**: every source table's rows/cells must survive completely into exactly one chunk, measured as a corruption rate (currently 0/75, including a 42-row balance sheet). Alarming: ANY nonzero corruption."

**Beat 5 — Testing.** "Three layers. (1) **Per-parser unit tests on real fixtures** — actual 10-Ks, not synthetic HTML; assert block kinds, section paths, table row counts. (2) **Property/fidelity checks over the whole corpus** — rows-in == rows-in-exactly-one-chunk-out, run every benchmark. (3) **End-to-end** — retrieve a known cell ('net sales 383,285') through the search API, because the point of tables is exact retrieval. Plus regression fixtures per historical failure class (colspan/rowspan, XBRL noise, scanned pages) and failure injection (corrupt file → batch survives). Meta-rule: parsers are pure functions source → blocks, no I/O — that's what makes them cheap to test."

**Beat 6 — Trade-offs + rejected alternatives.** "(1) **Normalize everything to one format** (all → Markdown via a converter): one parser, tempting; rejected — normalization is itself lossy on complex layouts (rowspan flattening) and moves the hard problem into a tool I don't control. (2) **LLM layout-parsing for everything**: highest fidelity ceiling; rejected today on cost (per-page × 4k/day) and non-determinism (financial tables need exact reproduction) — but it's the natural confidence-lift add-on for ambiguous pages later. (3) **Chosen: per-format strategies over a shared block model** — boring, testable, and the seam where OCR/LLM assist slots in without re-architecture."

### Follow-up A — "PPTX arrives next quarter. Walk me through the diff."
"Nothing downstream changes — that is the point of the seam. The diff: **(1)** new `DocumentFormat.PPTX` enum member; **(2)** a new `PptxParser` class — python-pptx walks slides → shapes: title placeholders → HEADING, body → PARAGRAPH, native tables → TABLE with `table_rows`, speaker notes → PARAGRAPH under a `notes` section path; **(3)** one registry line; **(4)** its fixtures + corruption check. Zero edits in the other five parsers, chunker, embedder, search. If adding a format ever touches more than two files, that's the smell the registry exists to remove."

### Follow-up B1 — "3 a.m., 40 docs/sec, every scanned PDF fails. Blast radius?"
"What *should* happen: scanned is allowed async, the failure isolates to its own document — `parse_failed` climbs, the batch finishes, the failure-rate alert fires. Blast radius is really three properties: **bounded** (per-document try/except, no shared mutable state between docs), **loud** (metric + alert, plus a dead-letter queue holding doc_id/exception/stack for replay after the fix), **diagnosable** (structured logs: format, size, parser version). What I would NOT do: retry in-line forever (clogs the batch) or drop silently ('0 docs failed' is how lies get told)."

### Follow-up B2 — "Prove the tables survived. Not vibes — proof."
"Corruption defined operationally: for every source table, rows/cells must appear **completely in exactly one chunk**. Mechanism: re-serialize each parsed table to markdown, count rows/cells at parse time; at chunk time verify the serialized table lands intact in one chunk (the atomic-table rule). Output: tables checked / corrupted / rate — run as a property test over the whole corpus on every benchmark, not a one-off assertion. Last run: 75 tables, 0 corrupted."

### Follow-up B3 — "Your testing strategy?" (one-liner)
"Unit per parser with real fixtures → corpus-wide property/fidelity checks → e2e known-cell retrieval → regression fixtures per failure class → failure injection. Parsers are pure functions, so all of this is cheap."

### Beat sheet (repeatability test — all 10, in order)
1. Clarify: format mix / table quality bar / latency budget — three questions BEFORE designing
2. Uniform output type: one interface, one method → `ParsedDocument` of typed `Block`s
3. Tables first-class AND atomic: `table_rows` + markdown serialization (two views, one truth)
4. `section_path` on every block → self-describing chunks
5. Registry dispatch = Strategy Pattern; rejected: method-per-format god-class (Open/Closed)
6. Hard failure: per-doc catch, `parse_failed` metric, batch survives, alert > 1%
7. Soft failure: fidelity/corruption check (0/75) — "you cannot except-clause a mangled table"
8. Testing: per-parser fixtures → corpus property checks → e2e cell retrieval
9. Rejected: normalize-everything (lossy, uncontrolled tool)
10. Rejected: LLM-parse-all (cost + determinism) — later as confidence lift, not the base


