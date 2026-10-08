/**
 * WorkspaceTopBar.tsx
 * Refactored enterprise top bar aligned with professional corporate layout guidelines.
 */
import React, { useEffect, useState, useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useSelector } from 'react-redux';
import { Sun, Moon, Bell, ChevronRight, LayoutGrid, CheckCircle2, AlertCircle, LogOut, Braces, X, Loader2 } from 'lucide-react';
import { useTheme } from '../utils/ThemeContext.tsx';
import GlobalSearch from '../Pages/Components/GlobalSearch.tsx';
import { Drawer, IconButton } from '@mui/material';
import { fetchPowerBiReport, listPowerBiReports } from '../services/powerbiReports.ts';

interface Props {
  onSearchOpen: () => void;
  fileName?: string;
}

const routeLabels: Record<string, string> = {
  '/files': 'Files',
  '/overview': 'Overview',
  '/datasources': 'Data Sources',
  '/tables': 'Tables',
  '/relationships': 'Report Explorer',
  '/dataflow': 'Data Flow',
  '/calculations': 'Calculations',
  '/consolidated-model': 'Catalog',
  '/kpiLineage': 'KPI Lineage',
  '/gap-analysis': 'Gap Analysis',
  '/bussiness-metadata': 'Business Metadata',
  '/intelligence-hub': 'Intelligence Hub',
  '/validations': 'Validation',
  '/validations/forward/new': 'Validation',
  '/validation-report': 'Validation',
  '/validation-dashboard': 'Validation',
  '/technicalSummary': 'Summary',
  '/code-gen': 'Code Generation',
  '/upload': 'Upload',
  '/migration': 'Migration',
  '/analyze': 'Analyze',
  '/lineage': 'Lineage',
};

export default function WorkspaceTopBar({ fileName, onSearchOpen }: Props) {
  const { theme, toggleTheme, isDark } = useTheme();
  const location = useLocation();
  const navigate = useNavigate();

  const currentLabel = routeLabels[location.pathname] || (location.pathname.includes('validation') ? 'Validation' : 'Workspace');

  const [reports, setReports] = useState<any[]>([]);
  const [selectedVersion, setSelectedVersion] = useState('');
  const [isJsonDrawerOpen, setIsJsonDrawerOpen] = useState(false);

  const activeFileLabel = fileName || localStorage.getItem('activePowerBiReportFile') || '';

  const runningValidationJob = useSelector((state: any) => {
    if (!state?.jobTracker?.jobs) return undefined;
    return Object.values(state.jobTracker.jobs).find(
      (j: any) => j.type === 'validation' && j.fileName === activeFileLabel
    ) as any;
  });

  const getToolName = (name: string) => {
    const n = String(name || "").toLowerCase();
    if (n.endsWith(".pbix")) return "powerbi";
    if (n.endsWith(".twb") || n.endsWith(".twbx")) return "tableau-workbook";
    return "powerbi";
  };

  const rawJsonData = useMemo(() => {
    try {
      return JSON.parse(localStorage.getItem('activePowerBiReportData') || '{}');
    } catch {
      return {};
    }
  }, [activeFileLabel, selectedVersion]);

  useEffect(() => {
    if (!activeFileLabel) return;

    let mounted = true;
    const loadReports = async () => {
      const [powerBiList, tableauList] = await Promise.all([
        listPowerBiReports('powerbi').catch(() => []),
        listPowerBiReports('tableau-workbook').catch(() => []),
      ]);

      if (!mounted) return;

      const combined = [...powerBiList, ...tableauList]
        .filter((report) => report.file_name === activeFileLabel)
        .sort(
          (a, b) =>
            new Date(b.completed_at || 0).getTime() -
            new Date(a.completed_at || 0).getTime()
        );

      setReports(combined);
      
      const activeReportId = localStorage.getItem('activePowerBiReportId') || '';
      if (activeReportId && combined.some(r => r.report_id === activeReportId)) {
        setSelectedVersion(activeReportId);
      } else if (combined[0]?.report_id) {
        setSelectedVersion(combined[0].report_id);
      }
    };

    loadReports();

    const handleReportChanged = () => {
      const activeReportId = localStorage.getItem('activePowerBiReportId') || '';
      if (activeReportId) setSelectedVersion(activeReportId);
    };
    window.addEventListener('jnj:active-report-changed', handleReportChanged);

    return () => {
      mounted = false;
      window.removeEventListener('jnj:active-report-changed', handleReportChanged);
    };
  }, [activeFileLabel]);

  const handleVersionChange = async (versionId: string) => {
    setSelectedVersion(versionId);

    const selectedReportVersion = reports.find((report) => report.report_id === versionId);
    if (!selectedReportVersion) return;

    try {
      const reportData = await fetchPowerBiReport(
        selectedReportVersion.file_name,
        selectedReportVersion.tool_type || getToolName(selectedReportVersion.file_name),
        { reportId: selectedReportVersion.report_id }
      );
      
      const reportBaseName =
        selectedReportVersion.file_name.substring(0, selectedReportVersion.file_name.lastIndexOf('.')) ||
        selectedReportVersion.file_name;

      localStorage.setItem('activePowerBiReportFile', selectedReportVersion.file_name);
      localStorage.setItem('activePowerBiReportId', selectedReportVersion.report_id || '');
      localStorage.setItem('activePowerBiReportData', JSON.stringify(reportData));
      localStorage.setItem(
        'fileDetails',
        JSON.stringify({
          ...(JSON.parse(localStorage.getItem('fileDetails') || '{}')),
          fileName: reportBaseName,
          etlTool: selectedReportVersion.tool_type || getToolName(selectedReportVersion.file_name),
        })
      );

      window.dispatchEvent(new CustomEvent('jnj:active-report-changed'));
    } catch (error) {
      console.error('Failed to change version:', error);
    }
  };

  return (
    <header style={{
      height: 'var(--topbar-height)', display: 'flex', alignItems: 'center',
      padding: '0 16px', gap: '12px',
      background: 'var(--surface-card)', borderBottom: '1px solid var(--border-secondary)',
      flexShrink: 0, zIndex: 100,
    }}>
      
      {/* ── LEFT SECTOR: LOGO + DATASET BREADCRUMBS ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
        {/* Workspace Brand */}
        <div 
          style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}
          onClick={() => navigate('/files')}
        >
          <div style={{
            width: 24, height: 24, borderRadius: 'var(--radius-sm)',
            background: 'var(--jnj-red)', display: 'flex',
            alignItems: 'center', justifyContent: 'center',
          }}>
            <LayoutGrid size={12} color="#fff" />
          </div>
          <span style={{
            fontSize: '12.5px', fontWeight: 700, color: 'var(--text-primary)',
            letterSpacing: 'var(--tracking-tight)',
          }}>
            JNJ Modernization
          </span>
        </div>

        {/* Separator */}
        <span style={{ color: 'var(--border-primary)', fontSize: '12px' }}>|</span>

        {/* Breadcrumb Hierarchy */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 4,
          fontSize: '11px', color: 'var(--text-tertiary)',
        }}>
          {fileName && (
            <>
              <span 
                style={{
                  maxWidth: 110, overflow: 'hidden', textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap', cursor: 'pointer', fontWeight: 500,
                }} 
                onClick={() => navigate('/overview')}
                title={fileName}
              >
                {fileName}
              </span>
              {reports.length > 0 && (
                <select
                  value={selectedVersion}
                  onChange={(e) => handleVersionChange(e.target.value)}
                  style={{
                    background: 'var(--jnj-red-light)',
                    color: 'var(--jnj-red)',
                    border: '1px solid rgba(200, 16, 46, 0.15)',
                    borderRadius: '12px',
                    padding: '0 6px',
                    fontSize: '9.5px',
                    fontWeight: 700,
                    cursor: 'pointer',
                    outline: 'none',
                    height: '18px',
                    display: 'inline-flex',
                    alignItems: 'center',
                    margin: '0 4px',
                    boxSizing: 'border-box',
                    transform: 'translateY(0.5px)',
                  }}
                >
                  {reports.map((report, index) => (
                    <option key={report.report_id} value={report.report_id}>
                      v{reports.length - index}
                    </option>
                  ))}
                </select>
              )}
              <ChevronRight size={9} style={{ color: 'var(--text-tertiary)' }} />
            </>
          )}
          <span style={{ color: 'var(--text-primary)', fontWeight: 'bold' }}>{currentLabel}</span>
        </div>
      </div>

      {/* ── CENTER SECTOR: COMMAND GLOBAL SEARCH ── */}
      <div style={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center', minWidth: 280 }}>
        <GlobalSearch />
      </div>

      {/* ── RIGHT SECTOR: ACTIONS + METADATA METRICS ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
        
        {/* Gap Analysis link */}
        <button
          onClick={() => navigate('/gap-analysis')}
          style={{
            display: 'flex', alignItems: 'center', gap: 4,
            padding: '3px 6px', fontSize: '10.5px', fontWeight: 600,
            borderRadius: '4px', border: 'none',
            background: location.pathname === '/gap-analysis' ? 'var(--surface-secondary)' : 'transparent',
            color: 'var(--text-secondary)',
            cursor: 'pointer', transition: 'all var(--transition-fast)',
            outline: 'none',
          }}
        >
          <AlertCircle size={12} style={{ color: 'var(--color-warning)' }} />
          <span>Intelligence Hub</span>
        </button>

        {/* Separator */}
        <span style={{ color: 'var(--border-secondary)', fontSize: '12px', margin: '0 4px' }}>|</span>

        {/* Notifications */}
        <button 
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--text-secondary)', display: 'flex', padding: 4,
          }}
          title="Notifications"
        >
          <Bell size={14} />
        </button>

        {/* Raw JSON View */}
        {activeFileLabel && (
          <button
            onClick={() => setIsJsonDrawerOpen(true)}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: 'var(--text-secondary)', display: 'flex', padding: 4,
            }}
            title="View raw API response JSON"
          >
            <Braces size={14} />
          </button>
        )}

        {/* Theme Toggle */}
        <button
          onClick={toggleTheme}
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--text-secondary)', display: 'flex', padding: 4,
          }}
          title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {isDark ? <Sun size={14} /> : <Moon size={14} />}
        </button>

        {/* Profile / Logout */}
        <button
          onClick={() => {
            localStorage.removeItem('isLoggedIn');
            navigate('/login');
          }}
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--text-secondary)', display: 'flex', padding: 4,
          }}
          title="Sign Out"
        >
          <LogOut size={14} />
        </button>
      </div>
      <Drawer
        anchor="right"
        open={isJsonDrawerOpen}
        onClose={() => setIsJsonDrawerOpen(false)}
        style={{ zIndex: 99999 }}
      >
        <div style={{ display: 'flex', height: '100%', width: 680, flexDirection: 'column', background: '#fff', fontFamily: 'var(--font-sans)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border-secondary)', padding: '16px 24px' }}>
            <div>
              <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>Raw API Response</h2>
              <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--text-tertiary)' }}>{activeFileLabel}</p>
            </div>
            <IconButton onClick={() => setIsJsonDrawerOpen(false)}>
              <X size={16} />
            </IconButton>
          </div>
          <div style={{ flex: 1, overflow: 'auto', background: '#1c1917', padding: 20 }}>
            <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-all', fontSize: 12, color: '#4ade80', fontFamily: 'var(--font-mono)' }}>
              {JSON.stringify(rawJsonData, null, 2)}
            </pre>
          </div>
        </div>
      </Drawer>

    </header>
  );
}
