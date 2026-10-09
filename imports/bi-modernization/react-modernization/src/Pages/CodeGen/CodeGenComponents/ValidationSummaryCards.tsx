import React from 'react';
import { ValidationResult } from '../../../services/ValidationService';

interface Props { result: ValidationResult; }

interface MetricCardProps {
  label: string;
  value: string | number;
  subValue?: string;
  isPositive?: boolean;
  isNegative?: boolean;
}

function MetricCard({ label, value, subValue, isPositive, isNegative }: MetricCardProps) {
  return (
    <div className="bg-white border border-slate-200 rounded p-3 flex flex-col gap-1">
      <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">{label}</span>
      <div className="flex items-baseline gap-2">
        <span className={`text-xl font-bold ${
          isPositive ? 'text-emerald-600' : isNegative ? 'text-red-600' : 'text-slate-800'
        }`}>
          {value}
        </span>
        {subValue && <span className="text-xs text-slate-400 font-medium">{subValue}</span>}
      </div>
    </div>
  );
}

export default function ValidationSummaryCards({ result }: Props) {
  const verdictPass = result.verdict === 'PASS';

  return (
    <div className="grid grid-cols-2 md:grid-cols-6 gap-3 mb-4">
      <div className={`col-span-2 md:col-span-2 rounded border px-4 py-3 flex items-center justify-between ${
        verdictPass ? 'bg-emerald-50/50 border-emerald-200' : 'bg-red-50/50 border-red-200'
      }`}>
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-1">Verdict</p>
          <p className={`text-2xl font-black ${verdictPass ? 'text-emerald-700' : 'text-red-700'}`}>
            {result.verdict}
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs text-slate-600 font-medium mb-0.5">Overall Score</p>
          <p className="text-lg font-bold text-slate-800">{result.overall_score === null ? 'N/A' : result.overall_score.toFixed(0)} <span className="text-xs text-slate-400 font-normal">{result.overall_score !== null && '/ 100'}</span></p>
        </div>
      </div>

      <MetricCard 
        label="Checks Passed" 
        value={result.passed_checks} 
        subValue={`/ ${result.total_checks}`} 
        isPositive={true} 
      />
      
      <MetricCard 
        label="Checks Failed" 
        value={result.failed_checks} 
        isNegative={result.failed_checks > 0} 
      />
      
      <MetricCard 
        label="Missing Items" 
        value={result.missing_validations} 
        isNegative={result.missing_validations > 0} 
      />
      
      <div className="bg-white border border-slate-200 rounded p-3 flex flex-col justify-center">
        <div className="flex items-center justify-between text-xs mb-1.5">
          <span className="text-slate-500 font-medium">Semantic</span>
          <span className="font-bold text-slate-700">{result.semantic_score === null ? 'N/A' : `${result.semantic_score.toFixed(0)}%`}</span>
        </div>
        <div className="flex items-center justify-between text-xs">
          <span className="text-slate-500 font-medium">Visual</span>
          <span className="font-bold text-slate-700">{result.visual_score === null ? 'N/A' : `${result.visual_score.toFixed(0)}%`}</span>
        </div>
      </div>
    </div>
  );
}
