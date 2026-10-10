---
tags: [book, track-a]
chapter: 01
prev: "[[Book]]"
next: "[[Ch 02 - Parsing]]"
---
# Ch 1 — The Problem: the answer that was confidently wrong

Picture the demo. An analyst types a question about a balance sheet. The system thinks for a moment
and returns an answer - fluent, cited, **and wrong**. Not hallucinated-wrong. Worse: it was built on
half a table, because somewhere upstream a chunker had sliced a balance sheet down the middle and
fed the model half the truth.

That is the moment this whole project grows from. Because here is the uncomfortable chain I want you
to remember: **retrieval quality bounds answer quality, and chunk quality bounds retrieval quality.**
Everyone tunes the model. Almost nobody audits the chunks. The model is the last mile - the chunks
are the road, and if the road is broken, a better car changes nothing.

So the flow is not a diagram to me; it is a set of promises:

```text
 docs -> parse -> chunk -> embed (dense+sparse) -> index (Qdrant)
 question -> embed -> retrieve -> fuse -> top-k
```

And three promises discovered the hard way in Week 1:

1. **Never split a table.** Half a balance sheet makes the model lie with confidence.
2. **Every chunk must say where it came from.** A fragment reading "operating expenses rose 3%" is
   noise unless it knows it lives under `Item 7 > MD&A > Liquidity`.
3. **No claim without a number.** Quality, latency, cost - measured, every week, or it did not happen.

Where does the story stand today? **290 chunks indexed across 8 documents** - a 10-K, an OCR-scanned
lease, a two-column research paper, markdown notes, a transcript - with hybrid retrieval live and
measured. The rest of this talk is how it got there, one honest mistake at a time.

> **Walk off stage with:** "RAG quality is bounded by retrieval quality, and retrieval quality is
> bounded by chunk quality - so I instrument the whole chain."