const REPORTS_API_BASE = 'http://20.72.80.42:8001';
const inferToolNameFromFile = (fileName?: string) => {
  const normalizedName = String(fileName || '').toLowerCase();
  if (normalizedName.endsWith('.pbix')) return 'powerbi';
  if (normalizedName.endsWith('.twb') || normalizedName.endsWith('.twbx')) return 'tableau-workbook';
  return '';
};

const normalizeToolName = (toolName?: string, fallbackFileName?: string) => {
  if (toolName === 'powerbi' || toolName === 'tableau-workbook') {
    return toolName;
  }

  const activeReportFile = localStorage.getItem('activePowerBiReportFile') || '';
  const inferredTool =
    inferToolNameFromFile(fallbackFileName) ||
    inferToolNameFromFile(activeReportFile);

  return inferredTool || 'powerbi';
};

const getToolName = () => {
  try {
    const fileDetails = JSON.parse(
      localStorage.getItem("fileDetails") || "{}"
    );

    return normalizeToolName(fileDetails?.etlTool, fileDetails?.fileName);
  } catch (error) {
    return "powerbi";
  }
};
export interface ReportListItem {
  report_id?: string;
  file_name: string;
  tool_type?: string;
  status?: string;
  completed_at?: string;
  runtime_seconds?: number;
}

export interface JobProgress {
  file_name?: string;

  status?: 'processing' | 'success' | 'failed' | string;

  overall_status?: 
    | 'processing'
    | 'completed'
    | 'failed'
    | string;

  error?: string;

  runtime?: number;
  runtime_seconds?: number;

  files?: Array<{
    file_name: string;
    status:
      | 'processing'
      | 'success'
      | 'failed'
      | string;

    error?: string;
    runtime?: number;
    runtime_seconds?: number;
  }>;
}

export async function listPowerBiReports(toolNameOverride?: string): Promise<ReportListItem[]> {
  const toolName = normalizeToolName(toolNameOverride || getToolName());
  const response = await fetch(`${REPORTS_API_BASE}/list-reports/?tool_name=${toolName}`);
  if (!response.ok) throw new Error(`Unable to load dataset history (${response.status})`);
  const data = await response.json();
  return Array.isArray(data) ? data : data?.reports || data?.data || [];
}

export async function fetchPowerBiReport(
  fileName: string,
  toolNameOverride?: string,
  options?: { reportId?: string }
): Promise<any> {
  try {
    const toolName = normalizeToolName(
      typeof toolNameOverride === "string"
        ? toolNameOverride
        : undefined,
      fileName
    );

    const body = new URLSearchParams();

    body.append("file_name", fileName);
    body.append("tool_name", toolName);

    if (options?.reportId) {
      body.append(
        "report_id",
        options.reportId
      );
    }

    const response = await fetch(
      `${REPORTS_API_BASE}/fetch-report/`,
      {
        method: "POST",
        headers: {
          "Content-Type":
            "application/x-www-form-urlencoded",
        },
        body: body.toString(),
      }
    );

    if (!response.ok) {
      throw new Error(
        `Unable to fetch dataset (${response.status})`
      );
    }

    const data = await response.json();
    const result = data?.result || data;

    // Ensure tool_type and file_name are embedded in the response payload
    // so they are correctly passed to Jira /chat and /upload-to-jira APIs
    if (typeof result === 'object' && result !== null) {
      if (!result.file_name) result.file_name = fileName;
      if (!result.tool_type) result.tool_type = toolName;
    }

    return result;
  } catch (error) {
    console.error(
      "fetchPowerBiReport failed:",
      error
    );

    throw error;
  }
}

export function uploadPowerBiDataset(
  files: File | File[],
  etlTool?: string | string[],
  modelId?: string,
  onProgress?: (progress: number) => void
): Promise<{ job_id: string; progress_url?: string; status?: string }> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    const formData = new FormData();
    const uploadFiles = Array.isArray(files) ? files : [files];
    const toolNames = Array.isArray(etlTool)
      ? etlTool.map((toolName, index) => normalizeToolName(toolName, uploadFiles[index]?.name))
      : uploadFiles.map((file) => normalizeToolName(etlTool, file.name));
    uploadFiles.forEach((file) => {
      formData.append('files', file);
    });
    toolNames.forEach((toolName) => {
      formData.append('etltools', toolName);
    });
    if (modelId) {
      formData.append('model', modelId);
    }

    request.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) onProgress(Math.round((event.loaded / event.total) * 100));
    };

    request.onload = () => {
      try {
        const data = JSON.parse(request.responseText || '{}');
        if (request.status >= 200 && request.status < 300 && data.job_id) resolve(data);
        else reject(new Error(data.error || data.detail || `Upload failed (${request.status})`));
      } catch (error) {
        reject(new Error('Upload failed: invalid server response'));
      }
    };

    request.onerror = () => reject(new Error('Upload failed: network error'));
    request.open('POST', `${REPORTS_API_BASE}/upload/batch/`);
    request.send(formData);
  });
}

export async function getJobProgress(jobId: string): Promise<JobProgress> {
  const response = await fetch(`${REPORTS_API_BASE}/jobs/${jobId}/progress`);
  if (!response.ok) throw new Error(`Unable to track job (${response.status})`);
  return response.json();
}
