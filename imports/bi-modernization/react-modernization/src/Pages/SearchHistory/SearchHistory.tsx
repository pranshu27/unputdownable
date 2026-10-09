import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDispatch } from 'react-redux';
import { setApiData } from '../../utils/DataSlice.ts';
import { setFormData } from '../../utils/formSlice.ts';
import { setSelectedCase } from "../../utils/selectedCaseSlice.ts";
import { 
  Search, Download, Share2, FileCode2, Clock, CheckCircle2, User, RefreshCw
} from 'lucide-react';
import ContentCard from '../../core/CardContent/CardContent.tsx';
import FileWorkspaceHeader from '../../core/FileWorkspaceHeader.tsx';

// Dummy Responses imports
import ssisResponse from '../../SSIS.json';
import XpierResponse from '../../xpier.json';
import Qliksense from '../../qliksense.json';
import Alteryx200Node from '../../200node.json';
import IIBFile from '../../iib.json';
import powerCenter from '../../powerCenter.json';
import IICS from '../../IICS.json';
import Datastage from '../../Datastage.json';
import Altreyx200Node from '../../200node.json';
import teradataSql from '../../teradatasql.json';
import teradata from '../../teradata.json';
import PowerbiFile from '../../Powerbi.json';
import basicInteraction from '../../basicInteractiongroup.json';
import SasResponse from '../../SAS.json';
import talendResponse from '../../talendPySpark.json';
import BTEQResponse from '../../BTEQResponse.json';
import talendPythonResp from '../../talend-python.json';
import AlteryxBigQueryResponse from '../../AlteryxBigQuery.json';
import TalendSnowFlakeResponse from'../../snowFlake.json';

function handle_dummy_sample_case(file) {
  if (!file || !file.fileName) return null;
  switch (true) {
    case file.fileName === "(SSIS) Salesforce_Downstream_AuditItem_and_AuditItem_ParsedLog 1 3.dtsx": return ssisResponse;
    case file.fileName === "(Xpier) DL_TC3_PM1_final_1_27 16_SAP_Hanna 2.yxmd": return XpierResponse;
    case file.fileName === "(Qliksense) asset_management_json_output 1.zip": return Qliksense;
    case file.fileName === "(Alteryx-Pyspark) C03_pjotr 4.yxmd": return Alteryx200Node;
    case file.fileName === "(IIB) sample_msgflow.xml": return IIBFile;
    case file.fileName === "(Powercenter) s_m_NU0C_NISS_AUTO_103_ATPRM_DTL_Upd_ClassCd": return powerCenter;
    case file.fileName === "(IICS) wf_W_CLAIM_CD_SCD3_IU-1747262510236.zip": return IICS;
    case file.fileName === "(Datastage) HANA_ldap_trn_hana_CREDIT_USER_INFO.xml": return Datastage;
    case file.fileName === "(Alteryx-Pyspark-Databricks) DL_TC3_PM1_final_1_27 17": return Altreyx200Node;
    case file.fileName === "(SQL) app_BLBIS_BILL3.BLBIS_BIL_Id_XT1_V1.sql": return teradataSql;
    case file.fileName === "app_BLBIS_BILL3.BLBIS_BIL_Id_XT1 3.bteq": return teradata;
    case file.fileName === "(Powerbi) AssetSpend_Pharma.pbix": return PowerbiFile;
    case file.fileName === "(Powercenter) wf_3202_baseinteractiongroup.XML": return basicInteraction;
    case file.fileName === "(SAS - Python)CustomerInsightEngine.sas": return SasResponse;
    case file.fileName === "(Talend - Pyspark) JOB_MKT_RISK_CALYPSO_SWAP_TXN_ARML2.item": return talendResponse;
    case file.fileName === "(BTEQ - Pyspark) app_BLBIS_BILL3.BLBIS_BIL_Id_XT1 10.bteq": return BTEQResponse;
    case file.fileName === "(Talend - Python) JOB_MKT_RISK_CALYPSO_SWAP_TXN_ARML2.item": return talendPythonResp;
    case file.fileName === "(Alteryx-BigQuery) DL_TC3_PM1_final_1_27 16_SAP_Hanna 2 1.yxmd": return AlteryxBigQueryResponse;
    case file.fileName === "(Talend - snowflake) JOB_MKT_RISK_CALYPSO_SWAP_TXN_ARML2.item": return TalendSnowFlakeResponse;
    default: return null;
  }
}

const dummyData = [
  { fileName: '(Talend - Pyspark) JOB_MKT_RISK_CALYPSO_SWAP_TXN_ARML2.item', date: new Date(), analysedBy: 'admin@dataeconomy.ai', type: 'analysed', isDisabled: false },
  { fileName: '(Talend - Python) JOB_MKT_RISK_CALYPSO_SWAP_TXN_ARML2.item', date: new Date(), analysedBy: 'admin@dataeconomy.ai', type: 'analysed', isDisabled: false },
  { fileName: '(Talend - snowflake) JOB_MKT_RISK_CALYPSO_SWAP_TXN_ARML2.item', date: new Date(), analysedBy: 'admin@dataeconomy.ai', type: 'analysed', isDisabled: false },
  { fileName: '(Powerbi) AssetSpend_Pharma.pbix', date: new Date(), analysedBy: 'admin@dataeconomy.ai', type: 'analysed', isDisabled: false },
  { fileName: '(Qliksense) asset_management_json_output 1.zip', date: new Date(), analysedBy: 'admin@dataeconomy.ai', type: 'analysed', isDisabled: false },
  { fileName: '(SAS - Python)CustomerInsightEngine.sas', date: new Date(), analysedBy: 'admin@dataeconomy.ai', type: 'analysed', isDisabled: false },
  { fileName: '(Alteryx-Pyspark) C03_pjotr 4.yxmd', date: new Date(), analysedBy: 'admin@dataeconomy.ai', type: 'analysed', isDisabled: false },
  { fileName: '(SQL) app_BLBIS_BILL3.BLBIS_BIL_Id_XT1_V1.sql', date: new Date(new Date().getTime() - 8 * 60 * 60 * 1000), analysedBy: 'admin@dataeconomy.ai', type: 'shared', isDisabled: false },
  { fileName: '(IICS) wf_W_CLAIM_CD_SCD3_IU-1747262510236.zip', date: new Date(new Date().getTime() - 8 * 60 * 60 * 1000), analysedBy: 'admin@dataeconomy.ai', type: 'shared', isDisabled: false },
  { fileName: '(Datastage) HANA_ldap_trn_hana_CREDIT_USER_INFO.xml', date: new Date(new Date().getTime() - 6 * 60 * 60 * 1000), analysedBy: 'admin@dataeconomy.ai', type: 'shared', isDisabled: false },
  { fileName: '(IIB) sample_msgflow.xml', date: new Date(new Date().getTime() - 6 * 60 * 60 * 1000), analysedBy: 'admin@dataeconomy.ai', type: 'shared', isDisabled: false },
  { fileName: '(Powercenter) wf_3202_baseinteractiongroup.XML', date: new Date(new Date().getTime() - 6 * 60 * 60 * 1000), analysedBy: 'admin@dataeconomy.ai', type: 'shared', isDisabled: false },
  { fileName: '(Powercenter) s_m_NU0C_NISS_AUTO_103_ATPRM_DTL_Upd_ClassCd', date: new Date(new Date().getTime() - 6 * 60 * 60 * 1000), analysedBy: 'admin@dataeconomy.ai', type: 'shared', isDisabled: false },
  { fileName: '(Alteryx-Pyspark-Databricks) DL_TC3_PM1_final_1_27 17', date: new Date(new Date().getTime() - 1 * 60 * 60 * 1000), analysedBy: 'admin@dataeconomy.ai', type: 'analysed', isDisabled: false },
  { fileName: '(SSIS) Salesforce_Downstream_AuditItem_and_AuditItem_ParsedLog 1 3.dtsx', date: new Date(new Date().getTime() - 1 * 60 * 60 * 1000), analysedBy: 'admin@dataeconomy.ai', type: 'analysed', isDisabled: false },
  { fileName: '(Xpier) DL_TC3_PM1_final_1_27 16_SAP_Hanna 2.yxmd', date: new Date(new Date().getTime() - 8 * 60 * 60 * 1000), analysedBy: 'admin@dataeconomy.ai', type: 'analysed', isDisabled: false },
  { fileName: '(BTEQ -PySpark) app_BLBIS_BILL3.BLBIS_BIL_Id_XT1 10.bteq', date: new Date(new Date().getTime() - 8 * 60 * 60 * 1000), analysedBy: 'admin@dataeconomy.ai', type: 'analysed', isDisabled: false },
  { fileName: '(Alteryx-BigQuery) DL_TC3_PM1_final_1_27 16_SAP_Hanna 2 1.yxmd', date: new Date(new Date().getTime() - 6 * 60 * 60 * 1000), analysedBy: 'admin@dataeconomy.ai', type: 'shared', isDisabled: false },
];

export default function SearchHistory() {
  const navigate = useNavigate();
  const dispatch = useDispatch();
  const [activeTab, setActiveTab] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState('recent');

  useEffect(() => {
    localStorage.removeItem("generatedStoredCode");
    localStorage.removeItem("generatedcodeId");
  }, []);

  const filteredFiles = useMemo(() => {
    let files = dummyData;
    if (activeTab === 'my_files') {
      files = files.filter(f => f.type === 'analysed');
    } else if (activeTab === 'shared') {
      files = files.filter(f => f.type === 'shared');
    }
    
    const q = searchQuery.toLowerCase().trim();
    if (q) {
      files = files.filter(f => f.fileName.toLowerCase().includes(q));
    }
    
    return [...files].sort((a, b) => {
      if (sortBy === 'name') return a.fileName.localeCompare(b.fileName);
      return b.date.getTime() - a.date.getTime();
    });
  }, [activeTab, searchQuery, sortBy]);

  const handleSelectedFileClick = (file) => {
    const response = handle_dummy_sample_case(file);
    if (file.fileName.includes("Alteryx") || file.fileName.includes("Xpier") || file.fileName.includes("Datastage") || file.fileName.includes("IIB") || file.fileName.includes("sas") || file.fileName.includes("Talend")) {
      dispatch(setSelectedCase("jnj"));
      localStorage.setItem("selectedCase", "CLIENT_B");
    } else {
      dispatch(setSelectedCase("CLIENT_B"));
    }
    
    if (response) {
      const {
        filename = '', etlTool = '', model = '', technology = '', framework = '',
      } = response;
      dispatch(setFormData({ filename, etlTool, model, technology, framework }));
      dispatch(setApiData(response.response));
      localStorage.setItem('analyzeResponse', JSON.stringify(response.response));
      localStorage.setItem("fileDetails", JSON.stringify({ filename, etlTool, model, technology, framework }));
    }

    if (file.fileName.includes("Powerbi")) {
      navigate('/overview');
    } else if (file.fileName.includes("Qliksense")) {
      navigate('/qliksense');
    } else {
      navigate('/technical-analysis');
    }
  };

  const stringToColor = (str) => {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      hash = str.charCodeAt(i) + ((hash << 5) - hash);
    }
    return `hsl(${hash % 360}, 60%, 45%)`;
  };

  return (
    <div className="flex h-[calc(100vh-116px)] flex-col bg-[#f8fafc] w-full relative">
      <FileWorkspaceHeader pageTitle="Legacy Migration Reports" />

      <ContentCard flat={true} noscroll={true}>
        <div className="flex h-full flex-col">
          {/* Toolbar */}
          <div className="flex items-center justify-between border-b border-slate-100 bg-white p-4">
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2 rounded-xl bg-slate-100 p-1">
                {['all', 'my_files', 'shared'].map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`rounded-lg px-4 py-1.5 text-sm font-semibold transition ${
                      activeTab === tab
                        ? 'bg-white text-[#003087] shadow-sm'
                        : 'text-slate-500 hover:text-slate-700'
                    }`}
                  >
                    {tab === 'all' && 'All Reports'}
                    {tab === 'my_files' && 'My Files'}
                    {tab === 'shared' && 'Shared With Me'}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-center gap-3">
              <div className="relative">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  placeholder="Search reports..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="h-9 w-64 rounded-lg border border-slate-200 pl-9 pr-4 text-sm outline-none focus:border-[#003087] focus:ring-1 focus:ring-[#003087] transition"
                />
              </div>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
                className="h-9 rounded-lg border border-slate-200 px-3 text-sm font-medium outline-none hover:bg-slate-50 focus:border-[#003087]"
              >
                <option value="recent">Recently Analyzed</option>
                <option value="name">File Name</option>
              </select>
              <button 
                onClick={() => {}} 
                className="flex h-9 items-center gap-2 rounded-lg border border-slate-200 px-3 text-sm font-medium hover:bg-slate-50 transition"
              >
                <RefreshCw size={14} /> Refresh
              </button>
            </div>
          </div>

          {/* Data Grid */}
          <div className="flex-1 overflow-auto bg-white">
            <table className="w-full text-left text-sm">
              <thead className="sticky top-0 z-10 bg-slate-50 shadow-sm">
                <tr>
                  <th className="px-6 py-4 font-semibold text-slate-500">File Name</th>
                  <th className="px-6 py-4 font-semibold text-slate-500">Status</th>
                  <th className="px-6 py-4 font-semibold text-slate-500">Analyzed By</th>
                  <th className="px-6 py-4 font-semibold text-slate-500">Last Analyzed</th>
                  <th className="px-6 py-4 font-semibold text-slate-500 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredFiles.map((file, idx) => {
                  const match = file.fileName.match(/^\((.*?)\)\s*(.*)$/);
                  const toolType = match ? match[1] : 'Dataset';
                  const baseName = match ? match[2] : file.fileName;

                  const ownerName = file.analysedBy.includes('user') ? 'You' : file.analysedBy.split('@')[0];
                  const ownerColor = stringToColor(ownerName);

                  return (
                    <tr 
                      key={idx} 
                      onClick={() => !file.isDisabled && handleSelectedFileClick(file)}
                      className={`group transition ${file.isDisabled ? 'opacity-50 cursor-not-allowed bg-slate-50' : 'cursor-pointer hover:bg-slate-50'}`}
                    >
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#003087]/5 text-[#003087] transition group-hover:bg-[#003087]/10">
                            <FileCode2 size={18} />
                          </div>
                          <div>
                            <p className="font-semibold text-slate-900 group-hover:text-[#003087] transition">{baseName}</p>
                            <span className="mt-0.5 inline-block rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-500">
                              {toolType}
                            </span>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700">
                          <CheckCircle2 size={12} /> Ready
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          <div 
                            className="flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold text-white shadow-sm"
                            style={{ backgroundColor: ownerColor }}
                          >
                            {ownerName.charAt(0).toUpperCase()}
                          </div>
                          <span className="text-slate-600 font-medium capitalize">{ownerName}</span>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2 text-slate-500">
                          <Clock size={14} />
                          <span>{file.date.toLocaleDateString()} at {file.date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-right">
                        <div className="flex justify-end gap-2" onClick={(e) => e.stopPropagation()}>
                          <button 
                            disabled={file.isDisabled}
                            onClick={() => handleSelectedFileClick(file)}
                            className="rounded-lg bg-slate-100 px-3 py-1.5 font-semibold text-slate-700 hover:bg-[#003087] hover:text-white transition disabled:opacity-50"
                          >
                            Analyze
                          </button>
                          <button 
                            disabled={file.isDisabled}
                            title="Download Report"
                            className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 text-slate-400 hover:border-[#003087] hover:text-[#003087] transition disabled:opacity-50"
                          >
                            <Download size={14} />
                          </button>
                          <button 
                            disabled={file.isDisabled}
                            onClick={() => navigate("/share", { state: { file } })}
                            title="Share"
                            className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 text-slate-400 hover:border-[#003087] hover:text-[#003087] transition disabled:opacity-50"
                          >
                            <Share2 size={14} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            {filteredFiles.length === 0 && (
              <div className="flex h-64 flex-col items-center justify-center text-slate-400">
                <FileCode2 size={48} className="mb-4 opacity-20" />
                <p className="text-lg font-semibold text-slate-600">No reports found</p>
                <p className="text-sm">Try adjusting your search or filters.</p>
              </div>
            )}
          </div>
        </div>
      </ContentCard>
    </div>
  );
}
