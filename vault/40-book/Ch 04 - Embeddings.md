---
tags: [book, track-a]
chapter: 04
prev: "[[Ch 03 - Chunking]]"
next: "[[Ch 05 - Indexing]]"
---
# Ch 4 — Embeddings: the number the vector could not see

Here is a query my retrieval system should ace and originally fumbled: *"What is ERR-4021?"*

ERR-4021 is a ledger-journal write-timeout from an incident postmortem. To you, it is a precise
string. To a dense embedding, it is **noise** - semantically, every paragraph about outages and
errors looks vaguely alike, and the vector has no idea this particular code is the needle. Dense
vectors capture *meaning*. They are blind to *exact strings*.

The mirror image is true too: lexical search nails `ERR-4021` but has no idea that "car" and
"automobile" are the same thing. Two tools, opposite blind spots. So every chunk in this pipeline is
embedded **twice**:

- **Dense** - BGE-family vectors, 384 dimensions today (1024-d BGE-M3/large is a config swap, not a
  rewrite). Meaning, paraphrase, intent.
- **Sparse** - a hashed bag-of-words into 65,536 buckets, with IDF weighting so rare terms punch
  above their weight. Exact match.

And one detail that quietly moves metrics: the contextual header travels **inside the embedding
text**. `Apple FY2023 Form 10-K > Item 7` is not decoration - it steers the vector so a chunk about
liquidity retrieves for liquidity questions even when the sentence itself never says "liquidity".

> **Walk off stage with:** "Dense understands meaning and drops exact identifiers; lexical does the
> opposite. Complementary blind spots - so I embed twice and fuse later."