---
tags: [book, track-a]
chapter: 10
prev: "[[Ch 09 - Guardrails]]"
next: "[[Ch 11 - Query Rewriting & Self-RAG (W3)]]"
---
# Ch 10 — Reranking: precision on top of recall (W2) - next up

The story so far ends at top-k: two witnesses, one cheap judge, and a list of candidates. But candidates are not answers. The next chapter of the talk is the one where a **cross-encoder** reads the question and each candidate *together* - something no bi-encoder can ever do - and spends real compute on the only fifty that matter.

Recall first, precision second. That is the two-stage shape, and it is where the latency budget finally gets spent on purpose. **Written the week it ships (W2) - with the measured Delta Recall@5 on the lexical-hard queries.**
