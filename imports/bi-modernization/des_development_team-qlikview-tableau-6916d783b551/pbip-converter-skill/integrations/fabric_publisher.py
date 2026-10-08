"""
fabric_publisher.py — Publish a generated PBIP project to a Microsoft Fabric
workspace via the Fabric REST API, and bind the report to the published
semantic model so it renders in the Power BI service.

Why this exists
---------------
A `.pbip` folder is NOT something you can POST to a single "publish" endpoint.
The Fabric REST API treats the two folders as two separate ITEMS:

    <Name>.SemanticModel/  →  a Fabric "semantic model" item
    <Name>.Report/         →  a Fabric "report" item

Publishing order matters — the report must bind to a model that already
exists, so the semantic model is created first, then the report's
`definition.pbir` is rewritten to a live `byConnection` reference, then the
report item is created.

Auth
----
OAuth 2.0 client-credentials (app-only) via MSAL. Three secrets, read from
the environment (.env), never hard-coded:

    FABRIC_TENANT_ID
    FABRIC_CLIENT_ID
    FABRIC_CLIENT_SECRET

The app registration (service principal) must:
  * be granted Fabric/Power BI API permission and admin-consented,
  * be added as a Member or Admin of the target workspace,
  * and the tenant must allow service principals to call Fabric APIs
    (Fabric admin portal → "Service principals can use Fabric APIs").

Public entry point
-------------------
`publish_pbip(output_dir, workspace_id) -> dict` — publishes both items and
returns ids + the in-service report URL.
"""
from __future__ import annotations

import base64
import json
import os
import time

import requests

try:
    import msal
except ImportError as _e:  # pragma: no cover - dependency guard
    msal = None
    _MSAL_IMPORT_ERROR = _e

_FABRIC_API   = "https://api.fabric.microsoft.com/v1"
_AUTH_SCOPE   = ["https://api.fabric.microsoft.com/.default"]
_POWERBI_API  = "https://api.powerbi.com/v1.0/myorg"
_POWERBI_SCOPE = ["https://analysis.windows.net/powerbi/api/.default"]
_APP_BASE_URL = "https://app.powerbi.com"


# ── Auth ──────────────────────────────────────────────────────────────────────
def get_access_token(tenant_id: str | None = None,
                     client_id: str | None = None,
                     client_secret: str | None = None) -> str:
    """Acquire an app-only bearer token for the Fabric API.

    Args default to the FABRIC_* environment variables so callers normally
    invoke this with no arguments.
    """
    if msal is None:
        raise RuntimeError(
            "The 'msal' package is required for Fabric publishing. "
            f"Install it (`pip install msal`). Import error: {_MSAL_IMPORT_ERROR}"
        )
    tenant_id     = tenant_id     or os.environ.get("FABRIC_TENANT_ID")
    client_id     = client_id     or os.environ.get("FABRIC_CLIENT_ID")
    client_secret = client_secret or os.environ.get("FABRIC_CLIENT_SECRET")
    missing = [n for n, v in (("FABRIC_TENANT_ID", tenant_id),
                              ("FABRIC_CLIENT_ID", client_id),
                              ("FABRIC_CLIENT_SECRET", client_secret)) if not v]
    if missing:
        raise RuntimeError(f"Missing Fabric credentials in environment: {', '.join(missing)}")

    app = msal.ConfidentialClientApplication(
        client_id,
        client_credential=client_secret,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
    )
    result = app.acquire_token_for_client(scopes=_AUTH_SCOPE)
    if "access_token" not in result:
        raise RuntimeError(
            f"Fabric authentication failed: {result.get('error')} - "
            f"{result.get('error_description')}"
        )
    return result["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def get_powerbi_token(tenant_id: str | None = None,
                      client_id: str | None = None,
                      client_secret: str | None = None) -> str:
    """Acquire an app-only bearer token for the Power BI REST API
    (`https://analysis.windows.net/powerbi/api`).

    Distinct from `get_access_token()` (Fabric scope). Needed for the legacy
    Power BI dataset / gateway / refresh endpoints that aren't yet in the
    Fabric v1 surface: BindToGateway, /datasources, /refreshes.
    """
    if msal is None:
        raise RuntimeError(
            "The 'msal' package is required for Fabric publishing. "
            f"Install it (`pip install msal`). Import error: {_MSAL_IMPORT_ERROR}"
        )
    tenant_id     = tenant_id     or os.environ.get("FABRIC_TENANT_ID")
    client_id     = client_id     or os.environ.get("FABRIC_CLIENT_ID")
    client_secret = client_secret or os.environ.get("FABRIC_CLIENT_SECRET")
    app = msal.ConfidentialClientApplication(
        client_id, client_credential=client_secret,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
    )
    res = app.acquire_token_for_client(scopes=_POWERBI_SCOPE)
    if "access_token" not in res:
        raise RuntimeError(
            f"Power BI authentication failed: {res.get('error')} - "
            f"{res.get('error_description')}")
    return res["access_token"]


# ── Auto-bind a published dataset to a pre-existing cloud connection ─────────
def list_dataset_datasources(token: str, workspace_id: str,
                              dataset_id: str) -> list[dict]:
    """Return the datasources the published dataset references. Used to obtain
    the `datasourceId` values needed for BindToGateway."""
    resp = requests.get(
        f"{_POWERBI_API}/groups/{workspace_id}/datasets/{dataset_id}/datasources",
        headers=_headers(token),
    )
    resp.raise_for_status()
    return resp.json().get("value", [])


def bind_dataset_to_connection(token: str, workspace_id: str, dataset_id: str,
                                connection_id: str,
                                datasource_ids: list[str] | None = None) -> None:
    """Bind the dataset's datasources to a pre-existing cloud connection.

    `connection_id` must reference a SHAREABLE cloud connection (one created
    in Fabric Settings → Manage connections and gateways → New cloud, NOT a
    Personal Cloud Connection from the dataset's own settings page) that the
    service principal has been granted `User` or `Owner` permission on.
    Personal connections fail at refresh time with
    `ModelRefreshFailed_CredentialsNotSpecified` regardless of bind success.
    """
    if datasource_ids is None:
        ds = list_dataset_datasources(token, workspace_id, dataset_id)
        datasource_ids = [d["datasourceId"] for d in ds if d.get("datasourceId")]
    if not datasource_ids:
        return
    body = {"gatewayObjectId": connection_id, "datasourceObjectIds": datasource_ids}
    resp = requests.post(
        f"{_POWERBI_API}/groups/{workspace_id}/datasets/{dataset_id}/Default.BindToGateway",
        headers=_headers(token), json=body,
    )
    if resp.status_code not in (200, 202):
        raise RuntimeError(
            f"BindToGateway failed (HTTP {resp.status_code}) for dataset "
            f"{dataset_id} -> connection {connection_id}: {resp.text[:400]}")


def trigger_dataset_refresh(token: str, workspace_id: str, dataset_id: str) -> str:
    """Kick off a refresh of the published dataset. Returns the request id."""
    resp = requests.post(
        f"{_POWERBI_API}/groups/{workspace_id}/datasets/{dataset_id}/refreshes",
        headers=_headers(token), json={"notifyOption": "NoNotification"},
    )
    if resp.status_code not in (200, 202):
        raise RuntimeError(
            f"Trigger refresh failed (HTTP {resp.status_code}): {resp.text[:400]}")
    return resp.headers.get("RequestId", "")


# ── Long-running-operation polling ────────────────────────────────────────────
def wait_for_lro(token: str, location: str, retry_after: int = 5,
                 max_wait: int = 600) -> dict:
    """Poll a Fabric LRO `Location` URL until it succeeds; return the result.

    Create-item calls return 202 Accepted with a `Location` header pointing
    at an operation resource. When the operation reaches `Succeeded`, the
    created item is fetched from `<Location>/result`.
    """
    waited = 0
    while waited < max_wait:
        time.sleep(retry_after)
        waited += retry_after
        resp = requests.get(location, headers={"Authorization": f"Bearer {token}"})
        resp.raise_for_status()
        data = resp.json()
        status = (data.get("status")
                  or data.get("properties", {}).get("status"))
        if status == "Succeeded":
            result = requests.get(f"{location.rstrip('/')}/result",
                                  headers={"Authorization": f"Bearer {token}"})
            result.raise_for_status()
            return result.json()
        if status in ("Failed", "Canceled", "Cancelled", "Undelivered"):
            raise RuntimeError(f"Fabric operation failed ({status}): {data}")
    raise RuntimeError(f"Fabric operation timed out after {max_wait}s: {location}")


def _resolve_created_item(token: str, resp: requests.Response) -> dict:
    """Normalise a create-item response: 201 returns the item inline; 202
    returns an LRO that must be polled. Returns the item dict (has 'id')."""
    if resp.status_code == 201:
        return resp.json()
    if resp.status_code == 202:
        location = resp.headers.get("Location")
        if not location:
            raise RuntimeError(f"202 Accepted but no Location header: {resp.text[:300]}")
        return wait_for_lro(token, location)
    raise RuntimeError(
        f"Fabric create-item failed (HTTP {resp.status_code}): {resp.text[:500]}"
    )


# ── Workspace ─────────────────────────────────────────────────────────────────
def list_workspaces(token: str) -> list[dict]:
    """All workspaces the calling service principal is a member of."""
    resp = requests.get(f"{_FABRIC_API}/workspaces", headers=_headers(token))
    resp.raise_for_status()
    return resp.json().get("value", [])


def get_workspace(token: str, workspace_id: str) -> dict:
    """Fetch a workspace by id (used to learn its displayName for the
    report→model connection string). Distinguishes 403 vs 404 so the caller
    knows whether the workspace is missing or just not shared with the SP."""
    resp = requests.get(f"{_FABRIC_API}/workspaces/{workspace_id}",
                        headers=_headers(token))
    if resp.status_code == 403:
        raise RuntimeError(
            f"Workspace {workspace_id} exists but this service principal is "
            f"NOT a member of it. Add the app (Client ID in FABRIC_CLIENT_ID) "
            f"to the workspace under 'Manage access' with the Member or Admin role.")
    if resp.status_code == 404:
        raise RuntimeError(
            f"Workspace {workspace_id} was not found. Check the GUID is correct "
            f"and that the workspace lives in the SAME Entra tenant as the "
            f"service principal (FABRIC_TENANT_ID).")
    resp.raise_for_status()
    return resp.json()


def resolve_workspace_id(token: str, workspace_name: str) -> str:
    """Resolve a workspace display name to its id by listing the workspaces the
    service principal can see."""
    visible = list_workspaces(token)
    for ws in visible:
        if ws.get("displayName") == workspace_name:
            return ws["id"]
    if not visible:
        hint = ("This service principal is a member of ZERO workspaces. "
                "Either it has not been added to any workspace, or the "
                "workspace lives in a different Entra tenant than the SP.")
    else:
        names = ", ".join(repr(w.get("displayName")) for w in visible)
        hint = f"Workspaces this service principal CAN see: {names}."
    raise RuntimeError(
        f"Workspace named {workspace_name!r} not found / not accessible by "
        f"this service principal. {hint} "
        f"Fix: add the app (FABRIC_CLIENT_ID) to the target workspace under "
        f"'Manage access' as Member/Admin, in the SAME tenant as the SP. "
        f"You can also pass the workspace GUID directly instead of its name.")


# ── Definition packaging ──────────────────────────────────────────────────────
def _long(p: str) -> str:
    if os.name == "nt" and os.path.isabs(p) and not p.startswith("\\\\?\\"):
        return "\\\\?\\" + os.path.normpath(p)
    return p


def _folder_to_parts(folder: str) -> list[dict]:
    """Walk a PBIP item folder and return Fabric `definition.parts` — every
    file base64-encoded, `path` relative to the folder root with forward
    slashes (Fabric requires POSIX-style part paths)."""
    parts: list[dict] = []
    root_long = _long(folder)
    for cur, _dirs, files in os.walk(root_long):
        for fn in files:
            full = os.path.join(cur, fn)
            real = full[4:] if full.startswith("\\\\?\\") else full
            rel = os.path.relpath(real, folder).replace(os.sep, "/")
            with open(full, "rb") as fh:
                payload = base64.b64encode(fh.read()).decode("ascii")
            parts.append({"path": rel, "payload": payload,
                          "payloadType": "InlineBase64"})
    if not parts:
        raise RuntimeError(f"No files found under {folder!r} to publish.")
    return parts


# ── Create items ──────────────────────────────────────────────────────────────
def create_semantic_model(token: str, workspace_id: str,
                          model_folder: str, display_name: str) -> str:
    """Create a semantic-model item from a `.SemanticModel` folder. Returns
    the new item id."""
    body = {
        "displayName": display_name,
        "definition": {"parts": _folder_to_parts(model_folder)},
    }
    resp = requests.post(
        f"{_FABRIC_API}/workspaces/{workspace_id}/semanticModels",
        headers=_headers(token), json=body,
    )
    item = _resolve_created_item(token, resp)
    return item["id"]


def create_report(token: str, workspace_id: str,
                   report_folder: str, display_name: str) -> str:
    """Create a report item from a `.Report` folder. Returns the new item id.
    The folder's `definition.pbir` must already reference the target model
    (see `patch_pbir_to_connection`)."""
    body = {
        "displayName": display_name,
        "definition": {"parts": _folder_to_parts(report_folder)},
    }
    resp = requests.post(
        f"{_FABRIC_API}/workspaces/{workspace_id}/reports",
        headers=_headers(token), json=body,
    )
    item = _resolve_created_item(token, resp)
    return item["id"]


# ── Report → semantic-model binding ───────────────────────────────────────────
def patch_pbir_to_connection(report_folder: str, workspace_name: str,
                             model_name: str, model_id: str) -> None:
    """Rewrite `<report_folder>/definition.pbir` so the report binds to the
    PUBLISHED semantic model via a live XMLA connection instead of a local
    `byPath` sibling folder. This is what lets a report-only PBIP render
    against a model that lives in the service."""
    pbir_path = os.path.join(report_folder, "definition.pbir")
    if not os.path.isfile(_long(pbir_path)):
        raise RuntimeError(f"definition.pbir not found in {report_folder!r}")
    with open(_long(pbir_path), encoding="utf-8") as fh:
        pbir = json.load(fh)

    # PBIR v4.0 byConnection rules:
    #   * schema allows ONLY `connectionString` as a sibling property — the
    #     older PBIX-style fields (pbiServiceModelId, pbiModelVirtualServerName,
    #     pbiModelDatabaseName, connectionType, name) are rejected with
    #     `Workload_FailedToParseFile`;
    #   * runtime also needs the target model identified explicitly by GUID,
    #     which it accepts as a `semanticModelId=<GUID>` PARAMETER INSIDE the
    #     connection string. Without it Fabric returns
    #     `InvalidConnectionInformation: The semantic model identifier is
    #     invalid`. `Initial Catalog=<name>` alone is not enough.
    conn = (f"Data Source=powerbi://api.powerbi.com/v1.0/myorg/{workspace_name};"
            f"Initial Catalog={model_name};Integrated Security=ClaimsToken;"
            f"semanticModelId={model_id}")
    pbir["datasetReference"] = {
        "byConnection": {
            "connectionString": conn,
        }
    }
    with open(_long(pbir_path), "w", encoding="utf-8") as fh:
        json.dump(pbir, fh, indent=2)


# ── Orchestration ─────────────────────────────────────────────────────────────
def _find_entry(output_dir: str, suffix: str) -> str | None:
    for entry in sorted(os.listdir(_long(output_dir))):
        if entry.endswith(suffix):
            return entry
    return None


import re as _re
_GUID_RE = _re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _resolve_workspace(token: str, workspace: str, log) -> tuple[str, str]:
    """Accept either a workspace GUID or a display name and return
    (workspace_id, workspace_name). A value matching the GUID pattern is
    used as the id directly; anything else is looked up by name."""
    workspace = (workspace or "").strip()
    if _GUID_RE.match(workspace):
        ws = get_workspace(token, workspace)
        return workspace, (ws.get("displayName") or workspace)
    log(f"[fabric] Looking up workspace by name: {workspace!r}")
    ws_id = resolve_workspace_id(token, workspace)
    return ws_id, workspace


def publish_pbip(output_dir: str, workspace: str,
                 model_name: str | None = None,
                 report_name: str | None = None,
                 log=print) -> dict:
    """Publish a generated PBIP (`output_dir` containing `.SemanticModel` and
    `.Report` folders) to a Fabric workspace.

    `workspace` may be EITHER the workspace GUID OR its display name — a
    GUID-shaped value is used directly, anything else is resolved by name.

    Steps:
      1. authenticate (service principal),
      2. resolve the workspace,
      3. create the semantic-model item,
      4. repoint the report's definition.pbir at the published model,
      5. create the report item,
      6. return ids + the in-service report URL.

    `model_name` / `report_name` default to the folder's `<Name>`.
    """
    model_folder_name  = _find_entry(output_dir, ".SemanticModel")
    report_folder_name = _find_entry(output_dir, ".Report")
    if not model_folder_name or not report_folder_name:
        raise RuntimeError(
            f"Expected .SemanticModel and .Report folders in {output_dir!r}; "
            f"found model={model_folder_name!r} report={report_folder_name!r}."
        )
    base_name   = model_folder_name[:-len(".SemanticModel")]
    model_name  = model_name  or base_name
    report_name = report_name or base_name
    model_folder  = os.path.join(output_dir, model_folder_name)
    report_folder = os.path.join(output_dir, report_folder_name)

    log("[fabric] Authenticating (service principal)...")
    token = get_access_token()

    log(f"[fabric] Resolving workspace: {workspace!r}")
    workspace_id, workspace_name = _resolve_workspace(token, workspace, log)
    log(f"[fabric]   workspace_id = {workspace_id}  ({workspace_name})")

    log(f"[fabric] Creating semantic model '{model_name}'...")
    model_id = create_semantic_model(token, workspace_id, model_folder, model_name)
    log(f"[fabric]   semantic model id = {model_id}")

    log("[fabric] Repointing report definition.pbir at the published model...")
    patch_pbir_to_connection(report_folder, workspace_name, model_name, model_id)

    log(f"[fabric] Creating report '{report_name}'...")
    report_id = create_report(token, workspace_id, report_folder, report_name)
    log(f"[fabric]   report id = {report_id}")

    report_url = f"{_APP_BASE_URL}/groups/{workspace_id}/reports/{report_id}"
    log(f"[fabric] Done. Report: {report_url}")
    return {
        "workspace_id":   workspace_id,
        "workspace_name": workspace_name,
        "model_id":       model_id,
        "model_name":     model_name,
        "report_id":      report_id,
        "report_name":    report_name,
        "report_url":     report_url,
    }
