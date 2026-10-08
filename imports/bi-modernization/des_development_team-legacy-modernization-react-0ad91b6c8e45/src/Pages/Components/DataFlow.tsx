import { useState } from 'react';
import { DataModel } from '../../data/sampleModel.ts';
import { FileInput, GitMerge, Filter, Database, Calculator, Wrench, Trash2, RefreshCw, Combine, Pencil, Columns2, Layers, ChevronRight, CircleDashed } from 'lucide-react';
import { cn } from "../../Lib/utils.ts";
import ContentCard from '../../core/CardContent/CardContent.tsx';
import FileWorkspaceHeader from '../../core/FileWorkspaceHeader.tsx';
import { useOutletContext } from 'react-router-dom';
import { Box, Typography, Tooltip, IconButton, Divider, Input } from '@mui/material';
interface Props {
  model: DataModel;
}

const stepMeta: Record<string, { icon: React.ElementType; color: string; bg: string; border: string; label: string }> = {
  read_source:    { icon: FileInput,    color: 'text-blue-700',      bg: 'bg-blue-50',      border: 'border-blue-200/60',      label: 'Read' },
  read:           { icon: FileInput,    color: 'text-blue-700',      bg: 'bg-blue-50',      border: 'border-blue-200/60',      label: 'Read' },

  join:           { icon: GitMerge,     color: 'text-violet-700',    bg: 'bg-violet-50',    border: 'border-violet-200/60',    label: 'Join' },
  filter:         { icon: Filter,       color: 'text-orange-700',    bg: 'bg-orange-50',    border: 'border-orange-200/60',    label: 'Filter' },
  create_extract: { icon: Database,     color: 'text-emerald-700',   bg: 'bg-emerald-50',   border: 'border-emerald-200/60',   label: 'Extract' },
  calculation:    { icon: Calculator,   color: 'text-rose-700',      bg: 'bg-rose-50',      border: 'border-rose-200/60',      label: 'Calc' },
  custom:         { icon: Wrench,       color: 'text-stone-700',     bg: 'bg-stone-50',     border: 'border-stone-200/60',     label: 'Custom' },
  remove_columns: { icon: Trash2,       color: 'text-red-700',       bg: 'bg-red-50',       border: 'border-red-200/60',       label: 'Remove' },
  change_type:    { icon: RefreshCw,    color: 'text-yellow-700',    bg: 'bg-yellow-50',    border: 'border-yellow-200/60',    label: 'Change Type' },
  merge:          { icon: Combine,      color: 'text-teal-700',      bg: 'bg-teal-50',      border: 'border-teal-200/60',      label: 'Merge' },
  rename:         { icon: Pencil,       color: 'text-cyan-700',      bg: 'bg-cyan-50',      border: 'border-cyan-200/60',      label: 'Rename' },
  split_column:   { icon: Columns2,     color: 'text-pink-700',      bg: 'bg-pink-50',      border: 'border-pink-200/60',      label: 'Split Column' },
  group:          { icon: Layers,       color: 'text-lime-700',      bg: 'bg-lime-50',      border: 'border-lime-200/60',      label: 'Group' },
};

const stepStylePresets = [
  { color: 'text-indigo-700',   bg: 'bg-indigo-50',   border: 'border-indigo-200/60' },
  { color: 'text-green-700',    bg: 'bg-green-50',    border: 'border-green-200/60' },
  { color: 'text-amber-700',    bg: 'bg-amber-50',    border: 'border-amber-200/60' },
  { color: 'text-purple-700',   bg: 'bg-purple-50',   border: 'border-purple-200/60' },
  { color: 'text-sky-700',      bg: 'bg-sky-50',      border: 'border-sky-200/60' },
  { color: 'text-slate-700',    bg: 'bg-slate-50',    border: 'border-slate-200/60' },
  { color: 'text-gray-700',     bg: 'bg-gray-50',     border: 'border-gray-200/60' },
  { color: 'text-neutral-700',  bg: 'bg-neutral-50',  border: 'border-neutral-200/60' },
  { color: 'text-zinc-700',     bg: 'bg-zinc-50',     border: 'border-zinc-200/60' },
  { color: 'text-fuchsia-700',  bg: 'bg-fuchsia-50',  border: 'border-fuchsia-200/60' },
];

const hashStepType = (stepType: string) => {
  let hash = 0;
  for (let i = 0; i < stepType.length; i += 1) {
    hash = (hash * 31 + stepType.charCodeAt(i)) >>> 0;
  }
  return hash;
};

const formatStepLabel = (stepType: string) =>
  stepType
    .replace(/_/g, ' ')
    .replace(/(^|\s)(\w)/g, (_, prefix, char) => `${prefix}${char.toUpperCase()}`);

const getStepMeta = (stepType: string) => {
  if (stepMeta[stepType]) {
    return stepMeta[stepType];
  }

  const hash = hashStepType(stepType);
  const preset = stepStylePresets[hash % stepStylePresets.length];

  return {
    icon: CircleDashed,
    label: formatStepLabel(stepType),
    ...preset,
  };
};

function PipelineRow({ table }: { table: Table }) {
  const [activeStep, setActiveStep] = useState<number | null>(null);

  return (
    <div className="rounded-2xl border border-slate-200/70 bg-white overflow-hidden shadow-sm hover:shadow-md transition-shadow duration-200">
      <div className="px-6 py-4 flex items-center gap-3 border-b border-slate-100 bg-slate-50/40">
        <span
          className={cn(
            'text-[10px] px-2 py-0.5 rounded-md font-bold uppercase tracking-wider',
            table.table_type === 'fact' ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'
          )}
        >
          {table.table_type}
        </span>
        <h3 className="text-[14.5px] font-semibold text-slate-900 font-mono">{table.name}</h3>
        <span className="text-xs text-slate-500 ml-auto font-medium">{table.ingestion.steps.length} steps</span>
      </div>

      <div className="px-6 pb-6 pt-4">
        <div className="overflow-x-auto -mx-2 px-2">
          <div className="flex items-center gap-2 pb-3 pt-2">
          {table.ingestion.steps.map((step, idx) => {
            const meta = getStepMeta(step.step_type);
            const Icon = meta.icon;
            const isActive = activeStep === idx;

            return (
              <div key={idx} className="flex items-center gap-2 shrink-0">
                <button
                  onClick={() => setActiveStep(isActive ? null : idx)}
                  className={cn(
                    'flex flex-col items-center gap-1.5 px-4 py-3 rounded-xl border transition-all duration-200 min-w-[96px]',
                    meta.bg,
                    meta.border,
                    isActive
                      ? 'ring-2 ring-offset-2 ring-offset-white ring-indigo-400 shadow-sm -translate-y-0.5'
                      : 'hover:-translate-y-0.5 hover:shadow-sm'
                  )}
                >
                  <Icon className={cn('w-[18px] h-[18px]', meta.color)} strokeWidth={2.2} />
                  <span className={cn('text-[10px] font-bold uppercase tracking-wider', meta.color)}>{meta.label}</span>
                  <span className="text-[9px] text-slate-500 font-mono font-semibold">#{step.order}</span>
                </button>
                {idx < table.ingestion.steps.length - 1 && (
                  <ChevronRight className="w-4 h-4 text-slate-300 shrink-0" strokeWidth={2.5} />
                )}
              </div>
            );
          })}
          </div>
        </div>

        {activeStep !== null && (
          <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50/60 p-5 animate-in fade-in slide-in-from-top-1 duration-200">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-1.5">
              Step {table.ingestion.steps[activeStep].order} · {table.ingestion.steps[activeStep].step_type}
            </div>
            <p className="text-[13.5px] text-slate-700 mb-4 leading-relaxed">{table.ingestion.steps[activeStep].description}</p>
            {table.ingestion.steps[activeStep].native_expressions?.tableau && (
              <div>
                <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-2">Native Expression</div>
                <code className="block text-[12.5px] font-mono text-indigo-700 bg-white rounded-lg px-4 py-3 border border-slate-200 break-all leading-relaxed">
                  {table.ingestion.steps[activeStep].native_expressions.tableau}
                </code>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function DataFlow({ model }: Props) {
  const { sideNavWidth } = useOutletContext();

  return (
    <ContentCard
    heading={null}
    sideNavWidth={sideNavWidth}
  >
    <div className="space-y-8">
      <FileWorkspaceHeader pageTitle="Data Flow" />
      <div>
        <p className="text-[14px] text-slate-500 mt-1.5">Ingestion pipelines per table — click a step to inspect</p>
      </div>

      <div className="flex gap-2 flex-wrap text-xs">
        {(() => {
          const usedStepTypes = new Set(model.tables.flatMap((t) => t.ingestion.steps.map((step) => step.step_type)));
          const stepTypeKeys = [
            ...Object.keys(stepMeta).filter((key) => usedStepTypes.has(key)),
            ...Array.from(usedStepTypes).filter((key) => !Object.prototype.hasOwnProperty.call(stepMeta, key)),
          ];

          return stepTypeKeys.map((key) => {
            const meta = getStepMeta(key);
            const Icon = meta.icon;

            return (
              <div key={key} className={cn('flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border font-semibold', meta.bg, meta.border)}>
                <Icon className={cn('w-3.5 h-3.5', meta.color)} strokeWidth={2.2} />
                <span className={meta.color}>{meta.label}</span>
              </div>
            );
          });
        })()}
      </div>

      <div className="space-y-4">
        {model.tables.map((t) => (
          <PipelineRow key={t.id} table={t} />
        ))}
      </div>
    </div>
  </ContentCard>
  );
}
