"""
jira_client.py — Fetch JSON data from a Jira issue.

A single ticket can carry one OR two common-model JSONs:
  - ONE  — Tableau export, or a single (non-live-connect) Power BI export.
  - TWO  — a Power BI thin / live-connect pair (dataset JSON + report JSON).

Strategy:
  1. Try API v2 attachments: collect EVERY usable .json attachment.
  2. If none found, fall back to API v3 description body (parse embedded JSON).
  3. Raise ValueError if nothing usable is found.

Auth: HTTP Basic with email + API token (no server-side storage).
"""
import json, logging
from typing import Any

import requests
from requests.auth import HTTPBasicAuth

log = logging.getLogger("jira_client")


def _auth(email: str, api_token: str) -> HTTPBasicAuth:
    return HTTPBasicAuth(email, api_token)


def _base(base_url: str) -> str:
    return base_url.rstrip("/")


def fetch_issue_jsons(
    base_url: str,
    email: str,
    api_token: str,
    issue_id: str,
) -> list[dict[str, Any]]:
    """
    Return EVERY usable common-model JSON attached to (or embedded in) a
    Jira issue, in attachment order (metadata-named files first).

    A ticket carries:
      - ONE JSON  → Tableau export, or a single Power BI export.
      - TWO JSONs → a Power BI thin / live-connect pair (dataset + report);
                    the caller merges them before conversion.

    Attachments named `*_kpi_lineage.json` / `*_technical_summary.*` are NOT
    data models and are always skipped. Falls back to a single JSON parsed
    from the issue description when there are no usable attachments.

    Raises ValueError on auth failure or when nothing usable is found.
    """
    auth = _auth(email, api_token)
    root = _base(base_url)

    # ── Step 1: fetch issue metadata (v2) and scan attachments ────────────────
    resp = requests.get(
        f"{root}/rest/api/2/issue/{issue_id}",
        auth=auth,
        timeout=30,
    )
    if resp.status_code == 401:
        raise ValueError(
            f"Jira authentication failed (401) — check email and API token. "
            f"Response: {resp.text[:300]}"
        )
    if resp.status_code == 403:
        raise ValueError(
            f"Jira access forbidden (403) — account may lack permission to view '{issue_id}'. "
            f"Response: {resp.text[:300]}"
        )
    if resp.status_code == 404:
        raise ValueError(
            f"Jira issue '{issue_id}' not found (404) — verify the issue key and base URL. "
            f"URL tried: {root}/rest/api/2/issue/{issue_id}  "
            f"Response: {resp.text[:300]}"
        )
    resp.raise_for_status()

    issue_data = resp.json()
    attachments = issue_data.get("fields", {}).get("attachment", [])
    log.info("Found %d attachment(s): %s", len(attachments), [a.get("filename") for a in attachments])

    # Prefer *_metadata.json; skip *_kpi_lineage.json and *_technical_summary.*
    def _priority(filename: str) -> int:
        if "kpi_lineage" in filename or "technical_summary" in filename:
            return 99   # never a data model — skip
        if "metadata" in filename:
            return 0
        return 1

    json_attachments = sorted(
        [a for a in attachments if a.get("filename", "").endswith(".json")],
        key=lambda a: _priority(a["filename"]),
    )
    log.info("JSON attachment(s) after filter: %s", [a.get("filename") for a in json_attachments])

    # Collect EVERY usable JSON attachment — a thin/live-connect Power BI
    # ticket carries two (dataset + report).
    out: list[dict[str, Any]] = []
    for att in json_attachments:
        if _priority(att["filename"]) == 99:
            log.info("Skipping %s (kpi_lineage / technical_summary)", att["filename"])
            continue
        log.info("Downloading attachment: %s", att["filename"])
        dl = requests.get(att["content"], auth=auth, timeout=60)
        dl.raise_for_status()
        try:
            data = dl.json()
        except ValueError:
            log.warning("Attachment %s is not valid JSON, skipping", att["filename"])
            continue
        if isinstance(data, dict):
            log.info("Parsed JSON from %s — top-level keys: %s",
                     att["filename"], list(data.keys())[:8])
            out.append(data)

    if out:
        return out

    # ── Step 2: fall back to description body (v3) ────────────────────────────
    resp3 = requests.get(
        f"{root}/rest/api/3/issue/{issue_id}",
        auth=auth,
        timeout=30,
    )
    resp3.raise_for_status()

    description = resp3.json().get("fields", {}).get("description") or {}
    text_nodes = _extract_text_nodes(description)
    combined = " ".join(text_nodes)

    start = combined.find("{")
    end   = combined.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return [json.loads(combined[start:end])]
        except ValueError:
            pass

    raise ValueError(
        f"No JSON found in attachments or description of issue '{issue_id}'."
    )


def fetch_issue_json(
    base_url: str,
    email: str,
    api_token: str,
    issue_id: str,
) -> dict[str, Any]:
    """Backwards-compatible single-JSON accessor — returns the FIRST usable
    JSON on the issue. New callers should use `fetch_issue_jsons` so a
    two-JSON (thin/live-connect) ticket isn't silently truncated."""
    return fetch_issue_jsons(base_url, email, api_token, issue_id)[0]


def _extract_text_nodes(node: Any) -> list[str]:
    """Recursively pull plain text from an Atlassian Document Format node."""
    if not isinstance(node, dict):
        return []
    if node.get("type") == "text":
        return [node.get("text", "")]
    results: list[str] = []
    for child in node.get("content", []):
        results.extend(_extract_text_nodes(child))
    return results
