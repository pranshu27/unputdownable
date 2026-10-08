import { useState, useCallback,useEffect, useRef  } from "react";
import { toast } from "sonner";
import type {
  JiraCredentials,
  JiraBoard,
  TargetPlatform,
  TicketUploadExtras,
  TicketCreationPayload,
} from "../types/api.ts";
import {
  authenticateJira,
  createJiraTicket,
  generateCode,
  commitToGitHub,
  generateTestCases,
} from "../services/api.ts";
import type { ConnectionStatus } from "../Pages/CodeGen/CodeGenComponents/StatusIndicator.tsx"; 
import { useDispatch, useSelector } from 'react-redux'; 
import { RootState } from '../utils/Store.ts';
import { storeCode, storeTestCasesCode,storeETL, storeSelectedBoard, storeSelectedPlatform, storeTicketKey } from "../utils/codegen.ts";
import test from "node:test";
export interface WorkflowState {
  // Auth state
  isAuthenticated: boolean;
  connectionStatus: ConnectionStatus;
  credentials: JiraCredentials | null;
  boards: JiraBoard[];
  
  // Board & Ticket state
  selectedBoard: JiraBoard | null;
  ticketKey: string | null;

  // Platform & Code state
  selectedPlatform: TargetPlatform | null;
  generatedCode: string | null;
  codeLanguage: string;
  hasGeneratedCode: boolean;

  // Raw API response (used by ETL Dashboard)
  apiResponse: any | null;
  
  // Test cases state (PySpark only)
  hasTestCases: boolean;
  testCasesCode: string | null;
  
  // Commit state
  isCommitted: boolean;
  commitUrl: string | null;
  
  // Loading states
  isAuthenticating: boolean;
  isCreatingTicket: boolean;
  isGenerating: boolean;
  isGeneratingTestCases: boolean;
  isCommitting: boolean;
}

const initialState: WorkflowState = {
  isAuthenticated: false,
  connectionStatus: "disconnected",
  credentials: null,
  boards: [],
  selectedBoard: null,
  ticketKey: null,
  selectedPlatform: null,
  generatedCode: null,
  codeLanguage: "python",
  hasGeneratedCode: false,
  apiResponse: null,
  hasTestCases: false,
  testCasesCode: null,
  isCommitted: false,
  commitUrl: null,
  isAuthenticating: false,
  isCreatingTicket: false,
  isGenerating: false,
  isGeneratingTestCases: false,
  isCommitting: false,
};

// State to reset when creating a new ticket
const getTicketResetState = (): Partial<WorkflowState> => ({
  selectedPlatform: null,
  generatedCode: null,
  codeLanguage: "python",
  hasGeneratedCode: false,
  apiResponse: null,
  hasTestCases: false,
  testCasesCode: null,
  isCommitted: false,
  commitUrl: null,
});

export function useWorkflow() {
  console.log("Initializing workflow hook...");
  const dispatch = useDispatch();
  const codeFromRedux = useSelector((state: RootState) => state.codeGen.code);
  const testCasesCodeFromRedux = useSelector((state: RootState) => state.codeGen.testCasesCode);
  const selectedBoardFromRedux = useSelector((state: RootState) => state.codeGen.selectedBoard);
  const selectedPlatformFromRedux = useSelector((state: RootState) => state.codeGen.selectedPlatform);
  const ticketKeyFromRedux = useSelector((state: RootState) => state.codeGen.ticketKey);
  const [state, setState] = useState<WorkflowState>( {
    ...initialState,
    generatedCode: codeFromRedux,
    hasTestCases: codeFromRedux ? true : false,
    testCasesCode: testCasesCodeFromRedux,
    selectedBoard: selectedBoardFromRedux,
    selectedPlatform: selectedPlatformFromRedux,
    ticketKey: ticketKeyFromRedux, // Sync ticketKey with ticketKey from Redux
    hasGeneratedCode: testCasesCodeFromRedux ? true : false,
    apiResponse: useSelector((state: RootState) => state.codeGen.ETLdata) || null,
  });
  console.log("Initial workflow state:", state);
  const apiData = useSelector((state: RootState) => state.apiData.data);
  const analyzeData = apiData ;
  const { selectedFile, etlTool, model, technology } = useSelector((state: RootState) => state.form);
  const reduxData = useSelector((state: RootState) => state.form);
  const dataToUse = reduxData;
  const fileDetails = dataToUse.selectedFile !== null ? dataToUse : JSON.parse(localStorage.getItem('fileDetails') as any);

  useEffect(() => {
    const savedCreds = localStorage.getItem("jira_credentials");
  
    if (!savedCreds) return;
  
    const creds = JSON.parse(savedCreds);
  
    authenticate(creds.username, creds.apiToken, creds.baseUrl);
  }, []); 

  // Authentication
  const authenticate = useCallback(
    async (username: string, apiToken: string, baseUrl: string) => {
      setState((prev) => ({
        ...prev,
        isAuthenticating: true,
        connectionStatus: "pending",
      }));

      const result = await authenticateJira({
        username,
        apiToken,
        baseUrl,
      });

      if (result.success) {
        setState((prev) => ({
          ...prev,
          isAuthenticated: true,
          connectionStatus: "connected",
          credentials: { username, apiToken, baseUrl },
          boards: result.boards,
          isAuthenticating: false,
        }));
        toast.success("Successfully connected to JIRA");
      } else {
        setState((prev) => ({
          ...prev,
          connectionStatus: "disconnected",
          isAuthenticating: false,
        }));
        toast.error(result.error || "Authentication failed");
        throw new Error(result.error);
      }
    },
    []
  );

  // Board selection
  const selectBoard = useCallback((board: JiraBoard) => {

    dispatch(storeSelectedBoard(board)); // Store selected board in Redux

    setState((prev) => ({
      ...prev,
      selectedBoard: board,
    }));
  }, [dispatch]);

  const extractTicketKey = (message: string): string | null => {
    const match = message.match(/\b[A-Z]+-\d+\b/);
    return match ? match[0] : null;
  };

  // Create ticket - RESETS all downstream state
  const createTicket = useCallback(
    async (data: {
      board: string;
      summary: string;
      description: string;
      issueType: string;
      etlTool?: string;
    }) => {
      setState((prev) => ({ ...prev, isCreatingTicket: true }));
  
      const selectedBoard = state.boards.find((b) => b.id === data.board);
  
      let reResponses = Array.isArray(analyzeData) ? analyzeData : [analyzeData];
      const pairedReportsJson = localStorage.getItem('pairedPowerBiReports');
      console.log('Jira Payload Builder - pairedReportsJson from localStorage:', pairedReportsJson ? pairedReportsJson.substring(0, 100) + '...' : 'null');
      if (pairedReportsJson) {
        try {
          const parsed = JSON.parse(pairedReportsJson);
          console.log('Jira Payload Builder - parsed length:', Array.isArray(parsed) ? parsed.length : 'not an array');
          if (Array.isArray(parsed) && parsed.length > 0) {
            reResponses = parsed;
          }
        } catch (e) {
          console.error("Failed to parse paired reports", e);
        }
      }

      console.log('Jira Payload Builder - final reResponses length:', reResponses.length);

      const payload: TicketCreationPayload = {
        re_responses: reResponses,
        board_id: "GA" 
      };
  
      // ← add extras as second argument
      const extras: TicketUploadExtras = {
        file_name: fileDetails?.fileName ?? fileDetails?.selectedFile ?? '',
        etltool:   fileDetails?.etlTool  ?? data.etlTool ?? '',
      };
  
      const result = await createJiraTicket(payload, extras);
  
      if (result.success && result.ticketKey) {
        dispatch(storeTicketKey(result.ticketKey));
        setState((prev) => ({
          ...prev,
          ...getTicketResetState(),
          ticketKey:     result.ticketKey!,
          selectedBoard,
          isCreatingTicket: false,
        }));
        toast.success(`Ticket ${result.ticketKey} created successfully`);
        return result.ticketKey;
      } else {
        setState((prev) => ({ ...prev, isCreatingTicket: false }));
        toast.error(result.error || 'Failed to create ticket');
        throw new Error(result.error || 'Ticket creation failed');
      }
    },
    [state.boards, analyzeData, fileDetails, dispatch]  // ← removed createJiraTicket from deps
  );

  // Set issue key manually - RESETS all downstream state
  const setIssueKey = useCallback((key: string) => {
    const upperKey = key.toUpperCase();
    dispatch(storeTicketKey(upperKey)); // Store ticket key in Redux
    setState((prev) => {
      // Only reset if the key actually changed
      if (prev.ticketKey !== upperKey) {
        return {
          ...prev,
          ...getTicketResetState(),
          ticketKey: upperKey,
        };
      }
      return prev;
    });
  }, [dispatch]);

  // Platform selection
  const selectPlatform = useCallback((platform: TargetPlatform) => {
    dispatch(storeSelectedPlatform(platform)); // Store selected platform in Redux
    setState((prev) => ({
      ...prev,
      selectedPlatform: platform,
      // Reset code-related state when platform changes
      generatedCode: null,
      apiResponse: null,
      hasGeneratedCode: false,
      hasTestCases: false,
      testCasesCode: null,
      isCommitted: false,
    }));
  }, []);

  // Generate code
  const generate = useCallback(async () => {
    if (!state.credentials || !state.ticketKey || !state.selectedPlatform) {
      toast.error("Missing required information");
      return;
    }

    setState((prev) => ({ 
      ...prev, 
      isGenerating: true, 
      generatedCode: null,
      apiResponse: null,
      hasGeneratedCode: false,
      hasTestCases: false,
      testCasesCode: null,
    }));

    const result = await generateCode({
      base_url: state.credentials.baseUrl,
      email: state.credentials.username,
      api_token: state.credentials.apiToken,
      issue_id: state.ticketKey,
      etlTool: fileDetails?.etlTool, 
      technology: state.selectedPlatform,
    });

    if (result.success && result.data.combined_final_code) {
      setState((prev) => ({
        ...prev,
        generatedCode: result.data.combined_final_code,
        codeLanguage: result.language || "python",
        hasGeneratedCode: true,
        apiResponse: result.data,   // ← store full raw response
        isGenerating: false,
      }));
      toast.success("Code generated successfully");
      dispatch(storeCode(result.data.combined_final_code));
      dispatch(storeETL(result.data));
    } else {
      setState((prev) => ({ ...prev, isGenerating: false }));
      toast.error(result.error || "Failed to generate code");
    }
  }, [state.credentials, state.ticketKey, state.selectedPlatform]);

  // Generate test cases (PySpark ONLY)
  const generateTests = useCallback(async () => {
    // Guard: Only for PySpark and only after code is generated
    if (state.selectedPlatform !== "pyspark") {
      toast.error("Test cases are only available for PySpark");
      return;
    }

    if (!state.hasGeneratedCode || !state.generatedCode || !state.ticketKey) {
      toast.error("Generate code first before creating test cases");
      return;
    }

    setState((prev) => ({ ...prev, isGeneratingTestCases: true }));

    const result = await generateTestCases({
      jira_issue_id: state.ticketKey,
      code: state.generatedCode,
    });

    if (result.success && result.code) {
      setState((prev) => ({
        ...prev,
        hasTestCases: true,
        testCasesCode: result.code,
        generatedCode: result.code, // Update displayed code to test cases
        isGeneratingTestCases: false,
      }));
      dispatch(storeTestCasesCode(result.code)); // Store test cases code in Redux
      toast.success("Test cases generated successfully");
    } else {
      setState((prev) => ({ ...prev, isGeneratingTestCases: false }));
      toast.error(result.error || "Failed to generate test cases");
    }
  }, [state.selectedPlatform, state.hasGeneratedCode, state.generatedCode, state.ticketKey]);

  // Commit to GitHub
  const commit = useCallback(
    async (data: {
      repoUrl: string;
      token: string;
      branch: string;
      folder: string;
      fileName: string;
    }) => {
      if (!state.generatedCode) {
        toast.error("No code to commit");
        return { success: false };
      }

      setState((prev) => ({ ...prev, isCommitting: true }));

      const result = await commitToGitHub({
        repo_url: data.repoUrl,
        token: data.token,
        branch_name: data.branch,
        folder_name: data.folder,
        file_name: data.fileName,
        code: state.generatedCode,
        technology: state.selectedPlatform 
      });

      if (result.success) {
        setState((prev) => ({
          ...prev,
          isCommitted: true,
          commitUrl: result.commit_url || null,
          isCommitting: false,
          showGitHubPreview:true,
          githubRepoUrl:result.commit_url
        }));
        toast.success("Code committed to GitHub");
        return { success: true, commitUrl: result.commit_url, branch: result.branch, jiraFolder: result.jiraFolder };
      } else {
        setState((prev) => ({ ...prev, isCommitting: false }));
        toast.error(result.message || "Failed to commit");
        return { success: false };
      }
    },
    [state.generatedCode]
  );

  // Get default file name - accounts for test cases
  const getDefaultFileName = useCallback(() => {
    if (!state.ticketKey || !state.selectedPlatform) return "generated_code";
    
    const ticketBase = state.ticketKey.toLowerCase().replace("-", "_");
    
    // For PySpark with test cases, use notebook format
    if (state.selectedPlatform === "pyspark" && state.hasTestCases) {
      return `ai_generated_pyspark_testcases.ipynb`;
    }
    
    // For PySpark without test cases
    if (state.selectedPlatform === "pyspark") {
      return `ai_generated_pyspark.ipynb`;
    }
    
    // For other platforms
    const extensions: Record<TargetPlatform, string> = {
      "pyspark": ".ipynb",
      "pyspark-databricks": ".py",
      "bigquery": ".sql",
      "dbt": ".sql",
      "dataiku": ".py",
      "powerbi": ".dax",
      "snowflake": ".sql",
    };
    
    return `${ticketBase}_${state.selectedPlatform}${extensions[state.selectedPlatform] || ".py"}`;
  }, [state.ticketKey, state.selectedPlatform, state.hasTestCases]);

  // Check if test cases can be generated
  const canGenerateTestCases = useCallback(() => {
    return (
      state.selectedPlatform === "pyspark" &&
      state.hasGeneratedCode &&
      !state.hasTestCases &&
      !!state.generatedCode
    );
  }, [state.selectedPlatform, state.hasGeneratedCode, state.hasTestCases, state.generatedCode]);

  // Reset workflow
  const reset = useCallback(() => {
    setState(initialState);
  }, []);

  return {
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
    canGenerateTestCases,
    reset,
  };
}