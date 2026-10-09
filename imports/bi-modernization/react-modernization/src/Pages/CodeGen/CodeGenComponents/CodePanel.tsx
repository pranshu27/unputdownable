import { useRef, useState } from "react";
import type React from "react";
import { Button } from "../../CodeGen/CodeGenComponents/button.tsx";
import {
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  Download,
  FileCode,
  GitBranch,
  LayoutDashboard,
  Maximize2,
  Minimize2,
  TestTube,
} from "lucide-react";
import { cn } from "../../../Lib/utils.ts";
import type { TargetPlatform } from "../../../types/api.ts";
import ETLDashboard from "../../CodeGen/CodeGenComponents/ETLDashboard.tsx";

type ViewMode = "code" | "dashboard" | "testcases";

interface CodePanelProps {
  code: string | null;
  isGenerating: boolean;
  onCopy: () => void;
  onDownload: () => void;
  onCommit: () => void;
  commitDisabled?: boolean;
  language?: string;
  platform?: TargetPlatform | null;
  apiResponse?: any;
  testCasesCode?: string | null;
  onGenerateTestCases?: () => void;
  isGeneratingTestCases?: boolean;
  hasTestCases?: boolean;
}

function highlightCode(code: string, language: string): React.ReactNode[] {
  const lines = code.split("\n");
  const keywords = language === "sql"
    ? ["SELECT", "FROM", "WHERE", "JOIN", "LEFT", "RIGHT", "ON", "AND", "OR", "GROUP", "BY", "ORDER", "CASE", "WHEN", "THEN", "ELSE", "END", "CREATE", "TABLE", "VIEW"]
    : ["from", "import", "def", "class", "return", "if", "else", "elif", "for", "in", "while", "try", "except", "with", "as", "None", "True", "False"];

  return lines.map((line, lineIndex) => {
    if (line.trim().startsWith("#") || line.trim().startsWith("--")) {
      return <span key={lineIndex} className="syntax-comment">{line}</span>;
    }

    const tokens = line.split(/(\s+|[().,\[\]:=<>!+\-*\/])/);
    return (
      <span key={lineIndex}>
        {tokens.map((token, i) => {
          const upperToken = token.toUpperCase();
          if (keywords.includes(token) || keywords.includes(upperToken)) {
            return <span key={i} className="syntax-keyword">{token}</span>;
          }
          if (/^".*"$/.test(token) || /^'.*'$/.test(token) || /^`.*`$/.test(token)) {
            return <span key={i} className="syntax-string">{token}</span>;
          }
          if (/^\d+\.?\d*$/.test(token)) {
            return <span key={i} className="syntax-number">{token}</span>;
          }
          if (/^[A-Z_][A-Z0-9_]*$/.test(token) && token.length > 1) {
            return <span key={i} className="syntax-constant">{token}</span>;
          }
          return <span key={i}>{token}</span>;
        })}
      </span>
    );
  });
}

function getLanguageLabel(platform: TargetPlatform | null | undefined): string {
  switch (platform) {
    case "bigquery":
      return "BigQuery SQL";
    case "dbt":
      return "DBT SQL";
    case "powerbi":
      return "DAX";
    case "pyspark":
      return "PySpark";
    case "pyspark-databricks":
      return "Databricks PySpark";
    case "dataiku":
      return "Dataiku Python";
    case "snowflake":
      return "Snowflake SQL";
    default:
      return "Code";
  }
}

function CodeViewer({
  code,
  language,
  codeRef,
  isFullscreen,
}: {
  code: string;
  language: string;
  codeRef: React.RefObject<HTMLPreElement>;
  isFullscreen: boolean;
}) {
  const lines = code.split("\n");
  return (
    <div className={cn("code-block enterprise-scroll overflow-auto", isFullscreen ? "max-h-[calc(100vh-12rem)]" : "max-h-[calc(100vh-28rem)] min-h-[320px]")}>
      <div className="flex">
        <div className="flex-shrink-0 select-none border-r border-slate-700 bg-slate-900 py-4 pl-4 pr-3 text-right">
          {lines.map((_, i) => (
            <div key={i} className="font-mono text-xs leading-6 text-slate-500">
              {i + 1}
            </div>
          ))}
        </div>
        <pre ref={codeRef} className="flex-1 overflow-x-auto px-4 py-4">
          <code className="text-sm leading-6">
            {highlightCode(code, language).map((line, i) => (
              <div key={i} className="hover:bg-white/5">{line}</div>
            ))}
          </code>
        </pre>
      </div>
    </div>
  );
}

export function CodePanel({
  code,
  isGenerating,
  onCopy,
  onDownload,
  onCommit,
  commitDisabled,
  language = "python",
  platform,
  apiResponse,
  testCasesCode,
  onGenerateTestCases,
  isGeneratingTestCases,
  hasTestCases,
}: CodePanelProps) {
  const [copied, setCopied] = useState(false);
  const [isExpanded, setIsExpanded] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>("code");
  const codeRef = useRef<HTMLPreElement>(null);

  const hasDashboardData = apiResponse && (apiResponse.combined_final_code || apiResponse.depths || apiResponse.reconciliation_report);
  const languageLabel = getLanguageLabel(platform);

  const handleCopy = () => {
    onCopy();
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  };

  const tabs = [
    { id: "code", label: "Code", icon: FileCode, available: true },
    { id: "dashboard", label: "Dashboard", icon: LayoutDashboard, available: Boolean(hasDashboardData) },
    { id: "testcases", label: "Test Cases", icon: TestTube, available: Boolean(code) },
  ] as const;

  return (
    <section className={cn("enterprise-card overflow-hidden", isFullscreen && "fixed inset-4 z-50")}>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-card px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-bold text-foreground">Generated Output</span>
          {platform && (
            <span className="rounded-lg border border-border bg-secondary px-2.5 py-1 text-xs font-bold text-muted-foreground">
              {languageLabel}
            </span>
          )}
          {code && (
            <span className="rounded-lg border border-primary/25 bg-primary/10 px-2.5 py-1 text-xs font-bold text-primary">
              Ready
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {code && onGenerateTestCases && platform !== "powerbi" && (
            <Button variant="toolbar" size="sm" onClick={onGenerateTestCases} disabled={isGeneratingTestCases}>
              {isGeneratingTestCases ? <span className="enterprise-loader" /> : <TestTube className="h-3.5 w-3.5" />}
              {isGeneratingTestCases ? "Generating" : hasTestCases ? "Regenerate Tests" : "Generate Tests"}
            </Button>
          )}
          <Button variant="toolbar" size="icon-sm" onClick={handleCopy} disabled={!code} title="Copy code">
            {copied ? <Check className="h-4 w-4 text-primary" /> : <Copy className="h-4 w-4" />}
          </Button>
          <Button variant="toolbar" size="icon-sm" onClick={onDownload} disabled={!code} title="Download">
            <Download className="h-4 w-4" />
          </Button>
          <Button variant="toolbar" size="icon-sm" onClick={onCommit} disabled={commitDisabled || !code} title="Commit to GitHub">
            <GitBranch className="h-4 w-4" />
          </Button>
          <Button variant="toolbar" size="icon-sm" onClick={() => setIsFullscreen(!isFullscreen)} title="Fullscreen">
            {isFullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
          </Button>
          <Button variant="toolbar" size="icon-sm" onClick={() => setIsExpanded(!isExpanded)} title="Collapse">
            {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      {isExpanded && (
        <>
          <div className="flex gap-1 border-b border-border bg-secondary px-3 py-2">
            {tabs.filter((tab) => tab.available).map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setViewMode(tab.id)}
                  className={cn(
                    "inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-bold transition-colors",
                    viewMode === tab.id ? "bg-card text-primary" : "text-muted-foreground hover:bg-card hover:text-foreground"
                  )}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {tab.label}
                </button>
              );
            })}
          </div>

          {isGenerating ? (
            <div className="space-y-3 p-6">
              <div className="enterprise-skeleton h-4 w-2/3" />
              <div className="enterprise-skeleton h-4 w-5/6" />
              <div className="enterprise-skeleton h-4 w-1/2" />
            </div>
          ) : viewMode === "dashboard" && hasDashboardData ? (
            <div className="p-3">
              <ETLDashboard data={apiResponse} />
            </div>
          ) : viewMode === "testcases" ? (
            testCasesCode ? (
              <CodeViewer code={testCasesCode} language="python" codeRef={codeRef} isFullscreen={isFullscreen} />
            ) : (
              <div className="p-6 text-sm font-medium text-muted-foreground">Generate test cases to preview them here.</div>
            )
          ) : code ? (
            <CodeViewer code={code} language={language} codeRef={codeRef} isFullscreen={isFullscreen} />
          ) : (
            <div className="p-8 text-center">
              <FileCode className="mx-auto h-10 w-10 text-muted-foreground" />
              <p className="mt-3 text-sm font-semibold text-foreground">No generated code yet</p>
              <p className="mt-1 text-sm text-muted-foreground">Connect JIRA, enter an issue key, select a platform, and generate code.</p>
            </div>
          )}
        </>
      )}
    </section>
  );
}
