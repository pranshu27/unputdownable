---
tags: [book, track-a]
chapter: 06
prev: "[[Ch 05 - Indexing]]"
next: "[[Ch 07 - Measurement]]"
---
# Ch 6 — Retrieval: two witnesses and a judge

So you have two witnesses. The dense witness says: "by meaning, these are the five passages that
matter." The sparse witness says: "by exact terms, here are mine." They disagree. They are both
partly right. Who decides?

You could add their scores. You should not: cosine lives in [0, 1] and BM25 is unbounded - adding
them is adding metres to kilograms. You could normalise per query - unstable, fiddly, wrong at the
edges. Or you could do what Reciprocal Rank Fusion does: **ignore the scores entirely and listen to
the ranks.**

```text
score(doc) = sum over lists L of 1 / (60 + rank_L(doc))
```

Rank one in both lists beats rank one in one list and rank forty in the other - but not
overwhelmingly, because k=60 deliberately dampens the head so *consensus* wins over confidence.
I implemented it from scratch - it is fifteen lines, and writing it is the interview flex; importing
it is not. And the punchline number: fusing two ranked lists costs **0.03 to 0.08 milliseconds** at
p95 against a 50 millisecond budget. Fusion is effectively free.

And then the honest coda, because this talk keeps its promises: on the 290-point corpus, hybrid
equals dense, 0.92 to 0.92. Fusion did not move the needle - *yet*. The witnesses both saw the whole
crowd. The judge gets interesting when the crowd gets to ten million.

> **Walk off stage with:** "RRF, from scratch: rank-only fusion with k=60 - no score normalisation,
> and it costs 0.08 milliseconds at p95."