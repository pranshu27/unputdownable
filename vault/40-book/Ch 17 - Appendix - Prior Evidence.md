---
tags: [book, track-a]
chapter: 17
prev: "[[Ch 16 - Evals & Observability (W13-14)]]"
next: "[[Book]]"
---
# Ch 17 — Appendix: before Track A, there was this

Track A did not start from zero. It started from scars. (Kept private in `imports/` - completed prior projects, deliberately separate from this build. Full metrics: `interview/company-projects.md`.)

**The agentic migration.** A Teradata EDW whose logic lived in Informatica mappings nobody could read, migrated by six specialised AutoGen agents: extractor, collector, modeller, PySpark generator, Iceberg writer, parity reviewer - then an adversarial critic, then a human gate. The RAG modeller was fed by **1,189 chunks** of indexed lineage. The validated run: **20/20 tests, critic flagged, human gate held.** The lesson I carried here: guardrails in and out, and HITL as a first-class stage, not an apology.

**The golden-set audit.** A RAG system with 22 golden queries and an audit that scored non-empty, refusal, no-evidence and length per answer. Result: **22/22 non-empty, 0 refused, 0 empty, 0 no-evidence.** And the insight that mattered more than the score: strategy attribution showed the LLM-primary path fired **once out of twenty-two**. Extractive, evidence-first fallbacks carried the other twenty-one. The audit did not just grade the system - it exposed the real answer distribution and forced the evidence-first contract.

**The BI modernization program.** 84 Power BI tabular models, eight-plus dashboard workspaces from an insurance client, converted with LLM-assisted tooling that had prompts and tests. *Lesson: parity review is the acceptance gate, not a nice-to-have.*

**The legacy React rebuild.** 175 components restructured into core, layouts, Hooks and Lib. *Lesson: structure is what makes the next person productive.*

> **Walk off stage with:** "I have already run an agentic migration with a human gate and a golden-set eval - Track A is the second, more disciplined iteration of ideas I have shipped."
