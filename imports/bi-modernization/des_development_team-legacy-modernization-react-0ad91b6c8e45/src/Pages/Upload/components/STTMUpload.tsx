import React from "react";
import { Box, Typography, Button } from "@mui/material";

export default function STTMUpload({
  files,
  onFileChange,
  onSubmit,
  loading,
  error,
}) {
  const FILES = [
    { key: "business_analysis", label: "Business Analysis" },
    { key: "meeting_minutes", label: "Meeting Minutes" },
  ];

  const allFilesSelected =
    files.business_analysis &&
    files.meeting_minutes;
  return (
    <Box sx={styles.wrapper}>
      {/* 🔹 Heading */}
      <Box sx={{ textAlign: "center", mb: 6 }}>
        <div className="font-extrabold tracking-tight leading-none">
          <span className="bg-gradient-to-r from-[#003087] to-[#C5162D] bg-clip-text text-transparent !text-6xl font-extrabold">
            STTM Agent
          </span>
        </div>

        <Typography sx={styles.subtitle}>
          Intelligent Source-to-Target Mapping Automation
        </Typography>
      </Box>

      {/* 🔹 Main Card */}
      <Box sx={styles.mainCard}>
        <Typography sx={styles.sectionTitle}>
          Upload Required Documentation
        </Typography>

        {error && (
          <Box sx={styles.errorBox}>
            <Typography sx={{ fontWeight: 600 }}>
              {error}
            </Typography>
          </Box>
        )}

        {/* 🔹 ROW LAYOUT (Not Grid) */}
        <Box sx={styles.rowContainer}>
          {FILES.map((file, index) => {
            const hasFile = files[file.key];

            return (
              <Box
                key={file.key}
                sx={{
                  ...styles.uploadCard,
                  borderColor: hasFile ? "#059669" : "#E5E7EB",
                }}
              >
                {/* Step Badge */}
                <Box sx={styles.stepBadge}>
                  Step {index + 1}
                </Box>

                <Typography sx={styles.cardTitle}>
                  {file.label}
                </Typography>

                <Typography sx={styles.cardSub}>
                  Upload document to proceed
                </Typography>

                <Box sx={styles.dropZone}>
                  {!hasFile ? (
                    <>
                      <Typography sx={styles.dropText}>
                        Drag & drop file
                      </Typography>

                      <Button
                        variant="outlined"
                        component="label"
                        sx={styles.chooseButton}
                      >
                        Select File
                        <input
                          type="file"
                          hidden
                          onChange={(e) =>
                            onFileChange(file.key, e.target.files?.[0])
                          }
                        />
                      </Button>
                    </>
                  ) : (
                    <>
                      <Typography sx={styles.fileName}>
                        {files[file.key].name}
                      </Typography>

                      <Typography sx={styles.successText}>
                        File uploaded successfully
                      </Typography>
                    </>
                  )}
                </Box>
              </Box>
            );
          })}
        </Box>

        {/* 🔹 Submit Button */}
        <Box sx={{ textAlign: "center", mt: 6 }}>
          <Button
            variant="contained"
            disabled={!allFilesSelected || loading}
            onClick={onSubmit}
            sx={styles.generateBtn}
          >
            {loading ? "Generating Mapping..." : "Generate Mapping"}
          </Button>
        </Box>
      </Box>
    </Box>
  );
}

/* 🔥 STYLES */

const styles = {
  wrapper: {
    padding: "0 20px 40px 20px",
  },

  subtitle: {
    mt: 3,
    fontSize: "18px",
    color: "#6B7280",
    fontWeight: 500,
  },

  mainCard: {
    maxWidth: "1200px",
    margin: "0 auto",
    background: "#ffffff",
    padding: "40px",
    borderRadius: "16px",
    boxShadow: "0 10px 30px rgba(0,0,0,0.05)",
  },

  sectionTitle: {
    fontSize: "20px",
    fontWeight: 700,
    mb: 5,
    color: "#111827",
  },

  /* ROW INSTEAD OF GRID */
  rowContainer: {
    display: "flex",
    gap: "24px",
    justifyContent: "space-between",
    flexWrap: "wrap",
  },

  uploadCard: {
    flex: 1,
    minWidth: "260px",
    border: "1.5px solid",
    borderRadius: "12px",
    padding: "24px",
    background: "#ffffff",
    transition: "all 0.25s ease",
    "&:hover": {
      boxShadow: "0 8px 20px rgba(0,0,0,0.08)",
      transform: "translateY(-2px)",
    },
  },

  stepBadge: {
    fontSize: "12px",
    fontWeight: 700,
    color: "#003087",
    mb: 2,
  },

  cardTitle: {
    fontSize: "16px",
    fontWeight: 600,
    mb: 1,
    color: "#1F2937",
  },

  cardSub: {
    fontSize: "13px",
    color: "#6B7280",
    mb: 3,
  },

  dropZone: {
    border: "1.5px dashed #D1D5DB",
    borderRadius: "10px",
    padding: "18px",
    textAlign: "center",
    background: "#FAFAFA",
  },

  dropText: {
    fontSize: "13px",
    color: "#6B7280",
    mb: 2,
  },

  chooseButton: {
    textTransform: "none",
    borderColor: "#003087",
    color: "#003087",
    fontWeight: 600,
    "&:hover": {
      borderColor: "#002060",
      background: "rgba(0,48,135,0.05)",
    },
  },

  fileName: {
    fontSize: "13px",
    fontWeight: 600,
    color: "#059669",
    wordBreak: "break-word",
  },

  successText: {
    fontSize: "12px",
    color: "#6B7280",
    mt: 1,
  },

  generateBtn: {
    background: "#003087",
    textTransform: "none",
    padding: "12px 50px",
    fontWeight: 700,
    fontSize: "14px",
    borderRadius: "8px",
    "&:hover": {
      background: "#002060",
    },
  },

  errorBox: {
    background: "#FEF2F2",
    border: "1px solid #FCA5A5",
    borderRadius: "8px",
    padding: "12px",
    mb: 4,
    color: "#B91C1C",
  },
};
