---
tags: [book, track-a]
chapter: 01
prev: "[[Book]]"
next: "[[Ch 02 - Parsing]]"
---
# Ch 1 — The Problem

An LLM does not know your documents. RAG fixes that by retrieving relevant passages and putting them in the prompt - which means **retrieval quality bounds answer quality**, and retrieval quality is bounded by **chunk quality**.

**The flow, memorised:**

```text
docs ─▶ parse ─▶ chunk ─▶ embed ─▶ index        (ingest side)
question ─▶ embed ─▶ retrieve ─▶ fuse ─▶ top-k   (query side)
```

**Three non-negotiables discovered in Week 1:**

1. Never split a table - a half balance sheet makes the model lie with confidence.
2. Every chunk must be self-describing (which document, which section) - otherwise it is noise.
3. Every claim needs a number - quality, latency and cost, measured, not felt.

**Where we are:** 290 chunks indexed across 8 documents (10-K filings, OCR'd scans, a two-column paper, markdown, transcripts), hybrid retrieval live.

> **Interview line:** "RAG quality is bounded by retrieval quality, and retrieval quality is bounded by chunk quality - so I instrument the whole chain."
