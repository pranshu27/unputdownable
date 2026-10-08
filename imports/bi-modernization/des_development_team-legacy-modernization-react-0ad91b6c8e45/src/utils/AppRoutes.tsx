import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import TechnicalAnalysis from '../Pages/TechnicalAnalysis/TechnicalAnalysis.tsx';
import Source from '../Pages/Source/Source.tsx';
import Transformations from '../Pages/Transformations/Transformations.tsx';
import Output from '../Pages/Output/Output.tsx';
import LineageWrapper from '../Pages/Lineage/LineageWrapper.tsx';
import CodeGen from '../Pages/CodeGen/CodeGen.tsx';
import Layout from './Layout.tsx';
import WorkspaceShell from '../layouts/WorkspaceShell.tsx';
import LegacyModernization from '../Pages/LegacyModernization/LegacyModernization.tsx';
import Login from '../Pages/Login/Login.tsx';
import Upload from '../Pages/Upload/Upload.tsx';
import SearchHistory from '../Pages/SearchHistory/SearchHistory.tsx';
import Share from '../Pages/Share/Share.tsx';
import { useEffect, useState } from "react";
import { useDispatch } from "react-redux";
import { useLocation } from 'react-router-dom';
import sampleModel from '../data/sampleModel.ts';
import {storeCode, storeTestCasesCode, storeTicketKey, storeETL, storeSelectedBoard, storeSelectedPlatform} from '../utils/codegen.ts'
import { setSelectedCase } from "../utils/selectedCaseSlice.ts";
import ReEngineeringCards from '../Pages/Upload/components/ReEngineeringCards.tsx';
import DashboardAnalysis from '../Pages/Dashboards/Dashboard.tsx';
import DataModel from '../Pages/PowerBiPages/DataModel/DataModel.tsx';
import DataTransformation from '../Pages/PowerBiPages/DataTransformation/DataTransformation.tsx'
import TransformationTableau from '../Pages/PowerBiPages/DataTransformation/DataTransformTablue.tsx';
import Dax from '../Pages/PowerBiPages/Hierarchies/DaxMeasures.tsx';
import Hierarchies from '../Pages/PowerBiPages/Hierarchies/Hierarchies.tsx';
import ReportPages from '../Pages/PowerBiPages/Visualization/ReportPages.tsx';
import Relationships from '../Pages/PowerBiPages/Filters/Relationships.tsx';
import Filters from '../Pages/PowerBiPages/Filters/Filters.tsx';
import SheetsComponent from '../Pages/PowerBiPages/Sheets/Sheets.tsx';
import UploadPage from '../Pages/Upload/Upload.tsx';
import DataEngineeringAgent from '../Pages/Upload/DataEngineeringAgent/DataEngineeringAgent.tsx';
import STTMAgent from '../Pages/Upload/STTMAgent/STTMAgent.tsx';
import MigrationAgent from '../Pages/Upload/MigrationAgent/MigrationAgent.tsx';
import ExistingReportsDashboard from '../Pages/ExistingReports/ExistingReportsDashboard.tsx';
import QliksenseResults from '../Pages/PowerBiPages/DataTransformation/QliksenseTable.tsx';
import DataSourceTablue from '../Pages/PowerBiPages/DataSources/DataSourcesTablaeu.tsx';
import Tables from '../Pages/PowerBiPages/DataModel/Tables.tsx';
import Visualization from '../Pages/PowerBiPages/Visualization/Visualization.tsx';
import Overview from '../Pages/Components/Overview.tsx';
import DataSources from '../Pages/Components/DataSources.tsx';
import TablesExplorer from '../Pages/Components/TablesExplorer.tsx';
import RelationshipsGraph from '../Pages/Components/RelationshipsGraph.tsx';
import DataFlow from '../Pages/Components/DataFlow.tsx';
import Calculations from '../Pages/Components/Calculations.tsx';
import ExecutiveSummary from '../Pages/Components/ExecutiveSummary.tsx';
import KpiLineage from '../Pages/Components/KPILineage.tsx';
import DataCatalog from '../Pages/Components/DataSources.tsx';
import ConsolidatedModelTable from '../Pages/Components/Calculations.tsx';
import FilesDashboard from '../Pages/FilesDashboard/FilesDashboard.tsx';
import GapAnalysis from '../Pages/Components/GapAnalysis.tsx';
import UnifiedValidationDashboard from '../Pages/Validation/UnifiedValidationDashboard.tsx';
import ConsolidatedModel from '../Pages/Components/ConsolidatedModel.tsx';
import GlossaryDashboard from '../Pages/Components/LinkerAgent.tsx';
import FullLineage from '../Pages/Components/FullLineage.tsx';
import IntelligenceHub from '../Pages/IntelligenceHub/IntelligenceHub.tsx';
import ValidationCenter from '../Pages/Validation/ValidationCenter.tsx';
import ForwardValidationRun from '../Pages/Validation/ForwardValidationRun.tsx';
import ForwardValidationReportPage from '../Pages/Validation/ForwardValidationReportPage.tsx';

const normalizeId = (id) => {
  if (!id) return '';
  return id
    .toLowerCase()
    .replace('tbl_', '')
    .replace(/\s+/g, '_')
    .replace(/[^a-z0-9_]/g, '');
};

const getNormalizedModel = (model) => {
  if (!model) return model;
  return {
    ...model,
    tables: Array.isArray(model.tables) ? model.tables.map(t => ({
      ...t,
      normalized_id: normalizeId(t.id),
    })) : [],
    relationships: Array.isArray(model.relationships) ? model.relationships.map(rel => ({
      ...rel,
      left_normalized: normalizeId(rel.left_table_id),
      right_normalized: normalizeId(rel.right_table_id),
    })) : [],
  };
};

const emptyPowerBiModel = {
  ...sampleModel,
  name: 'No report selected',
  model_id: '',
  extracted_at: new Date(0).toISOString(),
  data_sources: [],
  tables: [],
  relationships: [],
  calculations: [],
  technical_summary: '',
  kpi_lineage: [],
};

const AppRoutes = ({sideNavWidth}) => {
  const isLoggedIn = localStorage.getItem('isLoggedIn');
  const dispatch = useDispatch();
  const location = useLocation();
  const [reportRevision, setReportRevision] = useState(0);
  
  useEffect(() => {
    const savedCase = localStorage.getItem('selectedCase');
    if (savedCase) {
      dispatch(setSelectedCase(savedCase));
    }
  }, [dispatch]);

  useEffect(() => {
  if (location.pathname === '/' || location.pathname === '/analyze') {
    // clear redux code state
    dispatch(storeCode(null));
    dispatch(storeTestCasesCode(null));
    dispatch(storeTicketKey(null));
    dispatch(storeETL(null));
    dispatch(storeSelectedBoard(null));
    dispatch(storeSelectedPlatform(null));
    //
    localStorage.removeItem('jira_credentials');
    // common clears
    localStorage.removeItem('generatedStoredCode');
    localStorage.removeItem('generatedcodeId');
    localStorage.removeItem('apiResponse');
    localStorage.removeItem('combinedFinalCode');
    localStorage.removeItem('testCasesCode');
    localStorage.removeItem('hasTestCases');
    localStorage.removeItem('originalGeneratedCode');
    localStorage.removeItem('showEditor');
    localStorage.removeItem('analyzeResponse');
    localStorage.removeItem('fileDetails');
    localStorage.removeItem('selectedCase');
    localStorage.removeItem('generatedtestCasesStoredCode');
    localStorage.removeItem('originalGeneratedCode');
    localStorage.removeItem('testCasesCode');
    localStorage.removeItem('content');
  }

  // 🔴 ONLY when path is '/'
  if (location.pathname === '/') {
    localStorage.removeItem('selectedWorkflow');
  }

}, [location.pathname]);

  useEffect(() => {
    const refreshActiveReport = () => setReportRevision((current) => current + 1);
    window.addEventListener('jnj:active-report-changed', refreshActiveReport);
    window.addEventListener('storage', refreshActiveReport);
    return () => {
      window.removeEventListener('jnj:active-report-changed', refreshActiveReport);
      window.removeEventListener('storage', refreshActiveReport);
    };
  }, []);

const getActivePowerBiModel = () => {
  const raw = localStorage.getItem('activePowerBiReportData');
  if (!raw) return emptyPowerBiModel;
  try {
    const report = JSON.parse(raw);
    const result = report?.result || report?.data || report?.report || report;
    return {
      ...emptyPowerBiModel,
      ...result,
      name: result?.name || result?.file_name || emptyPowerBiModel.name,
      model_id: result?.report_id || result?.model_id || emptyPowerBiModel.model_id,
      extracted_at: result?.completed_at || result?.extracted_at || new Date().toISOString(),
      data_sources: Array.isArray(result?.data_sources) ? result.data_sources : [],
      tables: Array.isArray(result?.tables) ? result.tables.map((table, index) => ({
        id: table.id || table.name || `table_${index}`,
        name: table.name || `Table ${index + 1}`,
        table_type: table.table_type || table.type || 'dimension',
        source_data_source_id: table.source_data_source_id || null,
        source_derived_from_table_id: table.source_derived_from_table_id || null,
        is_materialized: table.is_materialized ?? true,
        description: table.description || 'Loaded from Power BI report API.',
        columns: Array.isArray(table.columns) ? table.columns.map((column, columnIndex) => ({
          name: column.name || `Column ${columnIndex + 1}`,
          data_type: column.data_type || column.type || 'string',
          nullable: column.nullable ?? true,
          hidden: column.hidden ?? false,
          semantic_role: column.semantic_role || null,
          used_in_relationships: column.used_in_relationships ?? false,
          used_in_filters: column.used_in_filters ?? false,
          used_in_groupby: column.used_in_groupby ?? false,
          used_in_calculations: column.used_in_calculations ?? false,
          distinct_count_high: column.distinct_count_high ?? false,
          description: column.description || '',
        })) : [],
        ingestion: table.ingestion || { steps: [] },
      })) : [],
      relationships: Array.isArray(result?.relationships) ? result.relationships : [],
      calculations: Array.isArray(result?.calculations) ? result.calculations : Array.isArray(result?.measures) ? result.measures : [],
      kpi_lineage: Array.isArray(result?.kpi_lineage) ? result.kpi_lineage : [],
      visualizations: result?.visualizations || null,
    };
  } catch (error) {
    return emptyPowerBiModel;
  }
};
void reportRevision;
const activePowerBiModel = getActivePowerBiModel();
const activeNormalizedPowerBiModel = getNormalizedModel(activePowerBiModel);
  return (
    <Routes>
      <Route
       path="/"
       element={isLoggedIn ? <Navigate to="/migration" replace /> : <Navigate to="/login" replace />}
      />

      <Route
        path="/login"
        // element={!isLoggedIn ? <Login /> : <Navigate to="/" replace />}
        element={<Login />}
      />
      <Route
        path="/signup"
        element={<Login />}
      />
      {/* Enterprise Workspace Shell */}
      <Route element={<WorkspaceShell sideNavWidth={sideNavWidth} model={activePowerBiModel} />}>
        <Route path="/files" element={<FilesDashboard model={activePowerBiModel} />} />
        <Route path="/files/:fileId" element={<Overview model={activePowerBiModel} />} />
        <Route path="/files/:fileId/overview" element={<Overview model={activePowerBiModel} />} />
        <Route path="/overview" element={<Overview model={activePowerBiModel} />} />
        <Route path="/datasources" element={<DataSources model={activePowerBiModel} />} />
        <Route path="/tables" element={<TablesExplorer model={activePowerBiModel} />} />
        <Route path="/relationships" element={<RelationshipsGraph model={activeNormalizedPowerBiModel} />} />
        <Route path="/dataflow" element={<DataFlow model={activePowerBiModel} />} />
        <Route path="/calculations" element={<ConsolidatedModelTable model={activePowerBiModel} />} />
        <Route path="/consolidated-model" element={<ConsolidatedModel model={activePowerBiModel} />} />
        <Route path="/lineage" element={<FullLineage model={activePowerBiModel} />} />
        <Route path="/kpiLineage" element={<KpiLineage model={activePowerBiModel} />} />
        <Route path="/intelligence-hub" element={<IntelligenceHub />} />
        <Route path="/gap-analysis" element={<Navigate to="/intelligence-hub" replace />} />
        <Route path="/bussiness-metadata" element={<Navigate to="/intelligence-hub" replace />} />
        <Route path="/validations" element={<ValidationCenter />} />
        <Route path="/validations/forward/new" element={<ForwardValidationRun />} />
        <Route path="/validations/:reportId" element={<ForwardValidationReportPage />} />
        <Route path="/validation-dashboard" element={<UnifiedValidationDashboard model={activePowerBiModel} />} />
        {/* Legacy redirect or alternate mapping if needed */}
        <Route path="/validation-report" element={<UnifiedValidationDashboard model={activePowerBiModel} />} />
        <Route path="/technicalSummary" element={<ExecutiveSummary model={activePowerBiModel} />} />
        <Route path="/code-gen" element={<CodeGen />} />
        <Route path="/visualizations" element={<Visualization model={activePowerBiModel} />} />
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/analyze" element={<SearchHistory />} />
        <Route path="/share" element={<Share />} />
        <Route path="/data" element={<DataEngineeringAgent />} />
        <Route path="/sttm" element={<STTMAgent />} />
        <Route path="/migration" element={<MigrationAgent />} />
      </Route>
      <Route path="/existing-reports" element={<ExistingReportsDashboard />} />
    </Routes>
  );
};

export default AppRoutes;
