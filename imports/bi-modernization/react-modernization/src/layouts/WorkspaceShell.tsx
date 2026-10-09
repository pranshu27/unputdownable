/**
 * WorkspaceShell.tsx
 * Main 3-panel workspace layout: Explorer | Center | Details
 * With top bar, bottom drawer, and global search.
 */
import React, { useState, useMemo, useCallback } from 'react';
import { Outlet, useOutletContext, useNavigate, useLocation } from 'react-router-dom';
import WorkspaceTopBar from './WorkspaceTopBar.tsx';
import WorkspaceExplorer from './WorkspaceExplorer.tsx';
import EnterpriseMetadataPanel from '../core/enterprise/EnterpriseMetadataPanel.tsx';
import EnterpriseBottomDrawer, { LogPanel } from '../core/enterprise/EnterpriseBottomDrawer.tsx';
import ChatWidget from '../core/ChatWidget.jsx';
import { TreeNode } from '../core/enterprise/EnterpriseExplorerTree.tsx';
import { useSelector } from 'react-redux';
import { selectAllJobs } from '../utils/jobTrackerSlice.ts';
import { Terminal, Activity, Table2, Database, Hash, Columns3, LayoutGrid } from 'lucide-react';

interface Props {
  sideNavWidth: number;
  model: any;
}

export default function WorkspaceShell({ sideNavWidth, model }: Props) {
  const navigate = useNavigate();
  const location = useLocation();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [selectedEntity, setSelectedEntity] = useState<TreeNode | null>(null);
  const allJobs = useSelector(selectAllJobs);

  const fileName = localStorage.getItem('activePowerBiReportFile') || '';

  // Determine if a workspace has been loaded and is active
  const isWorkspaceActive = useMemo(() => {
    return model && 
           !['/migration', '/upload', '/data', '/sttm', '/login', '/signup', '/files'].includes(location.pathname);
  }, [model, location.pathname]);

  const handleEntitySelect = useCallback((node: TreeNode) => {
    setSelectedEntity(node);
    setDetailsOpen(true);
  }, []);

  // Build detail sections for selected entity
  const detailSections = useMemo(() => {
    if (!selectedEntity) return [];
    const meta = selectedEntity.meta || {};
    const sections: any[] = [];

    if (selectedEntity.type === 'table') {
      sections.push({
        title: 'Properties',
        fields: [
          { label: 'Name', value: meta.name, mono: true },
          { label: 'Type', value: meta.table_type || 'dimension' },
          { label: 'Columns', value: String(meta.columns?.length || 0) },
          { label: 'Materialized', value: meta.is_materialized ? 'Yes' : 'No' },
          { label: 'Description', value: meta.description },
        ],
      });
    } else if (selectedEntity.type === 'column') {
      sections.push({
        title: 'Column Properties',
        fields: [
          { label: 'Name', value: meta.name, mono: true },
          { label: 'Table', value: meta.tableName },
          { label: 'Data Type', value: meta.data_type || 'string' },
          { label: 'Nullable', value: meta.nullable ? 'Yes' : 'No' },
          { label: 'Hidden', value: meta.hidden ? 'Yes' : 'No' },
          { label: 'Semantic Role', value: meta.semantic_role },
        ],
      });
      sections.push({
        title: 'Usage',
        fields: [
          { label: 'In Relationships', value: meta.used_in_relationships ? '✓' : '—' },
          { label: 'In Filters', value: meta.used_in_filters ? '✓' : '—' },
          { label: 'In Calculations', value: meta.used_in_calculations ? '✓' : '—' },
          { label: 'In GroupBy', value: meta.used_in_groupby ? '✓' : '—' },
        ],
      });
    } else if (selectedEntity.type === 'source') {
      sections.push({
        title: 'Data Source',
        fields: [
          { label: 'Name', value: meta.name, mono: true },
          { label: 'Type', value: meta.type || meta.connection_type },
          { label: 'Connection', value: meta.connection_string, mono: true },
        ],
      });
    } else if (selectedEntity.type === 'kpi') {
      sections.push({
        title: 'KPI Details',
        fields: [
          { label: 'Name', value: meta.kpi_name },
          { label: 'Definition', value: meta.business_definition },
          { label: 'Confidence', value: meta.confidence },
          { label: 'Classification', value: meta.classification },
        ],
      });
    } else if (selectedEntity.type === 'measure') {
      sections.push({
        title: 'Measure',
        fields: [
          { label: 'Name', value: meta.name, mono: true },
          { label: 'Table', value: meta.table_name },
          { label: 'Expression', value: meta.expression, mono: true },
        ],
      });
    }

    return sections;
  }, [selectedEntity]);

  // Build bottom drawer tabs
  const jobLogs = useMemo(() => {
    return Object.values(allJobs)
      .filter((j: any) => j.status !== 'idle')
      .flatMap((j: any) => (j.logs || []).map((msg: string) => ({
        time: new Date().toLocaleTimeString(), message: msg, level: 'info' as const,
      })));
  }, [allJobs]);

  const drawerTabs = [
    { id: 'logs', label: 'Logs', icon: <Terminal size={12} />, badge: jobLogs.length, content: <LogPanel logs={jobLogs} /> },
    { id: 'progress', label: 'Progress', icon: <Activity size={12} />, content: <div style={{ padding: 12, color: 'var(--text-tertiary)', fontSize: 'var(--text-xs)' }}>Background task progress appears here</div> },
  ];

  // STEP 1 & STEP 2: Render simplified setup view if workspace is not active yet
  if (!isWorkspaceActive) {
    return (
      <div style={{
        display: 'flex', flexDirection: 'column', height: '100vh',
        background: 'var(--surface-bg)', overflow: 'hidden',
      }}>
        {/* Simplified Setup Header */}
        <header style={{
          height: 'var(--topbar-height)', display: 'flex', alignItems: 'center',
          padding: '0 24px', background: 'var(--surface-card)',
          borderBottom: '1px solid var(--border-secondary)', flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{
              width: 28, height: 28, borderRadius: 'var(--radius-md)',
              background: 'var(--jnj-red)', display: 'flex',
              alignItems: 'center', justifyContent: 'center',
            }}>
              <LayoutGrid size={14} color="#fff" />
            </div>
            <span style={{
              fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--text-primary)',
              letterSpacing: 'var(--tracking-tight)',
            }}>
              BI Modernization
            </span>
          </div>
          <div style={{ flex: 1 }} />
        </header>

        {/* Content taking full workspace space */}
        <div style={{ flex: 1, overflow: 'auto', background: 'var(--surface-bg)', position: 'relative' }}>
          <Outlet context={{ sideNavWidth: 0, model }} />
        </div>
      </div>
    );
  }

  // STEP 3: Render complete active workspace shell
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', height: '100vh',
      background: 'var(--surface-bg)', overflow: 'hidden',
    }}>
      {/* Refactored Header */}
      <WorkspaceTopBar onSearchOpen={() => {}} fileName={fileName} />

      {/* Main workspace */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Left Explorer */}
        <WorkspaceExplorer
          model={model}
          collapsed={sidebarCollapsed}
          onToggleCollapse={() => setSidebarCollapsed(prev => !prev)}
          onEntitySelect={handleEntitySelect}
        />

        {/* Center Content */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div style={{ flex: 1, overflow: 'hidden', background: 'var(--surface-bg)', position: 'relative' }}>
            <Outlet context={{ sideNavWidth: 0, model }} />
          </div>

          {/* Bottom Drawer */}
          <EnterpriseBottomDrawer tabs={drawerTabs} />
        </div>

        {/* Right Details Panel */}
        {detailsOpen && selectedEntity && (
          <EnterpriseMetadataPanel
            title={selectedEntity.label}
            subtitle={selectedEntity.type}
            icon={
              selectedEntity.type === 'table' ? <Table2 size={14} /> :
              selectedEntity.type === 'column' ? <Columns3 size={14} /> :
              selectedEntity.type === 'source' ? <Database size={14} /> :
              <Hash size={14} />
            }
            sections={detailSections}
            onClose={() => { setDetailsOpen(false); setSelectedEntity(null); }}
          />
        )}
      </div>

      {/* Chat Widget (replacing GlobalJobTracker) */}
      <ChatWidget />
    </div>
  );
}
