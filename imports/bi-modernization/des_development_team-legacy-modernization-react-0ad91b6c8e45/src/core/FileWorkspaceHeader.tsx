import React, { useEffect, useMemo, useState } from 'react';
import { Button, Dialog, DialogContent, Drawer, IconButton, MenuItem, Select } from '@mui/material';
import { AlertTriangle, Braces, CheckCircle2, Clock, Database, Download, FileUp, FolderOpen, LogOut, RefreshCw, ShieldCheck, X } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { fetchPowerBiReport, listPowerBiReports, ReportListItem } from '../services/powerbiReports.ts';

interface FileWorkspaceHeaderProps {
  pageTitle: string;
}

const getActiveFileLabel = () => {
  try {
    const fileDetails = JSON.parse(localStorage.getItem('fileDetails') || '{}');
    return localStorage.getItem('activePowerBiReportFile') || fileDetails?.fileName || '';
  } catch {
    return localStorage.getItem('activePowerBiReportFile') || '';
  }
};

const getToolLabel = (fileName: string) => {
  const normalized = String(fileName || '').toLowerCase();
  if (normalized.endsWith('.pbix')) return 'Power BI';
  if (normalized.endsWith('.twb') || normalized.endsWith('.twbx')) return 'Tableau';
  return 'Dataset';
};

const getToolName = (fileName: string) => {
  const normalized = String(fileName || '').toLowerCase();
  if (normalized.endsWith('.pbix')) return 'powerbi';
  if (normalized.endsWith('.twb') || normalized.endsWith('.twbx')) return 'tableau-workbook';
  return 'powerbi';
};

const getReadinessScore = (report?: ReportListItem | null) => {
  const status = String(report?.status || '').toUpperCase();
  if (status === 'SUCCESS') return '92%';
  if (status === 'FAILED') return '41%';
  return '76%';
};

export default function FileWorkspaceHeader({ pageTitle }: FileWorkspaceHeaderProps) {
  return null;
}
