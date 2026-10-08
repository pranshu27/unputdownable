---
description: Always-on behavioral coding guidelines for this repository.
---

Follow these behavioral guidelines on all coding tasks. Merge with project-specific instructions as needed.

Tradeoff: these guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1) Think Before Coding

Don't assume. Don't hide confusion. Surface tradeoffs.

- State assumptions explicitly.
- If multiple interpretations exist, present them instead of silently choosing one.
- If a simpler approach exists, call it out.
- If something is unclear, stop and ask.

## 2) Simplicity First

Minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked.
- No abstractions for single-use code.
- No configurability unless requested.
- No error handling for impossible scenarios.
- If the implementation is overcomplicated, simplify it.

## 3) Surgical Changes

Touch only what you must. Clean up only your own mess.

- Don't refactor unrelated adjacent code.
- Match existing style.
- Remove only unused code introduced by your own edits.
- If unrelated dead code is noticed, mention it but do not delete unless asked.

## 4) Goal-Driven Execution

Define success criteria and verify.

- Translate vague asks into measurable checks.
- For multi-step work, use short plan + verification per step.
- Do not stop at "looks good"; stop only after verification.
