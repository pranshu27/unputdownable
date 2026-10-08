import React, {
  useEffect,
  useMemo,
  useState,
} from "react";
import { useNavigate } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Code2,
  Database,
  Download,
  FileUp,
  FolderOpen,
  LogOut,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  ArrowUpDown,
} from "lucide-react";
import {
  fetchPowerBiReport,
  listPowerBiReports,
  ReportListItem,
} from "../../services/powerbiReports.ts";

interface FilesDashboardProps {
  model?: any;
}

interface UploadedFileEntry {
  fileName: string;
}

const getToolName = (fileName: string) => {
  const n = String(fileName || "").toLowerCase();
  if (n.endsWith(".pbix")) return "powerbi";
  if (n.endsWith(".twb") || n.endsWith(".twbx")) return "tableau-workbook";
  return "powerbi";
};

const getToolLabel = (fileName: string) => {
  const n = String(fileName || "").toLowerCase();
  if (n.endsWith(".pbix")) return "Power BI";
  if (n.endsWith(".twb") || n.endsWith(".twbx")) return "Tableau";
  return "Dataset";
};

const readUploadedFiles = (): UploadedFileEntry[] => {
  try {
    const raw = localStorage.getItem("existingReports");
    const files = raw ? JSON.parse(raw) : [];
    if (Array.isArray(files) && files.length > 0) {
      return files.filter((e) => e?.fileName);
    }
  } catch {}

  try {
    const rawJob = localStorage.getItem("powerbiPendingJob");
    const job = rawJob ? JSON.parse(rawJob) : null;
    const pending = Array.isArray(job?.files)
      ? job.files
          .map((e: any) => ({ fileName: e?.file_name }))
          .filter((e: UploadedFileEntry) => e.fileName)
      : [];
    if (pending.length > 0) return pending;
  } catch {}

  const active = localStorage.getItem("activePowerBiReportFile");
  return active ? [{ fileName: active }] : [];
};

export default function FilesDashboard({ model }: FilesDashboardProps) {
  const navigate = useNavigate();
  const [isLoading, setIsLoading] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState("");

  const handleLogout = () => {
    localStorage.clear();
    navigate('/login');
  };

  const [uploadedFiles, setUploadedFiles] = useState<UploadedFileEntry[]>([]);
  const [reports, setReports] = useState<ReportListItem[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedReportFile, setSelectedReportFile] = useState("");
  const [sortBy, setSortBy] = useState("recent");

  const refreshPageData = async () => {
    const files = readUploadedFiles();
    setUploadedFiles(files);
    setSelectedReportFile(
      localStorage.getItem("activePowerBiReportFile") || files[0]?.fileName || ""
    );

    const tools = Array.from(new Set(files.map((e) => getToolName(e.fileName))));
    const groups = await Promise.all(
      tools.map((t) => listPowerBiReports(t).catch(() => []))
    );
    setReports(groups.flat());
  };

  useEffect(() => {
    refreshPageData();
  }, []);

  const filteredFiles = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    let files = uploadedFiles;

    if (q) {
      files = files.filter((e) => e.fileName.toLowerCase().includes(q));
    }

    return [...files].sort((a, b) => {
      const metaA = reports.find((r) => r.file_name === a.fileName);
      const metaB = reports.find((r) => r.file_name === b.fileName);

      switch (sortBy) {
        case "name":
          return a.fileName.localeCompare(b.fileName);
        case "status":
          return String(metaA?.status || "").localeCompare(String(metaB?.status || ""));
        case "type":
          return getToolLabel(a.fileName).localeCompare(getToolLabel(b.fileName));
        case "recent":
        default:
          return (
            new Date(metaB?.completed_at || 0).getTime() -
            new Date(metaA?.completed_at || 0).getTime()
          );
      }
    });
  }, [uploadedFiles, searchQuery, sortBy, reports]);

  const metrics = useMemo(() => {
    const total = uploadedFiles.length;
    const ready = uploadedFiles.filter(
      (e) =>
        reports.some(
          (r) =>
            r.file_name === e.fileName &&
            String(r.status || "").toUpperCase() === "SUCCESS"
        )
    ).length;

    const processing = uploadedFiles.filter(
      (e) =>
        reports.some(
          (r) =>
            r.file_name === e.fileName &&
            String(r.status || "").toUpperCase() === "PROCESSING"
        )
    ).length;

    return {
      totalFiles: total,
      readyFiles: ready,
      processingFiles: processing,
      pendingFiles: Math.max(total - ready - processing, 0),
    };
  }, [reports, uploadedFiles]);

  const activateFile = async (entry: UploadedFileEntry) => {
    const toolName = getToolName(entry.fileName);
    const meta = reports.find((r) => r.file_name === entry.fileName);

    const reportData = await fetchPowerBiReport(
      entry.fileName,
      toolName,
      { reportId: meta?.report_id }
    );

    const baseName =
      entry.fileName.substring(0, entry.fileName.lastIndexOf(".")) ||
      entry.fileName;

    localStorage.setItem("activePowerBiReportFile", entry.fileName);
    localStorage.setItem("activePowerBiReportId", meta?.report_id || "");
    localStorage.setItem("activePowerBiReportData", JSON.stringify(reportData));
    localStorage.setItem(
      "fileDetails",
      JSON.stringify({
        ...(JSON.parse(localStorage.getItem("fileDetails") || "{}")),
        fileName: baseName,
        etlTool: toolName,
      })
    );

    setSelectedReportFile(entry.fileName);
    window.dispatchEvent(new CustomEvent("jnj:active-report-changed"));
    return baseName;
  };

  const handleFileClick = async (entry: UploadedFileEntry) => {
    setIsLoading(true);
    setLoadingMessage("Fetching report schema...");
    try {
      await activateFile(entry);
      setLoadingMessage("Loading active workspace...");
      navigate('/overview');
    } catch (error) {
      console.error("Failed to load file:", error);
      alert("Failed to load report. Please make sure the backend is running and the report is valid.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleFileValidation = async (entry: UploadedFileEntry) => {
    setIsLoading(true);
    setLoadingMessage("Running initial validation schema...");
    try {
      await activateFile(entry);
      navigate("/validation-report");
    } catch (error) {
      console.error("Failed to validate file:", error);
      alert("Failed to validate report. Please check if the file is valid.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#f8fafc",
      }}
    >
      {/* HEADER */}
      <header
        style={{
          position: "sticky",
          top: 0,
          zIndex: 5,
          background: "rgba(255,255,255,0.95)",
          backdropFilter: "blur(12px)",
          borderBottom: "1px solid #e5e7eb",
        }}
      >
        <div
          style={{
            maxWidth: 1480,
            margin: "0 auto",
            height: 70,
            padding: "0 32px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          {/* LEFT BRAND */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
              <div style={{
                background: 'linear-gradient(135deg, #c8102e 0%, #8f0d22 100%)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                fontWeight: 800,
                fontSize: 18,
                letterSpacing: '-0.3px',
              }}>
                BI Modernization
              </div>
            </div>
          </div>

          {/* RIGHT ACTIONS */}
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <button
              onClick={() => navigate("/")}
              style={{
                height: 40,
                padding: "0 16px",
                borderRadius: 10,
                border: "none",
                background: "#c8102e",
                color: "#fff",
                fontWeight: 600,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <FileUp size={15} />
              Upload
            </button>

            <button
              onClick={() => navigate('/intelligence-hub')}
              style={{
                height: 36,
                padding: '0 14px',
                borderRadius: 999,
                background: '#fffbeb',
                color: '#92400e',
                fontSize: 12,
                fontWeight: 600,
                border: '1px solid #fde68a',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              <AlertTriangle size={13} /> Intelligence Hub
            </button>

            <button
              onClick={handleLogout}
              style={{
                height: 36,
                padding: '0 14px',
                borderRadius: 999,
                background: '#fff',
                color: '#3f3a3a',
                fontSize: 12,
                fontWeight: 700,
                border: '1px solid #e5e7eb',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              <LogOut size={13} /> Logout
            </button>
          </div>
        </div>
      </header>

      {/* CONTENT */}
      <main
        style={{
          maxWidth: 1480,
          margin: "0 auto",
          padding: "28px 32px 48px",
        }}
      >
        {/* TOOLBAR */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 18,
            gap: 16,
            flexWrap: "wrap",
          }}
        >
          {/* TOTALS */}
          <div>
            <h2 style={{ fontSize: 22, fontWeight: 700, color: "#111827", margin: 0 }}>
              Uploaded Files
            </h2>
            <p style={{ marginTop: 4, fontSize: 13, color: "#6b7280" }}>
              {metrics.totalFiles} uploaded · {metrics.readyFiles} ready · {metrics.pendingFiles} pending
            </p>
          </div>

          {/* SEARCH / FILTERS */}
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <div style={{ position: "relative" }}>
              <Search
                size={15}
                style={{
                  position: "absolute",
                  left: 14,
                  top: "50%",
                  transform: "translateY(-50%)",
                  color: "#9ca3af",
                }}
              />
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search files..."
                style={{
                  width: 280,
                  height: 40,
                  paddingLeft: 40,
                  paddingRight: 14,
                  borderRadius: 10,
                  border: "1px solid #e5e7eb",
                  background: "#fff",
                  fontSize: 13,
                  outline: "none",
                }}
              />
            </div>

            <div style={{ position: "relative" }}>
              <ArrowUpDown
                size={14}
                style={{
                  position: "absolute",
                  left: 12,
                  top: "50%",
                  transform: "translateY(-50%)",
                  color: "#9ca3af",
                }}
              />
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
                style={{
                  height: 40,
                  paddingLeft: 34,
                  paddingRight: 14,
                  borderRadius: 10,
                  border: "1px solid #e5e7eb",
                  background: "#fff",
                  fontSize: 13,
                  outline: "none",
                  appearance: "none",
                }}
              >
                <option value="recent">Recently Analyzed</option>
                <option value="name">File Name</option>
                <option value="status">Status</option>
                <option value="type">File Type</option>
              </select>
            </div>

            <button
              onClick={refreshPageData}
              style={{
                height: 40,
                padding: "0 16px",
                borderRadius: 10,
                background: "#fff",
                border: "1px solid #e5e7eb",
                color: "#111827",
                fontSize: 13,
                fontWeight: 600,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              <RefreshCw size={14} />
              Refresh
            </button>
          </div>
        </div>

        {/* TABLE */}
        <div
          style={{
            background: "#fff",
            borderRadius: 14,
            border: "1px solid #e5e7eb",
            overflow: "hidden",
            boxShadow: "0 4px 16px rgba(0,0,0,0.04)",
          }}
        >
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e5e7eb" }}>
                {["File Name", "Type", "Status", "Last Analyzed", "Actions"].map((h) => (
                  <th
                    key={h}
                    style={{
                      padding: "14px 18px",
                      textAlign: "left",
                      fontSize: 11,
                      fontWeight: 700,
                      color: "#6b7280",
                      textTransform: "uppercase",
                      letterSpacing: "0.04em",
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>

            <tbody>
              {filteredFiles.map((entry) => {
                const isActive = selectedReportFile === entry.fileName;
                const meta = reports.find((r) => r.file_name === entry.fileName);
                const status = String(meta?.status || "READY").toUpperCase();

                const statusStyle =
                  status === "FAILED"
                    ? { bg: "#fef2f2", color: "#dc2626" }
                    : status === "SUCCESS" || status === "READY"
                      ? { bg: "#ecfdf5", color: "#059669" }
                      : { bg: "#fffbeb", color: "#d97706" };

                return (
                  <tr
                    key={entry.fileName}
                    style={{
                      borderBottom: "1px solid #f3f4f6",
                      background: isActive ? "#fff5f5" : "#fff",
                      cursor: "pointer",
                    }}
                    onClick={() => handleFileClick(entry)}
                  >
                    {/* FILE NAME */}
                    <td style={{ padding: "16px 18px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                        <div style={{
                          width: 36,
                          height: 36,
                          borderRadius: 10,
                          background: "#f8fafc",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                        }}>
                          <Database size={16} color="#6b7280" />
                        </div>
                        <div>
                          <div style={{ fontSize: 14, fontWeight: 600, color: "#111827" }}>
                            {entry.fileName}
                          </div>
                          <div style={{ marginTop: 4, fontSize: 12, color: "#9ca3af" }}>
                            Enterprise Dataset
                          </div>
                        </div>
                      </div>
                    </td>

                    {/* TYPE */}
                    <td style={{ padding: "16px 18px" }}>
                      <span style={{
                        fontSize: 12,
                        fontWeight: 600,
                        padding: "6px 12px",
                        borderRadius: 999,
                        background: "#f3f4f6",
                        color: "#374151",
                      }}>
                        {getToolLabel(entry.fileName)}
                      </span>
                    </td>

                    {/* STATUS */}
                    <td style={{ padding: "16px 18px" }}>
                      <span style={{
                        fontSize: 12,
                        fontWeight: 700,
                        padding: "6px 12px",
                        borderRadius: 999,
                        background: statusStyle.bg,
                        color: statusStyle.color,
                      }}>
                        {status}
                      </span>
                    </td>

                    {/* DATE */}
                    <td style={{ padding: "16px 18px", fontSize: 13, color: "#6b7280" }}>
                      {meta?.completed_at ? new Date(meta.completed_at).toLocaleString() : "--"}
                    </td>

                    {/* ACTIONS */}
                    <td style={{ padding: "16px 18px" }}>
                      <div
                        style={{ display: "flex", gap: 8 }}
                        onClick={(e) => e.stopPropagation()}
                      >
                        <button
                          onClick={() => handleFileClick(entry)}
                          style={{
                            height: 34,
                            padding: "0 14px",
                            borderRadius: 10,
                            border: "1px solid #fecdd3",
                            background: "#fff1f2",
                            color: "#be123c",
                            fontWeight: 600,
                            cursor: "pointer",
                            display: "flex",
                            alignItems: "center",
                            gap: 6,
                          }}
                        >
                          <FolderOpen size={14} />
                          Analyze
                        </button>

                        <button
                          style={{
                            width: 34,
                            height: 34,
                            borderRadius: 10,
                            border: "1px solid #e5e7eb",
                            background: "#fff",
                            cursor: "pointer",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                          }}
                        >
                          <Download size={14} color="#374151" />
                        </button>

                        <button
                          onClick={() => handleFileValidation(entry)}
                          style={{
                            width: 34,
                            height: 34,
                            borderRadius: 10,
                            border: "1px solid #bbf7d0",
                            background: "#ecfdf5",
                            cursor: "pointer",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                          }}
                        >
                          <ShieldCheck size={14} color="#047857" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {filteredFiles.length === 0 && (
            <div style={{ padding: "64px 0", textAlign: "center", color: "#9ca3af" }}>
              No uploaded datasets found
            </div>
          )}
        </div>
      </main>

      {/* Loading Overlay */}
      {isLoading && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 9999,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            background: "rgba(15, 23, 42, 0.45)",
            backdropFilter: "blur(8px)",
            transition: "all 0.3s ease",
          }}
        >
          <div
            style={{
              background: "#ffffff",
              padding: "32px 48px",
              borderRadius: "16px",
              boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)",
              border: "1px solid rgba(226, 232, 240, 0.8)",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 16,
              maxWidth: 360,
              textAlign: "center",
            }}
          >
            {/* Spinning Indicator */}
            <div style={{ position: "relative", width: 48, height: 48 }}>
              <div
                style={{
                  width: 48,
                  height: 48,
                  borderRadius: "50%",
                  border: "4px solid #f3f4f6",
                  borderTop: "4px solid #c8102e",
                  animation: "spin 1s linear infinite",
                }}
              />
              <style>{`
                @keyframes spin {
                  0% { transform: rotate(0deg); }
                  100% { transform: rotate(360deg); }
                }
              `}</style>
            </div>
            
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: "#0f172a", fontFamily: "sans-serif" }}>
                Analyzing Report
              </h3>
              <p style={{ margin: 0, fontSize: 13, color: "#64748b", fontWeight: 500, fontFamily: "sans-serif" }}>
                {loadingMessage || "Please wait..."}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
