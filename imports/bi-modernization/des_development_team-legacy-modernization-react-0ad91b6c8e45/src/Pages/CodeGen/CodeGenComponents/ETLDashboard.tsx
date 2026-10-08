import React, { useMemo, useState } from "react";
import {
  Box,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Button,
  Chip,
  Divider,
  Grid,
  Card,
  CardContent,
  Alert,
  LinearProgress,
  Tabs,
  Tab,
} from "@mui/material";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorIcon from "@mui/icons-material/Error";
import WarningIcon from "@mui/icons-material/Warning";
import PendingIcon from "@mui/icons-material/Pending";
import BlockIcon from "@mui/icons-material/Block";
import CodeIcon from "@mui/icons-material/Code";
import HistoryIcon from "@mui/icons-material/History";

interface ETLDashboardProps {
  data: any;
}

const ETLDashboard: React.FC<ETLDashboardProps> = ({ data }) => {
  const [selectedNode, setSelectedNode] = useState<any>(null);
  const [codeAttemptTab, setCodeAttemptTab] = useState(0);

  // ─────────────────────────────────────────────────────────────────────────
  // Normalise data shape.
  //
  // Two shapes exist in the wild:
  //   A) GA-29606 (new): { depths, reconciliation, ... }          ← flat
  //   B) GA-28078 (old): { reconciliation_report: { depths, reconciliation } }
  //
  // We always work from `report` which is the object that owns depths +
  // reconciliation.
  // ─────────────────────────────────────────────────────────────────────────
  const report = useMemo(() => {
    if (!data) return null;
    // Shape A – depths lives directly on data
    if (data.depths) return data;
    // Shape B – depths lives inside reconciliation_report
    if (data.reconciliation_report?.depths) return data.reconciliation_report;
    return data;
  }, [data]);

  /* -------------------- SUMMARY -------------------- */
  const summary = useMemo(
    () => report?.reconciliation?.summary ?? null,
    [report]
  );

  const isTalendFormat = useMemo(() => {
    if (!report?.depths) return false;
  
    const firstDepth: any = Object.values(report.depths)[0];
    const firstBatch: any = firstDepth ? Object.values(firstDepth)[0] : null;
  
    return Array.isArray(firstBatch?.nodes);
  }, [report]);
  /* -------------------- RECONCILIATION NODES -------------------- */
  const reconNodes: any[] = useMemo(
    () => report?.reconciliation?.nodes ?? [],
    [report]
  );

  /* ──────────────────────────────────────────────────────────────────────────
   * FLATTEN ALL PIPELINE NODES from depths
   *
   * Structure (both shapes):
   *   report.depths.depth_N.batch_M = {
   *     nodes: [{ node_id, node_name, node_type, ... }],   // ARRAY
   *     code: "...",
   *     code_history: [ { attempt, code, status, logs } ] | null,
   *     execution_logs: "...",
   *   }
   *
   * Each flattened node gets:
   *   id            – node_name string  (matches reconciliation node_id)
   *   batchCode     – batch-level final code
   *   batchCodeHistory – batch-level code_history array (retry attempts)
   *   batchExecLogs – batch-level execution_logs string
   * ────────────────────────────────────────────────────────────────────────*/
  const nodes = useMemo(() => {
    const list: any[] = [];
    if (!report?.depths) return list;
  
    Object.entries(report.depths).forEach(([depthKey, depthValue]: any) => {
      Object.entries(depthValue).forEach(([batchKey, batchValue]: any) => {
  
        const batchCode: string = batchValue?.code ?? "";
        const batchCodeHistory =
          Array.isArray(batchValue?.code_history) ? batchValue.code_history : null;
        const batchExecLogs: string = batchValue?.execution_logs ?? "";
  
        /* =========================
           ✅ TALEND FORMAT
           ========================= */
        if (Array.isArray(batchValue?.nodes)) {
          batchValue.nodes.forEach((nodeData: any) => {
            const nodeName =
              nodeData.node_name ??
              nodeData.name ??
              String(nodeData.node_id ?? "");
  
            list.push({
              id: nodeName,
              depth: depthKey,
              batch: batchKey,
              batchCode,
              batchCodeHistory,
              batchExecLogs,
              format: "talend",
              ...nodeData,
            });
          });
        }
  
        /* =========================
           ✅ IICS FORMAT
           ========================= */
        else {
          Object.entries(batchValue).forEach(([key, val]: any) => {
            // skip metadata keys
            if (["code", "code_history", "execution_logs"].includes(key)) return;
  
            if (val && typeof val === "object" && val.id) {
              list.push({
                id: val.id || key,
                node_name: val.name || key,
                node_type: val.type || "transformation",
                depth: depthKey,
                batch: batchKey,
                batchCode: val.code ?? batchCode,
                batchCodeHistory: null,
                batchExecLogs: "",
                prev_nodes: val.previousnodeId
                  ? [].concat(val.previousnodeId)
                  : [],
                next_nodes: val.nextnodeId
                  ? [].concat(val.nextnodeId)
                  : [],
                format: "iics",
                ...val,
              });
            }
          });
        }
      });
    });
  
    return list;
  }, [report]);

  /* -------------------- HELPERS -------------------- */
  const getReconNode = (id: string) =>
    reconNodes.find((n: any) => n.node_id === id) ?? null;

  /**
   * Returns code history for a node.
   *
   * Priority:
   *   1. batch-level code_history (array of retry attempts)
   *   2. Wrap batchCode + batchExecLogs as single entry
   */
  const getCodeHistory = (node: any): any[] => {
    const reconNode = getReconNode(node.id);
  
    // ✅ 1. FIRST check reconciliation-level history (Talend case)
    if (Array.isArray(reconNode?.code_history) && reconNode.code_history.length > 0) {
      return reconNode.code_history.map((item: any, idx: number) => ({
        attempt: (item.attempt ?? item.attempt_number ?? idx) + 1,
        code: item.code,
        status: item.status,
        logs: item.logs,
      }));
    }
  
    // ✅ 2. Batch-level history (IICS case)
    if (Array.isArray(node?.batchCodeHistory) && node.batchCodeHistory.length > 0) {
      return node.batchCodeHistory.map((item: any, idx: number) => ({
        attempt: (item.attempt ?? item.attempt_number ?? idx) + 1,
        code: item.code,
        status: item.status,
        logs: item.logs,
      }));
    }
  
    // ✅ 3. Fallback single attempt
    if (node?.batchCode) {
      return [{
        attempt: 1,
        code: node.batchCode,
        status: "success",
        logs: node.batchExecLogs || null,
      }];
    }
  
    return [];
  };

  /* -------------------- BADGES -------------------- */
  const statusBadge = (status: string) => {
    const s = (status ?? "").toLowerCase();
    if (s === "pass" || s === "success")
      return <Chip label="Pass" size="small" color="success" icon={<CheckCircleIcon />} />;
    if (s === "fail" || s === "failed" || s === "error")
      return <Chip label="Failed" size="small" color="error" icon={<ErrorIcon />} />;
    if (s === "partial")
      return <Chip label="Partial" size="small" color="warning" icon={<WarningIcon />} />;
    if (s === "pending")
      return <Chip label="Pending" size="small" color="info" icon={<PendingIcon />} />;
    if (s === "not_executed")
      return <Chip label="Not Executed" size="small" color="default" icon={<BlockIcon />} />;
    if (s === "in_progress")
      return <Chip label="In Progress" size="small" color="warning" icon={<PendingIcon />} />;
    return <Chip label={status ?? "Unknown"} size="small" />;
  };

  const typeBadge = (type: string) => {
    const t = (type ?? "").toLowerCase();
    if (t === "source") return <Chip label="Source" size="small" color="success" />;
    if (t === "target" || t === "output") return <Chip label="Output" size="small" color="error" />;
    return <Chip label={type ?? "Transform"} size="small" color="warning" />;
  };

  /* -------------------- NODE ROW STATUS -------------------- */
  const getNodeDisplayStatus = (nodeId: string): string | null => {
    const rn = getReconNode(nodeId);
    if (rn?.status) return rn.status;

    const batchLogs: any[] = report?.reconciliation?.batch_log ?? [];
    for (const bl of batchLogs) {
      if (bl.statuses?.[nodeId]) return bl.statuses[nodeId];
    }

    const node = nodes.find((n) => n.id === nodeId);
    const history = getCodeHistory(node);
    if (history.length > 0) {
      const last = history[history.length - 1];
      return last.status ?? null;
    }

    return null;
  };

  /* ================== RENDER ================== */
  return (
    <Box
      sx={{
        height: "calc(100vh - 300px)",
        maxHeight: "calc(100vh - 300px)",
        overflowY: "auto",
        overflowX: "hidden",
        p: 2,
        pb: 4,
        border: "1px solid #e0e0e0",
        borderRadius: 2,
        backgroundColor: "#fafafa",
        scrollBehavior: "smooth",
        "&::-webkit-scrollbar": { width: "10px" },
        "&::-webkit-scrollbar-track": { background: "#f1f1f1", borderRadius: "10px" },
        "&::-webkit-scrollbar-thumb": {
          background: "#888",
          borderRadius: "10px",
          "&:hover": { background: "#555" },
        },
      }} className="etl-dashboard"
    >
      {/* ================= SUMMARY ================= */}
      {summary && (
        <Box sx={{ mb: 3 }}>
          <Typography variant="h6" fontWeight={600} mb={2}>
            Pipeline Execution Summary
          </Typography>

          <Alert
            severity={
              summary.overall_status?.toLowerCase() === "pass"
                ? "success"
                : summary.overall_status?.toLowerCase() === "in_progress"
                ? "info"
                : "warning"
            }
            sx={{ mb: 2 }}
          >
            <Typography variant="body1" fontWeight={600}>
              Overall Status: {summary.overall_status}
            </Typography>
            <Typography variant="body2">
              First Attempt Success:{" "}
              {summary.retry_statistics?.first_attempt_success_rate?.toFixed(1)}%
            </Typography>
          </Alert>
{/* 
          <Grid container spacing={2}>
            {[
              { label: "Total Nodes", value: summary.total_nodes ?? 0, color: undefined },
              { label: "Passed",      value: summary.passed   ?? 0, color: "success.main" },
              { label: "Failed",      value: summary.failed   ?? 0, color: (summary.failed  > 0 ? "error.main"   : undefined) },
              { label: "Partial",     value: summary.partial  ?? 0, color: (summary.partial > 0 ? "warning.main" : undefined) },
              { label: "Pending",     value: summary.pending  ?? 0, color: (summary.pending > 0 ? "info.main"    : undefined) },
            ].map(({ label, value, color }) => (
              <Grid item xs={12} sm={6} md={value !== undefined ? 2 : 3} key={label}>
                <Card variant="outlined" sx={{ borderColor: color ?? "divider" }}>
                  <CardContent sx={{ textAlign: "center", py: 1.5, "&:last-child": { pb: 1.5 } }}>
                    <Typography color={color ?? "text.secondary"} variant="caption">
                      {label}
                    </Typography>
                    <Typography variant="h4" fontWeight={600} color={color ?? "text.primary"}>
                      {value}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid> */}
{/* 
          {summary.retry_statistics && (
            <Box sx={{ mt: 2, p: 2, bgcolor: "background.paper", borderRadius: 1, border: "1px solid #e0e0e0" }}>
              <Typography variant="caption" fontWeight={600} display="block" mb={1}>
                Retry Statistics
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={4}>
                  <Typography variant="caption" color="text.secondary">Total Retries</Typography>
                  <Typography variant="body2" fontWeight={600}>{summary.retry_statistics.total_retries ?? 0}</Typography>
                </Grid>
                <Grid item xs={4}>
                  <Typography variant="caption" color="text.secondary">Batches with Retries</Typography>
                  <Typography variant="body2" fontWeight={600}>{summary.retry_statistics.batches_with_retries ?? 0}</Typography>
                </Grid>
                <Grid item xs={4}>
                  <Typography variant="caption" color="text.secondary">First Attempt Success</Typography>
                  <Typography variant="body2" fontWeight={600}>{summary.retry_statistics.first_attempt_success_rate?.toFixed(1)}%</Typography>
                </Grid>
              </Grid>
            </Box>
          )} */}

          <Divider sx={{ my: 3 }} />
        </Box>
      )}

      {/* ================= NODE LIST ================= */}
      {!selectedNode && (
        <>
          <Typography fontWeight={600} mb={2}>Pipeline Nodes</Typography>

          <TableContainer
            component={Paper}
            variant="outlined"
            sx={{ mb: 3, maxHeight: "calc(100vh - 550px)", overflow: "auto" }}
          >
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ bgcolor: "background.paper", fontWeight: 600 }}>Node</TableCell>
                  <TableCell sx={{ bgcolor: "background.paper", fontWeight: 600 }}>Type</TableCell>
                  <TableCell sx={{ bgcolor: "background.paper", fontWeight: 600 }}>Depth</TableCell>
                  <TableCell sx={{ bgcolor: "background.paper", fontWeight: 600 }}>Status</TableCell>
                  <TableCell align="right" sx={{ bgcolor: "background.paper", fontWeight: 600 }}>Action</TableCell>
                </TableRow>
              </TableHead>

              <TableBody>
                {nodes.map((node) => {
                  const status = getNodeDisplayStatus(node.id);
                  const history = getCodeHistory(node);
                  return (
                    <TableRow key={`${node.depth}-${node.id}`} hover>
                      <TableCell sx={{ fontFamily: "monospace" }}>
                        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                          {node.id}
                          {history.length > 1 && (
                            <Chip
                              icon={<HistoryIcon />}
                              label={`${history.length} attempts`}
                              size="small"
                              color="info"
                              sx={{ fontSize: "0.65rem" }}
                            />
                          )}
                        </Box>
                      </TableCell>
                      <TableCell>{typeBadge(node.node_type || node.type)}</TableCell>
                      <TableCell>
                        <Chip
                          label={node.depth?.toString().replace("depth_", "D") ?? "?"}
                          size="small"
                          variant="outlined"
                          sx={{ fontSize: "0.7rem" }}
                        />
                      </TableCell>
                      <TableCell>
                        {status ? statusBadge(status) : <Chip label="—" size="small" />}
                      </TableCell>
                      <TableCell align="right">
                        <Button
                          size="small"
                          variant="outlined"
                          onClick={() => {
                            setSelectedNode(node);
                            setCodeAttemptTab(0);
                          }}
                        >
                          View
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}

                {nodes.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5}>
                      <Typography color="text.secondary" align="center">No nodes found</Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </>
      )}

      {/* ================= NODE DETAILS ================= */}
      {selectedNode && (() => {
        const reconNode = getReconNode(selectedNode.id);
        const schema = reconNode?.schema_comparison ?? null;
        const aiSuggestions: string = reconNode?.ai_suggestions ?? "";
        const rowCount = reconNode?.row_count_comparison ?? null;
        const codeHistory = getCodeHistory(selectedNode);
        // Execution logs: prefer recon node logs, fall back to batch-level
        const execLogs: string =
          reconNode?.logs ?? selectedNode.batchExecLogs ?? "";

        return (
          <Box sx={{ pb: 3 }}>
            <Button
              size="small"
              onClick={() => {
                setSelectedNode(null);
                setCodeAttemptTab(0);
              }}
              sx={{ mb: 2 }}
            >
              ← Back to list
            </Button>

            <Typography variant="h6" fontFamily="monospace">{selectedNode.id}</Typography>
            {selectedNode.node_name && selectedNode.node_name !== selectedNode.id && (
              <Typography variant="body2" color="text.secondary" mb={0.5}>
                {selectedNode.node_name}
              </Typography>
            )}

            <Box sx={{ display: "flex", gap: 1, mb: 1, flexWrap: "wrap" }}>
              {typeBadge(selectedNode.node_type ?? selectedNode.type)}
              {reconNode?.status && statusBadge(reconNode.status)}
            </Box>

            {selectedNode.description && (
              <Typography variant="body2" color="text.secondary" mb={2}>
                {selectedNode.description}
              </Typography>
            )}

            {/* Depth / Batch / Prev / Next metadata */}
            <Box sx={{ display: "flex", gap: 1, mb: 2, flexWrap: "wrap" }}>
              <Chip label={`Depth: ${selectedNode.depth?.toString().replace("depth_", "") ?? "?"}`} size="small" variant="outlined" />
              <Chip label={`Batch: ${selectedNode.batch?.replace("batch_", "") ?? "?"}`} size="small" variant="outlined" />
              {selectedNode.prev_nodes?.length > 0 && (
                <Chip label={`Prev: ${selectedNode.prev_nodes.join(", ")}`} size="small" variant="outlined" />
              )}
              {selectedNode.next_nodes?.length > 0 && (
                <Chip label={`Next: ${selectedNode.next_nodes.join(", ")}`} size="small" variant="outlined" />
              )}
            </Box>

            <Divider sx={{ my: 2 }} />

            {/* ── SCHEMA COMPARISON ── */}
            {schema && Object.keys(schema).length > 0 && (
              <>
                <Typography fontWeight={600} mb={1}>Schema Comparison</Typography>
                <Paper variant="outlined" sx={{ p: 2, mb: 3 }}>
                  <Grid container spacing={2} sx={{ mb: 1 }}>
                    {[
                      { label: "Expected", value: schema.expected_column_count },
                      { label: "Actual",   value: schema.actual_column_count },
                      { label: "Matched",  value: schema.matched_count,  color: "success.main" },
                      { label: "Missing",  value: schema.missing_count,  color: schema.missing_count > 0 ? "error.main" : "success.main" },
                    ].map(({ label, value, color }) => (
                      <Grid item xs={3} key={label}>
                        <Typography variant="caption" color="text.secondary">{label}</Typography>
                        <Typography fontWeight={600} color={color}>{value}</Typography>
                      </Grid>
                    ))}
                  </Grid>

                  <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
                    <LinearProgress
                      variant="determinate"
                      value={schema.match_percentage ?? 0}
                      sx={{ flex: 1, height: 8, borderRadius: 1 }}
                      color={
                        (schema.match_percentage ?? 0) >= 80 ? "success"
                        : (schema.match_percentage ?? 0) >= 50 ? "warning"
                        : "error"
                      }
                    />
                    <Typography variant="caption" fontWeight={600}>
                      {schema.match_percentage?.toFixed(1)}%
                    </Typography>
                  </Box>

                  {schema.matched_columns?.length > 0 && (
                    <Box sx={{ mb: 2 }}>
                      <Typography variant="caption" color="text.secondary" display="block" mb={0.5}>Matched Columns</Typography>
                      <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap" }}>
                        {schema.matched_columns.map((c: string) => (
                          <Chip key={c} label={c} size="small" color="success" variant="outlined" />
                        ))}
                      </Box>
                    </Box>
                  )}

                  {schema.missing_columns?.length > 0 && (
                    <Box sx={{ mb: 2 }}>
                      <Typography variant="caption" color="text.secondary" display="block" mb={0.5}>Missing Columns</Typography>
                      <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap" }}>
                        {schema.missing_columns.map((c: string) => (
                          <Chip key={c} label={c} size="small" color="error" />
                        ))}
                      </Box>
                    </Box>
                  )}

                  {schema.extra_columns?.length > 0 && (
                    <Box>
                      <Typography variant="caption" color="text.secondary" display="block" mb={0.5}>Extra Columns (not in expected schema)</Typography>
                      <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap" }}>
                        {schema.extra_columns.map((c: string) => (
                          <Chip key={c} label={c} size="small" color="warning" variant="outlined" />
                        ))}
                      </Box>
                    </Box>
                  )}
                </Paper>
              </>
            )}

            {/* ── ROW COUNT ── */}
            {rowCount && Object.keys(rowCount).length > 0 && (
              <>
                <Typography fontWeight={600} mb={1}>Row Count Comparison</Typography>
                <Paper variant="outlined" sx={{ p: 2, mb: 3 }}>
                  <Grid container spacing={2}>
                    <Grid item xs={4}>
                      <Typography variant="caption" color="text.secondary">Expected</Typography>
                      <Typography fontWeight={600}>{rowCount.expected?.toLocaleString()}</Typography>
                    </Grid>
                    <Grid item xs={4}>
                      <Typography variant="caption" color="text.secondary">Actual</Typography>
                      <Typography fontWeight={600} color={!rowCount.match ? "error.main" : undefined}>
                        {rowCount.actual?.toLocaleString()}
                      </Typography>
                    </Grid>
                    <Grid item xs={4}>
                      <Typography variant="caption" color="text.secondary">Match</Typography>
                      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mt: 0.5 }}>
                        {rowCount.match
                          ? <CheckCircleIcon color="success" fontSize="small" />
                          : <ErrorIcon color="error" fontSize="small" />}
                        {!rowCount.match && rowCount.difference != null && (
                          <Typography variant="caption" color="error.main">
                            Δ {rowCount.difference?.toLocaleString()}
                          </Typography>
                        )}
                      </Box>
                    </Grid>
                  </Grid>
                </Paper>
              </>
            )}

            {/* ── AI SUGGESTIONS ── */}
            {aiSuggestions && (
              <>
                <Typography fontWeight={600} mb={1}>AI Suggestions</Typography>
                <Paper
                  sx={{
                    p: 2, mb: 3,
                    bgcolor: "#0f172a", color: "#e5e7eb",
                    fontFamily: "monospace", fontSize: "0.78rem",
                    whiteSpace: "pre-wrap",
                    maxHeight: 400, overflow: "auto",
                    borderLeft: "6px solid #6366f1",
                  }}
                >
                  {aiSuggestions}
                </Paper>
              </>
            )}

            {/* ── CODE HISTORY (RETRY ATTEMPTS) ── */}
            {codeHistory.length > 0 && (
              <>
                <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
                  <Typography fontWeight={600}>Code</Typography>
                  {codeHistory.length > 1 && (
                    <Chip icon={<HistoryIcon />} label={`${codeHistory.length} attempts`} size="small" color="info" />
                  )}
                </Box>

                {codeHistory.length > 1 ? (
                  <>
                    <Tabs
                      value={codeAttemptTab}
                      onChange={(_, v) => setCodeAttemptTab(v)}
                      variant="scrollable"
                      scrollButtons="auto"
                      sx={{ borderBottom: 1, borderColor: "divider", mb: 2 }}
                    >
                      {codeHistory.map((attempt: any, idx: number) => (
                        <Tab
                          key={idx}
                          label={
                            <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                              <CodeIcon fontSize="small" />
                              <span>Attempt {attempt.attempt ?? idx + 1}</span>
                              {statusBadge(attempt.status)}
                            </Box>
                          }
                        />
                      ))}
                    </Tabs>

                    {codeHistory.map((attempt: any, idx: number) => (
                      <Box key={idx} hidden={codeAttemptTab !== idx}>
                        {attempt.error && (
                          <Alert severity="error" sx={{ mb: 2, fontFamily: "monospace", fontSize: "0.72rem", whiteSpace: "pre-wrap" }}>
                            {attempt.error}
                          </Alert>
                        )}
                        <Typography variant="caption" fontWeight={600} display="block" mb={0.5}>Generated Code</Typography>
                        <Box sx={{ maxHeight: "20rem", overflow: "auto", borderRadius: 1, border: "1px solid #ddd", mb: 2 }}>
                          <SyntaxHighlighter language="python" style={vscDarkPlus} showLineNumbers customStyle={{ margin: 0, fontSize: "0.75rem" }}>
                            {attempt.code || "# No code available"}
                          </SyntaxHighlighter>
                        </Box>
                        {attempt.logs && attempt.logs !== "None" && (
                          <>
                            <Typography variant="caption" fontWeight={600} display="block" mb={0.5}>
                              Execution Logs {idx === codeHistory.length - 1 ? "(Final)" : "(Attempt)"}
                            </Typography>
                            <Box sx={{
                              fontFamily: "monospace", fontSize: "0.70rem", whiteSpace: "pre-wrap",
                              bgcolor: "#1e1e1e", color: "#d4d4d4", p: 1.5, borderRadius: 1,
                              maxHeight: "400px", overflow: "auto", mb: 2,
                            }}>
                              {attempt.logs}
                            </Box>
                          </>
                        )}
                      </Box>
                    ))}
                  </>
                ) : (
                  // Single attempt
                  <>
                    {codeHistory[0].error && (
                      <Alert severity="error" sx={{ mb: 2, fontFamily: "monospace", fontSize: "0.72rem", whiteSpace: "pre-wrap" }}>
                        {codeHistory[0].error}
                      </Alert>
                    )}
                    <Box sx={{ maxHeight: "20rem", overflow: "auto", borderRadius: 1, border: "1px solid #ddd", mb: 2 }}>
                      <SyntaxHighlighter language="python" style={vscDarkPlus} showLineNumbers customStyle={{ margin: 0, fontSize: "0.75rem" }}>
                        {codeHistory[0].code || "# No code available"}
                      </SyntaxHighlighter>
                    </Box>
                  </>
                )}
              </>
            )}

            {/* ── EXECUTION LOGS ── */}
            {execLogs && execLogs !== "None" && (
              <>
                <Typography fontWeight={600} mb={1}>Execution Logs</Typography>
                <Box sx={{
                  fontFamily: "monospace", fontSize: "0.70rem", whiteSpace: "pre-wrap",
                  bgcolor: "#1e1e1e", color: "#d4d4d4", p: 1.5, borderRadius: 1,
                  maxHeight: "400px", overflow: "auto", mb: 2,
                  border: "1px solid #333",
                }}>
                  {execLogs}
                </Box>
              </>
            )}
          </Box>
        );
      })()}
    </Box>
  );
};

export default ETLDashboard;