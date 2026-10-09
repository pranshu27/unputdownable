import os
import json
import requests
import markdown

from typing import List
from dotenv import load_dotenv
from atlassian import Jira
from bs4 import BeautifulSoup
from pydantic import BaseModel
from requests.auth import HTTPBasicAuth
from fastapi.responses import JSONResponse
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

app = FastAPI()

origins = [
    "http://localhost.tiangolo.com",
    "https://localhost.tiangolo.com",
    "http://localhost",
    "http://localhost:8080",
    "*",
    "http://mca-243900498.us-east-2.elb.amazonaws.com",
    "http://copilot-882210223.us-east-2.elb.amazonaws.com"
]

class REChatInput(BaseModel):
    re_responses: List[dict]  # 1 item for Tableau, 2 items for Power BI (semantic + report)
    board_id: str

class REInputData(BaseModel):
    re_responses: List[dict]  # 1 item for Tableau, 2 items for Power BI (semantic + report)
    jira_story_id: str
    file_name: str  # base name of the parent file (used for attachment naming)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SAVE_FOLDER = 'output_files'
os.makedirs(SAVE_FOLDER, exist_ok=True)

# ---------------------------------------------------------------------------
# Helper – extract the RE result block from the incoming payload.
# Supports both:
#   - New format: { "report_id": ..., "result": { ...RE content... } }
#   - Old format: { "name": ..., "model_id": ..., ...RE content directly... }
# ---------------------------------------------------------------------------

def extract_re_result(re_response: dict) -> dict:
    if "result" in re_response and isinstance(re_response["result"], dict):
        return re_response["result"]
    return re_response


# ---------------------------------------------------------------------------
# Helper – detect file type label (semantic/report/tableau)
# ---------------------------------------------------------------------------

def _detect_file_label(re: dict, wrapper: dict) -> str:
    """
    Determines a label for the RE response based on file name or tool type.
    Returns 'dataset', 'report', or 'tableau'.
    """
    file_name = (wrapper.get("file_name") or re.get("name") or "").lower()
    tool_type = (wrapper.get("tool_type") or "").lower()

    if "dataset" in file_name or "semantic" in file_name:
        return "dataset"
    elif "report" in file_name:
        return "report"
    elif "tableau" in tool_type or file_name.endswith(".twbx") or file_name.endswith(".twb"):
        return "tableau"
    # Default: use tool_type if available, otherwise generic
    if tool_type:
        return tool_type
    return "analysis"


# ---------------------------------------------------------------------------
# Helpers – text conversion
# ---------------------------------------------------------------------------

def convert_markdown_to_plain_text(md_content):
    html = markdown.markdown(md_content)
    soup = BeautifulSoup(html, 'html.parser')
    return soup.get_text()


# ---------------------------------------------------------------------------
# Helpers – build JIRA ticket content from RE result
# ---------------------------------------------------------------------------

def _safe(value, fallback="N/A"):
    if value is None:
        return fallback
    s = str(value).strip()
    return s if s else fallback


def build_ticket_summary(re_responses: List[dict]) -> str:
    """
    Builds a ticket summary from the list of RE responses.
    Uses the first response's file name as the base name.
    """
    first_wrapper = re_responses[0]
    first_re = extract_re_result(first_wrapper)

    name = _safe(first_wrapper.get("file_name") or first_re.get("name"), "Unnamed Model")
    # Strip _dataset/_report/_semantic suffix to get the parent file name
    base_name = name
    for suffix in ["_dataset", "_report", "_semantic"]:
        if base_name.lower().endswith(suffix):
            base_name = base_name[: -len(suffix)]
            break

    extracted_at = _safe(first_re.get("extracted_at"), "")
    date_part = extracted_at[:10] if extracted_at != "N/A" else ""
    date_suffix = f" - {date_part}" if date_part else ""

    if len(re_responses) > 1:
        return f"RE Analysis: {base_name} (Power BI){date_suffix}"
    return f"RE Analysis: {base_name}{date_suffix}"


def build_single_description(re: dict, wrapper: dict, label: str) -> str:
    """
    Builds a structured plain-text JIRA description for a single RE result.
    Sections: Job Info | Model Metadata | Data Sources | Tables |
              Relationships | Calculations/KPIs | Visualizations |
              AI Summary | Technical Summary excerpt
    """
    lines = []

    # ── Job Info (from wrapper) ───────────────────────────────────────────────
    if wrapper.get("report_id"):
        lines.append("*JOB INFO*")
        lines.append(f"Report ID      : {_safe(wrapper.get('report_id'))}")
        lines.append(f"File Name      : {_safe(wrapper.get('file_name'))}")
        lines.append(f"Tool Type      : {_safe(wrapper.get('tool_type'))}")
        lines.append(f"Status         : {_safe(wrapper.get('status'))}")
        lines.append(f"Completed At   : {_safe(wrapper.get('completed_at'))}")
        lines.append(f"Runtime (s)    : {_safe(wrapper.get('runtime_seconds'))}")
        lines.append("")

    # ── Model Metadata ───────────────────────────────────────────────────────
    lines.append("*MODEL METADATA*")
    lines.append(f"Name           : {_safe(re.get('name'))}")
    lines.append(f"Model ID       : {_safe(re.get('model_id'))}")
    lines.append(f"Schema Version : {_safe(re.get('schema_version'))}")
    lines.append(f"Extracted At   : {_safe(re.get('extracted_at'))}")
    lines.append("")

    # ── Data Sources ─────────────────────────────────────────────────────────
    data_sources = re.get("data_sources", [])
    lines.append(f"*DATA SOURCES ({len(data_sources)})*")
    for ds in data_sources:
        lines.append(
            f"  - {_safe(ds.get('name'))} | type: {_safe(ds.get('source_type'))} "
            f"| mode: {_safe(ds.get('connection_mode'))} | path: {_safe(ds.get('path'))}"
        )
    lines.append("")

    # ── Tables ───────────────────────────────────────────────────────────────
    tables = re.get("tables", [])
    lines.append(f"*TABLES ({len(tables)})*")
    for tbl in tables:
        col_count = len(tbl.get("columns", []))
        lines.append(
            f"  - {_safe(tbl.get('name'))} | type: {_safe(tbl.get('table_type'))} "
            f"| columns: {col_count} | materialized: {tbl.get('is_materialized', False)}"
        )
        desc = _safe(tbl.get("description"), "")
        if desc and desc != "N/A":
            lines.append(f"    {desc}")
    lines.append("")

    # ── Relationships ─────────────────────────────────────────────────────────
    relationships = re.get("relationships", [])
    lines.append(f"*RELATIONSHIPS ({len(relationships)})*")
    for rel in relationships:
        lines.append(
            f"  - {_safe(rel.get('left_table_id'))}.{_safe(rel.get('left_column'))} "
            f"-> {_safe(rel.get('right_table_id'))}.{_safe(rel.get('right_column'))} "
            f"| {_safe(rel.get('join_type'))} join | cardinality: {_safe(rel.get('cardinality'))} "
            f"| type: {_safe(rel.get('relationship_type'))}"
        )
    lines.append("")

    # ── Calculations / KPIs ───────────────────────────────────────────────────
    calculations = re.get("calculations", [])
    lines.append(f"*CALCULATIONS / KPIs ({len(calculations)})*")
    for calc in calculations:
        lines.append(f"  - {_safe(calc.get('name'))} | semantic type: {_safe(calc.get('semantic_type'))}")
        expr = (calc.get("expressions") or {}).get("tableau") or calc.get("formula", "")
        if expr:
            lines.append(f"    Formula   : {expr}")
        dep_cols = calc.get("depends_on_columns") or []
        if dep_cols:
            lines.append(f"    Depends on: {', '.join(dep_cols)}")
    lines.append("")

    # ── Visualizations ────────────────────────────────────────────────────────
    viz = re.get("visualizations", {})
    pages = viz.get("pages", [])
    total_visuals = sum(len(p.get("visuals", [])) for p in pages)
    lines.append(f"*VISUALIZATIONS ({len(pages)} pages, {total_visuals} visuals)*")
    for page in pages:
        lines.append(f"  Page: {_safe(page.get('display_name'))}")
        for v in page.get("visuals", []):
            title = _safe(v.get("title"), "(untitled)")
            vtype = _safe(v.get("visual_type"), "unknown")
            lines.append(f"    - {title} ({vtype})")
    lines.append("")

    # ── AI Summary ───────────────────────────────────────────────────────────
    ai_summary = _safe(re.get("ai_summary"), "")
    if ai_summary and ai_summary != "N/A":
        lines.append("*AI SUMMARY*")
        lines.append(ai_summary[:1000])
        lines.append("")

    # ── Technical Summary excerpt ─────────────────────────────────────────────
    tech_summary = _safe(re.get("technical_summary"), "")
    if tech_summary and tech_summary != "N/A":
        plain = convert_markdown_to_plain_text(tech_summary)
        excerpt = plain[:1500]
        if len(plain) > 1500:
            excerpt += "\n... (see attached RE JSON for full content)"
        lines.append("*TECHNICAL SUMMARY (EXCERPT)*")
        lines.append(excerpt)
        lines.append("")

    lines.append(f"Attachment: {label}_re_response.json (full RE output)")

    return "\n".join(lines)


def build_combined_description(re_responses: List[dict]) -> str:
    """
    Builds a combined JIRA description from multiple RE responses.
    For a single response (Tableau), returns a single description.
    For multiple responses (Power BI), returns labeled sections.
    """
    if len(re_responses) == 1:
        wrapper = re_responses[0]
        re = extract_re_result(wrapper)
        label = _detect_file_label(re, wrapper)
        return build_single_description(re, wrapper, label)

    # Multiple responses – build separated sections
    sections = []
    for wrapper in re_responses:
        re = extract_re_result(wrapper)
        label = _detect_file_label(re, wrapper)
        section_header = f"{'=' * 60}\n  {label.upper()} FILE\n{'=' * 60}"
        section_body = build_single_description(re, wrapper, label)
        sections.append(f"{section_header}\n\n{section_body}")

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Helpers – save attachments and upload to JIRA
# ---------------------------------------------------------------------------

def save_all_files(re_responses: List[dict], base_file_name: str) -> List[str]:
    """
    Saves each RE response as a separate JSON attachment.
    Returns the list of saved file paths.
    """
    saved_paths = []
    try:
        for wrapper in re_responses:
            re = extract_re_result(wrapper)
            label = _detect_file_label(re, wrapper)
            attachment_name = f"{base_file_name}_{label}_re_response.json"
            attachment_path = os.path.join(SAVE_FOLDER, attachment_name)
            with open(attachment_path, 'w', encoding='utf-8') as f:
                json.dump(wrapper, f, indent=2, ensure_ascii=False)
            saved_paths.append(attachment_path)
            print(f"File saved: {attachment_path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving files: {str(e)}")
    return saved_paths


def upload_all_to_jira(jira_story: str, file_paths: List[str]):
    """Uploads all saved attachment files to the JIRA ticket."""
    try:
        jira = _get_jira_client()
        for file_path in file_paths:
            jira.add_attachment(jira_story, file_path)
            print(f"{file_path} uploaded to JIRA story {jira_story}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error uploading to JIRA: {str(e)}")


def update_jira_issue_description(issue_key: str, description: str) -> str:
    jira = _get_jira_client()
    issue = jira.issue(issue_key)
    current_description = issue['fields'].get('description', '') or ''
    updated_description = current_description + "\n\n" + description
    update_fields = {'description': updated_description}
    jira.update_issue_field(issue_key, update_fields)
    return "Updated the description successfully"


def create_jira_ticket(project_key: str, summary: str, description: str) -> str:
    jira = _get_jira_client()
    fields = {
        "project": {"key": project_key},
        "summary": summary,
        "description": description,
        "issuetype": {"name": "Story"},
    }
    result = jira.issue_create_or_update(fields)
    issue_key = result.get("key")
    if not issue_key:
        raise ValueError(f"JIRA ticket creation failed or returned no key. Response: {result}")
    return issue_key


def _get_jira_client() -> Jira:
    return Jira(
        url=os.getenv("JIRA_BASE_URL"),
        username=os.getenv("JIRA_USERNAME"),
        password=os.getenv("JIRA_PASSWORD"),
        cloud=True
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    return JSONResponse(status_code=200, content={"status": "healthy"})


@app.post("/JIRA/")
async def submit_string(username: str, password: str, base_url: str):
    """
    Authenticate with JIRA and return available boards.
    """
    msg = ""
    try:
        url = f'{base_url}/rest/api/2/myself'
        response = requests.get(url, auth=HTTPBasicAuth(username, password))
        if response.status_code == 200:
            msg = "Authentication successful"
            boards_url = f"{base_url}/rest/agile/1.0/board"
            boards_response = requests.get(boards_url, auth=HTTPBasicAuth(username, password))
            if boards_response.status_code == 200:
                boards = []
                boards_data = boards_response.json().get("values", [])
                for board_data in boards_data:
                    boards.append(board_data["location"]["displayName"])
                return {"message": msg, "boards": boards}
            else:
                return {"message": msg, "boards_error": "Failed to fetch boards"}
        else:
            raise HTTPException(status_code=401, detail="Invalid Credentials")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat")
async def chat(data: REChatInput):
    """
    Step 1 – Ticket Creation.
    Accepts a list of RE responses (1 for Tableau, 2 for Power BI),
    builds a structured JIRA description, creates a single ticket,
    and returns the issue key.
    """
    try:
        if not data.re_responses:
            raise ValueError("re_responses list cannot be empty")

        summary     = build_ticket_summary(data.re_responses)
        description = build_combined_description(data.re_responses)

        issue_key = create_jira_ticket(
            project_key=data.board_id,
            summary=summary,
            description=description,
        )

        attachment_count = len(data.re_responses)
        return (
            f"The JIRA ticket has been successfully created with the key: **{issue_key}** "
            f"({attachment_count} file{'s' if attachment_count > 1 else ''} will be attached)"
        )

    except Exception as error:
        return f"Error while creating the JIRA ticket: {error}"


@app.post("/upload-to-jira/")
async def handle_request(data: REInputData):
    """
    Step 2 – File Upload & Description Update.
    Saves all RE responses as separate JSON attachments,
    uploads them to the existing JIRA ticket, and appends the combined description.
    """
    try:
        if not data.re_responses:
            raise ValueError("re_responses list cannot be empty")

        description = build_combined_description(data.re_responses)

        # Save all RE responses as separate JSON attachments
        saved_paths = save_all_files(data.re_responses, data.file_name)

        # Upload all files to JIRA
        upload_all_to_jira(data.jira_story_id, saved_paths)

        # Append combined structured description to the ticket
        update_jira_issue_description(data.jira_story_id, description)

        return {
            "status": "success",
            "message": f"{len(saved_paths)} file(s) uploaded to JIRA successfully",
            "attachments": [os.path.basename(p) for p in saved_paths]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
