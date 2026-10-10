---
tags: [book, track-a]
chapter: 07
prev: "[[Ch 06 - Retrieval & RRF]]"
next: "[[Ch 08 - Serving]]"
---
# Ch 7 — Measurement: the two times I lied to myself

This chapter is the confession chapter. Three categories get measured every single measure-day -
quality, latency, cost - and this week they caught me twice.

**Lie number one.** I benchmarked a brute-force algorithm against a reference and reported a win.
Except the input alphabet was five characters long, which means the brute force broke out of its
inner loop almost immediately - it was never O(n-squared) on that input, it was O(n times alphabet).
Same code, different regime, different truth. **Name the regime or the benchmark is fiction.**

**Lie number two.** I measured `slots=True` saving 288 bytes per object with `sys.getsizeof`, felt
great about it - and then `tracemalloc` over 100,000 live objects said 40 bytes. Both were "correct".
Key-sharing dictionaries, interned strings - the method defines the truth. So now I say: *"you save
one dict per instance - tens to hundreds of megabytes per million records"*, an order of magnitude,
not a fake constant.

The numbers that *survived* scrutiny, and now form the baseline:

- Parse: **96 ms** for a 1.5 MB 10-K. Parsing is not the bottleneck.
- Embed: **60-95 s p95** for that same 10-K on CPU. The bottleneck, and the Week-2 target.
- Search spans: embed 3-9 ms, dense 4-8 ms, sparse 2-8 ms, fuse 0.08 ms. p50 total 11-18 ms.
- Tables: **0/75 corrupted**. Parse failures: **0/8**.
- Cost: $0.0025 per 1k pages embedded, $0.088 stored - reference prices, computed not guessed.

> **Walk off stage with:** "Three fixed categories every measure-week - and my harness caught me
> lying to myself twice, which is exactly what a harness is for."