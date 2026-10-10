---
tags: [book, track-a]
chapter: 04
prev: "[[Ch 03 - Chunking]]"
next: "[[Ch 05 - Indexing]]"
---
# Ch 4 — Embeddings: the number the vector could not see

Here is a query my retrieval system should ace and originally fumbled: *"What is ERR-4021?"*

ERR-4021 is a ledger-journal write-timeout from an incident postmortem. To you, it is a precise string. To a dense embedding, it is **noise** - semantically, every paragraph about outages and errors looks vaguely alike, and the vector has no idea this particular code is the needle. Dense vectors capture *meaning*. They are blind to *exact strings*.

The mirror image is true too: lexical search nails `ERR-4021` but has no idea that "car" and "automobile" are the same thing. Two tools, opposite blind spots. So every chunk in this pipeline is embedded **twice**:

- **Dense** - BGE-family vectors, 384 dimensions today (1024-d BGE-M3/large is a config swap, not a rewrite). Meaning, paraphrase, intent.
- **Sparse** - a hashed bag-of-words into 65,536 buckets, with IDF weighting so rare terms punch above their weight. Exact match.

And one detail that quietly moves metrics: the contextual header travels **inside the embedding text**. `Apple FY2023 Form 10-K > Item 7` is not decoration - it steers the vector so a chunk about liquidity retrieves for liquidity questions even when the sentence itself never says "liquidity".

**Worked example - the same three strings, counted two ways** (why word counts and token counts are different animals):

| Text | Whitespace words | BPE tokens (approx) |
| :--- | :--- | :--- |
| `What is ERR-4021?` | 4 | ~7 - the code splits into `ERR`, `-`, `402`, `1` |
| `CIK 0001874410` | 2 | ~6 - digit groups tokenize in small chunks |
| `retrieval augmented generation` | 3 | ~5-6 - common words mostly survive |

And the arithmetic that keeps chunks inside the embedding window:

```text
chunk body   250 whitespace tokens  ~  330-375 BPE tokens
header       ~10-20 whitespace tokens ~   15-30 BPE tokens
                                          -----------------
total                                      ~ 350-405 BPE   <  512 window (BGE-small)  OK

raise the target to 400 whitespace tokens  ->  ~550+ BPE  ->  the encoder silently truncates the tail
```

This is also the mechanism behind the giant-atomic-table risk (Ch 3): a table that is one huge chunk is not "one big embedding" - it is the FIRST 512 BPE tokens of a big chunk. Rows after the cut never reach the vector, while the payload stays complete. The corruption check cannot see it; only a token-budget check or row-group splitting can.

> **Walk off stage with:** "Dense understands meaning and drops exact identifiers; lexical does the opposite. Complementary blind spots - so I embed twice and fuse later."
