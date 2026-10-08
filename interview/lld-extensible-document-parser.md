# LLD Drill — Extensible Document Parser

**Plan item:** Week 1 Thu · spoken LLD, 25 minutes, no code, no notes.
**Prompt (say this to yourself, then design out loud):**

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
