import type {
  JiraAuthResponse,
  JiraCredentials,
  JiraBoard,
  TicketCreationPayload,
  CodeGenerationPayload,
  CodeGenerationResponse,
  GitHubCommitPayload,
  GitHubCommitResponse,
  TargetPlatform,
} from "@/types/api";
import { TicketUploadExtras } from "../types/api";

const API_BASE = "https://xcompanion.dataeconomy.ai";
const DBT_API_BASE = "https://dbt-genai.apps.cfgclusternew.pg7v.p1.openshiftapps.com";

// Parse board string like "GEN AI (GA)" into { id: "GA", name: "GEN AI", key: "GA" }
function parseBoardString(boardStr: string): JiraBoard {
  const match = boardStr.match(/^(.+?)\s*\(([^)]+)\)$/);
  if (match) {
    return {
      id: match[2],
      name: match[1].trim(),
      key: match[2],
    };
  }
  return {
    id: boardStr,
    name: boardStr,
    key: boardStr,
  };
}

// JIRA Authentication
export async function authenticateJira(
  credentials: JiraCredentials
): Promise<{ success: boolean; boards: JiraBoard[]; error?: string }> {
  try {

    const params = new URLSearchParams({
      username: credentials.username,
      password: credentials.apiToken,
      base_url: credentials.baseUrl,
    });

    const response = await fetch(
      `http://20.72.80.42:8003/JIRA/?${params.toString()}`,
      {
        method: "POST",
        headers: {
          accept: "application/json",
        },
      }
    );

    if (!response.ok) {
      throw new Error(`Authentication failed: ${response.statusText}`);
    }

    const data: JiraAuthResponse = await response.json();

    if (data.message === "Authentication successful" && data.boards) {

      const boards = data.boards.map(parseBoardString);

      // ✅ STORE JIRA CREDENTIALS
      localStorage.setItem(
        "jira_credentials",
        JSON.stringify({
          username: credentials.username,
          apiToken: credentials.apiToken,
          baseUrl: credentials.baseUrl,
        })
      );

      // ✅ STORE BOARDS
      localStorage.setItem(
        "jira_boards",
        JSON.stringify(boards)
      );

      return { success: true, boards };
    }

    return { success: false, boards: [], error: data.message };

  } catch (error) {

    console.error("JIRA auth error:", error);

    return {
      success: false,
      boards: [],
      error: error instanceof Error ? error.message : "Authentication failed",
    };

  }
}

// Create JIRA Ticket
export async function createJiraTicket(
  payload: TicketCreationPayload,
  extras: TicketUploadExtras
): Promise<{ success: boolean; ticketKey?: string; error?: string }> {
  try {
    // ── API 1: /chat — create the Jira ticket ─────────────────────────
    const response1 = await fetch(`http://20.72.80.42:8003/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!response1.ok) {
      throw new Error(`Ticket creation failed: ${response1.statusText}`);
    }

    const text = await response1.text();

    // Handles both:
    // "The Epic has been successfully created with the Epic key ID: GA-26773"
    // "...with the Epic key ID: **GA-26773**"
    const keyMatch =
      text.match(/key\s*(?:ID)?[:\s]+\*{0,2}([A-Z]+-\d+)\*{0,2}/i) ??
      text.match(/\b([A-Z]+-\d+)\b/);                                  // ← fallback

    const ticketKey = keyMatch?.[1];

    if (!ticketKey) {
      throw new Error('Could not extract ticket key from response');
    }

    // ── API 2: /upload-to-jira — upload analysis ──────────────────────
    const uploadPayload = {
      "re_responses":     payload.re_responses,
      jira_story_id:      ticketKey,
      file_name:          extras.file_name,
      etltool:            extras.etltool,
    };

    const response2 = await fetch(
      `http://20.72.80.42:8003/upload-to-jira/`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(uploadPayload),
      }
    );

    if (!response2.ok) {
      throw new Error(`Upload to Jira failed: ${response2.statusText}`);
    }

    return { success: true, ticketKey };

  } catch (error) {
    console.error('Ticket creation error:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Failed to create ticket',
    };
  }
}

// Get Code Generation Endpoint based on platform
function getCodeGenEndpoint(platform: TargetPlatform): { url: string; method: string; contentType: string } {
  switch (platform) {
    case "pyspark":
      return { url: `${API_BASE}:8006/generate_code/`, method: "POST", contentType: "application/json" };
    case "pyspark-databricks":
      return { url: `${DBT_API_BASE}/api/v1/generate_pyspark_codegen/`, method: "POST", contentType: "application/json" };
    case "bigquery":
      return { url: `${API_BASE}:97/generate_bigquery/`, method: "POST", contentType: "application/json" };
    case "dbt":
      return { url: `${DBT_API_BASE}/api/v1/generate_dbt_codegen/`, method: "POST", contentType: "application/x-www-form-urlencoded" };
    case "dataiku":
      return { url: `${API_BASE}:97/generate_code/`, method: "POST", contentType: "application/json" };
    case "powerbi":
      return { url: `${API_BASE}:97/generate_code/`, method: "POST", contentType: "application/json" };
    default:
      return { url: `${API_BASE}:97/generate_code/`, method: "POST", contentType: "application/json" };
  }
}

export async function generateCode(payload: CodeGenerationPayload) {
  try {
    const { technology, etlTool } = payload;

    let response: Response;
    let result: any;
    let combinedCode: string = '';

    // ── 1. PySpark / Databricks + IICS ────────────────────────────────
    if (
      (technology === 'pyspark-datbricks' || technology === 'pyspark') &&
      etlTool === 'iics'
    ) {
      response = await fetch(
        'https://xcompanion.dataeconomy.ai:8006/generate_code/',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: new URLSearchParams({
            jira_base_url:  payload.base_url,
            jira_email:     payload.email,
            jira_api_token: payload.api_token,
            jira_issue_id:  payload.issue_id,
          }).toString(),
        }
      );

      result      = await response.json();
      combinedCode = result?.combined_final_code ?? '';

    // ── 2. PySpark / Databricks + Talend ──────────────────────────────
    } else if (
      (technology === 'pyspark-datbricks' || technology === 'pyspark') &&
      etlTool === 'talend'
    ) {
      response = await fetch(
        `https://xcompanion.dataeconomy.ai:8005/generate_code/?base_url=${payload.base_url}&email=${payload.email}&api_token=${payload.api_token}&issue_id=${payload.issue_id}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: '',
        }
      );

      result       = await response.json();
      combinedCode = result?.combined_final_code ?? '';

    // ── 3.datastage ─────────────────────────────────────────────────
    }  else  if (
      (technology === 'pyspark-datbricks' || technology === 'pyspark') &&
      etlTool === 'datastage'
    ) {
      response = await fetch(
        'https://xcompanion.dataeconomy.ai:8006/generate_code/',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: new URLSearchParams({
            jira_base_url:  payload.base_url,
            jira_email:     payload.email,
            jira_api_token: payload.api_token,
            jira_issue_id:  payload.issue_id,
          }).toString(),
        }
      );

      result      = await response.json();
      combinedCode = result?.generated_code ?? '';

    // ── 2. PySpark / Databricks + Talend ──────────────────────────────
    } else if (technology === 'dbt' && etlTool === 'iics') {
      const formBody = new URLSearchParams({
        rally_workspace: 'string',
        issue_id:        payload.issue_id,
        base_url:        payload.base_url,
        rally_project:   'string',
        feature_id:      'string',
        rally_api_key:   'string',
        rally_username:  'string',
        api_token:       payload.api_token,
        rally_server:    'string',
        email:           payload.email,
        source_type:     'jira',
      });

      response = await fetch(
        'https://dbt-genai.apps.cfgclusternew.pg7v.p1.openshiftapps.com/api/v1/generate_dbt_codegen/',
        {
          method: 'POST',
          headers: {
            accept: 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded',
          },
          body: formBody.toString(),
        }
      );

      result       = await response.json();
      combinedCode = typeof result === 'string'
        ? result
        : JSON.stringify(result, null, 2);

    // ── 4. BigQuery ───────────────────────────────────────────────────
    } else if (technology === 'snowflake' && etlTool === 'talend') {

      const formBody = new URLSearchParams({
        feature_id: payload.issue_id,
        jira_base_url: payload.base_url,
        jira_email: payload.email,
        jira_api_token: payload.api_token,
      });
    
      response = await fetch(
        'https://xcompanion.dataeconomy.ai:3007/api/v1/generate_snowflake_sql/',
        {
          method: 'POST',
          headers: {
            accept: 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded',
          },
          body: formBody.toString(),
        }
      );
    
      result = await response.json();
    
      combinedCode =result?.generated_sql ?? '';
    }else if (technology === 'bigquery') {
      response = await fetch(
        `https://genai-dev.dataeconomy.ai:97/generate_bigquery/?base_url=${payload.base_url}&email=${payload.email}&api_token=${payload.api_token}&issue_id=${payload.issue_id}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: '',
        }
      );

      if (!response.ok) {
        throw new Error(`BigQuery API failed with status ${response.status}`);
      }

      result       = await response.json();
      combinedCode = `\`\`\`sql
      ${result.code}
      \`\`\``;
    // ── 5. Python ─────────────────────────────────────────────────────
    } else if (technology === 'python') {
      response = await fetch(
        `https://xcompanion.dataeconomy.ai:8003/generate_code/?base_url=${payload.base_url}&email=${payload.email}&api_token=${payload.api_token}&issue_id=${payload.issue_id}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: '',
        }
      );

      result       = await response.json();
      combinedCode = JSON.stringify(result, null, 2);

    // ── 6. Xpier ──────────────────────────────────────────────────────
    } else if (technology === 'xpier') {
      response = await fetch('https://genai.dataeconomy.io:93/upsert/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '',
      });

      result       = await response.json();
      combinedCode = result?.combined_final_code
        ? JSON.stringify(result, null, 2)
        : '';

    // ── 7. Default (PySpark / everything else) ────────────────────────
    } else {
      response = await fetch(
        `https://genai-dev.dataeconomy.ai:97/generate_code/?base_url=${payload.base_url}&email=${payload.email}&api_token=${payload.api_token}&issue_id=${payload.issue_id}&type=pyspark`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        }
      );

      result       = await response.json();
      combinedCode = typeof result === 'string'
        ? result
        : JSON.stringify(result, null, 2);
    }

    // ── Common response check ─────────────────────────────────────────
    if (!response.ok) {
      const err = await response.text().catch(() => '');
      throw new Error(err || `Request failed: ${response.statusText}`);
    }

    if (!combinedCode) {
      throw new Error('No generated code found in API response');
    }

    // Patch combined_final_code onto result if not already present
    const patchedData = result?.combined_final_code
      ? result
      : { ...result, combined_final_code: combinedCode };

    return {
      success:  true,
      data:     patchedData,
      language: getLanguageForPlatform(technology),
    };

  } catch (error) {
    console.error('Code generation error:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : 'API failed',
    };
  }
}


function getLanguageForPlatform(platform: TargetPlatform): string {
  switch (platform) {
    case "bigquery":
    case "dbt":
      return "sql";
    case "pyspark":
    case "pyspark-databricks":
    case "dataiku":
      return "python";
    case "powerbi":
      return "dax";
    default:
      return "python";
  }
}

// Commit to GitHub
export async function commitToGitHub(
  payload: GitHubCommitPayload & { technology?: string }
): Promise<GitHubCommitResponse> {
  try {
    let response: Response;

    /* ── 1. DBT FLOW ───────────────────────────────────── */
    if (payload.technology === 'dbt') {
      const formBody = new URLSearchParams({
        github_token: payload.token,
        rally_id: payload.folder_name,
        git_url: payload.repo_url,
        branch_name: payload.branch_name,
        commit_message: payload.commit_message || 'Added dbt project',
      });

      response = await fetch(
        'https://dbt-genai.apps.cfgclusternew.pg7v.p1.openshiftapps.com/api/v1/push_dbt_project/',
        {
          method: 'POST',
          headers: {
            accept: 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded',
          },
          body: formBody.toString(),
        }
      );

    /* ── 2. DEFAULT FLOW (existing) ───────────────────── */
    } else {
      response = await fetch(
        'https://dbt-genai.apps.cfgclusternew.pg7v.p1.openshiftapps.com/api/v1/update-repo/',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            repo_url: payload.repo_url,
            branch_name: payload.branch_name,
            folder_name: payload.folder_name,
            file_name: payload.file_name,
            code: payload.code,
            token: payload.token,
          }),
        }
      );
    }

    /* ── COMMON RESPONSE HANDLING ───────────────────── */
    if (!response.ok) {
      const errText = await response.text().catch(() => '');
      throw new Error(errText || `GitHub commit failed: ${response.statusText}`);
    }

    const data = await response.json();
    console.log("GitHub commit response data:", data);
    return {
      success: true,
      commit_url: data.commit_url || data.url || data.repository_url || '',
      branch: data.branch || '',
      jiraFolder: data.jira_folder || '',
      message: data.message || 'Successfully committed to GitHub',
    };

  } catch (error) {
    console.error("GitHub commit error:", error);

    return {
      success: false,
      message:
        error instanceof Error
          ? error.message
          : "Failed to commit to GitHub",
    };
  }
}
// Generate Test Cases (PySpark ONLY)
const TEST_CASES_API = "https://xcompanion.dataeconomy.ai:3004/api/pyspark/";

export async function generateTestCases(payload: {
  jira_issue_id: string;
  code: string;
}): Promise<{ success: boolean; code?: string; error?: string }> {
  try {
    // Base64 encode the code
    const base64Code = btoa(unescape(encodeURIComponent(payload.code)));
    
    const response = await fetch(TEST_CASES_API, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        jira_issue_id: payload.jira_issue_id,
        code: base64Code,
      }),
    });

    if (!response.ok) {
      throw new Error(`Test case generation failed: ${response.statusText}`);
    }

    const data = await response.json();
    
    return {
      success: true,
      code: data || "",
    };
  } catch (error) {
    console.error("Test case generation error:", error);
    return {
      success: false,
      error: error instanceof Error ? error.message : "Failed to generate test cases",
    };
  }
}

// File extension helper
export function getFileExtension(platform: TargetPlatform): string {
  switch (platform) {
    case "bigquery":
    case "dbt":
      return ".sql";
    case "pyspark":
    case "pyspark-databricks":
    case "dataiku":
      return ".py";
    case "powerbi":
      return ".dax";
    default:
      return ".py";
  }
}