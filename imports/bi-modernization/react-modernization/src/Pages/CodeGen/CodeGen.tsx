import { useState, useCallback, useEffect } from "react";
import { toast } from "sonner";
import { PrimaryPanel } from "../CodeGen/CodeGenComponents/PrimaryPanel.tsx";
import { ContextPanel } from "../CodeGen/CodeGenComponents/ContextPanel.tsx";
import { JiraAuthModal } from "../CodeGen/CodeGenComponents/JiraAuthModal.tsx";
import { useNavigate, useOutletContext } from "react-router-dom";
import { Box, Tabs, Tab, Typography } from "@mui/material";
import AssessmentIcon from "@mui/icons-material/Assessment";
import CodeIcon from "@mui/icons-material/Code";
import ScienceIcon from "@mui/icons-material/Science";
import "./CodeGen.css";
import { AnimatePresence, motion } from "framer-motion";
import {
  CheckCircle, Download, FileArchive, ShieldCheck, Loader2,
} from "lucide-react";
import { Construction } from "@mui/icons-material";
import ContentCard from "../../core/CardContent/CardContent.tsx";
import FileWorkspaceHeader from "../../core/FileWorkspaceHeader.tsx";
import { PlatformSelector } from "../CodeGen/CodeGenComponents/PlatformSelector.tsx";
import { GitHubCommitModal } from "../CodeGen/CodeGenComponents/GitHubCommitModal.tsx";
import { WorkflowStatusBar } from "../CodeGen/CodeGenComponents/WorkflowStatusBar.tsx";
import { useWorkflow } from "../../Hooks/useWorkflow.ts";
import ETLDashboard from "../CodeGen/CodeGenComponents/ETLDashboard.tsx";
// Validation is now handled in the Unified Validation Dashboard


interface OutletContextType {
  sideNavWidth: number;
}

const CodeGen = () => {

  const { sideNavWidth } = useOutletContext<OutletContextType>();
  const navigate = useNavigate();

  const {
    state,
    authenticate,
    selectBoard,
    createTicket,
    setIssueKey,
    selectPlatform,
    generate,
    generateTests,
    commit,
    getDefaultFileName,
  } = useWorkflow();

  const [showAuthModal, setShowAuthModal] = useState(false);
  const [showGitHubModal, setShowGitHubModal] = useState(false);
  const [theme] = useState<"light" | "dark">(() =>
    (localStorage.getItem("codegenTheme") as "light" | "dark") || "light"
  );
  const [isPbipGenerating, setIsPbipGenerating] = useState(false);
  const [activeTab, setActiveTab] = useState<"code" | "dashboard" | "testcases">("code");
  const [showPbipError, setShowPbipError] = useState(false);
  const [pbipErrorMessage, setPbipErrorMessage] = useState("");
  const [pbipErrorCode, setPbipErrorCode] = useState<number | string>("");
  const [pbipErrorTimestamp, setPbipErrorTimestamp] = useState("");
  const [showPbipSuccess, setShowPbipSuccess] = useState(false);
  const [generatedPbipFileName, setGeneratedPbipFileName] = useState("");
  const [generatedBlob, setGeneratedBlob] = useState<Blob | null>(null);
  const [sourceUrl, setSourceUrl] = useState("");
  const [outputMode, setOutputMode] = useState<"split" | "single">("single");
  const hasTicket = !!state.ticketKey;
  const hasPlatform = !!state.selectedPlatform;
  const hasCode = !!state.generatedCode;

  const handleAuthenticate = async (username: string, apiToken: string, baseUrl: string) => {
    await authenticate(username, apiToken, baseUrl);
  };

  const handleGenerateCode = async () => {

    // POWER BI FLOW
    if (state.selectedPlatform === "powerbi") {
      let controller: AbortController | null = null;

      try {
        toast.loading("Generating PBIP package...", { id: "pbip-gen" });

        const jiraDetails = JSON.parse(localStorage.getItem("jira_credentials") || "{}");
        const issueKey = state.ticketKey;
        const baseUrl  = jiraDetails.baseUrl;
        const email    = jiraDetails.username;
        const apiToken = jiraDetails.apiToken;

        if (!baseUrl || !email || !apiToken || !issueKey) {
          const msg = "Missing Jira details";
          setPbipErrorMessage(msg);
          setPbipErrorCode("VALIDATION_ERROR");
          setPbipErrorTimestamp(new Date().toLocaleString());
          setShowPbipError(true);
          toast.error(msg, { id: "pbip-gen" });
          return;
        }

        // Reset old state
        setShowPbipError(false);
        setPbipErrorMessage("");
        setPbipErrorCode("");
        setPbipErrorTimestamp("");
        setShowPbipSuccess(false);
        setIsPbipGenerating(true);
        controller = new AbortController();
        const timeoutId = setTimeout(() => controller?.abort(), 300000);

        const params = new URLSearchParams({
          base_url: baseUrl,
          email,
          api_token: apiToken,
          issue_id: issueKey,
          output_mode: outputMode,
        });
        if (sourceUrl.trim()) {
          params.set("source_url", sourceUrl.trim());
        }
        const response = await fetch(
          `http://20.72.80.42:8004/generate_pbip/?${params.toString()}`,
          { method: "POST", headers: { accept: "application/zip" }, signal: controller.signal }
        );
        clearTimeout(timeoutId);

        if (!response.ok) {
          let errorMessage = "PBIP generation failed";
          try {
            const ed = await response.json();
            errorMessage = ed?.detail || ed?.message || ed?.error || JSON.stringify(ed);
          } catch {
            try { const t = await response.text(); if (t) errorMessage = t; } catch { /**/ }
          }
          setPbipErrorMessage(errorMessage);
          setPbipErrorCode(response.status);
          setPbipErrorTimestamp(new Date().toLocaleString());
          setShowPbipError(true);
          toast.error(errorMessage, { id: "pbip-gen" });
          throw new Error(errorMessage);
        }

        const blob = await response.blob();
        if (!blob || blob.size === 0) {
          const emptyErr = "Generated PBIP file is empty.";
          setPbipErrorMessage(emptyErr);
          setPbipErrorCode("EMPTY_FILE");
          setPbipErrorTimestamp(new Date().toLocaleString());
          setShowPbipError(true);
          toast.error(emptyErr, { id: "pbip-gen" });
          return;
        }

        const disposition = response.headers.get("content-disposition");
        let fileName = `${issueKey}_pbip.zip`;
        if (disposition) {
          const match = disposition.match(/filename="?([^"]+)"?/i);
          if (match?.[1]) fileName = match[1];
        }

        setGeneratedPbipFileName(fileName);
        setGeneratedBlob(blob);

        // Auto download
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = downloadUrl;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(downloadUrl);

        // Show success modal with "Proceed to Validation" CTA
        setShowPbipSuccess(true);
        toast.success("PBIP downloaded successfully", { id: "pbip-gen" });

      } catch (error: any) {
        console.error(error);
        let finalError = error?.message || "PBIP generation failed";
        if (error?.message?.includes("Failed to fetch")) finalError = "Unable to connect to PBIP generation service.";
        if (error?.name === "AbortError") finalError = "PBIP generation timed out.";
        setPbipErrorMessage(finalError);
        setPbipErrorTimestamp(new Date().toLocaleString());
        setShowPbipError(true);
        toast.error(finalError, { id: "pbip-gen" });
      } finally {
        setIsPbipGenerating(false);
      }
      return;
    }

    // NORMAL FLOW
    setActiveTab("code");
    await generate();
  };

  const handleDownloadAgain = () => {
    if (!generatedBlob) return;
    const url = window.URL.createObjectURL(generatedBlob);
    const a = document.createElement("a");
    a.href = url;
    a.download = generatedPbipFileName;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  };

  const handleGenerateTests = async () => {
    setActiveTab("testcases");
    await generateTests();
  };

  const handleCopyCode = useCallback(() => {
    if (state.generatedCode) {
      navigator.clipboard.writeText(state.generatedCode);
      toast.success("Code copied to clipboard");
    }
  }, [state.generatedCode]);

  const handleDownloadCode = useCallback(() => {
    if (!state.generatedCode) return;
    const blob = new Blob([state.generatedCode], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = getDefaultFileName();
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast.success("Code downloaded successfully");
  }, [state.generatedCode]);

  const handleCommit = async (data: {
    repoUrl: string;
    token: string;
    branch: string;
    folder: string;
    fileName: string;
  }) => {
    return await commit(data);
  };

  const etlData = (() => {
    const r = state.apiResponse;
    if (!r) return null;
    if (r.depths || r.reconciliation) return r;
    if (r.reconciliation_report?.depths) return r.reconciliation_report;
    return null;
  })();

  const showDashboardTab = !!etlData;

  useEffect(() => {
    if (state.testCasesCode) setActiveTab("testcases");
  }, [state.testCasesCode]);

  return (
    <ContentCard
      heading={null}
      sideNavWidth={sideNavWidth}
      headerComponent={<FileWorkspaceHeader pageTitle="Code Generation" />}
      flat={true}
    >
      <div className="codeGen codegen-page" data-theme={theme}>

        <WorkflowStatusBar
          isAuthenticated={state.isAuthenticated}
          hasTicket={hasTicket}
          hasPlatform={hasPlatform}
          hasCode={hasCode}
          isCommitted={state.isCommitted}
        />

        <main className="codegen-main">
          <div className="grid w-full gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">

            {/* LEFT PANEL */}
            <div className="space-y-6 w-full">

              <PrimaryPanel
                issueKey={state.ticketKey || ""}
                onIssueKeyChange={setIssueKey}
                onGenerateCode={handleGenerateCode}
                isAuthenticated={state.isAuthenticated}
                hasTicket={hasTicket}
                hasPlatform={hasPlatform}
                selectedPlatform={state.selectedPlatform}
                isGenerating={state.isGenerating || isPbipGenerating}
                onAuthRequired={() => setShowAuthModal(true)}
                sourceUrl={sourceUrl}
                onSourceUrlChange={setSourceUrl}
                outputMode={outputMode}
                onOutputModeChange={setOutputMode}
              />

              {hasTicket && (
                <PlatformSelector
                  selectedPlatform={state.selectedPlatform}
                  onSelect={selectPlatform}
                  disabled={!hasTicket}
                />
              )}

              {/* TAB BAR */}
              {hasCode && (
                <Box sx={{ border: "1px solid hsl(var(--border))", borderBottom: "none", borderRadius: "12px 12px 0 0", bgcolor: "hsl(var(--card))" }}>
                  <Tabs
                    value={activeTab}
                    onChange={(_, v) => setActiveTab(v)}
                    sx={{
                      "& .MuiTab-root": { color: "hsl(var(--muted-foreground))", fontSize: "0.85rem", textTransform: "none" },
                      "& .Mui-selected": { color: "hsl(var(--primary)) !important", fontWeight: 600 },
                      "& .MuiTabs-indicator": { backgroundColor: "hsl(var(--primary))", height: 3 },
                    }}
                  >
                    <Tab value="code" icon={<CodeIcon fontSize="small" />} iconPosition="start" label="Generated Code" />
                    {showDashboardTab && (
                      <Tab value="dashboard" icon={<AssessmentIcon fontSize="small" />} iconPosition="start" label="ETL Dashboard" />
                    )}
                    <Tab value="testcases" icon={<ScienceIcon fontSize="small" />} iconPosition="start" label="Test Cases" />
                  </Tabs>
                </Box>
              )}

              {/* DASHBOARD TAB */}
              {activeTab === "dashboard" && showDashboardTab && (
                <Box sx={{ border: "1px solid hsl(var(--border))", borderTop: "none", borderRadius: "0 0 8px 8px", bgcolor: "hsl(var(--card))", p: 1 }}>
                  <ETLDashboard data={state.apiResponse} />
                </Box>
              )}

              {/* TEST CASES TAB */}
              {activeTab === "testcases" && (
                <Box sx={{ border: "1px solid hsl(var(--border))", borderTop: "none", borderRadius: "0 0 8px 8px", bgcolor: "hsl(var(--card))", p: 0, overflow: "hidden" }}>
                  {state.isGeneratingTestCases ? (
                    <Typography sx={{ p: 3, color: "hsl(var(--muted-foreground))" }}>Generating test cases...</Typography>
                  ) : state.testCasesCode ? (
                    <pre style={{ margin: 0, padding: "16px", fontSize: "13px", color: "var(--code-fg)", background: "var(--code-bg)", overflow: "auto" }}>
                      {state.testCasesCode}
                    </pre>
                  ) : (
                    <Typography sx={{ p: 3, color: "hsl(var(--muted-foreground))" }}>Click "Generate Tests" to create test cases</Typography>
                  )}
                </Box>
              )}

            </div>

            {/* RIGHT PANEL */}
            <div className="flex flex-col items-start w-full h-full">
              <ContextPanel
                isAuthenticated={state.isAuthenticated}
                connectionStatus={state.connectionStatus}
                boards={state.boards}
                selectedBoard={state.selectedBoard}
                ticketKey={state.ticketKey}
                selectedPlatform={state.selectedPlatform}
                generatedCode={state.generatedCode}
                isCommitted={state.isCommitted}
                isCreatingTicket={state.isCreatingTicket}
                onBoardChange={selectBoard}
                onAuthClick={() => setShowAuthModal(true)}
                onCreateTicket={createTicket}
              />
            </div>

          </div>
        </main>

        <JiraAuthModal
          isOpen={showAuthModal}
          onClose={() => setShowAuthModal(false)}
          onAuthenticate={handleAuthenticate}
        />

        <GitHubCommitModal
          isOpen={showGitHubModal}
          onClose={() => setShowGitHubModal(false)}
          ticketKey={state.ticketKey || ""}
          fileName={getDefaultFileName()}
          onCommit={handleCommit}
        />

        {/* PBIP SUCCESS MODAL */}
        <AnimatePresence>
          {showPbipSuccess && (
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="codegen-modal-backdrop"
            >
              <motion.div
                initial={{ scale: 0.85, opacity: 0, y: 30 }}
                animate={{ scale: 1, opacity: 1, y: 0 }}
                exit={{ scale: 0.85, opacity: 0 }}
                transition={{ type: "spring", stiffness: 180, damping: 18 }}
                className="codegen-modal p-6"
              >
                <div className="flex justify-center">
                  <div className="flex h-14 w-14 items-center justify-center rounded-xl border border-primary/25 bg-primary/10">
                    <CheckCircle className="h-7 w-7 text-primary" />
                  </div>
                </div>

                <div className="mt-6 text-center">
                  <h2 className="text-xl font-bold text-foreground">PBIP Generated Successfully</h2>
                  <p className="mt-2 text-sm text-muted-foreground">Your Power BI project package is ready.</p>
                </div>

                <div className="mt-6 rounded-xl border border-border bg-secondary p-4">
                  <div className="flex items-center gap-3">
                    <div className="rounded-lg bg-primary/10 p-3">
                      <FileArchive className="h-6 w-6 text-primary" />
                    </div>
                    <div className="flex-1 overflow-hidden">
                      <p className="text-sm font-semibold text-foreground truncate">{generatedPbipFileName}</p>
                      <p className="text-xs text-muted-foreground">Power BI Project Package (.zip)</p>
                    </div>
                  </div>
                </div>

                {/* Info about what comes next */}
                <div className="mt-4 rounded-xl bg-blue-50 border border-blue-100 px-4 py-3">
                  <p className="text-xs text-blue-800">
                    <span className="font-semibold">Next step:</span> Upload your Dataset ZIP and Report ZIP to run Forward Engineering Validation automatically.
                  </p>
                </div>

                <div className="mt-6 flex flex-col gap-2">
                  <button
                    onClick={() => { setShowPbipSuccess(false); navigate('/validation-dashboard?tab=forward'); }}
                    className="flex items-center justify-center gap-2 rounded-lg bg-[#003087] px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#002060] w-full"
                  >
                    <ShieldCheck className="h-4 w-4" />
                    Proceed to Forward Engineering Validation
                  </button>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setShowPbipSuccess(false)}
                      className="flex-1 rounded-lg border border-border bg-card px-4 py-2.5 text-sm font-medium text-foreground transition hover:bg-secondary"
                    >
                      Skip Validation
                    </button>
                    <button
                      onClick={handleDownloadAgain}
                      className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground transition hover:bg-destructive"
                    >
                      <Download className="h-4 w-4" />
                      Download Again
                    </button>
                  </div>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* PBIP ERROR MODAL */}
        <AnimatePresence>
          {showPbipError && (
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="fixed inset-0 z-[1000] flex items-center justify-center bg-slate-950/55 p-4"
            >
              <motion.div
                initial={{ scale: 0.9, opacity: 0, y: 20 }}
                animate={{ scale: 1, opacity: 1, y: 0 }}
                exit={{ scale: 0.9, opacity: 0 }}
                transition={{ type: "spring", stiffness: 180, damping: 18 }}
                className="relative w-full max-w-[520px] rounded-xl border border-border bg-card p-6 shadow-lg"
              >
                <div className="flex justify-center">
                  <div className="flex h-16 w-16 items-center justify-center rounded-xl border border-primary/25 bg-primary/10">
                    <Construction className="h-8 w-8 text-primary" />
                  </div>
                </div>

                <div className="mt-4 text-center">
                  <h2 className="text-xl font-bold text-foreground">PBIP Generation Failed</h2>
                </div>

                <div className="mt-5 max-h-[180px] overflow-y-auto rounded-xl border border-border bg-secondary p-4">
                  <pre className="whitespace-pre-wrap break-words text-[10px] leading-5 text-foreground font-mono">
                    {pbipErrorMessage}
                  </pre>
                </div>

                <div className="mt-4 rounded-xl border border-border bg-secondary p-4">
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Issue Key</span>
                      <span className="font-medium text-foreground">{state.ticketKey}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Status Code</span>
                      <span className="font-medium text-primary">{pbipErrorCode || "N/A"}</span>
                    </div>
                    <div className="flex justify-between gap-4">
                      <span className="text-muted-foreground">Timestamp</span>
                      <span className="text-right text-foreground">{pbipErrorTimestamp}</span>
                    </div>
                  </div>
                </div>

                <div className="mt-6 flex gap-3">
                  <button
                    onClick={() => setShowPbipError(false)}
                    className="flex-1 rounded-xl border border-border bg-card px-4 py-3 text-sm font-medium text-foreground transition hover:bg-secondary"
                  >
                    Close
                  </button>
                  <button
                    onClick={() => { setShowPbipError(false); handleGenerateCode(); }}
                    className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground transition hover:bg-destructive"
                  >
                    Retry Generation
                  </button>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

      </div>
    </ContentCard>
  );
};

export default CodeGen;
