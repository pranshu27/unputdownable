"""
server.py — FastAPI server: fetch JSON from Jira → run PBIP skill → return the
generated Power BI project, split into a dataset zip and a report zip.

One skill only: JsonToPbipSkill.

Run:
    cd pbip-converter-skill
    uvicorn server:app --reload --port 8000

Endpoints
---------
GET  /health
POST /generate_pbip/
        Query params: base_url, email, api_token, issue_id
POST /publish_pbip/
        Upload the zip /generate_pbip/ returned and publish it to a Microsoft
        Fabric workspace. The endpoint unpacks the bundle (incl. nested zips),
        stitches the dataset's .SemanticModel + the report's .Report into one
        PBIP, and creates both items in the target workspace. Returns the
        semantic-model id, report id, and the in-service report URL.
POST /validate_pbip/
        Upload 1-2 extraction JSONs + the generated PBIP zip(s); routes each
        JSON to the semantic / report validator and returns a result JSON in
        the testoutput.json format.

        `issue_id` accepts ONE Jira issue key, or TWO comma-separated keys:
          - one key   → that ticket's JSON is a full single-PBIX extraction.
          - two keys  → thin / live-connect pair (data ticket + report ticket);
                        the two JSONs are merged before conversion. Order does
                        not matter — the merger auto-detects which is which.

        Returns a single .zip download (`<Name>_pbip.zip`) that contains TWO
        zips:
          <Name>_dataset.zip  → the <Name>.SemanticModel folder (tables,
                                 relationships, calculations)
          <Name>_report.zip   → the <Name>.pbip entry file + <Name>.Report
                                 folder (pages, visuals)
"""
import io, json, logging, os, re, shutil, sys, tempfile, traceback, zipfile
from urllib.parse import urlparse
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Silence harmless asyncio "Event loop is closed" finalizer noise from the
# autogen Azure client on Windows (cleanup runs after our event loop exits).
def _hide_asyncio_cleanup(unraisable):
    if (isinstance(unraisable.exc_value, RuntimeError)
            and "Event loop is closed" in str(unraisable.exc_value)):
        return
    sys.__unraisablehook__(unraisable)
sys.unraisablehook = _hide_asyncio_cleanup

from fastapi import FastAPI, File, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from integrations.jira_client import fetch_issue_jsons
from integrations.fabric_publisher import (
    _APP_BASE_URL,
    _resolve_workspace,
    bind_dataset_to_connection,
    create_report,
    create_semantic_model,
    get_access_token,
    get_powerbi_token,
    patch_pbir_to_connection,
    trigger_dataset_refresh,
)
from skills.json_to_pbip.skill import JsonToPbipSkill
from skills.json_to_pbip.src.merger import merge_thin_live
from skills.json_to_pbip.src.writer import set_data_source_url, write_empty_report
from validation_runner import extract_zip, pick_pbip_folder, run_validation

# Quiet uvicorn's per-request access logs so the demo output stays clean.
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.basicConfig(level=logging.WARNING, format="%(message)s")

app = FastAPI(title="PBIP Converter", version="1.0.0")
_skill = JsonToPbipSkill()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


# Where the skill writes generated PBIPs — matches JsonToPbipSkill's default.
_OUTPUTS_DIR = str(Path(__file__).resolve().parent / "outputs")


def _banner(text: str):
    bar = "=" * 70
    print(f"\n{bar}\n  {text}\n{bar}")


def _step(num: int, total: int, title: str):
    print(f"\n[{num}/{total}] {title}")


def _ok(msg: str):
    # ASCII marker — non-ASCII glyphs crash on Windows consoles whose code
    # page is cp1252 (UnicodeEncodeError).
    print(f"      [ok] {msg}")


def _fail(msg: str):
    print(f"      [x] {msg}")


# ── Zip helpers ───────────────────────────────────────────────────────────────
def _long(p: str) -> str:
    """Prefix absolute Windows paths with the long-path marker so os.walk and
    file reads can reach PBIP visual JSONs nested past MAX_PATH (260)."""
    if os.name == "nt" and os.path.isabs(p) and not p.startswith("\\\\?\\"):
        return "\\\\?\\" + os.path.normpath(p)
    return p


def _add_to_zip(zf: zipfile.ZipFile, abs_path: str, arc_prefix: str) -> None:
    """Add a file (or a folder, recursively) to the open ZipFile `zf`, placing
    its contents under `arc_prefix` in the archive."""
    lp = _long(abs_path)
    if os.path.isfile(lp):
        zf.write(lp, arc_prefix)
        return
    for root, _, files in os.walk(lp):
        for fn in files:
            full = os.path.join(root, fn)
            real = full[4:] if full.startswith("\\\\?\\") else full
            arc = os.path.join(arc_prefix, os.path.relpath(real, abs_path))
            zf.write(full, arc)


def _make_zip(items: list) -> bytes:
    """items: list of (abs_path, arc_prefix). Returns the zip as bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for abs_path, arc_prefix in items:
            _add_to_zip(zf, abs_path, arc_prefix)
    return buf.getvalue()


def _find_entry(output_dir: str, suffix: str) -> str | None:
    """Return the name of the first entry in `output_dir` ending with `suffix`
    (e.g. '.SemanticModel', '.Report', '.pbip'), or None."""
    for entry in sorted(os.listdir(_long(output_dir))):
        if entry.endswith(suffix):
            return entry
    return None


def _normalize_url(url: str) -> str:
    """Strip whitespace, fix obvious scheme typos, normalize SharePoint sharing
    links to the site URL form, validate.

    Defensive against pasting issues so users don't see refresh-time errors:
      'https;//foo'                → 'https://foo'   (semicolon for colon)
      'http;//foo'                 → 'http://foo'
      'foo.com'                    → 'https://foo.com'  (missing scheme)
      '  https://foo.com/  '       → 'https://foo.com'  (whitespace + trailing /)
      'https://h/:f:/s/<site>/<token>'  → 'https://h/sites/<site>'
                                          (SharePoint sharing link -> site URL)

    Raises ValueError if the result still isn't a valid http(s) URL.
    """
    if not url:
        return url
    s = url.strip()
    # Common scheme typos — colon often gets autocorrected to semicolon on
    # phones/copy-paste from chat.
    s = s.replace("https;//", "https://").replace("http;//", "http://")
    # If no scheme survives, default to https.
    if not re.match(r"^https?://", s, flags=re.IGNORECASE):
        s = "https://" + s.lstrip("/")

    p = urlparse(s)

    # SharePoint / OneDrive-for-Business "browse URLs" carry the real
    # folder path in the `?id=` query param (URL-encoded, starts with `/`).
    # Examples this catches:
    #   …/Shared%20Documents/Forms/AllItems.aspx?id=%2Fsites%2F…   (SharePoint)
    #   …/personal/<user>/_layouts/15/onedrive.aspx?id=%2Fpersonal%2F…  (ODB)
    # Convert to a clean folder URL so Web.Contents can fetch each file.
    if p.query:
        from urllib.parse import parse_qs, quote, unquote
        q = parse_qs(p.query)
        if "id" in q:
            id_val = unquote(q["id"][0])
            if id_val.startswith("/"):
                # Re-encode for M (spaces -> %20, keep / and a few safe chars).
                folder_path = quote(id_val, safe="/()-_.~")
                s = f"{p.scheme}://{p.netloc}{folder_path}"
                p = urlparse(s)

    # SharePoint sharing link (`/:f:/s/<site>/<token>`) is NOT something
    # SharePoint.Files can enumerate; rewrite to the site URL form.
    m = re.match(r"^(https?://[^/]+)/:[a-z]:/s/([^/?#]+)", s, flags=re.IGNORECASE)
    if m:
        s = f"{m.group(1)}/sites/{m.group(2)}"

    s = s.rstrip("/")
    p = urlparse(s)
    if p.scheme.lower() not in ("http", "https") or not p.netloc:
        raise ValueError(
            f"Invalid URL: {url!r} (normalized to {s!r}). "
            f"Expected a full https URL like "
            f"'https://<host>/sites/<site>' or 'https://<host>/path/to/folder'."
        )
    return s


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/generate_pbip/")
def generate_pbip(
    base_url: str  = Query(..., description="Jira base URL, e.g. https://acme.atlassian.net"),
    email: str     = Query(..., description="Jira account email"),
    api_token: str = Query(..., description="Jira API token"),
    issue_id: str  = Query(
        ...,
        description="One Jira issue key. The ticket carries the extraction "
                    "JSON(s): one JSON for Tableau / single Power BI, or two "
                    "JSONs (dataset + report) for a Power BI thin/live-connect "
                    "report. Example: 'GA-31999'.",
    ),
    source_url: str | None = Query(
        None,
        description="Optional cloud folder URL the generated PBIP loads its "
                    "source CSVs from. Default = the dataeconomy "
                    "DeliveryGovernance-JnJ SharePoint site. Accepts any "
                    "https URL — SharePoint site, OneDrive / OneDrive-for-"
                    "Business folder, public web folder, Azure Blob, etc. "
                    "Minor scheme typos (https;//) and SharePoint sharing "
                    "links (/:f:/s/<site>/<token>) are auto-fixed.",
    ),
    output_mode: str = Query(
        "split",
        description="'split' (default) returns the existing bundle zip with "
                    "the dataset half + the report half as two separate zips. "
                    "'single' returns ONE zip containing a complete openable "
                    "PBIP folder (.pbip + .SemanticModel + .Report) ready to "
                    "drop into Power BI Desktop.",
    ),
):
    issue_id = issue_id.strip()

    # ── Validate the two extra params up front ────────────────────────────────
    output_mode = (output_mode or "split").strip().lower()
    if output_mode not in ("split", "single"):
        return JSONResponse(status_code=400, content={
            "status": "error",
            "detail": f"output_mode must be 'split' or 'single', got {output_mode!r}.",
        })
    normalized_source_url = None
    if source_url:
        try:
            normalized_source_url = _normalize_url(source_url)
        except ValueError as exc:
            return JSONResponse(status_code=400, content={
                "status": "error", "detail": str(exc),
            })

    _banner(f"PBIP CONVERTER — Jira ticket {issue_id}  (mode={output_mode})")
    if normalized_source_url:
        _ok(f"data source URL override: {normalized_source_url}")

    # ── Step 1: fetch ALL JSON attachments from the one ticket ────────────────
    # A Power BI thin/live-connect ticket carries TWO JSONs (dataset + report);
    # a Tableau / single Power BI ticket carries ONE.
    _step(1, 4, f"Fetching dashboard JSON(s) from Jira ({issue_id})")
    _inputs_dir = Path(__file__).resolve().parent / "inputs"
    _inputs_dir.mkdir(exist_ok=True)
    try:
        jsons = fetch_issue_jsons(
            base_url=base_url, email=email, api_token=api_token, issue_id=issue_id,
        )
    except ValueError as exc:
        _fail(f"Jira error: {exc}")
        return JSONResponse(status_code=400, content={"status": "error", "detail": str(exc)})
    except Exception:
        _fail("Unexpected error fetching from Jira")
        traceback.print_exc()
        return JSONResponse(status_code=502, content={
            "status": "error", "detail": traceback.format_exc(),
        })

    if len(jsons) not in (1, 2):
        _fail(f"Ticket {issue_id} yielded {len(jsons)} JSON attachment(s)")
        return JSONResponse(status_code=422, content={
            "status": "error",
            "detail": (f"Jira ticket {issue_id} yielded {len(jsons)} usable JSON "
                       f"attachment(s). Expected 1 (Tableau / single Power BI) "
                       f"or 2 (Power BI thin/live-connect: dataset + report)."),
        })

    # Persist each fetched JSON for traceability / re-runs.
    for idx, data in enumerate(jsons, start=1):
        suffix = "" if len(jsons) == 1 else f"_{idx}"
        _input_file = _inputs_dir / f"{issue_id}{suffix}.json"
        with open(_input_file, "w", encoding="utf-8") as _f:
            json.dump(data, _f, indent=2)
        size_kb = round(_input_file.stat().st_size / 1024, 1)
        _ok(f"Saved inputs/{_input_file.name} ({size_kb} KB)")

    # ── Step 2: merge when the ticket carries two JSONs (Power BI thin/live) ──
    if len(jsons) == 2:
        _step(2, 4, "Merging dataset + report JSON (Power BI thin / live-connect)")
        try:
            input_json = merge_thin_live(jsons[0], jsons[1])
            _ok("Merged the two extractions into one common-model JSON")
        except ValueError as exc:
            _fail(f"Merge error: {exc}")
            return JSONResponse(status_code=400, content={"status": "error", "detail": str(exc)})
        except Exception:
            _fail("Unexpected error merging the two JSONs")
            traceback.print_exc()
            return JSONResponse(status_code=500, content={
                "status": "error", "detail": traceback.format_exc(),
            })
    else:
        _step(2, 4, "Single JSON — no merge needed")
        input_json = jsons[0]

    # ── Step 3: run the PBIP skill ────────────────────────────────────────────
    # If the caller supplied source_url, override the writer's data-source URL
    # for THIS run only. The override is a module-level global, so it MUST be
    # reset in `finally` even on the error path — otherwise one request's URL
    # leaks into the next request's generated M queries.
    _step(3, 4, "Converting to a Power BI .pbip project")
    if normalized_source_url:
        set_data_source_url(normalized_source_url)
    try:
        result = _skill.run(_input_data=input_json)
    except Exception:
        _fail("Pipeline crashed")
        traceback.print_exc()
        return JSONResponse(status_code=500, content={
            "status": "error", "detail": traceback.format_exc(),
        })
    finally:
        if normalized_source_url:
            set_data_source_url(None)   # reset to default

    output_dir = result.get("output_dir") or ""
    if not output_dir or not os.path.isdir(_long(output_dir)):
        return JSONResponse(status_code=500, content={
            "status": "error",
            "detail": result.get("errors") or "Pipeline produced no output folder.",
        })

    # ── Step 4: package the output into report + dataset zips ─────────────────
    # The two deliverables are cleanly separated — report content vs data
    # model — so they can be published independently (the report connects to
    # the published semantic model live):
    #   report  zip → <Name>.pbip + <Name>.Report ONLY (no semantic model)
    #   dataset zip → <Name>.pbip + <Name>.SemanticModel + <Name>.Report
    #                 (an EMPTY report shell — PBIP requires a report artifact,
    #                  so the dataset is shipped as a full PBIP whose report
    #                  is blank; opening it shows just the data model)
    _step(4, 4, f"Packaging output (mode={output_mode})")
    model_folder  = _find_entry(output_dir, ".SemanticModel")
    report_folder = _find_entry(output_dir, ".Report")
    pbip_file     = _find_entry(output_dir, ".pbip")
    if not model_folder or not report_folder or not pbip_file:
        return JSONResponse(status_code=500, content={
            "status": "error",
            "detail": (f"Expected .pbip + .SemanticModel + .Report in {output_dir}; "
                       f"found pbip={pbip_file!r} model={model_folder!r} "
                       f"report={report_folder!r}."),
        })

    # `<Name>` is the SemanticModel folder name minus the suffix.
    name = model_folder[:-len(".SemanticModel")]

    # ── Single-mode branch ───────────────────────────────────────────────────
    # `output_mode=single` ships ONE download zip that contains the two PBIP
    # folders, EACH as its own nested zip:
    #     <Name>.SemanticModel.zip   (the .SemanticModel folder)
    #     <Name>.Report.zip          (the .Report folder)
    # Extract the download and you have two zips you can hand straight to
    # /validate_pbip/ (one carries the .SemanticModel, the other the .Report)
    # with no manual re-zipping.
    if output_mode == "single":
        _step(4, 4, "Packaging .SemanticModel.zip + .Report.zip")
        sem_zip = _make_zip([(os.path.join(output_dir, model_folder), model_folder)])
        rep_zip = _make_zip([(os.path.join(output_dir, report_folder), report_folder)])
        bundle = io.BytesIO()
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"{model_folder}.zip", sem_zip)   # <Name>.SemanticModel.zip
            zf.writestr(f"{report_folder}.zip", rep_zip)  # <Name>.Report.zip
        bundle.seek(0)
        _ok(f"{model_folder}.zip  ({round(len(sem_zip)/1024, 1)} KB)")
        _ok(f"{report_folder}.zip  ({round(len(rep_zip)/1024, 1)} KB)")
        validation = "ok" if not result.get("errors") else "validation_warnings"
        _banner("[ok] DONE — returning .SemanticModel.zip + .Report.zip")
        return StreamingResponse(
            bundle,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{name}_validate.zip"',
                "X-PBIP-Mode":         "single",
                "X-PBIP-Validation":   validation,
                "X-PBIP-Report-Name":  name,
            },
        )

    # ── Split-mode (default) — the existing two-zip bundle ──────────────────
    # report zip — ONLY the report part: <Name>.pbip + <Name>.Report.
    # The semantic model is deliberately NOT bundled — the report is meant
    # to live-connect to the dataset after it is published to the service.
    report_zip = _make_zip([
        (os.path.join(output_dir, pbip_file),     pbip_file),
        (os.path.join(output_dir, report_folder), report_folder),
    ])

    # dataset zip — the data model (.SemanticModel) + .pbip, plus a freshly-
    # built EMPTY .Report so the .pbip is a valid, openable PBIP.
    with tempfile.TemporaryDirectory() as _tmp:
        empty_report_dir = write_empty_report(_tmp, name, name)
        dataset_zip = _make_zip([
            (os.path.join(output_dir, pbip_file),    pbip_file),
            (os.path.join(output_dir, model_folder), model_folder),
            (empty_report_dir,                       report_folder),
        ])

    # Bundle both zips into one downloadable container.
    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{name}_dataset.zip", dataset_zip)
        zf.writestr(f"{name}_report.zip", report_zip)
    bundle.seek(0)

    _ok(f"{name}_dataset.zip  ({round(len(dataset_zip)/1024, 1)} KB)")
    _ok(f"{name}_report.zip   ({round(len(report_zip)/1024, 1)} KB)")
    validation = "ok" if not result.get("errors") else "validation_warnings"
    _banner("[ok] DONE — returning dataset + report zip bundle")

    return StreamingResponse(
        bundle,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{name}_pbip.zip"',
            "X-PBIP-Validation": validation,
            "X-PBIP-Report-Name": name,
        },
    )


@app.post("/publish_pbip/")
async def publish_pbip_endpoint(
    pbip_zip: UploadFile = File(...,
        description="The zip returned by /generate_pbip/. Accepts either the "
                    "combined <Name>_pbip.zip bundle (which contains the "
                    "nested <Name>_dataset.zip + <Name>_report.zip) or any "
                    "zip that carries <Name>.SemanticModel and <Name>.Report "
                    "folders inside it."),
    workspace: str = Query(...,
        description="Target Microsoft Fabric workspace - its GUID or its "
                    "display name."),
    model_name: str | None = Query(None,
        description="Override the published semantic model's display name "
                    "(default: the <Name> derived from the zip's "
                    ".SemanticModel folder)."),
    report_name: str | None = Query(None,
        description="Override the published report's display name "
                    "(default: the <Name> derived from the zip's .Report "
                    "folder)."),
):
    """Publish a PBIP zip to a Microsoft Fabric workspace in THREE explicit
    steps — the dataset half and the report half stay separate; they are
    NOT stitched into one folder:

      Step 1  Publish the SEMANTIC MODEL from the dataset half  → model_id
      Step 2  Rewrite the report's definition.pbir to bind to model_id
      Step 3  Publish the REPORT from the report half (pre-bound)

    Optional Step 4 (auto-credentials, runs only when the env var
    SHAREPOINT_CONNECTION_ID is set):
      * bind the published dataset's data source to that pre-existing
        shareable cloud connection,
      * trigger a refresh — visuals populate without anyone clicking
        "Take over" in the Fabric UI.

    The connection referenced by SHAREPOINT_CONNECTION_ID must be a
    SHAREABLE cloud connection (created in Fabric Settings → Manage
    connections, not the Personal Cloud Connection the dataset settings
    page creates) and the service principal must have `User` role on it.
    Personal connections refuse refresh with `CredentialsNotSpecified`.
    """
    _banner(f"PUBLISH - upload {pbip_zip.filename!r} -> Fabric workspace {workspace}")

    with tempfile.TemporaryDirectory(prefix="pbippub_") as tmp:
        # ── Setup: receive zip, extract, locate the two folders ──────────────
        _step(0, 4, f"Receiving + extracting {pbip_zip.filename!r}")
        zip_path = os.path.join(tmp, pbip_zip.filename or "bundle.zip")
        with open(zip_path, "wb") as zf:
            zf.write(await pbip_zip.read())
        extract_root = os.path.join(tmp, "extracted")
        os.makedirs(extract_root, exist_ok=True)
        try:
            extract_zip(zip_path, extract_root)
        except zipfile.BadZipFile:
            return JSONResponse(status_code=400, content={
                "status": "error",
                "detail": f"Uploaded file {pbip_zip.filename!r} is not a valid zip.",
            })

        # The /generate_pbip/ bundle ships the dataset half and the report
        # half in separate nested zips. `pick_pbip_folder` returns the richer
        # of duplicates, so we get the REAL .Report (from the report half),
        # not the empty shell that the dataset half carries.
        sem_folder = pick_pbip_folder(extract_root, ".SemanticModel")
        rep_folder = pick_pbip_folder(extract_root, ".Report")
        if not sem_folder or not rep_folder:
            return JSONResponse(status_code=400, content={
                "status": "error",
                "detail": (f"Could not locate both .SemanticModel and .Report "
                           f"inside the uploaded zip. "
                           f".SemanticModel={sem_folder!r}, .Report={rep_folder!r}."),
            })
        model_display = model_name or os.path.basename(sem_folder)[:-len(".SemanticModel")]
        report_display = report_name or os.path.basename(rep_folder)[:-len(".Report")]
        _ok(f".SemanticModel  : {os.path.basename(sem_folder)}")
        _ok(f".Report         : {os.path.basename(rep_folder)}")

        # Authenticate + resolve workspace (shared by all four steps).
        try:
            token = get_access_token()
            workspace_id, workspace_name = _resolve_workspace(
                token, workspace, log=lambda m: print(f"      {m}"))
        except Exception as exc:
            _fail(f"Auth / workspace resolution failed: {exc}")
            return JSONResponse(status_code=502, content={
                "status": "error", "detail": str(exc),
            })
        _ok(f"workspace_id = {workspace_id} ({workspace_name})")

        # ── STEP 1 ── Publish the SEMANTIC MODEL from the dataset half ───────
        _step(1, 4, f"Publishing SEMANTIC MODEL '{model_display}' (dataset half)")
        try:
            model_id = create_semantic_model(
                token, workspace_id, sem_folder, model_display)
        except Exception as exc:
            _fail(f"Semantic model publish failed: {exc}")
            traceback.print_exc()
            return JSONResponse(status_code=502, content={
                "status": "error", "stage": "semantic_model",
                "detail": str(exc),
            })
        _ok(f"semantic_model_id = {model_id}")

        # ── STEP 2 ── Bind the REPORT to that model id (rewrite the pbir) ────
        _step(2, 4, "Connecting REPORT to the published semantic model")
        try:
            patch_pbir_to_connection(
                rep_folder, workspace_name, model_display, model_id)
        except Exception as exc:
            _fail(f"PBIR patch failed: {exc}")
            traceback.print_exc()
            return JSONResponse(status_code=500, content={
                "status": "error", "stage": "patch_pbir", "detail": str(exc),
                "semantic_model_id": model_id,
                "note": ("Semantic model is published, but its report could "
                         "not be bound. Delete the orphan model and retry."),
            })
        _ok(f"definition.pbir → semanticModelId={model_id}")

        # ── STEP 3 ── Publish the REPORT from the report half (pre-bound) ───
        _step(3, 4, f"Publishing REPORT '{report_display}' (report half, pre-bound)")
        try:
            report_id = create_report(
                token, workspace_id, rep_folder, report_display)
        except Exception as exc:
            _fail(f"Report publish failed: {exc}")
            traceback.print_exc()
            return JSONResponse(status_code=502, content={
                "status": "error", "stage": "report", "detail": str(exc),
                "semantic_model_id": model_id,
                "note": (f"Semantic model {model_id} is published; the report "
                         f"failed. Delete the orphan model and retry."),
            })
        _ok(f"report_id = {report_id}")

        # ── STEP 4 (optional) ── Auto-bind the dataset to a cloud connection
        # and trigger a refresh, so visuals populate without the user having
        # to Take-Over the dataset and wire up credentials by hand.
        bind_info: dict = {}
        connection_id = os.environ.get("SHAREPOINT_CONNECTION_ID")
        if connection_id:
            _step(4, 4, f"Auto-bind dataset → connection {connection_id} + refresh")
            try:
                pbi_token = get_powerbi_token()
                bind_dataset_to_connection(
                    pbi_token, workspace_id, model_id, connection_id)
                refresh_request_id = trigger_dataset_refresh(
                    pbi_token, workspace_id, model_id)
                bind_info = {
                    "connection_id":       connection_id,
                    "refresh_triggered":   True,
                    "refresh_request_id":  refresh_request_id,
                }
                _ok(f"bound + refresh triggered (request_id={refresh_request_id!r})")
            except Exception as exc:
                # Non-fatal: the dataset / report ARE published — the user can
                # still bind/refresh manually. Surface the warning in the response.
                _fail(f"auto-bind failed (publish itself succeeded): {exc}")
                bind_info = {
                    "connection_id":     connection_id,
                    "refresh_triggered": False,
                    "warning":           str(exc),
                }
        else:
            bind_info = {
                "connection_id":     None,
                "refresh_triggered": False,
                "note": ("SHAREPOINT_CONNECTION_ID env var is not set; "
                         "skipping auto-bind. Set it to a shareable cloud "
                         "connection's GUID (one the service principal has "
                         "`User` role on) to automate credential binding."),
            }

    report_url = f"{_APP_BASE_URL}/groups/{workspace_id}/reports/{report_id}"
    _banner("[ok] PUBLISHED")
    return {
        "status":         "ok",
        "workspace_id":   workspace_id,
        "workspace_name": workspace_name,
        "model_id":       model_id,
        "model_name":     model_display,
        "report_id":      report_id,
        "report_name":    report_display,
        "report_url":     report_url,
        "binding":        bind_info,
    }


@app.post("/validate_pbip/")
async def validate_pbip(
    json1: UploadFile       = File(..., description="The first extraction JSON "
                                   "(semantic, report, or a full single JSON)."),
    json2: UploadFile | None = File(None, description="Optional second extraction "
                                    "JSON — used for a thin/live-connect pair."),
    dataset_zip: UploadFile | None = File(None, description="The dataset PBIP zip "
                                          "(<Name>_dataset.zip — carries the "
                                          ".SemanticModel folder)."),
    report_zip: UploadFile | None  = File(None, description="The report PBIP zip "
                                          "(<Name>_report.zip — carries the "
                                          ".Report folder)."),
):
    """Validate generated PBIP zip(s) against their extraction JSON(s).

    Accepts 1 or 2 JSONs plus the generated zip(s). Each JSON is routed by
    content:
      * a JSON WITH tables   → semantic validator (scemanticvalidator.py)
                               against the `.SemanticModel` folder;
      * a JSON WITHOUT tables (visuals only) → report validator
                               (reportvalidator.py) against the `.Report` folder.
    A single full JSON carrying both tables and visuals runs both validators.

    You may upload `dataset_zip` + `report_zip` separately, or a single zip
    (even the combined `<Name>_pbip.zip` bundle) in either field — nested zips
    are unpacked and the `.SemanticModel` / `.Report` folders are auto-located.

    Returns results in the `testoutput.json` format (score_breakdown /
    check_summary / all_results / gap_report):
      * ONE input JSON  → a single result object.
      * TWO input JSONs → a JSON array of TWO result objects, one per input
        JSON (the semantic result and the report result, kept separate —
        not merged).
    """
    _banner("PBIP VALIDATOR")

    # ── Step 1: parse the uploaded JSON(s) ────────────────────────────────────
    _step(1, 4, "Reading extraction JSON(s)")
    jsons = []
    for up in (json1, json2):
        if up is None:
            continue
        try:
            raw = await up.read()
            jsons.append(json.loads(raw.decode("utf-8")))
            _ok(f"Parsed {up.filename}")
        except Exception as exc:
            _fail(f"Could not parse {up.filename}: {exc}")
            return JSONResponse(status_code=400, content={
                "status": "error",
                "detail": f"Uploaded file '{up.filename}' is not valid JSON: {exc}",
            })
    if not jsons:
        return JSONResponse(status_code=400, content={
            "status": "error", "detail": "At least one JSON file is required.",
        })

    # ── Step 2 + 3: extract zip(s) and locate the PBIP folders ────────────────
    with tempfile.TemporaryDirectory(prefix="pbipval_") as tmp:
        extract_root = os.path.join(tmp, "extracted")
        os.makedirs(extract_root, exist_ok=True)

        _step(2, 4, "Extracting PBIP zip(s)")
        any_zip = False
        for up in (dataset_zip, report_zip):
            if up is None:
                continue
            any_zip = True
            zip_path = os.path.join(tmp, up.filename or f"upload_{id(up)}.zip")
            with open(zip_path, "wb") as zf:
                zf.write(await up.read())
            try:
                extract_zip(zip_path, extract_root)
                _ok(f"Extracted {up.filename}")
            except zipfile.BadZipFile:
                _fail(f"{up.filename} is not a valid zip")
                return JSONResponse(status_code=400, content={
                    "status": "error",
                    "detail": f"Uploaded file '{up.filename}' is not a valid zip.",
                })
        if not any_zip:
            return JSONResponse(status_code=400, content={
                "status": "error",
                "detail": "At least one zip (dataset_zip and/or report_zip) is required.",
            })

        _step(3, 4, "Locating .SemanticModel / .Report folders")
        semantic_dir = pick_pbip_folder(extract_root, ".SemanticModel")
        report_dir   = pick_pbip_folder(extract_root, ".Report")
        _ok(f".SemanticModel : {os.path.basename(semantic_dir) if semantic_dir else 'not found'}")
        _ok(f".Report        : {os.path.basename(report_dir) if report_dir else 'not found'}")

        # ── Step 4: route to the validators and assemble the result ───────────
        _step(4, 4, "Running validators")
        try:
            result = run_validation(jsons, semantic_dir, report_dir, tmp)
        except ValueError as exc:
            _fail(f"Validation error: {exc}")
            return JSONResponse(status_code=422, content={
                "status": "error", "detail": str(exc),
            })
        except Exception:
            _fail("Validator crashed")
            traceback.print_exc()
            return JSONResponse(status_code=500, content={
                "status": "error", "detail": traceback.format_exc(),
            })

    # 1 input JSON → one result dict; 2 input JSONs → a list of two result
    # dicts, one per input JSON (semantic result + report result, unmerged).
    results = result if isinstance(result, list) else [result]
    for i, r in enumerate(results, start=1):
        _ok(f"result {i}/{len(results)}: score {r['score']} — {r['verdict']}  "
            f"({r['gaps_count']} gap(s))")
    _banner(f"[ok] DONE — returning {len(results)} validation result(s)")
    return JSONResponse(content=result)
