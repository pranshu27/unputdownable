# imports/ — completed past projects (evidence vault)

> [!warning] Separate projects — do not mix
> Everything here is **completed prior work**. The current build lives in `track-a/` and is a
> **separate project** with its own design docs (`vault/30-design/`). Nothing here is part of Track A.

| Folder | What it is | State |
| :--- | :--- | :--- |
| `bi-modernization/react-modernization/` | Legacy UI modernization: 175 `.tsx` modules across core/layouts/Hooks/Lib, 56 deps | code committed; data payloads untracked |
| `bi-modernization/qlikview-converter/` | QlikView -> Power BI/Tableau conversion tooling (prompts + tests) | code committed; client report bundles untracked |
| `bi-modernization/jira-copilot-service/` | Containerised Jira<->Copilot integration service (AWS Secrets Manager) | complete |
| `freedom/rag-system/` | RAG system: golden-set eval (22/22 non-empty, 0 no-evidence), `prompts.yml`, Streamlit UI, 8 design docs | complete |
| `freedom/project1/` | Agentic Informatica -> PySpark migration: 6 AutoGen agents, 1,189-chunk live run, 20/20 tests, human review gate | complete |
| `freedom/apps/` | genai-portfolio-tracker-react, tracker-backend, obsidian vault | working |
| `freedom/documents/` | P2-P5 LLD docs (local benchmarking, observability, fine-tuning, realtime multimodal) | committed |

## Publishing notes (this repo is public)

- **Untracked + gitignored** (kept local, never published): the two root archives, converter variants
  a/b, `pbib_input_files/` (client report bundles), `_ref_zips/`, all 19 `src/*.json` client ETL
  conversion datasets (up to 11 MB), heavy images.
- **Source scrubbed** (2026-10-08): client names replaced with `CLIENT_A` / `CLIENT_B` / `CLIENT_C`
  across 26 tracked files; verified zero remaining hits.
- **History caveat:** earlier commits (`1fd6877`, `77368c0`) still contain the archives and client
  data. **Before linking this repo publicly: keep it private, or publish a fresh sanitised repo** and
  link that instead. Do not link this one until that decision is made.

## Entry points
- Metrics and STAR stories: `../interview/company-projects.md`
- Polish backlog: `POLISH-PLAN.md`
