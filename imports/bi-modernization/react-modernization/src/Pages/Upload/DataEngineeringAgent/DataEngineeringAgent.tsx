import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from '../../CodeGen/CodeGenComponents/button.tsx';
import { ArrowLeft, ArrowRight, Check, X, CheckCircle } from 'lucide-react';

interface StatusItem {
    type: "info" | "success" | "error";
    message: string;
    timestamp: string;
}

const DataEngineeringAgent = () => {
    const navigate = useNavigate();
    const eventSourceRef = useRef<EventSource | null>(null);

    const [jiraUrl, setJiraUrl] = useState("");
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [issueKey, setIssueKey] = useState("");

    const [loading, setLoading] = useState(false);
    const [progress, setProgress] = useState(0);
    const [progressText, setProgressText] = useState("Initializing...");
    const [statusLogs, setStatusLogs] = useState<StatusItem[]>([]);
    const [result, setResult] = useState<any>(null);

    useEffect(() => {
        return () => {
            eventSourceRef.current?.close();
        };
    }, []);

    const addStatusLog = (type: "info" | "success" | "error", message: string) => {
        const timestamp = new Date().toLocaleTimeString();
        setStatusLogs((prev) => [...prev, { type, message, timestamp }]);
    };

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();

        setLoading(true);
        setProgress(0);
        setResult(null);
        setStatusLogs([]);
        setProgressText("Initializing...");

        const apiBase = 'https://xcompanion.dataeconomy.ai:7010';

        const sseUrl =
            `${apiBase}/api/v1/intent/sql/databricks-etl/jira/stream?` +
            `jira_url=${encodeURIComponent(jiraUrl)}&` +
            `username=${encodeURIComponent(username)}&` +
            `password=${encodeURIComponent(password)}&` +
            `issue_key=${encodeURIComponent(issueKey)}`;

        eventSourceRef.current?.close();
        const eventSource = new EventSource(sseUrl);
        eventSourceRef.current = eventSource;

        eventSource.addEventListener("progress", (e: any) => {
            const data = JSON.parse(e.data);
            setProgress(data.progress || 0);
            setProgressText(data.message);
            addStatusLog("info", data.message);
        });

        eventSource.addEventListener("success", (e: any) => {
            const data = JSON.parse(e.data);
            setProgress(data.progress || 100);
            addStatusLog("success", data.message);
            setResult(data);
        });

        eventSource.addEventListener("complete", () => {
            addStatusLog("success", "Pipeline generation completed.");
            setLoading(false);
            eventSource.close();
        });

        eventSource.onerror = () => {
            addStatusLog("error", "Connection error occurred.");
            setLoading(false);
            eventSource.close();
        };
    };

    return (
        <div style={styles.page}>

    {/* CONSTRAINED WRAPPER (same width as card) */}
    <div className="max-w-4xl mx-auto px-6">

        {/* Header Row */}
        <div className="relative flex items-center justify-center mb-4">

            {/* Back Button (inside boundary) */}
            <div className="absolute left-[-70px]">
                <Button
                    variant="outline"
                    className="flex items-center gap-2 border-2 border-blue-600 !text-blue-600 hover:bg-blue-50 font-medium"
                    onClick={() => navigate('/')}
                >
                    <ArrowLeft className="w-4 h-4" />
                    Back
                </Button>
            </div>

            {/* Heading */}
            <div className="font-extrabold tracking-tight leading-none text-center">
                <span className="bg-gradient-to-r from-[#003087] to-[#C5162D] bg-clip-text text-transparent !text-6xl md:!text-6xl lg:!text-6xl font-extrabold">
                    Data Engineering Agent
                </span>
            </div>
        </div>

        {/* Tagline */}
        <p className="text-center text-gray-600 text-sm font-bold mb-14">
            Generate and deploy automated data pipelines on Databricks
        </p>

    </div>

            {/* CARD */}
            <div style={styles.card}>
                <form onSubmit={handleSubmit}>
                    <Input label="Jira URL" icon="🔗" value={jiraUrl} setValue={setJiraUrl} />
                    <Input label="Username" icon="👤" value={username} setValue={setUsername} />
                    <Input
                        label="API Token"
                        icon="🔑"
                        type="password"
                        value={password}
                        setValue={setPassword}
                    />
                    <Input
                        label="Issue Key"
                        icon="🎫"
                        value={issueKey}
                        setValue={setIssueKey}
                    />

                    <button type="submit" style={styles.button} disabled={loading}>
                        {loading ? "Processing..." : "Generate Pipeline"}
                    </button>
                </form>

                {loading && (
                    <div style={{ marginTop: 30 }}>
                        <div style={styles.progressBarBackground}>
                            <div
                                style={{
                                    ...styles.progressBar,
                                    width: `${progress}%`,
                                }}
                            />
                        </div>
                        <div style={styles.progressText}>
                            {progressText} ({progress}%)
                        </div>
                    </div>
                )}

                {statusLogs.length > 0 && (
                    <div style={styles.logContainer}>
                        {statusLogs.map((log, index) => (
                            <div key={index} style={styles.logItem(log.type)}>
                                <strong>[{log.timestamp}]</strong> {log.message}
                            </div>
                        ))}
                    </div>
                )}

                {result && (
                    <div style={styles.resultCard}>
                        <h4>Pipeline Deployed Successfully</h4>
                        <div style={styles.resultRow}>
                            <span>Pipeline ID:</span>
                            <strong>{result.pipeline_id}</strong>
                        </div>
                        <div style={styles.resultRow}>
                            <span>Catalog:</span>
                            <strong>{result.catalog}</strong>
                        </div>
                        <div style={styles.resultRow}>
                            <span>Schema:</span>
                            <strong>{result.schema}</strong>
                        </div>

                        <a
                            href={result.pipeline_url}
                            target="_blank"
                            rel="noreferrer"
                            style={styles.link}
                        >
                            Open in Databricks →
                        </a>
                    </div>
                )}
            </div>
        </div>
    );
};

/* Reusable Input */
const Input = ({
    label,
    value,
    setValue,
    type = "text",
    icon,
}: any) => (
    <div style={{ marginBottom: 22 }}>
        <label style={styles.label}>{label}</label>
        <div style={styles.inputWrapper}>
            <span style={styles.inputIcon}>{icon}</span>
            <input
                type={type}
                value={value}
                onChange={(e) => setValue(e.target.value)}
                required
                style={styles.input}
            />
        </div>
    </div>
);

/* STYLES */
const styles: any = {
    page: {
        minHeight: "100vh",
        background: "linear-gradient(135deg,#f5f7fa,#c3cfe2)",
        padding: "40px 20px",
    },
    topBar: {
        maxWidth: 900,
        margin: "0 auto 20px auto",
    },
    backButton: {
        background: "transparent",
        border: "none",
        fontWeight: 600,
        fontSize: 15,
        cursor: "pointer",
    },
    heroSection: {
        textAlign: "center",
        marginBottom: 40,
    },
    heroTitle: {
        fontSize: 42,
        fontWeight: 700,
        marginBottom: 10,
    },
    heroSubtitle: {
        fontSize: 16,
        opacity: 0.7,
    },
    card: {
        maxWidth: 900,
        margin: "0 auto",
        background: "#fff",
        padding: 40,
        borderRadius: 20,
        boxShadow: "0 30px 80px rgba(0,0,0,0.12)",
    },
    label: {
        fontWeight: 600,
        fontSize: 14,
        marginBottom: 6,
        display: "block",
    },
    inputWrapper: {
        position: "relative",
    },
    inputIcon: {
        position: "absolute",
        left: 12,
        top: "50%",
        transform: "translateY(-50%)",
    },
    input: {
        width: "100%",
        padding: "12px 12px 12px 38px",
        borderRadius: 10,
        border: "1px solid #ccc",
    },
    button: {
        marginTop: 15,
        padding: "14px",
        borderRadius: 12,
        border: "none",
        background: "#000",
        color: "#fff",
        fontWeight: 600,
        width: "100%",
        cursor: "pointer",
    },
    progressBarBackground: {
        width: "100%",
        height: 10,
        background: "#eee",
        borderRadius: 10,
    },
    progressBar: {
        height: 10,
        background: "#000",
        borderRadius: 10,
        transition: "width 0.4s ease",
    },
    progressText: {
        marginTop: 8,
        fontSize: 14,
    },
    logContainer: {
        marginTop: 30,
        maxHeight: 250,
        overflowY: "auto",
        background: "#f8f9fa",
        padding: 15,
        borderRadius: 12,
    },
    logItem: (type: string) => ({
        padding: 6,
        fontSize: 13,
        color:
            type === "success"
                ? "green"
                : type === "error"
                    ? "red"
                    : "#333",
    }),
    resultCard: {
        marginTop: 30,
        padding: 20,
        borderRadius: 14,
        background: "#e6f4ea",
    },
    resultRow: {
        display: "flex",
        justifyContent: "space-between",
        marginBottom: 8,
    },
    link: {
        display: "inline-block",
        marginTop: 15,
        fontWeight: 600,
        textDecoration: "none",
        color: "#000",
    },
};

export default DataEngineeringAgent;
