import { Button } from "../CodeGenComponents/button.tsx";
import { Input } from "../CodeGenComponents/input.tsx";
import { StepProgress, StepStatus } from "../CodeGenComponents/StepProgress.tsx";
import { AlertCircle, ArrowRight, Code2 } from "lucide-react";

interface PrimaryPanelProps {
  issueKey: string;
  onIssueKeyChange: (key: string) => void;
  onGenerateCode: () => void;
  isAuthenticated: boolean;
  hasTicket: boolean;
  hasPlatform: boolean;
  selectedPlatform?: string | null;
  isGenerating: boolean;
  onAuthRequired: () => void;
  sourceUrl: string;
  onSourceUrlChange: (value: string) => void;
  outputMode: "split" | "single";
  onOutputModeChange: (value: "split" | "single") => void;
}

export function PrimaryPanel({
  issueKey,
  onIssueKeyChange,
  onGenerateCode,
  isAuthenticated,
  hasTicket,
  hasPlatform,
  selectedPlatform,
  isGenerating,
  onAuthRequired,
  sourceUrl,
  onSourceUrlChange,
  outputMode,
  onOutputModeChange,
}: PrimaryPanelProps) {
  const getSteps = () => {
    const authStatus: StepStatus = isAuthenticated ? "completed" : "active";
    const ticketStatus: StepStatus = !isAuthenticated ? "locked" : hasTicket ? "completed" : "active";
    const codeStatus: StepStatus = !hasTicket ? "locked" : "active";

    return [
      { id: "auth", label: "Authenticate", status: authStatus },
      { id: "ticket", label: "Issue Ready", status: ticketStatus },
      { id: "generate", label: "Generate", status: codeStatus },
    ];
  };

  const canGenerate = isAuthenticated && hasTicket && issueKey.trim() !== "" && hasPlatform;

  const handleGenerateClick = () => {
    if (!isAuthenticated) {
      onAuthRequired();
      return;
    }
    onGenerateCode();
  };

  return (
    <section className="enterprise-card p-6 flex flex-col w-full">
      <div className="mb-6 border-b border-border pb-5 shrink-0">
        <StepProgress steps={getSteps()} />
      </div>

      <div className="flex-1 flex flex-col justify-center space-y-5">
        <div>
          <div className="mb-2 flex items-center justify-between gap-3">
            <label className="text-sm font-semibold">JIRA Issue Key</label>
            <span className="text-xs font-medium text-muted-foreground">Required for generation</span>
          </div>

          <div className="flex flex-col gap-3 md:flex-row">
            <Input
              placeholder="PROJ-1234"
              value={issueKey}
              onChange={(e) => onIssueKeyChange(e.target.value.toUpperCase())}
              className="h-11 font-mono text-base"
            />
            <Button
              onClick={handleGenerateClick}
              disabled={isGenerating || !issueKey.trim()}
              className="h-11 min-w-[170px]"
            >
              {isGenerating ? (
                <>
                  <span className="enterprise-loader" />
                  Generating
                </>
              ) : (
                <>
                  <Code2 className="h-4 w-4" />
                  Generate Code
                </>
              )}
            </Button>
          </div>

          {issueKey.trim() !== "" && (
            <div className="space-y-4 rounded-xl border border-border bg-secondary p-4">
              <div>
                <div className="mb-2 flex items-center justify-between gap-3">
                  <label className="text-sm font-semibold">Source URL</label>
                  <span className="text-xs font-medium text-muted-foreground">Optional</span>
                </div>
                <Input
                  placeholder="https://..."
                  value={sourceUrl}
                  onChange={(e) => onSourceUrlChange(e.target.value)}
                  className="h-11"
                />
                <p className="mt-2 text-xs text-muted-foreground">
                  Cloud folder URL for the generated PBIP to load source CSVs from.
                </p>
              </div>
              <div>
                <div className="mb-2 flex items-center justify-between gap-3">
                  <label className="text-sm font-semibold">Output Mode</label>
                  {/* <span className="text-xs font-medium text-muted-foreground">Default: single</span> */}
                </div>
                <select
                  value={outputMode}
                  onChange={(e) => onOutputModeChange(e.target.value as "split" | "single")}
                  className="flex h-11 w-full rounded-lg border border-border bg-input px-3 py-2 text-base text-foreground transition-colors duration-150 focus-visible:outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/15"
                >
                  <option value="single">single</option>
                  <option value="split">split</option>
                </select>
                <p className="mt-2 text-xs text-muted-foreground">
                  Use "single" for one PBIP-ready zip, or "split" to return separate dataset and report packages.
                </p>
              </div>
            </div>
          )}

          {!isAuthenticated && issueKey && (
            <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
              <AlertCircle className="h-4 w-4" />
              <span>Connect to JIRA to enable code generation.</span>
              <Button variant="link" size="sm" onClick={onAuthRequired} className="h-auto p-0">
                Connect now <ArrowRight className="ml-1 h-3 w-3" />
              </Button>
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold text-muted-foreground">Examples</span>
          {["SPARK-001", "DATA-123", "ETL-456"].map((example) => (
            <button
              key={example}
              onClick={() => onIssueKeyChange(example)}
              className="rounded-lg border border-border bg-secondary px-2.5 py-1 font-mono text-xs font-semibold text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              {example}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
