---
tags: [book, track-a, chunk-catalog]
chapter: 03b
prev: "[[Ch 03 - Chunking]]"
next: "[[Ch 04 - Embeddings]]"
---
# Ch 3b — The Chunk Catalog: every shape the pipeline emits

Every chunk *shape* the chunker can produce, shown with real output captured from the actual pipeline (not mocked). If a new shape appears, it belongs in this catalog.

## Product Notes (markdown) - 4 chunks (3 prose / 1 table)
**First chunk (header shape)** - header: `Product Notes: Payments Platform > Product Notes: Payments Platform > Architecture` - tokens: 42 - is_table: False
> `The payments platform is an event-driven service built on Kafka with idempotent consumers. Each ledger entry is written twice: once to the append-only journal and once to the materialized balance view.`

**Atomic table chunk (biggest)** - header: `Product Notes: Payments Platform > Product Notes: Payments Platform > Fee Schedule` - tokens: 43 - is_table: True
> `| Tier | Domestic fee | Cross-border fee | | |---|---|---| | | Standard | 1.9% | 3.1% | | | Premium | 1.2% | 2.4% | | | Enterprise | 0.8% | 1.6% |`

- structured `table_rows` (4 rows) ship in the payload: `['Tier', 'Domestic fee', 'Cross-border fee']` ...
**Another chunk** - header: `Product Notes: Payments Platform > Product Notes: Payments Platform > Fee Schedule` - tokens: 43 - is_table: True
> `| Tier | Domestic fee | Cross-border fee | | |---|---|---| | | Standard | 1.9% | 3.1% | | | Premium | 1.2% | 2.4% | | | Enterprise | 0.8% | 1.6% |`

- structured `table_rows` (4 rows) ship in the payload: `['Tier', 'Domestic fee', 'Cross-border fee']` ...

## Q3 Transcript (plain text) - 1 chunks (1 prose / 0 table)
**First chunk (header shape)** - header: `Q3 Retrieval Sync Transcript` - tokens: 63 - is_table: False
> `The quarterly review opened with the retrieval quality dashboard. Recall at five improved after we added contextual chunk headers. The team agreed to adopt hybrid retrieval with reciprocal rank fusion next sprint. Latenc...`


## Apple 10-K (SEC HTML) - 239 chunks (173 prose / 66 table)
**First chunk (header shape)** - header: `Apple FY2023 Form 10-K` - tokens: 5 - is_table: False
> `aapl-20230930`

**Atomic table chunk (biggest)** - header: `Apple FY2023 Form 10-K` - tokens: 806 - is_table: True
> `|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | | |  | Years ended | | |  | September 30, 2023 |  | September 24, 2022 |  | September 25, 2021 | | | Cash, cash equivalents and restricted cash, beginning balances ...`

- structured `table_rows` (46 rows) ship in the payload: `['', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '']` ...
**Another chunk** - header: `Apple FY2023 Form 10-K` - tokens: 13 - is_table: False
> `UNITED STATES |  | SECURITIES AND EXCHANGE COMMISSION |  | Washington, D.C. 20549`

**Overlap seam found** - chunk N+1 begins with the first 5 words of chunk N (`This Annual Report on Form...`) - this is the head-not-tail overlap quirk from the contract deep-dive, visible in real data.


## ACME 10-K (SEC HTML, merged headers) - 13 chunks (9 prose / 4 table)
**First chunk (header shape)** - header: `ACME Robotics FY2023 Form 10-K` - tokens: 12 - is_table: False
> `ACME Robotics Holdings, Inc. Form 10-K FY2023`

**Atomic table chunk (biggest)** - header: `ACME Robotics FY2023 Form 10-K > ACME Robotics Holdings, Inc. > Item 8. Financial Statements and Supplementary Data > Consolidated Balance Sheets` - tokens: 205 - is_table: True
> `|  | As of December 31, | | | 2023 | 2022 | | | ASSETS |  |  | | | Current assets: |  |  | | | Cash and cash equivalents | 489 | 312 | | | Accounts receivable, net of allowance of $14 and $9 | 377 | 296 | | | Inventories...`

- structured `table_rows` (21 rows) ship in the payload: `['', 'As of December 31,']` ...
**Another chunk** - header: `ACME Robotics FY2023 Form 10-K > ACME Robotics Holdings, Inc. > Item 8. Financial Statements and Supplementary Data > Consolidated Statements of Operations` - tokens: 29 - is_table: False
> `(in millions, except per share amounts)`


## Incident Postmortem (markdown, deep hierarchy) - 6 chunks (5 prose / 1 table)
**First chunk (header shape)** - header: `Incident Postmortem > Incident Postmortem: Payment Authorization Degradation (SEV-1) > Incident Summary` - tokens: 53 - is_table: False
> `On 2026-09-14 between 14:02 and 14:47 UTC, authorization latency breached the 150ms p95 budget, peaking at 940ms, with a card-auth error rate of 2.3% against the 0.1% SLO. The incident was declared SEV-1 under runbook RB...`

**Atomic table chunk (biggest)** - header: `Incident Postmortem > Incident Postmortem: Payment Authorization Degradation (SEV-1) > Remediation Plan` - tokens: 92 - is_table: True
> `| ID | Action | Owner | Due | Status | | |---|---|---|---|---| | | RAG-482-1 | Add single-flight dedup to idempotency cache | @payments-core | 2026-09-28 | done | | | RAG-482-2 | Trip breaker on timeout-class errors | @s...`

- structured `table_rows` (5 rows) ship in the payload: `['ID', 'Action', 'Owner', 'Due', 'Status']` ...
**Another chunk** - header: `Incident Postmortem > Incident Postmortem: Payment Authorization Degradation (SEV-1) > Root Cause` - tokens: 111 - is_table: False
> `The deploy-de7a2b91 build enabled the new idempotency-key cache with a 30-second TTL. Under burst traffic the cache stampede saturated the journal writer connection pool (24 connections), causing ERR-4021 timeouts. The r...`


## Scanned Lease (OCR noise) - 12 chunks (11 prose / 1 table)
**First chunk (header shape)** - header: `Commercial Lease (Scanned OCR)` - tokens: 11 - is_table: False
> `Commercial Lease Agreement - Scanned Copy (OCR)`

**Atomic table chunk (biggest)** - header: `Commercial Lease (Scanned OCR) > COMMERCIAL LEASE AGREEMENT > ARTICLE 3. BASE RENT` - tokens: 92 - is_table: True
> `| Lease Year | Period | Monthly Base Rent (USD) | Annualized (USD) | | | 1 | Oct 2024 - Sep 2025 | $4,275.00 | $51,300.00 | | | 2 | Oct 2025 - Sep 2026 | $4,403.25 | $52,839.00 | | | 3 | Oct 2026 - Sep 2027 | $4,535.35 |...`

- structured `table_rows` (6 rows) ship in the payload: `['Lease Year', 'Period', 'Monthly Base Rent (USD)', 'Annualized (USD)']` ...
**Another chunk** - header: `Commercial Lease (Scanned OCR) > COMMERCIAL LEASE AGREEMENT > ARTICLE 1. PREMISES` - tokens: 67 - is_table: False
> `Landlord hereby leases to Tenant, and Tenant leases from Landlord, the prem- ises commonly known as Suite 400, 1100 Market Street, Denver, CO 80202, consist- ing of approximately 12,480 rentable square feet (the "Prem1se...`


## Two-Column Paper (CSS columns) - 11 chunks (10 prose / 1 table)
**First chunk (header shape)** - header: `Two-Column Layout RAG Paper` - tokens: 11 - is_table: False
> `Two-Column Layout Robustness in Retrieval-Augmented Generation Pipelines`

**Atomic table chunk (biggest)** - header: `Two-Column Layout RAG Paper > Two-Column Layout Robustness in Retrieval-Augmented Generation Pipelines > 4. Degradation Study` - tokens: 72 - is_table: True
> `| Retriever | Left-half R@5 | Right-half R@5 | Gap | | | Dense (384-d) | 0.72 | 0.49 | 0.23 | | | Sparse (BM25 + IDF) | 0.64 | 0.55 | 0.09 | | | Hybrid RRF (k=60) | 0.71 | 0.61 | 0.10 | | | Hybrid + column pre-pass | 0.7...`

- structured `table_rows` (5 rows) ship in the payload: `['Retriever', 'Left-half R@5', 'Right-half R@5', 'Gap']` ...
**Another chunk** - header: `Two-Column Layout RAG Paper > Two-Column Layout Robustness in Retrieval-Augmented Generation Pipelines > 1. Introduction` - tokens: 150 - is_table: False
> `Retrieval-augmented generation (RAG) systems are increasingly deployed over heterogeneous document corpora: SEC filings, academic preprints, and scanned contracts. While chunking strategies have received attention, the i...`


## The shape taxonomy (what this catalog proves)

| Shape | Produced by | Seen in |
| :--- | :--- | :--- |
| Prose-under-heading with full hierarchy header | markdown with headings | Product Notes, Postmortem |
| Atomic table chunk (rows in payload) | any source with tables | Apple, ACME, Product Notes, Lease, Paper |
| Title-only header (empty `section_path`) | SEC HTML without h1-h6 | Apple, ACME, Lease, Paper |
| Whole-document single chunk | no headings, short text | Q3 Transcript |
| OCR-noise chunk | scanned-source stand-in | Lease (`Prem1ses`, `Septenber`) |
| Two-column interleaved chunk | CSS-column source | Paper |
| Layout-noise table chunk (all-empty cells) | SEC page furniture | Apple (the `tokens=10` chunk) |
| Overlap seam (head-not-tail quirk) | the 50-token overlap | detected above |

## Known defects visible in this catalog (all recorded, none hidden)

1. **Title duplication** in markdown headers (`Title > Title > Section`) - the H1 equals the document title and gets prepended again.
2. **Layout-noise table chunks** - all-empty 2-row SEC tables become real embedded points.
3. **Empty `section_path`** for SEC HTML (no h1-h6) - headers degrade to title-only.
4. **Head-not-tail overlap** - the seam carries the beginning of the previous chunk.

Each has a one-line fix; all change chunk counts, so they ship together with a benchmark re-run.
