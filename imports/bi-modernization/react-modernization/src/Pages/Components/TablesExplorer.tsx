import { useState } from 'react';
import { DataModel, Table, Column } from '../../data/sampleModel';
import { ChevronDown, ChevronRight, Key, Filter, Calculator, Link2, Hash, Type, Calendar, ToggleLeft } from 'lucide-react';
import { cn } from "../../Lib/utils.ts";
import ContentCard from '../../core/CardContent/CardContent.tsx';
import FileWorkspaceHeader from '../../core/FileWorkspaceHeader.tsx';
import { useOutletContext } from 'react-router-dom';
import { Box, Typography, Tooltip, IconButton, Divider, Input } from '@mui/material';
interface TablesExplorerProps {
  model: DataModel;
}

const typeIcon = (t: string) => {
  if (t === 'string') return Type;
  if (t === 'integer' || t === 'float') return Hash;
  if (t === 'datetime') return Calendar;
  return ToggleLeft;
};

const typeColor = (t: string) => {
  if (t === 'string') return 'text-sky-600';
  if (t === 'integer' || t === 'float') return 'text-emerald-600';
  if (t === 'datetime') return 'text-amber-600';
  return 'text-slate-500';
};

function ColumnBadges({ col }: { col: Column }) {
  const badges = [];
  if (col.used_in_relationships) badges.push({ icon: Link2, label: 'Key', color: 'bg-violet-50 text-violet-700 border-violet-200/60' });
  if (col.used_in_filters) badges.push({ icon: Filter, label: 'Filter', color: 'bg-orange-50 text-orange-700 border-orange-200/60' });
  if (col.used_in_calculations) badges.push({ icon: Calculator, label: 'Calc', color: 'bg-pink-50 text-pink-700 border-pink-200/60' });
  if (col.semantic_role) badges.push({ icon: Key, label: 'Geo', color: 'bg-cyan-50 text-cyan-700 border-cyan-200/60' });

  return (
    <div className="flex items-center gap-1 flex-wrap">
      {badges.map((b, i) => {
        const I = b.icon;
        return (
          <span key={i} className={cn('text-[10px] px-1.5 py-0.5 rounded-md border flex items-center gap-1 font-semibold', b.color)}>
            <I className="w-2.5 h-2.5" strokeWidth={2.5} />
            {b.label}
          </span>
        );
      })}
    </div>
  );
}

function TableCard({ table, relCount }: { table: Table; relCount: number }) {
  const [expanded, setExpanded] = useState(false);

  const keyColumns = table.columns.filter((c) => c.used_in_relationships);
  const isFact = table.table_type === 'fact';

  return (
    <div
      className={cn(
        'rounded-2xl border bg-white overflow-hidden transition-all duration-200 shadow-sm',
        expanded ? 'border-slate-300 shadow-md' : 'border-slate-200/70 hover:border-slate-300 hover:shadow-md hover:-translate-y-0.5'
      )}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left px-6 py-5 flex items-start justify-between gap-4 hover:bg-slate-50/50 transition-colors"
      >
        <div className="flex items-start gap-4 min-w-0 flex-1">
          <div
            className={cn(
              'w-11 h-11 rounded-xl flex items-center justify-center shrink-0 mt-0.5 ring-4',
              isFact ? 'bg-amber-50 ring-amber-50/50' : 'bg-emerald-50 ring-emerald-50/50'
            )}
          >
            <span className={cn('text-[10px] font-bold uppercase tracking-wider', isFact ? 'text-amber-700' : 'text-emerald-700')}>
              {isFact ? 'Fact' : 'Dim'}
            </span>
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="font-semibold text-slate-900 text-[15px] truncate">{table.name}</h3>
              {table.is_materialized && (
                <span className="text-[10px] px-1.5 py-0.5 rounded-md border bg-emerald-50 text-emerald-700 border-emerald-200/60 font-semibold">
                  materialized
                </span>
              )}
            </div>
            <p className="text-[13px] text-slate-500 mt-1.5 line-clamp-2 leading-relaxed">{table.description}</p>
            <div className="flex items-center gap-5 mt-3">
              {[
                { value: table.columns.length, label: 'cols' },
                { value: keyColumns.length, label: 'keys' },
                { value: relCount, label: 'rel' },
                { value: table.ingestion.steps.length, label: 'steps' },
              ].map(({ value, label }) => (
                <div key={label} className="flex items-baseline gap-1">
                  <span className="text-[13px] font-semibold text-slate-900">{value}</span>
                  <span className="text-[11px] text-slate-500">{label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
        <div
          className={cn(
            'shrink-0 text-slate-400 mt-1 transition-transform duration-200',
            expanded && 'rotate-0 text-slate-700'
          )}
        >
          {expanded ? <ChevronDown className="w-[18px] h-[18px]" /> : <ChevronRight className="w-[18px] h-[18px]" />}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-slate-100 bg-slate-50/40">
          <div className="px-6 py-3 flex items-center justify-between border-b border-slate-100">
            <span className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">Columns</span>
          </div>
          <div className="divide-y divide-slate-100">
            {table.columns.map((col) => {
              const Icon = typeIcon(col.data_type);
              const color = typeColor(col.data_type);
              return (
                <div
                  key={col.name}
                  className="px-6 py-3 flex items-center gap-4 hover:bg-white transition-colors group"
                  title={col.description}
                >
                  <Icon className={cn('w-4 h-4 shrink-0', color)} strokeWidth={2.2} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-[13.5px] font-mono text-slate-800 truncate font-medium">{col.name}</span>
                      {col.distinct_count_high && (
                        <span
                          className="text-[9px] uppercase tracking-wider text-slate-400 font-semibold"
                          title="High distinct count"
                        >
                          HD
                        </span>
                      )}
                    </div>
                    <div className="text-[11.5px] text-slate-500 mt-0.5 line-clamp-2">
                      {col.description}
                    </div>
                  </div>
                  <span className={cn('text-[10px] font-mono uppercase tracking-wider shrink-0 font-bold', color)}>
                    {col.data_type}
                  </span>
                  <ColumnBadges col={col} />
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export default function TablesExplorer({ model }: TablesExplorerProps) {
  const [filter, setFilter] = useState<'all' | 'fact' | 'dimension'>('all');

  const filtered = model.tables.filter((t) => filter === 'all' || t.table_type === filter);

  const relCountFor = (tableId: string) =>
    model.relationships.filter((r) => r.left_table_id === tableId || r.right_table_id === tableId).length;
  const { sideNavWidth } = useOutletContext();

  return (
    <ContentCard
    heading={null}
    sideNavWidth={sideNavWidth}

  >
   <div className="space-y-8">
      <FileWorkspaceHeader pageTitle="Tables" />
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <p className="text-[14px] text-slate-500 mt-1.5">Click a table to expand its columns</p>
        </div>
        <div className="flex items-center gap-1 p-1 bg-white border border-slate-200/70 rounded-xl shadow-sm">
          {(['all', 'fact', 'dimension'] as const).map((key) => (
            <button
              key={key}
              onClick={() => setFilter(key)}
              className={cn(
                'px-3.5 py-1.5 text-[12.5px] font-semibold rounded-lg transition-all duration-200 capitalize',
                filter === key ? 'bg-slate-900 text-white shadow-sm' : 'text-slate-500 hover:text-slate-900 hover:bg-slate-50'
              )}
            >
              {key === 'all' ? `All (${model.tables.length})` : key}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-4">
        {filtered.map((t) => (
          <TableCard key={t.id} table={t} relCount={relCountFor(t.id)} />
        ))}
      </div>
    </div>
  </ContentCard>
 
  );
}
