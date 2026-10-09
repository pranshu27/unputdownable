---
tags: [book, track-a]
chapter: 17
prev: "[[Ch 16 - Evals & Observability (W13-14)]]"
next: "[[Book]]"
---
# Ch 17 — Appendix: prior evidence (completed projects)

**These are completed prior projects, deliberately separate from Track A** (in `imports/`, kept private). Full metrics and STAR drafts: `interview/company-projects.md`.

- **Agentic Informatica -> PySpark migration** - 6 specialised AutoGen agents (extractor -> collector -> modeller -> generator -> Iceberg writer -> parity reviewer -> critic -> human gate that held), RAG-as-tool over **1,189 chunks**, PII/secret redaction, Langfuse tracing, **20/20 tests**. *Lesson carried into Track A:* guardrails in and out, HITL as a first-class stage.
- **RAG system with a golden-set eval gate** - 22 golden queries, hybrid k=6; audit: **22/22 non-empty, 0 refused, 0 empty, 0 no-evidence**, p95 22.6 s; strategy attribution showed the LLM primary carried only 1/22 answers - extractive evidence-first fallbacks carried 21/22. *Lesson carried into Track A:* evidence-first answering, and an eval that changes the design.
- **BI modernization program** - 84 Power BI tabular models, 8+ dashboard workspaces migrated with LLM-assisted converter tooling (prompts + tests). *Lesson:* conversion tooling needs parity review as the acceptance gate.
- **Legacy React modernization** - 175 `.tsx` modules restructured into core/layouts/Hooks/Lib.

> **Interview line:** "I have already run an agentic migration with a human gate and a golden-set eval - Track A is the second, more disciplined iteration of ideas I have shipped."
