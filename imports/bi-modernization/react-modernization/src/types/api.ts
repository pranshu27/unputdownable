// JIRA API Types
export interface JiraAuthResponse {
    message: string;
    boards: string[];
  }
  
  export interface JiraCredentials {
    username: string;
    apiToken: string;
    baseUrl: string;
  }
  
  export interface JiraBoard {
    id: string;
    name: string;
    key: string;
  }
  
  // Ticket Creation Types
  export interface TicketCreationPayload {
    // ── API 1: /chat ───────────────────────────────────────────────────
    re_responses: any[],
    board_id: string;
  }

  export interface TicketUploadExtras {
    file_name: string;
    etltool:   string;
  }
  
  // ── Full response shape from createJiraTicket ──────────────────────
  export interface TicketCreationResult {
    success:    boolean;
    ticketKey?: string;
    error?:     string;
  }
  
  export interface TicketCreationResponse {
    message: string;
    ticketKey?: string;
  }
  
  // Target Platform Types
  export type TargetPlatform = 
    | "bigquery"
    | "dataiku"
    | "powerbi"
    | "pyspark"
    | "pyspark-databricks"
    | "dbt"
    | "snowflake";
  
  export interface PlatformOption {
    name: string;
    code: TargetPlatform;
    description: string;
    icon: string;
  }
  
  export const PLATFORM_OPTIONS: PlatformOption[] = [
    // { name: "BigQuery", code: "bigquery", description: "Google BigQuery SQL", icon: "database" },
    // { name: "Dataiku", code: "dataiku", description: "Dataiku DSS", icon: "layers" },
    { name: "PowerBI", code: "powerbi", description: "Microsoft PowerBI", icon: "bar-chart-2" },
  //   { name: "PySpark", code: "pyspark", description: "Apache PySpark", icon: "zap" },
  //   { name: "PySpark (Databricks)", code: "pyspark-databricks", description: "Databricks Runtime", icon: "cpu" },
  //   { name: "DBT", code: "dbt", description: "Data Build Tool", icon: "git-merge" },
  //   { name: "SnowFlake", code: "snowflake", description: "Cloud Data Warehouse", icon: "snowflake" }
  ];
  
  // Code Generation Types
  export interface CodeGenerationPayload {
    base_url: string;
    email: string;
    api_token: string;
    issue_id: string;
    technology: TargetPlatform;
    etlTool:   string;
  }
  
  export interface CodeGenerationResponse {
    code: string;
    language?: string;
    metadata?: Record<string, unknown>;
  }
  
  // GitHub Commit Types
  export interface GitHubCommitPayload {
    repo_url: string;
    token: string;
    branch_name: string;
    folder_name: string;
    file_name: string;
    code: string;
    technology: string;
  }
  
  export interface GitHubCommitResponse {
    success: boolean;
    commit_url?: string;
    message?: string;
  }
  
  // Workflow State Types
  export type WorkflowStep = 
    | "auth"
    | "board"
    | "ticket"
    | "platform"
    | "generate"
    | "commit";
  
  export interface WorkflowState {
    currentStep: WorkflowStep;
    isAuthenticated: boolean;
    selectedBoard: JiraBoard | null;
    ticketKey: string | null;
    selectedPlatform: TargetPlatform | null;
    generatedCode: string | null;
    isCommitted: boolean;
  }
  