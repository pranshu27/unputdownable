import React, { useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Box, Tooltip, Typography, Button, IconButton } from '@mui/material';
import MenuOpenIcon from '@mui/icons-material/MenuOpen';
import MenuIcon from '@mui/icons-material/Menu';
import AddIcon from '@mui/icons-material/Add';
import SpaceDashboardIcon from '@mui/icons-material/SpaceDashboard';
import AssignmentIcon from '@mui/icons-material/Assignment';
import StorageIcon from '@mui/icons-material/Storage';
import HubIcon from '@mui/icons-material/Hub';
import TableChartIcon from '@mui/icons-material/TableChart';
import InsightsIcon from '@mui/icons-material/Insights';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import TaskAltIcon from '@mui/icons-material/TaskAlt';
import CodeIcon from '@mui/icons-material/Code';
import ViewModuleIcon from '@mui/icons-material/ViewModule';
import { useDispatch } from 'react-redux';
import { storeCode } from './codegen.ts';
import ChatWidget from '../core/ChatWidget.jsx';

const iconSx = { color: 'inherit', fontSize: '20px !important' };
const navItems = [
  { icon: <SpaceDashboardIcon sx={iconSx} />, label: 'Overview', path: '/overview' },
  { icon: <AssignmentIcon sx={iconSx} />, label: 'Summary', path: '/technicalSummary' },
  { icon: <StorageIcon sx={iconSx} />, label: 'Data Sources', path: '/datasources' },
  { icon: <HubIcon sx={iconSx} />, label: 'Relationships', path: '/relationships' },
  { icon: <TableChartIcon sx={iconSx} />, label: 'Calculations', path: '/calculations' },
  { icon: <InsightsIcon sx={iconSx} />, label: 'KPI Lineage', path: '/kpiLineage' },
  { icon: <ViewModuleIcon sx={iconSx} />, label: 'Consolidated Model', path: '/consolidated-model' },
  { icon: <WarningAmberIcon sx={iconSx} />, label: 'Intelligence Hub', path: '/intelligence-hub' },
  { icon: <TaskAltIcon sx={iconSx} />, label: 'Validation Report', path: '/validation-dashboard' },
  { icon: <CodeIcon sx={iconSx} />, label: 'Code Generation', path: '/code-gen' },
];

const WorkspaceLayout = () => {
  const [expanded, setExpanded] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const dispatch = useDispatch();
  const collapsedWidth = 72;
  const expandedWidth = 244;
  const sideNavWidth = expanded ? expandedWidth : collapsedWidth;

  const handleSourceClick = () => {
    localStorage.removeItem('genratedStoredCode');
    dispatch(storeCode(''));
    navigate('/');
  };

  return (
    <Box display="flex" sx={{ height: '100vh', background: '#f8f6f5' }}>
      <Box sx={{
        position: 'fixed', top: 0, left: 0, bottom: 0, width: sideNavWidth,
        background: 'rgba(255,253,252,0.96)', backdropFilter: 'blur(18px)',
        borderRight: '1px solid rgba(126,113,109,0.14)',
        boxShadow: '4px 0 24px rgba(70,44,42,0.06)',
        display: 'flex', flexDirection: 'column',
        transition: 'width 0.26s cubic-bezier(0.2,0.8,0.2,1)',
        zIndex: 1200, overflow: 'hidden',
      }}>
        <Box sx={{ px: expanded ? 2 : 1.5, pt: 2.5, pb: 1 }}>
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            height: 52, width: expanded ? 210 : 46, margin: '0 auto',
            background: '#fff', borderRadius: 8,
            border: '1px solid rgba(200,16,46,0.14)',
            boxShadow: '0 8px 24px rgba(70,44,42,0.06)', cursor: 'pointer',
            transition: 'width 0.26s ease',
          }} onClick={() => navigate('/')}>
            <div style={{
              background: 'linear-gradient(90deg,#8f0d22,#c8102e)',
              WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
              fontWeight: 'bold', fontSize: expanded ? 15 : 13,
            }}>{expanded ? 'J&J Companion' : 'J&J'}</div>
          </div>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1, mt: 2, mb: 1 }}>
            {!expanded ? (
              <Button sx={{ background: '#c8102e', borderRadius: '999px', minWidth: '38px !important', height: 38, '&:hover': { background: '#a00d24' } }} variant="contained" onClick={handleSourceClick}>
                <AddIcon sx={{ fontSize: '17px !important' }} />
              </Button>
            ) : (
              <Button sx={{ fontSize: '13px !important', background: 'linear-gradient(135deg,#c8102e,#8f0d22)', borderRadius: '999px', width: 170, height: 42, '&:hover': { background: '#a00d24' }, textTransform: 'capitalize' }} variant="contained" onClick={handleSourceClick}>
                <AddIcon sx={{ fontSize: '16px !important', mr: '6px' }} /> Add Source
              </Button>
            )}
            <IconButton size="small" onClick={() => setExpanded(p => !p)} sx={{ background: '#fff', color: '#c8102e', border: '1px solid rgba(200,16,46,0.18)', '&:hover': { background: '#fff4f4' }, '& svg': { height: '16px !important', width: '16px !important' } }}>
              {expanded ? <MenuOpenIcon /> : <MenuIcon />}
            </IconButton>
          </Box>
        </Box>
        <Box sx={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', px: expanded ? 1.5 : 1, pt: 0.5 }}>
          {navItems.map((item, index) => {
            const isActive = location.pathname === item.path;
            return (
              <Tooltip key={index} title={!expanded ? item.label : ''} placement="right">
                <Box onClick={() => navigate(item.path)} sx={{
                  display: 'flex', alignItems: 'center', cursor: 'pointer',
                  padding: expanded ? '10px 12px' : '10px', mb: '4px',
                  bgcolor: isActive ? '#fff' : 'transparent',
                  color: isActive ? '#c8102e' : '#5c5355',
                  border: isActive ? '1px solid rgba(200,16,46,0.12)' : '1px solid transparent',
                  boxShadow: isActive ? '0 6px 18px rgba(106,50,47,0.08)' : 'none',
                  '&:hover': { bgcolor: isActive ? '#fff' : 'rgba(255,255,255,0.70)', transform: 'translateX(1px)' },
                  '& svg': { color: isActive ? '#c8102e !important' : '#6f6668 !important' },
                  whiteSpace: 'nowrap', borderRadius: '8px', transition: 'all 0.2s ease',
                  justifyContent: expanded ? 'flex-start' : 'center', minHeight: 40,
                }}>
                  {item.icon}
                  {expanded && (
                    <Typography sx={{ fontSize: '13px !important', fontWeight: isActive ? '600' : '500', ml: '10px', color: isActive ? '#c8102e' : '#5c5355' }}>
                      {item.label}
                    </Typography>
                  )}
                </Box>
              </Tooltip>
            );
          })}
        </Box>
        <Box sx={{ px: 2, py: 2, borderTop: '1px solid rgba(0,0,0,0.06)' }}>
          <Typography sx={{ fontSize: '10px !important', color: '#9ca3af', textAlign: 'center', letterSpacing: '0.5px', textTransform: 'uppercase' }}>
            {expanded ? 'J&J' : 'J&J'}
          </Typography>
        </Box>
      </Box>
      <Box sx={{ flex: 1, ml: `${sideNavWidth}px`, transition: 'margin-left 0.26s cubic-bezier(0.2,0.8,0.2,1)', height: '100vh', overflow: 'hidden', position: 'relative' }}>
        <Outlet context={{ sideNavWidth: 0 }} />
      </Box>
      {/* Chat Widget (replacing GlobalJobTracker) */}
      <ChatWidget />
    </Box>
  );
};

export default WorkspaceLayout;
