import React, { useState, useEffect } from 'react';
import { Database, Loader2, FileSearch, Brain, CheckCircle, FileCode, Clock3, X, Search, Filter, ArrowLeft } from 'lucide-react';
import { Button } from '../CodeGen/CodeGenComponents/button.tsx';
import { cn } from '../../Lib/utils.ts';
import { fetchPowerBiReport, listPowerBiReports, ReportListItem } from '../../services/powerbiReports.ts';
import { useDispatch } from 'react-redux';
import { setApiData } from "../../utils/DataSlice.ts";
import { setFormData } from '../../utils/formSlice.ts';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';

const ExistingReportsDashboard = () => {
  const [databaseReports, setDatabaseReports] = useState<ReportListItem[]>([]);
  const [isLoadingDatabaseReports, setIsLoadingDatabaseReports] = useState(false);
  const [databaseReportsError, setDatabaseReportsError] = useState<string | null>(null);
  const [selectedDatabaseReport, setSelectedDatabaseReport] = useState<ReportListItem | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  
  const [searchQuery, setSearchQuery] = useState('');
  const [filterTool, setFilterTool] = useState<string>('all');

  const dispatch = useDispatch();
  const navigate = useNavigate();

  const loadDatabaseReports = async () => {
    setIsLoadingDatabaseReports(true);
    setDatabaseReportsError(null);
    try {
      const reports = await listPowerBiReports();
      setDatabaseReports(reports);
    } catch (err) {
      setDatabaseReportsError('Failed to fetch processed reports from database.');
      console.error(err);
    } finally {
      setIsLoadingDatabaseReports(false);
    }
  };

  useEffect(() => {
    loadDatabaseReports();
  }, []);

  const selectDatabaseReport = (report: ReportListItem) => {
    if (selectedDatabaseReport?.report_id === report.report_id && selectedDatabaseReport?.file_name === report.file_name) {
      setSelectedDatabaseReport(null);
    } else {
      setSelectedDatabaseReport(report);
    }
  };

  const analyzeDatabaseReport = async () => {
    if (!selectedDatabaseReport) return;
    setIsAnalyzing(true);
    try {
      const etlTool = selectedDatabaseReport.tool_type === 'tableau-workbook' ? 'tableau-workbook' : 'powerbi';
      
      toast.info('Analyzing Report', {
        description: `Fetching details for ${selectedDatabaseReport.file_name}...`
      });

      const reportPayload = await fetchPowerBiReport(
        selectedDatabaseReport.file_name,
        etlTool,
        { reportId: selectedDatabaseReport.report_id }
      );

      const activeBaseName = selectedDatabaseReport.file_name.substring(0, selectedDatabaseReport.file_name.lastIndexOf('.')) || selectedDatabaseReport.file_name;
      
      localStorage.removeItem('pairedPowerBiReports');
      localStorage.setItem('activePowerBiReportFile', selectedDatabaseReport.file_name);
      localStorage.setItem('activePowerBiReportId', selectedDatabaseReport.report_id || '');
      localStorage.setItem('activePowerBiReportData', JSON.stringify(reportPayload));
      localStorage.setItem('fileDetails', JSON.stringify({
        fileName: activeBaseName,
        etlTool: etlTool,
        model: 'gemini-1.5-pro', // default
        technology: 'React',
        framework: 'MUI',
      }));

      dispatch(setApiData(reportPayload));
      dispatch(setFormData({
        fileName: activeBaseName,
        etlTool: etlTool,
        model: 'gemini-1.5-pro',
        technology: 'React',
        framework: 'MUI',
      }));

      toast.success('Report Loaded', {
        description: `${selectedDatabaseReport.file_name} successfully loaded.`
      });

      navigate('/overview');
    } catch (error) {
      console.error(error);
      toast.error('Analysis Failed', {
        description: 'Failed to fetch the report payload from the database.'
      });
    } finally {
      setIsAnalyzing(false);
    }
  };

  const filteredReports = databaseReports.filter(report => {
    const matchesSearch = report.file_name.toLowerCase().includes(searchQuery.toLowerCase());
    const toolType = report.tool_type === 'tableau-workbook' ? 'tableau' : 'powerbi';
    const matchesFilter = filterTool === 'all' || toolType === filterTool;
    return matchesSearch && matchesFilter;
  });

  return (
    <div className="min-h-screen bg-slate-50 p-8">
      {/* Header Section */}
      <div className="mb-6">
        <button 
          onClick={() => navigate('/migration')}
          className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-800 transition-colors mb-4"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Workspace
        </button>
        <h1 className="text-2xl font-bold text-[#002147] tracking-tight">Existing Reports</h1>
        <p className="mt-1 text-sm text-slate-500">
          Open a report to continue analysis and validation.
        </p>
      </div>

      {databaseReportsError && (
        <div className="mb-4 shrink-0 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700 flex items-center gap-2">
          <X className="h-4 w-4" />
          {databaseReportsError}
        </div>
      )}

      {/* Main Table Card */}
      <div className="bg-white border border-slate-200 rounded-lg shadow-sm">
        
        {/* Sticky Toolbar (Attached to Table) */}
        <div className="sticky top-0 z-30 bg-white/95 backdrop-blur border-b border-slate-200 p-4 rounded-t-lg flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
              <input
                type="text"
                placeholder="Search files..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="h-9 w-64 rounded-lg border border-slate-200 pl-9 pr-4 text-sm outline-none transition-colors focus:border-[#002147] focus:ring-1 focus:ring-[#002147]"
              />
            </div>
            <div className="relative">
              <Filter className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
              <select
                value={filterTool}
                onChange={(e) => setFilterTool(e.target.value)}
                className="h-9 appearance-none rounded-lg border border-slate-200 bg-white pl-9 pr-8 text-sm outline-none transition-colors focus:border-[#002147] focus:ring-1 focus:ring-[#002147]"
              >
                <option value="all">All Types</option>
                <option value="powerbi">Power BI</option>
                <option value="tableau">Tableau</option>
              </select>
              <div className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2">
                <svg className="h-4 w-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"></path></svg>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {selectedDatabaseReport && (
              <span className="text-xs font-semibold text-[#002147] bg-[#002147]/5 border border-[#002147]/10 px-3 py-1.5 rounded-md mr-1">
                1 report selected
              </span>
            )}
            <Button
              type="button"
              onClick={loadDatabaseReports}
              disabled={isLoadingDatabaseReports}
              variant="outline"
              className="flex h-9 items-center gap-2 rounded-lg border border-slate-200 px-3 text-sm font-semibold text-slate-700 hover:bg-slate-50"
            >
              {isLoadingDatabaseReports ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileSearch className="h-4 w-4" />}
              {isLoadingDatabaseReports ? 'Fetching...' : 'Refresh'}
            </Button>
            <Button
              type="button"
              onClick={analyzeDatabaseReport}
              disabled={!selectedDatabaseReport || isAnalyzing}
              className={cn(
                'flex h-9 items-center gap-2 rounded-lg px-4 text-sm font-semibold transition-all',
                selectedDatabaseReport && !isAnalyzing
                  ? 'bg-[#c8102e] text-white hover:bg-[#a30d24] shadow-sm'
                  : 'bg-slate-200 text-slate-500 cursor-not-allowed'
              )}
            >
              {isAnalyzing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Brain className="h-4 w-4" />}
              Open Workspace
            </Button>
          </div>
        </div>

        {/* Data Grid */}
        {filteredReports.length > 0 ? (
          <table className="w-full text-left text-sm">
            <thead className="sticky top-[69px] z-20 bg-slate-50/95 backdrop-blur border-b border-slate-200 shadow-sm">
              <tr>
                <th className="px-6 py-4 font-semibold text-slate-600">Report Name</th>
                <th className="px-6 py-4 font-semibold text-slate-600">Platform</th>
                <th className="px-6 py-4 font-semibold text-slate-600">Status</th>
                <th className="px-6 py-4 font-semibold text-slate-600 text-right">Last Updated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredReports.map((report) => {
                const isSelected =
                  selectedDatabaseReport?.report_id === report.report_id &&
                  selectedDatabaseReport?.file_name === report.file_name;
                const toolLabel = report.tool_type === 'tableau-workbook' ? 'Tableau' : 'Power BI';
                
                return (
                  <tr
                    key={report.report_id || `${report.tool_type}-${report.file_name}`}
                    onClick={() => selectDatabaseReport(report)}
                    className={cn(
                      "cursor-pointer transition-colors hover:bg-slate-50 group",
                      isSelected ? "bg-[#c8102e]/5 border-l-2 border-[#c8102e]" : "border-l-2 border-transparent"
                    )}
                  >
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className={cn(
                          "flex h-9 w-9 items-center justify-center rounded-lg border transition-colors",
                          isSelected ? "border-[#c8102e] bg-[#c8102e] text-white" : "border-slate-200 bg-white text-slate-500 group-hover:border-[#c8102e]/30 group-hover:text-[#c8102e]"
                        )}>
                          {isSelected ? <CheckCircle className="h-4 w-4" /> : <FileCode className="h-4 w-4" />}
                        </div>
                        <span className={cn(
                          "font-semibold",
                          isSelected ? "text-[#c8102e]" : "text-slate-900"
                        )}>
                          {report.file_name}
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span className="inline-flex items-center rounded-md bg-slate-100 px-2 py-1 text-xs font-medium text-slate-600">
                        {toolLabel}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span className={cn(
                        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold",
                        isSelected ? "bg-[#002147] text-white" : "bg-emerald-50 text-emerald-700"
                      )}>
                        {isSelected ? 'Selected' : 'Ready'}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      {report.completed_at ? (
                        <div className="flex items-center justify-end gap-1.5 text-slate-500">
                          <Clock3 className="h-3.5 w-3.5" />
                          <span>{new Date(report.completed_at).toLocaleString()}</span>
                        </div>
                      ) : (
                        <span className="text-slate-400">-</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <div className="flex h-[400px] flex-col items-center justify-center text-slate-400">
            <Database className="mb-3 h-10 w-10 opacity-20" />
            <p className="font-semibold text-slate-600">No reports available yet.</p>
            <p className="mt-1 text-sm">Upload a Power BI or Tableau file to begin analysis.</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default ExistingReportsDashboard;
