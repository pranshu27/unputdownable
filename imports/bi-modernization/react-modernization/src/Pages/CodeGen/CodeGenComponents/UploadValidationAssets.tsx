import React, { useRef } from 'react';
import { Upload, X, FileArchive, Loader2, CheckCircle2, Database, LayoutTemplate } from 'lucide-react';
import { cn } from '../../../Lib/utils.ts';

interface FileInputProps {
  label: string;
  icon: React.ReactNode;
  description: string;
  file: File | null;
  onChange: (file: File | null) => void;
  disabled?: boolean;
}

function FileInput({ label, icon, description, file, onChange, disabled }: FileInputProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null;
    onChange(f);
  };

  return (
    <div
      onClick={() => !disabled && !file && inputRef.current?.click()}
      className={cn(
        "relative flex flex-col items-center justify-center p-8 rounded-xl border-2 border-dashed transition-all text-center",
        disabled ? "bg-slate-50 border-slate-200 cursor-not-allowed opacity-75" :
        file ? "bg-[#c8102e]/5 border-[#c8102e]/30 cursor-default" :
        "bg-white border-slate-300 hover:border-[#002147] hover:bg-slate-50 cursor-pointer"
      )}
    >
      <input ref={inputRef} type="file" accept=".zip" className="hidden" onChange={handleChange} disabled={disabled} />
      
      {file ? (
        <div className="flex flex-col items-center gap-3">
          <div className="h-12 w-12 rounded-full bg-[#c8102e]/10 flex items-center justify-center text-[#c8102e]">
            <CheckCircle2 size={24} />
          </div>
          <div>
            <p className="text-sm font-bold text-slate-900 truncate max-w-[200px]" title={file.name}>{file.name}</p>
            <p className="text-xs text-slate-500 mt-1">Ready for validation</p>
          </div>
          {!disabled && (
            <button
              onClick={(e) => { e.stopPropagation(); onChange(null); }}
              className="mt-2 text-xs font-semibold text-slate-500 hover:text-[#c8102e] transition-colors"
            >
              Remove file
            </button>
          )}
        </div>
      ) : (
        <div className="flex flex-col items-center gap-3">
          <div className="h-12 w-12 rounded-full bg-slate-100 flex items-center justify-center text-slate-500">
            {icon}
          </div>
          <div>
            <p className="text-sm font-bold text-slate-900">{label}</p>
            <p className="text-xs text-slate-500 mt-1 max-w-[200px]">{description}</p>
          </div>
          <div className="mt-2 text-xs font-semibold text-[#002147] bg-slate-100 px-3 py-1.5 rounded-lg">
            Browse files
          </div>
        </div>
      )}
    </div>
  );
}

interface Props {
  datasetFile: File | null;
  reportFile: File | null;
  onDatasetChange: (f: File | null) => void;
  onReportChange: (f: File | null) => void;
  onValidate: () => void;
  isLoading?: boolean;
  disabled?: boolean;
}

export default function UploadValidationAssets({
  datasetFile, reportFile, onDatasetChange, onReportChange, onValidate, isLoading, disabled,
}: Props) {
  const bothReady = datasetFile !== null && reportFile !== null;

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8 bg-slate-50/50 h-full">
      <div className="max-w-2xl w-full bg-white rounded-2xl shadow-sm border border-slate-200 p-10">
        
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center h-12 w-12 rounded-xl bg-[#002147]/5 text-[#002147] mb-4">
            <Upload size={24} />
          </div>
          <h2 className="text-2xl font-bold text-[#002147] tracking-tight">Upload Validation Assets</h2>
          <p className="text-sm text-slate-500 mt-2 max-w-md mx-auto">
            Provide the required Power BI dataset and report ZIP packages to execute forward engineering rules.
          </p>
        </div>

        <div className="grid grid-cols-2 gap-6 mb-8">
          <FileInput 
            label="Dataset Package (.zip)" 
            description="The extracted dataset contents"
            icon={<Database size={24} />}
            file={datasetFile} 
            onChange={onDatasetChange} 
            disabled={isLoading || disabled} 
          />
          <FileInput 
            label="Report Package (.zip)" 
            description="The extracted report visual contents"
            icon={<LayoutTemplate size={24} />}
            file={reportFile} 
            onChange={onReportChange} 
            disabled={isLoading || disabled} 
          />
        </div>

        <div className="flex justify-center border-t border-slate-100 pt-8">
          <button
            onClick={onValidate}
            disabled={!bothReady || isLoading || disabled}
            className={cn(
              "flex items-center gap-2 px-8 py-3 rounded-xl text-sm font-bold transition-all shadow-sm",
              isLoading ? 'bg-slate-100 text-slate-400 cursor-not-allowed shadow-none'
              : !bothReady ? 'bg-slate-100 text-slate-400 cursor-not-allowed shadow-none'
              : 'bg-[#c8102e] text-white hover:bg-[#a30d24] shadow-md shadow-[#c8102e]/20'
            )}
          >
            {isLoading ? <Loader2 size={16} className="animate-spin" /> : null}
            {isLoading ? 'Running Validation...' : 'Execute Validation'}
          </button>
        </div>
        
      </div>
    </div>
  );
}
