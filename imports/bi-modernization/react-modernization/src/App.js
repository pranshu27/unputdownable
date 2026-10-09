
import React, { useEffect, useState } from 'react';
import { BrowserRouter, useLocation, useNavigate } from 'react-router-dom';
import { Box, Avatar, Typography } from '@mui/material';
import Header from './core/Header/Header.tsx';
import SideNav from './core/SideNav/SideNav.tsx';
import PartnerLogo from './Assets/Logo.png';
import AppRoutes from './utils/AppRoutes.tsx';
import './App.css';
import StorageIcon from '@mui/icons-material/Storage';
import AccountTreeIcon from '@mui/icons-material/AccountTree';
import CalculateIcon from '@mui/icons-material/Calculate';
import HubIcon from '@mui/icons-material/Hub';
import ViewModuleIcon from '@mui/icons-material/ViewModule';
import TroubleshootIcon from '@mui/icons-material/Troubleshoot'; 
import InsightsIcon from '@mui/icons-material/Insights'; 
import LogoutIcon from '@mui/icons-material/Logout';
import technicialAnalysis from './Assets/technicialAnalysis.svg';
import SummaryIcon from './Assets/executivesummary.svg';
import FolderOpenIcon from '@mui/icons-material/FolderOpen';
import SourceIcon from './Assets/source.svg';
import transformations from './Assets/transformations.svg';
import OutputIcon from '@mui/icons-material/Output';
import LineageIcon from '@mui/icons-material/Timeline';
import CodeGenIcon from '@mui/icons-material/Code';
import TableChartIcon from '@mui/icons-material/TableChart';
import FilterListIcon from '@mui/icons-material/FilterList';
import BarChartIcon from '@mui/icons-material/BarChart';
import LanIcon from '@mui/icons-material/Lan';
import SwapHorizIcon from '@mui/icons-material/SwapHoriz';
import SchemaIcon from '@mui/icons-material/Schema';
import SettingsSystemDaydreamIcon from '@mui/icons-material/SettingsSystemDaydream';
import SpaceDashboardIcon from '@mui/icons-material/SpaceDashboard';
import AssignmentIcon from '@mui/icons-material/Assignment';
import DownloadIcon from '@mui/icons-material/Download';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import TaskAltIcon from '@mui/icons-material/TaskAlt';
import { useDispatch } from 'react-redux';
import { setApiData } from './utils/DataSlice.ts';
import ExcelJS from "exceljs";
import JSZip from "jszip";
import { saveAs } from "file-saver";
import { Document, Packer, Paragraph, TextRun } from "docx";
import { RootState } from './utils/Store.ts';
import { useSelector } from 'react-redux';
import { sanitizeToHTML } from './utils/SanitizeAndRender.tsx';
import { Button } from '@mui/material';
import download from './Assets/download.png';
import { marked } from 'marked';
import HtmlDocx from 'html-docx-js/dist/html-docx';
import userProfile from './Assets/userprofile.svg';
import { fetchConfig } from './utils/configSlice.js';
import ChatWidget from './core/ChatWidget.jsx';


const topNavItemsPowerBisx= {
  color: 'white',
  fontSize: '25px !important',
};

const AppLayout = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [isExpanded, setIsExpanded] = useState(false);
  const sideNavWidth = isExpanded ? 256 : 74;

 const [config, setConfig] = useState(null);



  const handleLogoutClick = () => {
    localStorage.clear();
    navigate('/login');
  }
  const reduxData = useSelector((state: RootState) => state.apiData.data);
  const localStorageData = localStorage.getItem('analyzeResponse');
  const parsedLocalData = localStorageData ? JSON.parse(localStorageData) : null;

  const jsonData = parsedLocalData || reduxData;

  let isDownloading = false;


const generateZip = async () => {
  if (isDownloading) return;
  isDownloading = true;

  const zip = new JSZip();
  
  const rawName = fileDetails?.fileName || fileDetails?.filename
  const FileName = rawName
  ? rawName.replace(/\.[a-zA-Z]+$/, "")
  : "analysis_bundle";

  // 1. EXECUTIVE SUMMARY (Word)
  const markdown = jsonData.executivesummary || "<p>No Executive Summary provided.</p>";
  const rawHtml = marked(markdown);
  const styledHtml = `
    <html>
      <head>
        <style>
          body { font-family: Arial, sans-serif; font-size: 12pt; }
          h1, h2, h3, h4 { font-weight: bold; margin-bottom: 10px; }
          p { margin: 5px 0; }
          ul, ol { margin-left: 20px; }
          table { border-collapse: collapse; width: 100%; margin-top: 10px; }
          th, td { border: 1px solid #333; padding: 4px; text-align: left; }
          strong { font-weight: bold; }
        </style>
      </head>
      <body>${rawHtml}</body>
    </html>
  `;
  const docBuffer = HtmlDocx.asBlob(styledHtml);
  zip.file(`${FileName}_Summary.docx`, docBuffer);
  let summaryText = "No summary provided.";
  try {
    if (Array.isArray(jsonData?.summary)) {
      summaryText = jsonData.summary
        .map(line => line.replace(/\*\*/g, '').trim())
        .join("\n")
        .trim();
    }
  } catch (error) {
    console.error("Error processing summary text:", error);
    summaryText = "No summary provided due to error.";
  }
  zip.file(`${FileName}_Tech_Analysis.txt`, summaryText);

  
  const workbook = new ExcelJS.Workbook();
  const headerStyle = {
    fill: { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFDAE8FC' } },
    font: { bold: true, color: { argb: 'FF000000' } },
    alignment: { vertical: 'middle', horizontal: 'center' },
  };

  
  const addDynamicSheet = (sheetName, dataArray) => {
    const sheet = workbook.addWorksheet(sheetName);
    if (!dataArray?.length) return;

    const headers = Object.keys(dataArray[0]);
    const headerRow = sheet.addRow(headers);
    headerRow.eachCell((cell) => (cell.style = headerStyle));

    dataArray.forEach((obj) => {
      const rowValues = headers.map((h) => JSON.stringify(obj[h] ?? ''));
      sheet.addRow(rowValues);
    });

    sheet.columns.forEach((col) => {
      let maxLength = 10;
      col.eachCell({ includeEmpty: true }, (cell) => {
        maxLength = Math.max(maxLength, (cell.value?.toString().length || 0));
      });
      col.width = maxLength + 2;
    });
  };

  if (jsonData.source?.length) addDynamicSheet('Source', jsonData.source);
  if (jsonData.transformations?.length) addDynamicSheet('Transformation', jsonData.transformations);
  if (jsonData.output?.length) {
    const outputData = jsonData.output.map((o) =>
      o.field_names ? { ...o, ...o.field_names } : o
    );
    addDynamicSheet('Output', outputData);
  }
  if (jsonData.customCalculations?.length) {
    addDynamicSheet('Custom Calculation', jsonData.customCalculations);
  }

  const excelBuffer = await workbook.xlsx.writeBuffer();
  zip.file(`${FileName}_Analysis.xlsx`, excelBuffer);

  const zipBlob = await zip.generateAsync({ type: "blob" });
  saveAs(zipBlob,`${FileName}.zip`);
  isDownloading = false;
};

  const rightIcons = [
    {
      icon: (
        <Button
          variant="contained"
          onClick={generateZip}
          className="btn-download"
          style={{
            minWidth: '48px',
            height: '48px',
            width: '48px',
            borderRadius: '50%',
            backgroundColor: 'rgba(255, 255, 255, 1)',
            color: 'rgba(197,45,22,1)',
            // boxShadow: '4px 4px 8px 0px rgba(255, 195, 203, 0.15)',
            padding: '8px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <img
            src={download}
            alt="Download"
            style={{ width: '24px', height: '24px',
            }}
          />
        </Button>
      ),
      tooltip: 'Download Analysis',
      onClick: () => generateZip(),
    },
   {
  icon: (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        bgcolor: '#ffffff',
        p: 1,
        width:'182px',
        maxWidth:'182px',
        borderRadius: '999px',
        // boxShadow: 1,
        cursor: 'pointer',
      }}
    >
     <img src={userProfile} alt='User Profile' />

      <Box sx={{ ml: 1,marginTop:'4px' }}>
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          Admin
        </Typography>
        <Typography variant="caption" color="text.secondary">
          Administrator
        </Typography>
      </Box>
      {/* <KeyboardArrowDownIcon fontSize="small" sx={{ ml: 1 }} /> */}
    </Box>
  ),
  tooltip: 'Profile',
  menuItems: [{ label: 'Logout', onClick: () => handleLogoutClick() }],
},
  ];
  const topNavItems = [
    { icon: <img color='red' src={technicialAnalysis} alt= "Technicial Analysis" />, label: 'Technical Analysis', path: '/technical-analysis', onClick: () => navigate('/technical-analysis') },
    { icon: <img src= {SummaryIcon} alt="executive summary Logo" />, label: 'Executive Summary', path: '/executive-summary', onClick: () => navigate('/executive-summary') },
    { icon: <img src={SourceIcon} alt="Source Logo" />, label: 'Source', path: '/source', onClick: () => navigate('/source') },
    { icon: <img src={transformations} alt="Transformations" />, label: 'Transformation', path: '/transformation', onClick: () => navigate('/transformation') },
    { icon: <OutputIcon sx={{ color: 'white', fontSize: '25px !important' }} />, label: 'Output', path: '/output', onClick: () => navigate('/output') },
    { icon: <LineageIcon sx={{ color: 'white' ,fontSize: '25px !important'}} />, label: 'Lineage', path: '/lineage', onClick: () => navigate('/lineage') },
    { icon: <CodeGenIcon sx={{ color: 'white',fontSize: '25px !important' }} />, label: 'Code Gen', path: '/code-gen', onClick: () => navigate('/code-gen') },
  ];

  const topNavItemsPowerBi = [
    {
      icon: <FolderOpenIcon sx={topNavItemsPowerBisx} />,
      label: 'Files',
      path: '/files',
      onClick: () => navigate('/files'),
    },
    {
      icon: <SpaceDashboardIcon sx={topNavItemsPowerBisx} />,
      label: 'Overview',
      path: '/overview',
      onClick: () => navigate('/overview'),
    },
    {
      icon: <AssignmentIcon sx={topNavItemsPowerBisx} />,
      label: 'Summary',
      path: '/technicalSummary',
      onClick: () => navigate('/technicalSummary'),
    },
    {
      icon: <StorageIcon sx={topNavItemsPowerBisx} />,
      label: 'Data Sources',
      path: '/datasources',
      onClick: () => navigate('/datasources'),
    },
    {
      icon: <ViewModuleIcon sx={topNavItemsPowerBisx}  />,
      label: 'Consolidated Model',
      path: '/calculations',
      onClick: () => navigate('/calculations'),
    },
    {
      icon: <HubIcon sx={topNavItemsPowerBisx} />,
      label: 'Report Explorer',
      path: '/relationships',
      onClick: () => navigate('/relationships'),
    },
    {
      icon: <TroubleshootIcon sx={topNavItemsPowerBisx} />,
      label: 'Intelligence Hub',
      path: '/intelligence-hub',
      onClick: () => navigate('/intelligence-hub'),
    },
    { icon: <CodeGenIcon sx={topNavItemsPowerBisx} />, label: 'Code Generation', path: '/code-gen', onClick: () => navigate('/code-gen') },
  ];

  const topNavItemsTablue = [
    { icon: <AssignmentIcon  sx={topNavItemsPowerBisx} />, label: 'Executive Summary', path: '/executive-summary', onClick: () => navigate('/executive-summary') },
    { icon: <SpaceDashboardIcon  sx={topNavItemsPowerBisx} />, label: 'Dashboards', path: '/dashboards', onClick: () => navigate('/dashboards') },
    { icon: <SettingsSystemDaydreamIcon  sx={topNavItemsPowerBisx} />, label: 'Data Sources', path: '/data-tableau', onClick: () => navigate('/data-tableau') },
    { icon: <SchemaIcon  sx={topNavItemsPowerBisx} />, label: 'Data Model', path: '/datamodel', onClick: () => navigate('/datamodel') },
    { icon: <SwapHorizIcon  sx={topNavItemsPowerBisx} />, label: 'Data Transformation', path: '/trasformation-tableau', onClick: () => navigate('/trasformation-tableau') },
    { icon: <LanIcon  sx={topNavItemsPowerBisx} />, label: 'Hierarchies', path: '/hierarchies', onClick: () => navigate('/hierarchies') },
    { icon: <FilterListIcon  sx={topNavItemsPowerBisx} />, label: 'Filters', path: '/filters', onClick: () => navigate('/filters') },
    { icon: <TableChartIcon sx={topNavItemsPowerBisx}  />, label: 'Sheets', path: '/sheets', onClick: () => navigate('/sheets') },
    { icon: <CodeGenIcon sx={topNavItemsPowerBisx} />, label: 'Code Gen', path: '/code-gen', onClick: () => navigate('/code-gen') },
  ];

  const topNavQliksense = [
    // { icon: <SpaceDashboardIcon  sx={topNavItemsPowerBisx} />, label: 'Dashboards', path: '/dashboards', onClick: () => navigate('/dashboards') },
    { icon: <SwapHorizIcon  sx={topNavItemsPowerBisx} />, label: 'Results', path: '/qliksense', onClick: () => navigate('/qliksense') },
    // { icon: <TableChartIcon sx={topNavItemsPowerBisx}  />, label: 'Sheets', path: '/sheets', onClick: () => navigate('/sheets') },
    // { icon: <CodeGenIcon sx={topNavItemsPowerBisx} />, label: 'Code Gen', path: '/code-gen', onClick: () => navigate('/code-gen') },
  ];

  const bottomNavItems = [
    {
      icon: (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <img src={PartnerLogo} alt="Partner Logo"  />
        { isExpanded &&  <Typography
            sx={{ fontWeight: 500, color: 'rgba(225, 225, 225, 1)',fontSize:'14px !important',letterSpacing:'0.1px'
            }}
          >
            J&J
          </Typography>}
        </Box>
      ),
      onClick: () => handleLogoutClick(),
    },
  ];

  const routeTitles = {
    '/technical-analysis': 'Technical Analysis',
    '/executive-summary': 'Executive Summary',
    '/source': 'Source',
    '/transformation': 'Transformation',
    '/output': 'Output',
    '/lineage': 'Lineage',
    '/code-gen': 'Code Gen',
  };
  const currentTitle = routeTitles[location.pathname] || ' ';
  const hideLayoutRoutes = ['/', '/login','/signup','/upload','/data','/sttm','/migration'];
  const shouldHideLayout = hideLayoutRoutes.includes(location.pathname);
  const filesOverviewRoute = location.pathname === '/files';
  const dispatch = useDispatch();
  const fileDetails = JSON.parse(localStorage.getItem('fileDetails'));
  const etlTool = fileDetails?.etlTool ;
  // const selectedTopNavItems = etlTool === "tableau-workbook" ? topNavItemsPowerBi : topNavItems;
  const selectedTopNavItems =
  (location.pathname.startsWith('/files') || etlTool === 'powerbi' || etlTool === 'tableau-workbook')
      ? topNavItemsPowerBi
      : etlTool === 'qlik'
        ? topNavQliksense : ( etlTool === 'qlikview') ? topNavItemsTablue
        : topNavItems;

  useEffect(() => {
    if (localStorage.getItem('analyzeResponse')) {
      dispatch(setApiData(JSON.parse(localStorage.getItem('analyzeResponse'))))
    }
  }, [])

  useEffect(() => {
    dispatch(fetchConfig());
  }, [dispatch]);

  useEffect(() => {
    const handleExportRequest = () => {
      generateZip();
    };
    window.addEventListener('jnj:export-request', handleExportRequest);
    return () => window.removeEventListener('jnj:export-request', handleExportRequest);
  }, []);

  return (
    <Box display="flex" sx={{backgroundColor:'var(--surface-bg)',height:'100vh', color:'var(--text-primary)'}}>
      
      <Box flex={1}>
        
        <AppRoutes sideNavWidth={0} />
      </Box>
      
    </Box>
  );
};

const App = () => (
  <BrowserRouter>
    <AppLayout  />
  </BrowserRouter>
);

export default App;
