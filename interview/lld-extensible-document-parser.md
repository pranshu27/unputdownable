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
