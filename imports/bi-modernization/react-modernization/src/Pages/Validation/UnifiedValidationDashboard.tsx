import React, { useState } from 'react';
import { useOutletContext, useSearchParams } from 'react-router-dom';
import ContentCard from '../../core/CardContent/CardContent.tsx';
import FileWorkspaceHeader from '../../core/FileWorkspaceHeader.tsx';
import ValidationReport from '../Components/ValidationReport.tsx';
import { DataModel } from '../../data/sampleModel';

// Forward Validation imports
import UploadValidationAssets from '../CodeGen/CodeGenComponents/UploadValidationAssets.tsx';
import ValidationDashboard from '../CodeGen/ValidationDashboard.tsx';
import { useValidation } from '../../Hooks/useValidation.ts';

interface OutletContextType {
  sideNavWidth: number;
}

interface Props {
  model: DataModel;
}

const getActiveFileName = () => {
  try {
    const details = JSON.parse(localStorage.getItem('fileDetails') || '{}');
    return localStorage.getItem('activePowerBiReportFile') || details?.fileName || '';
  } catch { return localStorage.getItem('activePowerBiReportFile') || ''; }
};

export default function UnifiedValidationDashboard({ model }: Props) {
  const activeFileName = getActiveFileName();
  const { sideNavWidth } = useOutletContext<OutletContextType>();
  const [searchParams, setSearchParams] = useSearchParams();
  const currentTab = searchParams.get('tab') === 'forward' ? 'forward' : 'reverse';

  const [theme] = useState<"light" | "dark">(() =>
    (localStorage.getItem("codegenTheme") as "light" | "dark") || "light"
  );

  const handleTabChange = (newTab: 'reverse' | 'forward') => {
    setSearchParams({ tab: newTab });
  };

  const validation = useValidation(activeFileName);

  return (
    <ContentCard
      heading={null}
      sideNavWidth={sideNavWidth}
      headerComponent={<FileWorkspaceHeader pageTitle="Validation Platform" />}
      noscroll
      noPadding={true}
    >
      <div className="validation-dashboard flex-1 w-full flex flex-col bg-slate-50 overflow-hidden" data-theme={theme}>
        
        {/* Segmented Tabs Header */}
        <div className="bg-white border-b border-slate-200 px-8 py-5 flex items-center justify-between shrink-0 shadow-sm">
          <div>
            <h1 className="text-2xl font-bold text-[#002147] tracking-tight">
              {currentTab === 'reverse' ? 'Reverse Engineering Validation' : 'Forward Engineering Validation'}
            </h1>
            <p className="text-sm text-slate-500 mt-1">
              {currentTab === 'reverse' 
                ? 'Validate report output against enterprise semantics and syntax.' 
                : 'Upload datasets and reports to validate forward engineering rules.'}
            </p>
          </div>
          <div className="flex p-1 bg-slate-100/80 rounded-lg border border-slate-200/60 shadow-inner">
            <button 
              onClick={() => handleTabChange('reverse')}
              className={`px-6 py-2 rounded-md text-sm font-semibold transition-all ${
                currentTab === 'reverse' ? 'bg-white text-[#c8102e] shadow-sm border border-slate-200' : 'text-slate-500 hover:text-slate-700 hover:bg-slate-200/50'
              }`}
            >
              Reverse Engineering
            </button>
            <button 
              onClick={() => handleTabChange('forward')}
              className={`px-6 py-2 rounded-md text-sm font-semibold transition-all ${
                currentTab === 'forward' ? 'bg-white text-[#c8102e] shadow-sm border border-slate-200' : 'text-slate-500 hover:text-slate-700 hover:bg-slate-200/50'
              }`}
            >
              Forward Engineering
            </button>
          </div>
        </div>

        {/* Tab Content Area */}
        <div className="flex-1 overflow-y-auto">
          {currentTab === 'reverse' && (
            <ValidationReport model={model} isTab={true} />
          )}

          {currentTab === 'forward' && (
            <div className="w-full h-full flex flex-col">
              {validation.step !== 'success' && (
                <UploadValidationAssets
                  datasetFile={validation.datasetFile}
                  reportFile={validation.reportFile}
                  onDatasetChange={validation.setDatasetFile}
                  onReportChange={validation.setReportFile}
                  onValidate={() => {
                    if (validation.datasetFile && validation.reportFile) {
                      validation.runValidation(validation.datasetFile, validation.reportFile);
                    }
                  }}
                  isLoading={validation.step === 'uploading' || validation.step === 'validating'}
                />
              )}

              {validation.step === 'error' && (
                <div className="m-6 border border-red-200 bg-red-50 px-4 py-3 rounded shrink-0">
                  <p className="text-sm font-semibold text-red-700 mb-1">Validation Pipeline Failed</p>
                  <p className="text-xs text-red-600 mb-3">{validation.error}</p>
                  <button
                    onClick={validation.reset}
                    className="px-3 py-1.5 rounded bg-white border border-red-200 text-[11px] font-semibold text-red-600 hover:bg-red-50 transition-colors"
                  >
                    Retry Validation
                  </button>
                </div>
              )}

              {validation.step === 'success' && validation.result && (
                <div className="flex-1 h-full">
                  <ValidationDashboard
                    result={validation.result}
                    onReset={validation.reset}
                  />
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </ContentCard>
  );
}
