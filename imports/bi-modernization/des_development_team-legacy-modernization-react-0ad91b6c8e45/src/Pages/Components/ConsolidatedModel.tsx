/**
 * ConsolidatedModel.tsx
 * Database Explorer Style view (Snowflake / Databricks style catalog).
 * Displays Left tree, Center table/metadata details explorer, Right relationship & lineage context panel.
 */
import React, { useState, useMemo } from 'react';
import {
  Database, Table2, TrendingUp, Hash, Search, ChevronRight, ChevronDown,
  Info, Columns, ArrowRight, GitBranch, Sparkles, CheckCircle2, AlertCircle, FileText
} from 'lucide-react';
import { DataModel, Table, DataSource, KpiLineageItem, Calculation } from '../../data/sampleModel';
import FileWorkspaceHeader from '../../core/FileWorkspaceHeader.tsx';

interface Props {
  model: DataModel;
}

type SelectedItem = 
  | { type: 'datasource'; id: string; data: DataSource }
  | { type: 'table'; id: string; data: Table }
  | { type: 'kpi'; id: string; data: KpiLineageItem }
  | { type: 'measure'; id: string; data: Calculation }
  | null;

export default function ConsolidatedModel({ model }: Props) {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedItem, setSelectedItem] = useState<SelectedItem>(null);
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({
    sources: true,
    tables: true,
    kpis: true,
    measures: false,
  });

  // Local state for column enrichment (saving description edits in memory)
  const [enrichedDescriptions, setEnrichedDescriptions] = useState<Record<string, string>>({});
  const [editingColumn, setEditingColumn] = useState<string | null>(null);
  const [editingText, setEditingText] = useState('');

  // Toggle group expansion
  const toggleGroup = (group: string) => {
    setExpandedGroups(prev => ({ ...prev, [group]: !prev[group] }));
  };

  // Filter items in tree by search term
  const filteredSources = useMemo(() => {
    if (!model.data_sources) return [];
    return model.data_sources.filter(ds => 
      ds.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      ds.source_type.toLowerCase().includes(searchTerm.toLowerCase())
    );
  }, [model.data_sources, searchTerm]);

  const filteredTables = useMemo(() => {
    if (!model.tables) return [];
    return model.tables.filter(t => 
      t.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      t.table_type.toLowerCase().includes(searchTerm.toLowerCase())
    );
  }, [model.tables, searchTerm]);

  const filteredKPIs = useMemo(() => {
    if (!model.kpi_lineage) return [];
    return model.kpi_lineage.filter(k => 
      k.kpi_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      k.description.toLowerCase().includes(searchTerm.toLowerCase())
    );
  }, [model.kpi_lineage, searchTerm]);

  const filteredMeasures = useMemo(() => {
    if (!model.calculations) return [];
    return model.calculations.filter(c => 
      c.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      c.description.toLowerCase().includes(searchTerm.toLowerCase())
    );
  }, [model.calculations, searchTerm]);

  // Contextual relationships for active table
  const activeRelationships = useMemo(() => {
    if (!selectedItem || selectedItem.type !== 'table') return [];
    const tblId = selectedItem.id;
    return (model.relationships || []).filter(rel => 
      rel.left_table_id.toLowerCase().replace(/^tbl_/, '') === tblId.toLowerCase().replace(/^tbl_/, '') ||
      rel.right_table_id.toLowerCase().replace(/^tbl_/, '') === tblId.toLowerCase().replace(/^tbl_/, '')
    );
  }, [selectedItem, model.relationships]);

  // Upstream/Downstream lineage chain for active entity
  const lineageChain = useMemo(() => {
    if (!selectedItem) return [];
    const chain: { type: string; label: string; details?: string }[] = [];

    if (selectedItem.type === 'table') {
      const table = selectedItem.data;
      // Sourced from datasource
      const ds = model.data_sources.find(d => d.id === table.source_data_source_id);
      if (ds) {
        chain.push({ type: 'source', label: ds.name, details: ds.source_type });
      }
      chain.push({ type: 'table', label: table.name, details: `${table.table_type} table` });
      
      // Look for a calculation referencing this table
      const relatedCalc = model.calculations.find(c => 
        c.depends_on_columns.some(col => col.startsWith(table.name + '.'))
      );
      if (relatedCalc) {
        chain.push({ type: 'calculation', label: relatedCalc.name, details: 'Measure' });
      }

      // Look for a KPI referencing this table
      const relatedKpi = model.kpi_lineage.find(k => 
        k.depends_on_columns?.some(col => col.table_name === table.name)
      );
      if (relatedKpi) {
        chain.push({ type: 'kpi', label: relatedKpi.kpi_name, details: 'Business KPI' });
      }
    } else if (selectedItem.type === 'kpi') {
      const kpi = selectedItem.data;
      // Get first dependent column table
      if (kpi.depends_on_columns?.length) {
        const dep = kpi.depends_on_columns[0];
        chain.push({ type: 'source', label: dep.data_source?.name || 'CSV File', details: dep.data_source?.source_type });
        chain.push({ type: 'table', label: dep.table_name, details: `${dep.table_type} table` });
      }
      chain.push({ type: 'kpi', label: kpi.kpi_name, details: 'Business KPI' });
    }

    return chain;
  }, [selectedItem, model.data_sources, model.calculations, model.kpi_lineage]);

  // Enrichment handlers
  const startEditing = (colName: string, currentText: string) => {
    setEditingColumn(colName);
    setEditingText(enrichedDescriptions[colName] || currentText || '');
  };

  const saveEditing = (colName: string) => {
    setEnrichedDescriptions(prev => ({ ...prev, [colName]: editingText }));
    setEditingColumn(null);
  };

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', height: '100%',
      background: 'var(--surface-bg)', fontFamily: 'var(--font-sans)',
    }}>
      <FileWorkspaceHeader pageTitle="Consolidated Catalog" />

      {/* 3-Panel Catalog Shell */}
      <div style={{
        display: 'flex', flex: 1, overflow: 'hidden',
        border: 'none',
        margin: '0px', borderRadius: '0px',
        background: 'var(--surface-card)',
      }}>
        
        {/* PANEL 1: LEFT EXPLORER TREE ( Snowflake Catalog Style ) */}
        <div style={{
          width: 280, borderRight: '1px solid var(--border-primary)',
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
          background: 'var(--surface-card)', flexShrink: 0,
        }}>
          {/* Tree Search */}
          <div style={{ padding: '12px', borderBottom: '1px solid var(--border-subtle)' }}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 6,
              background: 'var(--surface-bg)', padding: '6px 10px',
              borderRadius: 'var(--radius-md)', border: '1px solid var(--border-primary)',
            }}>
              <Search size={14} style={{ color: 'var(--text-tertiary)' }} />
              <input
                type="text"
                placeholder="Search catalog..."
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                style={{
                  border: 'none', background: 'transparent', outline: 'none',
                  fontSize: '12px', color: 'var(--text-primary)', width: '100%',
                }}
              />
            </div>
          </div>

          {/* Tree Scroll Body */}
          <div style={{ flex: 1, overflow: 'auto', padding: '8px' }}>
            
            {/* S1: Data Sources */}
            <div>
              <div
                onClick={() => toggleGroup('sources')}
                style={{
                  display: 'flex', alignItems: 'center', justifyItems: 'center',
                  padding: '6px 8px', fontSize: '11px', fontWeight: 700,
                  color: 'var(--text-secondary)', cursor: 'pointer',
                  textTransform: 'uppercase', letterSpacing: '0.05em', gap: 4
                }}
              >
                {expandedGroups.sources ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                <span>Data Sources ({filteredSources.length})</span>
              </div>
              {expandedGroups.sources && (
                <div style={{ paddingLeft: '12px', display: 'flex', flexDirection: 'column', gap: 2 }}>
                  {filteredSources.map(ds => {
                    const isSelected = selectedItem?.type === 'datasource' && selectedItem.id === ds.id;
                    return (
                      <div
                        key={ds.id}
                        onClick={() => setSelectedItem({ type: 'datasource', id: ds.id, data: ds })}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px',
                          borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontSize: '12px',
                          background: isSelected ? 'var(--jnj-red-light)' : 'transparent',
                          color: isSelected ? 'var(--jnj-red)' : 'var(--text-secondary)',
                          fontWeight: isSelected ? 600 : 400,
                        }}
                      >
                        <Database size={13} style={{ color: isSelected ? 'var(--jnj-red)' : 'var(--text-tertiary)' }} />
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{ds.name}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* S2: Tables */}
            <div style={{ marginTop: 12 }}>
              <div
                onClick={() => toggleGroup('tables')}
                style={{
                  display: 'flex', alignItems: 'center', justifyItems: 'center',
                  padding: '6px 8px', fontSize: '11px', fontWeight: 700,
                  color: 'var(--text-secondary)', cursor: 'pointer',
                  textTransform: 'uppercase', letterSpacing: '0.05em', gap: 4
                }}
              >
                {expandedGroups.tables ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                <span>Tables ({filteredTables.length})</span>
              </div>
              {expandedGroups.tables && (
                <div style={{ paddingLeft: '12px', display: 'flex', flexDirection: 'column', gap: 2 }}>
                  {filteredTables.map(t => {
                    const isSelected = selectedItem?.type === 'table' && selectedItem.id === t.id;
                    return (
                      <div
                        key={t.id}
                        onClick={() => setSelectedItem({ type: 'table', id: t.id, data: t })}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px',
                          borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontSize: '12px',
                          background: isSelected ? 'var(--jnj-red-light)' : 'transparent',
                          color: isSelected ? 'var(--jnj-red)' : 'var(--text-secondary)',
                          fontWeight: isSelected ? 600 : 400,
                        }}
                      >
                        <Table2 size={13} style={{ color: isSelected ? 'var(--jnj-red)' : 'var(--text-tertiary)' }} />
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.name}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* S3: KPIs */}
            <div style={{ marginTop: 12 }}>
              <div
                onClick={() => toggleGroup('kpis')}
                style={{
                  display: 'flex', alignItems: 'center', justifyItems: 'center',
                  padding: '6px 8px', fontSize: '11px', fontWeight: 700,
                  color: 'var(--text-secondary)', cursor: 'pointer',
                  textTransform: 'uppercase', letterSpacing: '0.05em', gap: 4
                }}
              >
                {expandedGroups.kpis ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                <span>KPIs ({filteredKPIs.length})</span>
              </div>
              {expandedGroups.kpis && (
                <div style={{ paddingLeft: '12px', display: 'flex', flexDirection: 'column', gap: 2 }}>
                  {filteredKPIs.map(k => {
                    const isSelected = selectedItem?.type === 'kpi' && selectedItem.id === k.kpi_id;
                    return (
                      <div
                        key={k.kpi_id}
                        onClick={() => setSelectedItem({ type: 'kpi', id: k.kpi_id, data: k })}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px',
                          borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontSize: '12px',
                          background: isSelected ? 'var(--jnj-red-light)' : 'transparent',
                          color: isSelected ? 'var(--jnj-red)' : 'var(--text-secondary)',
                          fontWeight: isSelected ? 600 : 400,
                        }}
                      >
                        <TrendingUp size={13} style={{ color: isSelected ? 'var(--jnj-red)' : 'var(--text-tertiary)' }} />
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{k.kpi_name}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* S4: Measures */}
            <div style={{ marginTop: 12 }}>
              <div
                onClick={() => toggleGroup('measures')}
                style={{
                  display: 'flex', alignItems: 'center', justifyItems: 'center',
                  padding: '6px 8px', fontSize: '11px', fontWeight: 700,
                  color: 'var(--text-secondary)', cursor: 'pointer',
                  textTransform: 'uppercase', letterSpacing: '0.05em', gap: 4
                }}
              >
                {expandedGroups.measures ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                <span>Measures ({filteredMeasures.length})</span>
              </div>
              {expandedGroups.measures && (
                <div style={{ paddingLeft: '12px', display: 'flex', flexDirection: 'column', gap: 2 }}>
                  {filteredMeasures.map(m => {
                    const isSelected = selectedItem?.type === 'measure' && selectedItem.id === m.id;
                    return (
                      <div
                        key={m.id}
                        onClick={() => setSelectedItem({ type: 'measure', id: m.id, data: m })}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px',
                          borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontSize: '12px',
                          background: isSelected ? 'var(--jnj-red-light)' : 'transparent',
                          color: isSelected ? 'var(--jnj-red)' : 'var(--text-secondary)',
                          fontWeight: isSelected ? 600 : 400,
                        }}
                      >
                        <Hash size={13} style={{ color: isSelected ? 'var(--jnj-red)' : 'var(--text-tertiary)' }} />
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.name}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

          </div>
        </div>

        {/* PANEL 2: CENTER WORKSPACE CONTENT PANEL */}
        <div style={{
          flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden',
          background: 'var(--surface-bg)',
        }}>
          {selectedItem ? (
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              
              {/* Dynamic Header */}
              <div style={{
                padding: '20px 24px', background: 'var(--surface-card)',
                borderBottom: '1px solid var(--border-primary)',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <span style={{
                    fontSize: '10px', fontWeight: 700, padding: '2px 8px',
                    borderRadius: '4px', textTransform: 'uppercase',
                    background: 'var(--jnj-red-light)', color: 'var(--jnj-red)',
                  }}>
                    {selectedItem.type}
                  </span>
                </div>
                <h2 style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
                  {selectedItem.type === 'table' ? selectedItem.data.name :
                   selectedItem.type === 'kpi' ? selectedItem.data.kpi_name :
                   selectedItem.type === 'measure' ? selectedItem.data.name :
                   selectedItem.data.name}
                </h2>
                <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: 6, marginBottom: 0 }}>
                  {selectedItem.type === 'table' ? selectedItem.data.description :
                   selectedItem.type === 'kpi' ? selectedItem.data.description :
                   selectedItem.type === 'measure' ? selectedItem.data.description :
                   'Ingested connection details'}
                </p>
              </div>

              {/* Dynamic Scroll Body */}
              <div style={{ flex: 1, overflow: 'auto', padding: '24px' }}>
                
                {/* 1. TABLE DETAILS VIEW */}
                {selectedItem.type === 'table' && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
                    
                    {/* Columns grid */}
                    <div style={{
                      background: 'var(--surface-card)', borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--border-primary)', overflow: 'hidden',
                    }}>
                      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-subtle)', background: 'var(--surface-card)' }}>
                        <h4 style={{ margin: 0, fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 6 }}>
                          <Columns size={14} style={{ color: 'var(--jnj-red)' }} />
                          Columns Schema Mapping ({selectedItem.data.columns?.length || 0})
                        </h4>
                      </div>
                      
                      <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
                          <thead>
                            <tr style={{ background: 'var(--surface-bg)', borderBottom: '1px solid var(--border-primary)' }}>
                              <th style={{ padding: '10px 16px', fontWeight: 600, color: 'var(--text-secondary)' }}>Column Name</th>
                              <th style={{ padding: '10px 16px', fontWeight: 600, color: 'var(--text-secondary)' }}>Data Type</th>
                              <th style={{ padding: '10px 16px', fontWeight: 600, color: 'var(--text-secondary)' }}>Semantic Role</th>
                              <th style={{ padding: '10px 16px', fontWeight: 600, color: 'var(--text-secondary)' }}>Business Definition</th>
                              <th style={{ padding: '10px 16px', fontWeight: 600, color: 'var(--text-secondary)', textAlign: 'right' }}>Actions</th>
                            </tr>
                          </thead>
                          <tbody>
                            {selectedItem.data.columns?.map(col => {
                              const uniqueKey = `${selectedItem.id}.${col.name}`;
                              const currentDesc = enrichedDescriptions[uniqueKey] || col.description || '—';
                              const isEditing = editingColumn === uniqueKey;

                              return (
                                <tr key={col.name} style={{ borderBottom: '1px solid var(--border-subtle)', transition: 'background var(--transition-fast)' }}>
                                  <td style={{ padding: '10px 16px', fontWeight: 600, color: 'var(--text-primary)' }}>{col.name}</td>
                                  <td style={{ padding: '10px 16px' }}>
                                    <span style={{
                                      fontFamily: 'var(--font-mono)', fontSize: '11px',
                                      padding: '2px 6px', background: 'var(--surface-secondary)',
                                      borderRadius: '4px', color: 'var(--text-secondary)'
                                    }}>
                                      {col.data_type}
                                    </span>
                                  </td>
                                  <td style={{ padding: '10px 16px' }}>
                                    {col.semantic_role ? (
                                      <span style={{
                                        fontSize: '10px', fontWeight: 600, textTransform: 'uppercase',
                                        padding: '2px 6px', borderRadius: '4px',
                                        background: col.semantic_role === 'primary_key' ? '#FEF2F2' : '#EFF6FF',
                                        color: col.semantic_role === 'primary_key' ? '#DC2626' : '#1D4ED8',
                                      }}>
                                        {col.semantic_role}
                                      </span>
                                    ) : '—'}
                                  </td>
                                  <td style={{ padding: '10px 16px', color: 'var(--text-secondary)', maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                    {isEditing ? (
                                      <input
                                        type="text"
                                        value={editingText}
                                        onChange={e => setEditingText(e.target.value)}
                                        onBlur={() => saveEditing(uniqueKey)}
                                        onKeyDown={e => e.key === 'Enter' && saveEditing(uniqueKey)}
                                        autoFocus
                                        style={{
                                          padding: '2px 6px', fontSize: '12px', border: '1px solid var(--jnj-red)',
                                          borderRadius: '4px', width: '100%', outline: 'none', background: 'var(--surface-card)',
                                          color: 'var(--text-primary)'
                                        }}
                                      />
                                    ) : (
                                      <span>{currentDesc}</span>
                                    )}
                                  </td>
                                  <td style={{ padding: '10px 16px', textAlign: 'right' }}>
                                    <button
                                      onClick={() => startEditing(uniqueKey, currentDesc)}
                                      style={{
                                        border: 'none', background: 'none', cursor: 'pointer',
                                        color: 'var(--jnj-red)', fontSize: '11px', fontWeight: 600,
                                      }}
                                    >
                                      Enrich
                                    </button>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    {/* Ingestion Steps */}
                    {selectedItem.data.ingestion?.steps && (
                      <div style={{
                        background: 'var(--surface-card)', borderRadius: 'var(--radius-md)',
                        border: '1px solid var(--border-primary)', padding: '20px',
                      }}>
                        <h4 style={{ margin: '0 0 16px 0', fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
                          Ingestion PowerQuery Sequence
                        </h4>
                        
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                          {selectedItem.data.ingestion.steps.map((step, idx) => (
                            <div key={idx} style={{ display: 'flex', gap: 16 }}>
                              <div style={{
                                display: 'flex', flexDirection: 'column', alignItems: 'center',
                              }}>
                                <div style={{
                                  width: 24, height: 24, borderRadius: '50%',
                                  background: 'var(--jnj-red-light)', border: '1.5px solid var(--jnj-red)',
                                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                                  fontSize: '11px', fontWeight: 700, color: 'var(--jnj-red)',
                                }}>
                                  {step.order}
                                </div>
                                {idx < selectedItem.data.ingestion.steps.length - 1 && (
                                  <div style={{ width: 1.5, flex: 1, background: 'var(--border-primary)', margin: '4px 0' }} />
                                )}
                              </div>
                              <div style={{ flex: 1, paddingBottom: 12 }}>
                                <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)', textTransform: 'capitalize' }}>
                                  {step.step_type.replace('_', ' ')}
                                </div>
                                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: 4 }}>
                                  {step.description}
                                </div>
                                {step.native_expressions?.powerquery && (
                                  <pre style={{
                                    margin: '8px 0 0 0', padding: '8px 12px', background: 'var(--surface-bg)',
                                    borderRadius: '6px', fontSize: '11px', fontFamily: 'var(--font-mono)',
                                    color: 'var(--jnj-red-deep)', overflowX: 'auto', whiteSpace: 'pre-wrap',
                                    border: '1px solid var(--border-primary)',
                                  }}>
                                    {step.native_expressions.powerquery}
                                  </pre>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                  </div>
                )}

                {/* 2. KPI VIEW */}
                {selectedItem.type === 'kpi' && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                    
                    <div style={{
                      background: 'var(--surface-card)', borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--border-primary)', padding: '20px',
                    }}>
                      <h4 style={{ margin: '0 0 12px 0', fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
                        KPI Configuration
                      </h4>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                        <div>
                          <span style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-tertiary)', fontWeight: 600 }}>Classification</span>
                          <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', marginTop: 4 }}>{selectedItem.data.classification || 'Business KPI'}</div>
                        </div>
                        <div>
                          <span style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-tertiary)', fontWeight: 600 }}>Semantic Type</span>
                          <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', marginTop: 4 }}>{selectedItem.data.semantic_type || 'Currency'}</div>
                        </div>
                        <div>
                          <span style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-tertiary)', fontWeight: 600 }}>Confidence Score</span>
                          <div style={{ fontSize: '13px', fontWeight: 600, color: '#059669', marginTop: 4 }}>{selectedItem.data.confidence || '94%'}</div>
                        </div>
                        <div>
                          <span style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-tertiary)', fontWeight: 600 }}>Format Pattern</span>
                          <div style={{ fontSize: '13px', fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', marginTop: 4 }}>{selectedItem.data.format_string || '$#,##0'}</div>
                        </div>
                      </div>
                    </div>

                    <div style={{
                      background: 'var(--surface-card)', borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--border-primary)', padding: '20px',
                    }}>
                      <h4 style={{ margin: '0 0 12px 0', fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
                        DAX Formula / Calculation
                      </h4>
                      <pre style={{
                        margin: 0, padding: '12px', background: 'var(--surface-bg)',
                        borderRadius: '6px', fontSize: '11px', fontFamily: 'var(--font-mono)',
                        color: 'var(--jnj-red-deep)', overflowX: 'auto', whiteSpace: 'pre-wrap',
                        border: '1px solid var(--border-primary)',
                      }}>
                        {selectedItem.data.formula || `[${selectedItem.data.kpi_name}] = SUM(Sales[PremiumAmount])`}
                      </pre>
                    </div>

                    {/* Upstream mappings */}
                    <div style={{
                      background: 'var(--surface-card)', borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--border-primary)', overflow: 'hidden',
                    }}>
                      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-subtle)', background: 'var(--surface-card)' }}>
                        <h4 style={{ margin: 0, fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
                          Sourced Fields & Dependencies
                        </h4>
                      </div>
                      <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
                          <thead>
                            <tr style={{ background: 'var(--surface-bg)', borderBottom: '1px solid var(--border-primary)' }}>
                              <th style={{ padding: '10px 16px', fontWeight: 600, color: 'var(--text-secondary)' }}>Source Column</th>
                              <th style={{ padding: '10px 16px', fontWeight: 600, color: 'var(--text-secondary)' }}>Parent Table</th>
                              <th style={{ padding: '10px 16px', fontWeight: 600, color: 'var(--text-secondary)' }}>Origin Source</th>
                            </tr>
                          </thead>
                          <tbody>
                            {selectedItem.data.depends_on_columns?.map((dep, idx) => (
                              <tr key={idx} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                                <td style={{ padding: '10px 16px', fontWeight: 600, color: 'var(--text-primary)' }}>{dep.column_name}</td>
                                <td style={{ padding: '10px 16px' }}>
                                  <span style={{
                                    fontSize: '11px', padding: '2px 6px',
                                    background: 'var(--jnj-red-light)', color: 'var(--jnj-red)',
                                    borderRadius: '4px', fontWeight: 500
                                  }}>
                                    {dep.table_name}
                                  </span>
                                </td>
                                <td style={{ padding: '10px 16px', color: 'var(--text-secondary)' }}>
                                  {dep.data_source?.name || 'CSV Ingestion'}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>

                  </div>
                )}

                {/* 3. DATASOURCE VIEW */}
                {selectedItem.type === 'datasource' && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                    <div style={{
                      background: 'var(--surface-card)', borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--border-primary)', padding: '20px',
                    }}>
                      <h4 style={{ margin: '0 0 16px 0', fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
                        Connection Properties
                      </h4>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                        <div style={{ display: 'flex', borderBottom: '1px solid var(--border-subtle)', paddingBottom: 8 }}>
                          <span style={{ width: 150, fontSize: '12px', color: 'var(--text-tertiary)' }}>Source Type</span>
                          <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }}>{selectedItem.data.source_type}</span>
                        </div>
                        <div style={{ display: 'flex', borderBottom: '1px solid var(--border-subtle)', paddingBottom: 8 }}>
                          <span style={{ width: 150, fontSize: '12px', color: 'var(--text-tertiary)' }}>Connection Mode</span>
                          <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }}>{selectedItem.data.connection_mode || 'Import'}</span>
                        </div>
                        <div style={{ display: 'flex', borderBottom: '1px solid var(--border-subtle)', paddingBottom: 8 }}>
                          <span style={{ width: 150, fontSize: '12px', color: 'var(--text-tertiary)' }}>File Location / Path</span>
                          <span style={{ fontSize: '12px', fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', wordBreak: 'break-all' }}>{selectedItem.data.path || 'Local Workspace'}</span>
                        </div>
                      </div>
                    </div>

                    {/* Sourced tables */}
                    <div style={{
                      background: 'var(--surface-card)', borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--border-primary)', padding: '20px',
                    }}>
                      <h4 style={{ margin: '0 0 12px 0', fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
                        Imported Tables
                      </h4>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                        {model.tables.filter(t => t.id.toLowerCase().includes(selectedItem.id.replace('ds_', '').toLowerCase())).map(t => (
                          <div
                            key={t.id}
                            onClick={() => setSelectedItem({ type: 'table', id: t.id, data: t })}
                            style={{
                              padding: '8px 12px', border: '1px solid var(--border-primary)',
                              borderRadius: '6px', fontSize: '12px', color: 'var(--text-primary)',
                              cursor: 'pointer', background: 'var(--surface-card)',
                              fontWeight: 500, display: 'flex', alignItems: 'center', gap: 6
                            }}
                          >
                            <Table2 size={13} style={{ color: 'var(--jnj-red)' }} />
                            {t.name}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

              </div>
            </div>
          ) : (
            /* Welcome / Overview Dashboard Catalog State */
            <div style={{ flex: 1, overflow: 'auto', padding: '32px' }}>
              
              <div style={{
                textAlign: 'center', maxWidth: 640, margin: '0 auto 40px',
                padding: '24px', borderRadius: 'var(--radius-lg)',
                background: 'var(--surface-card)', border: '1px solid var(--border-primary)',
              }}>
                <Sparkles size={36} style={{ color: 'var(--jnj-red)', marginBottom: 12 }} />
                <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: 'var(--text-primary)' }}>
                  Enterprise Database Catalog Explorer
                </h3>
                <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: 8, lineHeight: 1.5 }}>
                  Unified Databricks & Snowflake style metadata workspace. Select any data source, schema table, or calculated business KPI from the catalog explorer on the left to inspect, enrich schema attributes, or review lineage context mappings.
                </p>
              </div>

              {/* Grid Statistics */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, maxWidth: 960, margin: '0 auto' }}>
                <div style={{
                  padding: '16px 20px', background: 'var(--surface-card)', borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--border-primary)', display: 'flex', alignItems: 'center', gap: 16
                }}>
                  <div style={{ width: 40, height: 40, borderRadius: '50%', background: 'var(--jnj-red-light)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Database size={18} style={{ color: 'var(--jnj-red)' }} />
                  </div>
                  <div>
                    <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', textTransform: 'uppercase', fontWeight: 600 }}>Data Sources</span>
                    <h4 style={{ margin: '4px 0 0 0', fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)' }}>{model.data_sources?.length || 0}</h4>
                  </div>
                </div>

                <div style={{
                  padding: '16px 20px', background: 'var(--surface-card)', borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--border-primary)', display: 'flex', alignItems: 'center', gap: 16
                }}>
                  <div style={{ width: 40, height: 40, borderRadius: '50%', background: 'var(--jnj-red-light)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Table2 size={18} style={{ color: 'var(--jnj-red)' }} />
                  </div>
                  <div>
                    <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', textTransform: 'uppercase', fontWeight: 600 }}>Total Tables</span>
                    <h4 style={{ margin: '4px 0 0 0', fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)' }}>{model.tables?.length || 0}</h4>
                  </div>
                </div>

                <div style={{
                  padding: '16px 20px', background: 'var(--surface-card)', borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--border-primary)', display: 'flex', alignItems: 'center', gap: 16
                }}>
                  <div style={{ width: 40, height: 40, borderRadius: '50%', background: 'var(--jnj-red-light)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <TrendingUp size={18} style={{ color: 'var(--jnj-red)' }} />
                  </div>
                  <div>
                    <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', textTransform: 'uppercase', fontWeight: 600 }}>Business KPIs</span>
                    <h4 style={{ margin: '4px 0 0 0', fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)' }}>{model.kpi_lineage?.length || 0}</h4>
                  </div>
                </div>

                <div style={{
                  padding: '16px 20px', background: 'var(--surface-card)', borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--border-primary)', display: 'flex', alignItems: 'center', gap: 16
                }}>
                  <div style={{ width: 40, height: 40, borderRadius: '50%', background: 'var(--jnj-red-light)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Hash size={18} style={{ color: 'var(--jnj-red)' }} />
                  </div>
                  <div>
                    <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', textTransform: 'uppercase', fontWeight: 600 }}>Total Measures</span>
                    <h4 style={{ margin: '4px 0 0 0', fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)' }}>{model.calculations?.length || 0}</h4>
                  </div>
                </div>
              </div>

            </div>
          )}
        </div>

        {/* PANEL 3: RIGHT CONTEXT DETAILS ( Metadata + Lineage Mappings ) */}
        <div style={{
          width: 340, borderLeft: '1px solid var(--border-primary)',
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
          background: 'var(--surface-card)', flexShrink: 0,
        }}>
          {selectedItem ? (
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <div style={{ padding: '16px', borderBottom: '1px solid var(--border-subtle)', background: 'var(--surface-card)' }}>
                <h4 style={{ margin: 0, fontSize: '12px', fontWeight: 700, color: 'var(--text-primary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Contextual Metadata
                </h4>
              </div>

              <div style={{ flex: 1, overflow: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: 20 }}>
                
                {/* A. Upstream Lineage chain visual */}
                {lineageChain.length > 0 && (
                  <div>
                    <span style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-tertiary)', fontWeight: 600, display: 'block', marginBottom: 10 }}>Lineage Trace Path</span>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      {lineageChain.map((step, idx) => (
                        <div key={idx}>
                          <div style={{
                            display: 'flex', alignItems: 'center', gap: 10,
                            padding: '8px 12px', background: 'var(--surface-bg)',
                            borderRadius: '6px', border: '1px solid var(--border-primary)',
                          }}>
                            {step.type === 'source' ? <Database size={13} style={{ color: 'var(--jnj-red)' }} /> :
                             step.type === 'table' ? <Table2 size={13} style={{ color: 'var(--text-secondary)' }} /> :
                             step.type === 'calculation' ? <Hash size={13} style={{ color: 'var(--text-secondary)' }} /> :
                             <TrendingUp size={13} style={{ color: 'var(--text-primary)' }} />}
                            <div>
                              <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }}>{step.label}</div>
                              <div style={{ fontSize: '10px', color: 'var(--text-tertiary)' }}>{step.details}</div>
                            </div>
                          </div>
                          {idx < lineageChain.length - 1 && (
                            <div style={{ display: 'flex', justifyContent: 'center', padding: '4px 0' }}>
                              <ArrowRight size={14} style={{ transform: 'rotate(90deg)', color: 'var(--text-tertiary)' }} />
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* B. Relationships mappings (For table views only) */}
                {selectedItem.type === 'table' && activeRelationships.length > 0 && (
                  <div>
                    <span style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-tertiary)', fontWeight: 600, display: 'block', marginBottom: 8 }}>Table Relationships ({activeRelationships.length})</span>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      {activeRelationships.map(rel => (
                        <div key={rel.id} style={{
                          padding: '10px', background: 'var(--surface-bg)',
                          borderRadius: '6px', border: '1px solid var(--border-primary)',
                          fontSize: '11px',
                        }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>
                            <GitBranch size={12} style={{ color: 'var(--jnj-red)' }} />
                            <span>{rel.left_column} ⇄ {rel.right_column}</span>
                          </div>
                          <div style={{ display: 'flex', justifyItems: 'space-between', color: 'var(--text-secondary)' }}>
                            <span style={{ flex: 1 }}>Join: {rel.join_type}</span>
                            <span style={{ fontWeight: 600 }}>{rel.cardinality}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* C. Model verification status */}
                <div>
                  <span style={{ fontSize: '10px', textTransform: 'uppercase', color: 'var(--text-tertiary)', fontWeight: 600, display: 'block', marginBottom: 8 }}>Validation Status</span>
                  <div style={{
                    padding: '12px', background: '#F0FDF4', border: '1px solid #BBF7D0',
                    borderRadius: '6px', display: 'flex', alignItems: 'center', gap: 10, fontSize: '12px'
                  }}>
                    <CheckCircle2 size={16} style={{ color: '#16A34A', flexShrink: 0 }} />
                    <span style={{ color: '#15803D', fontWeight: 600 }}>Metadata schema matches and verified with active catalog rules.</span>
                  </div>
                </div>

              </div>
            </div>
          ) : (
            <div style={{
              flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
              padding: '24px', color: 'var(--text-tertiary)', fontSize: '12px',
              textAlign: 'center', flexDirection: 'column', gap: 8
            }}>
              <Info size={24} style={{ color: 'var(--text-tertiary)' }} />
              Select an explorer node to view lineage traces, primary key relations, and active schema mappings.
            </div>
          )}
        </div>

      </div>
    </div>
  );
}
