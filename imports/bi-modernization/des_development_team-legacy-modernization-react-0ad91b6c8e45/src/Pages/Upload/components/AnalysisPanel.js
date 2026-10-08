import React from 'react';
import { motion } from 'framer-motion';
import {
  FileCode, ArrowRight, Cpu, Brain, CheckCircle2,
  Sparkles, Clock, AlertTriangle, Play
} from 'lucide-react';
import { Button } from '../../CodeGen/CodeGenComponents/button.tsx';
import { cn } from '../../../Lib/utils.ts';
import PowerBiIcon from '../../../Assets/powerbi.png';
import TableautIcon from '../../../Assets/tableau-icon.svg';
import GPT from '../../../Assets/openAi.svg';
import claude from '../../../Assets/claude.png';
import Gemini from '../../../Assets/gemini.svg';
import AWS from '../../../Assets/aws.svg';

export default function AnalysisPanel({
  file,
  selectedFiles,
  sourcePlatform,
  framework,
  model,
  onAnalyze,
  isAnalyzing
}) {
  const isComplete = file && sourcePlatform && model;
  const filesList = selectedFiles?.length > 0 ? selectedFiles : file ? [file] : [];
  const getPlatformMeta = (fileName) => {
    const normalized = String(fileName || '').toLowerCase();
    if (normalized.endsWith('.pbix')) {
        return {
          id: 'powerbi',
          name: 'Power BI',
          icon: PowerBiIcon,
          badgeClass: 'bg-red-50 text-red-900 border-red-300',
        };
    }
    if (normalized.endsWith('.twb') || normalized.endsWith('.twbx')) {
        return {
          id: 'tableau-workbook',
          name: 'Tableau',
          icon: TableautIcon,
          badgeClass: 'bg-orange-50 text-orange-900 border-orange-300',
        };
    }
    return null;
  };
  const sourceGroups = Array.from(
    filesList.reduce((map, currentFile) => {
      const meta = getPlatformMeta(currentFile?.name);
      if (!meta) return map;
      const existing = map.get(meta.id);
      if (existing) {
        existing.count += 1;
      } else {
        map.set(meta.id, { ...meta, count: 1 });
      }
      return map;
    }, new Map()).values()
  );
  const sourceSummary = sourceGroups.map((group) =>
    group.count > 1 ? `${group.name} (${group.count})` : group.name
  ).join(' + ');

  const configItems = [
    //{ label: 'Source File', value: file?.name, icon: FileCode, color: 'blue' },
    // { label: 'Framework', value: framework?.name, icon: Cpu, color: 'purple' }, // Commented out - Framework selection hidden
    { label: 'AI Model', value: model?.selectedVersionLabel || model?.name, icon: Brain, color: 'pink' },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-800">Ready to Analyze</h2>
        <p className="text-sm text-slate-500 mt-1">
          Review your configuration and start the transformation
        </p>
      </div>

      {/* Configuration Summary */}
      <div className="bg-gradient-to-br from-slate-50 to-white border border-slate-200 rounded-2xl p-6">
        <h3 className="text-sm font-medium text-slate-400 uppercase tracking-wider mb-4">
          Configuration Summary
        </h3>

        <div className="space-y-3">

      {/* Files — all stacked on right of single row */}
      {(selectedFiles?.length > 0 ? selectedFiles : file ? [file] : []).length > 0 && (
        <motion.div
  initial={{ opacity: 0, x: -20 }}
  animate={{ opacity: 1, x: 0 }}
  transition={{ delay: 0 }}
  className="flex flex-col gap-3 p-3 bg-white rounded-xl border border-slate-100"
>
  {/* Always: icon + label on left */}
  <div className="flex items-center justify-between gap-4">
    <div className="flex items-center gap-3">
      <div className="w-10 h-10 rounded-lg flex items-center justify-center bg-blue-50">
        <FileCode className="w-5 h-5 text-blue-500" />
      </div>
      <span className="text-sm font-medium text-slate-700">
        {(selectedFiles?.length > 1) ? 'Source Files' : 'Source File'}
      </span>
    </div>

    {/* Single file: show inline on the right like other rows */}

    {(selectedFiles?.length <= 1) && (
      <div className="flex items-center gap-1.5 bg-slate-50 border border-slate-200 rounded-full px-3 py-1.5">
        <span className="max-w-[420px] truncate text-sm font-semibold text-slate-800" title={(selectedFiles?.[0] ?? file)?.name}>
          {(selectedFiles?.[0] ?? file)?.name}
        </span>
        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />
      </div>
    )}

    {/* Multiple files: show count badge */}
    {selectedFiles?.length > 1 && (
      <span className="text-xs font-semibold bg-blue-50 text-blue-800 px-2 py-0.5 rounded-full border border-blue-200">
        {selectedFiles.length} files
      </span>
    )}
  </div>

  {/* Multiple files only: pill grid below */}
  {selectedFiles?.length > 1 && (
    <div className="flex flex-wrap gap-2">
      {selectedFiles.map((f) => (
        <div key={f.name} className="flex items-center gap-1.5 bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5">
          <span className="max-w-[320px] truncate text-sm font-semibold text-slate-800" title={f.name}>{f.name}</span>
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />
        </div>
      ))}
    </div>
  )}
</motion.div>
      )}
          {sourceGroups.length > 0 && (
            <motion.div
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.05 }}
              className="flex flex-col gap-3 p-4 bg-white rounded-xl border border-slate-100"
            >
              <div className="flex items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-50">
                    <Sparkles className="w-5 h-5 text-indigo-500" />
                  </div>
                  <span className="text-sm font-medium text-slate-700">Source Platform</span>
                </div>

                {/* <div className="flex items-center gap-2">
                    <span className="text-right font-semibold text-slate-900">
                      {sourceSummary}
                    </span>
                  <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                </div> */}
                <div className="flex flex-wrap gap-2">
                {sourceGroups.map((group) => (
                  <div
                    key={group.id}
                    className={cn(
                      'flex items-center gap-2 rounded-full border px-3 py-1.5 shadow-sm',
                      group.badgeClass
                    )}
                  >
                    <img src={group.icon} alt={group.name} className="h-4 w-4 object-contain" />
                    <span className="text-xs font-medium leading-none text-slate-800">{group.name}</span>
                    <span className="rounded-full border border-white/70 bg-white px-1.5 py-0.5 text-[10px] font-bold text-slate-700">
                      {group.count}
                    </span>
                  </div>
                ))}
              </div>
              </div>

              
            </motion.div>
          )}
          {configItems
            .filter(item => item.value)
            .map((item, idx) => {
              const IconComponent = item.icon;
              return (
                <motion.div
                  key={item.label}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: idx * 0.1 }}
                  className="flex items-center justify-between p-3 bg-white rounded-xl border border-slate-100"
                >
                  <div className="flex items-center gap-3">
                    <div className={cn(
                      "w-10 h-10 rounded-lg flex items-center justify-center",
                      `bg-${item.color}-50`
                    )}>
                      {typeof IconComponent === 'function' ? (
                        <IconComponent className={`w-5 h-5 text-${item.color}-500`} />
                      ) : (
                        <IconComponent />
                      )}
                    </div>
                    <span className="text-sm font-medium text-slate-700">{item.label}</span>
                  </div>

                  {/* AI Model pill with matching color */}
                  {item.label === 'AI Model' ? (
                    (() => {
                      const modelName = (item.value || '').toLowerCase();
                      const isGPT = modelName.includes('gpt');
                      const isClaude = modelName.includes('claude');
                      const isGemini = modelName.includes('gemini');
                      const isAWS = modelName.includes('aws') || modelName.includes('bedrock');

                      const pillStyle = isGPT
                        ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                        : isClaude
                        ? 'bg-orange-50 border-orange-200 text-orange-800'
                        : isGemini
                        ? 'bg-blue-50 border-blue-200 text-blue-800'
                        : isAWS
                        ? 'bg-yellow-50 border-yellow-200 text-yellow-800'
                        : 'bg-slate-50 border-slate-200 text-slate-800';

                      const icon = isGPT ? GPT : isClaude ? claude : isGemini ? Gemini : isAWS ? AWS : null;

                      return (
                        <div className={`flex items-center gap-2 rounded-full border px-3 py-1.5 shadow-sm ${pillStyle}`}>
                          {icon && <img src={icon} alt="" className="h-4 w-4 object-contain" />}
                          <span className="text-sm font-medium leading-none">{item.value}</span>
                        </div>
                      );
                    })()
                  ) : (
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-slate-900">{item.value}</span>
                      <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                    </div>
                  )}
                </motion.div>
              );
            })}
        </div>
      </div>

      {/* Transformation Preview */}

      {/* Warning for incomplete */}
      {!isComplete && (
        <div className="flex items-center gap-3 p-4 bg-amber-50 border border-amber-200 rounded-xl">
          <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0" />
          <p className="text-sm text-amber-700">
            Please complete all steps before starting the analysis.
          </p>
        </div>
      )}

      {/* Action Button */}
      <motion.div
        whileHover={isComplete ? { scale: 1.02 } : {}}
        whileTap={isComplete ? { scale: 0.98 } : {}}
      >
        <Button
          onClick={onAnalyze}
          disabled={!isComplete || isAnalyzing}
          className={cn(
            "w-full h-14 rounded-lg text-lg font-semibold transition-all duration-300 text-white flex items-center justify-center",
            isComplete
              ? "bg-gradient-to-r from-red-700 to-red-900 hover:from-red-800 hover:to-red-950 shadow-lg shadow-red-500/20"
              : "bg-stone-200 text-stone-500"
          )}
        >
          {isAnalyzing ? (
            <div className="flex items-center gap-3">
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
              >
                <Cpu className="w-5 h-5" />
              </motion.div>
              <span>Analyzing...</span>
            </div>
          ) : (
            <div className="flex items-center gap-3">
              <Play className="w-5 h-5" />
              <span>Start Analysis</span>
            </div>
          )}
        </Button>
      </motion.div>
    </div>
  );
}
