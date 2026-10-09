import React, { useState } from "react";
import UploadScreen from "../components/STTMUpload.tsx";
import ResultsScreen from "../components/STTMResult.tsx";
import { ArrowLeft } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from '../../CodeGen/CodeGenComponents/button.tsx';
export default function STTMAgent() {
  const navigate = useNavigate();

  const [screen, setScreen] = useState("upload");
  const [files, setFiles] = useState({
    business_analysis: null,
    meeting_minutes: null,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [resultData, setResultData] = useState(null);
  const API_BASE_URL ='https://xcompanion.dataeconomy.ai:7011'
  const handleFileChange = (key, file) => {
    setFiles((prev) => ({ ...prev, [key]: file }));
    setError(null);
  };

  const handleSubmit = async () => {
    setLoading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("business_analysis", files.business_analysis);
      formData.append("meeting_minutes", files.meeting_minutes);
      const response = await fetch(`${API_BASE_URL}/generate-mapping`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errBody = await response.json().catch(() => null);
        throw new Error(errBody?.detail || `Server error (${response.status})`);
      }

      const data = await response.json();
      setResultData(data);
      setScreen("results");
    } catch (err) {
      setError(err.message || "Backend connection failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleBack = () => {
    setScreen("upload");
    setFiles({
      business_analysis: null,
      meeting_minutes: null,
    });
    setResultData(null);
    setError(null);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#F4F6F9] to-[#E8F4FD]">

  {/* 🔹 SHARED HEADER WRAPPER */}
  <div className="max-w-7xl mx-auto px-6 pt-16 relative">

    {/* Back Button */}
    <div className="absolute left-20 top-20">
      <Button
        variant="outline"
        className="flex items-center gap-2 border-2 border-blue-600 !text-blue-600 hover:bg-blue-50 font-medium"
        onClick={() => navigate('/')}
      >
        <ArrowLeft className="w-4 h-4" />
        Back
      </Button>
    </div>

    {/* MAIN CONTENT */}
    <div className="pb-10">
      {screen === "upload" && (
        <UploadScreen
          files={files}
          onFileChange={handleFileChange}
          onSubmit={handleSubmit}
          loading={loading}
          error={error}
        />
      )}

      {screen === "results" && resultData && (
        <ResultsScreen data={resultData} onBack={handleBack} />
      )}
    </div>

  </div>

</div>

  )}
