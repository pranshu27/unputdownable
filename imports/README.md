# imports/ — external work brought into this repo

**Provenance:** extracted from the two archives pushed in commit `1fd6877` ("bi-mod and rag work") and kept alongside them in the repo root.

| Folder | Source archive | Files | Size | What it is |
| :--- | :--- | :--- | :--- | :--- |
| `bi-modernization/` | `BI-Modernization-Complete-Code.zip` (5 nested zips) | 999 | ~57 MB | BI workstreams: legacy React modernization (46 MB incl. large JSON/image assets), QlikView→Tableau conversions ×3, Jira→Copilot tooling |
| `freedom_portable_nocache/` | `freedom_portable_nocache.zip` | 306 | ~4.6 MB | RAG-system workspace: `apps/`, `rag-system/`, `project1/`, `documents/`, `.agents/skills/`, `.github/skills/`, `rag-system.code-workspace` |

### Extraction notes
- Windows-style `\` paths in the archives were normalized to `/`; `.git/` and `__MACOSX/` entries were skipped; stored executable bits were restored.
- No `node_modules`, `.venv`, `__pycache__`, or nested `.zip` payloads were present.
- These are **snapshots** — they carry no git history from their origin, so review before trusting them as a source of truth.

### Secrets / client data
- `.env` files are excluded by the repo `.gitignore` (verified with `git check-ignore`) — e.g. `bi-modernization/des_development_team-legacy-modernization-react-*/.../.env` holds only API base URLs, but one points at a client, so it stays out of git.
- Two `.env.example` templates *are* committed (they contain no values).
- `AWSSecretsManager.py` (×3) are helper modules that read secrets at runtime — no credentials in them.

### Size warning
- The repo root still holds the original archives (~26 MB of binaries) and commit `1fd6877` keeps them in history forever. If this repo should stay lean, `git rm --cached *.zip` + a `.gitignore` rule stops future growth (history rewrite is a separate, riskier step).
