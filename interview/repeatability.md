# Repeatability Protocol — how answers get tested

**The rule of this phase:** every non-DSA drill has a written MODEL ANSWER. You study it, understand it, and memorize the **beat sheet** — not the prose. My job: test that you can reproduce the answer live, in random order, under time pressure, until it's interview-proof.

## The loop (each test session)
1. **I pick the drill at random** — never let yourself warm up on a favorite. Say: "surprise me" and I choose.
2. **You reproduce out loud** (voice memo, or typed fast into the session). Timed: LLD 25 min · whiteboard 30 min · STAR 90 s cut + 5 min pushback · MBB case 30 min.
3. **I score against the beat sheet** — for every beat: ✅ hit (right shape + right content) · 🟡 right idea, wrong shape (acceptable; note the gap) · ❌ missed, wrong order, or wrong number.
4. **Numbers must be exact.** 0/75 tables · 1,189 chunks · 20/20 tests · 22/22 and 1/22 · 15/6/1 · 61/62 rank-gap · ~53 GB @ 10M · 96 ms vs 60–95 s · p95 < 2 s · Δ=0 at 290 pts. A wrong number is a ❌, not a 🟡 — interviewers check numbers.
5. **Pass bar:** zero ❌, everything else ≥ 🟡, delivered inside the time cap. **Two consecutive passes spaced ≥ 48 h = burned in.**
6. **Fail rule:** any ❌ → rewrite THAT beat in your own words the same day (own words stick; my prose is scaffolding), re-test that drill first next session.

## Schedule (anti-cramming)
- **D0** study the model answer → **D1** first reproduction → **D3** → **D7** → then weekly rotation inside mixed sessions.
- Mixed sessions interleave drills (whiteboard + STAR + ADR in one sitting) — blocked practice fools you.
- Cap: max 3 test drills per session; more and you pattern-match instead of recall.

## Priority tiers (if time is short)
- **T1 (interview-critical, test weekly):** LLD Extensible Parser · Whiteboard 10M docs · ADR-002 walk (hybrid+rerank, with Δ=0 honesty beat) · STAR 1–3 cuts · Company ADR #1.
- **T2 (test biweekly):** LLD RRF ranker · LLD Query Rewriter · Whiteboard ingestion (Drill 1) · KB-search drill · MBB Case 1 · ADR-003 walk.
- **T3:** question-bank one-liners (spot-check 5 random per session).

## Tracker (update after every attempt)

| Drill | Tier | Attempt 1 (date/score) | Attempt 2 | Attempt 3 | Burned in (2× ≥48h apart) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| LLD Extensible Parser | T1 | | | | ⬜ |
| Whiteboard 10M docs | T1 | | | | ⬜ |
| ADR-002 walk (hybrid+rerank) | T1 | | | | ⬜ |
| STAR 1 cut | T1 | | | | ⬜ |
| STAR 2 cut | T1 | | | | ⬜ |
| STAR 3 cut | T1 | | | | ⬜ |
| Company ADR #1 (human gate) | T1 | | | | ⬜ |
| LLD RRF ranker | T2 | | | | ⬜ |
| LLD Query Rewriter | T2 | | | | ⬜ |
| Whiteboard ingestion | T2 | | | | ⬜ |
| Whiteboard KB search | T2 | | | | ⬜ |
| MBB Case 1 | T2 | | | | ⬜ |
| ADR-003 walk (transform+reflection) | T2 | | | | ⬜ |

## What I do each session
- Pick drills randomly, read the prompt verbatim, time you, score beats, log the tracker row, and dictate the weakest-beat rewrite prompt.
- Pushback round after every pass: one hostile follow-up per drill (from the drill's "if pressed" pool) — memorized answers must survive follow-ups, not just first asks.

## Beat-sheet index (what gets scored)

| Answer | File | Beats |
| :--- | :--- | :--- |
| Extensible Document Parser | `lld-extensible-document-parser.md` | 10 + 3 follow-ups (A, B1, B2) |
| RRF Ranker | `lld-rrf-ranker.md` | 8 |
| Query Rewriter (CoR) | `lld-query-rewriter.md` | 8 |
| Whiteboard: ingestion | `whiteboard-drills.md` Drill 1 | 9 |
| Whiteboard: 10M docs | `whiteboard-drills.md` Drill 2 | 8 |
| Whiteboard: KB search | `whiteboard-drills.md` Drill 3 | 7 |
| MBB Case 1 | `mbb-case-1.md` | 12 |
| Company ADR #1 | `company-adr-001.md` | 9 |
| ADR-002 walk | `adr-walks.md` | 10 |
| ADR-003 walk | `adr-walks.md` | 10 |
| STAR 1 / 2 / 3 | `star-stories.md` | 8 each |

## DSA exception
DSA drills stay solve-first (no memorized answers by design — pattern recognition, not recall): solve cold, verify against the notebook fuzz, and the beat there is the *pattern one-liner* you add to `dsa/patterns.md`.
