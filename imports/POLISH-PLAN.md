# Polish Plan — imports/ made interview-presentable

**Audit date:** 2026-10-08 · **Verdict:** hygiene is good (0 junk files: no pycache/venv/node_modules);
what needs work is **naming, weight, and the missing sanitized layer**.

---

## 0. The strategic decision first

"Neat" means different things for two audiences:

| Audience | What neat means |
| :--- | :--- |
| **You, in the room** | stories + numbers + diagrams you can draw from memory. The archives are evidence, not a showcase. |
| **A public portfolio** (if you link GitHub) | **sanitized project pages** - never the company dumps verbatim. Client names, insurance data and proprietary logic must not ship. |

**Recommendation:** keep `imports/` private evidence; build a sanitized `portfolio/` layer only if you
plan to link this repo. Decide: **will this repo be public / linked on your resume?**

---

## 1. Phase 1 - mechanical cleanup (low risk, ~30 min)

| # | Action | Why |
| :--- | :--- | :--- |
| 1.1 | Rename `des_development_team-*` folders to human names (map below) | nobody can read the current names; you will fumble them in interviews |
| 1.2 | `git rm --cached BI-Modernization-Complete-Code.zip freedom_portable_nocache.zip` + gitignore `*.zip` | 25 MB binary, already in history; stop it growing and stop re-downloading it |
| 1.3 | Gitignore `_ref_zips/` (nested archives), `generated/`, `.env` (already) | archives inside archives; the original projects own these rules anyway |
| 1.4 | Delete `.gitignore copy`; review `_weeks2.py` at the freedom root | stray/scratch files read as sloppiness |
| 1.5 | Untrack >1 MB non-code data files (11 MB `800node.json`, 8 MB `login.jpg`, 4 MB JSONs, 1.3 MB `lineageData.js`, duplicate theme PNGs) | ~20 MB of data that proves nothing in an interview; keep locally, cite sizes in docs instead |

**Proposed rename map**

| Current | New |
| :--- | :--- |
| `bi-modernization/des_development_team-legacy-modernization-react-0ad91b6c8e45` | `bi-modernization/react-modernization/` |
| `bi-modernization/des_development_team-qlikview-tableau-2b6345786bda` | `bi-modernization/qlikview-converter/` (the full one: tests + prompts, 865 files) |
| `bi-modernization/des_development_team-qlikview-tableau-857432597538` | `bi-modernization/qlikview-converter-variant-a/` |
| `bi-modernization/des_development_team-qlikview-tableau-6916d783b551` | `bi-modernization/qlikview-converter-variant-b/` |
| `bi-modernization/des_development_team-copilot_jira-6955c4fb2127` | `bi-modernization/jira-copilot-service/` |
| `freedom_portable_nocache` | `freedom/` |

Decide: are the two converter variants worth keeping at all, or archive outside git?

---

## 2. Phase 2 - documentation pass (the real "neat", ~2 h)

For each project, a README in this fixed shape (1 screen, no dumps):

1. **Problem** - one paragraph, business framing, anonymized client
2. **What I built** - architecture diagram (mermaid), stack bullets
3. **Decisions** - 2-3, each with the rejected alternative
4. **Measured results** - the artifact-derived numbers + your business numbers
5. **Limitations / what I would do differently** - this is what senior interviewers actually probe

Specific gaps found:

| Project | README | Fix |
| :--- | :--- | :--- |
| `e2e_infa_to_pyspark` | has TRACKER.md (excellent) | add a top summary + metrics table; link the mermaid diagram |
| `react-modernization` | has README | add decisions/results sections |
| `qlikview-converter` (full) | has README | add the parity/acceptance metric table |
| `jira-copilot-service` | **NO README** | write one (it is 7 files, 30 min) |
| `qlikview-converter-variant-b` | **NO README** | write one or archive it |
| `rag-system` | 8 design docs, no README | one README linking the docs + the eval results table |

Plus **`imports/PORTFOLIO.md`**: a one-page index of all four projects with their metric tables
(fed from `interview/company-projects.md`).

---

## 3. Phase 3 - the sanitized public layer (only if the repo goes public)

- Per-project page: sanitized diagrams + metrics + 2-3 curated snippets (no client data, no names).
- Never ship: `documents/`, `pbib_input_files/` (client reports), the big JSONs (they embed real
  schema/data - `nationWide1.json` names a client).
- Options: (a) sanitize in place, (b) new repo `yourname/portfolio` with pages only. (b) is cleaner.

---

## 4. Effort estimate

| Phase | Time |
| :--- | :--- |
| 1 mechanical | 30 min (I can execute on your nod) |
| 2 documentation | ~2 h (I draft every README, you fill the `[YOU]` business numbers) |
| 3 sanitized layer | ~2 h, only if going public |
