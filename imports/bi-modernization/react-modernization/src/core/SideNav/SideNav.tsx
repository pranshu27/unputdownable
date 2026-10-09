import React, { useState, useRef, useEffect } from 'react';
import {
  Box,
  IconButton,
  Tooltip,
  Typography,
  Divider,
  Button
} from '@mui/material';
import MenuOpenIcon from '@mui/icons-material/MenuOpen';
import MenuIcon from '@mui/icons-material/Menu';
import AddIcon from '@mui/icons-material/Add';
import './SideNav.scss'
import { useLocation, useNavigate } from 'react-router-dom';

import { useDispatch, UseDispatch } from 'react-redux';
import { storeCode } from '../../utils/codegen.ts';
import type { AppDispatch } from '../../utils/Store';
import CodeGen from '../../Pages/CodeGen/CodeGen.tsx';


const SideNav = ({
  topNavItems = [],
  bottomNavItems = [],
  showExpandToggle = true,
  initialExpanded = false,
  onToggleExpanded
}) => {
  const [expanded, setExpanded] = useState(initialExpanded);
  const location = useLocation();
  const collapsedWidth = 76;
  const expandedWidth = 248;
  const headerHeight = 25;
  const navigate = useNavigate();
  const toggleExpanded = () => {
    const newExpanded = !expanded;
    setExpanded(newExpanded);
    onToggleExpanded?.(newExpanded);
  };
  // use redex to clear the redex store and local storage for gen code 
  const dispatch = useDispatch<AppDispatch>();

  const handleSourceClick = () => {
    localStorage.removeItem("genratedStoredCode")
    dispatch(storeCode(""))
    navigate('/');
  }
  const OverflowTooltip = ({ children, label }) => {
    const textRef = useRef(null);
    const [isOverflowed, setIsOverflowed] = useState(false);

    useEffect(() => {
      const checkOverflow = () => {
        const el = textRef.current;
        if (el) {
          setIsOverflowed(el.scrollWidth > el.clientWidth);
        }
      };
      checkOverflow();
    }, [label]);

    const content = (
      <Typography
        ref={textRef}
        variant="body2"
        noWrap
        sx={{
          ml: 2,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          userSelect: 'none',
          display: 'inline-block',
          maxWidth: expandedWidth - collapsedWidth - 24,
        }}
      >
        {label}
      </Typography>
    );

    return isOverflowed ? (
      <Tooltip title={label} placement="right">
        <Box>{content}</Box>
      </Tooltip>
    ) : (
      content
    );
  };

  const renderNavItem = (item, index) => {
    const isActive = location.pathname === item.path;
  
    return (
      <Tooltip key={index} title={!expanded ? item.label : ''} placement="right">
        <Box
          onClick={() => {
            if (item.path) navigate(item.path);
            if (item.onClick) item.onClick();
          }}
          sx={{
            display: 'flex',
            alignItems: 'center',
            cursor: 'pointer',
            padding: expanded ? '11px 12px' : '11px',
            marginBottom: '6px',
            bgcolor: isActive ? '#fff' : 'transparent',
            color: isActive ? '#c8102e' : '#5c5355',
            border: isActive ? '1px solid rgba(200, 16, 46, 0.12)' : '1px solid transparent',
            boxShadow: isActive ? '0 10px 24px rgba(106, 50, 47, 0.10)' : 'none',
            '&:hover': {
              bgcolor: isActive ? '#fff' : 'rgba(255,255,255,0.70)',
              transform: 'translateX(2px)',
            },
            '& img': {
              filter: isActive ? 'none' : 'grayscale(1) brightness(0.45)',
            },
            '& svg': {
              color: isActive ? '#c8102e !important' : '#6f6668 !important',
            },
            whiteSpace: 'nowrap',
            borderRadius: '8px',
            transition: 'all 0.22s ease',
            justifyContent: expanded ? 'flex-start' : 'center',
            width: expanded ? '206px' : '46px',
          }}
        >
          {item.icon}
          {expanded && (
            <Typography
              sx={{
                fontSize: '14px !important',
                fontWeight: isActive ? '600' : '500',
                ml: '10px',
                color: isActive ? '#c8102e' : '#5c5355'
              }}
            >
              {item.label}
            </Typography>
          )}
        </Box>
      </Tooltip>
    );
  };
  

  return (
    <Box sx={{}}>
      <Box
        sx={{
          position: 'fixed',
          margin: '10px 8px',
          height: `calc(100vh - ${headerHeight}px)`,
          width: expanded ? expandedWidth : collapsedWidth,
          background: 'rgba(255, 253, 252, 0.92)',
          backdropFilter: 'blur(18px)',
          border: '1px solid rgba(126, 113, 109, 0.18)',
          boxShadow: '0 24px 70px rgba(70, 44, 42, 0.12)',
          borderRadius: '8px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          alignItems: 'center',
          transition: 'width 0.28s cubic-bezier(0.2, 0.8, 0.2, 1)',
          zIndex: (theme) => theme.zIndex.appBar - 1,
        }}
      >
        <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: !expanded ? 'center' : 'flex-start' }}>
          {showExpandToggle && (
            <Box sx={{ display: 'flex', justifyContent: 'center', flexDirection: 'column', alignItems: !expanded ? 'center' : 'flex-start', marginTop: '24px' }}>
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center', height: '61px',
                width: expanded ? '200px' : '52px', maxWidth: '200px', background: '#fff', borderRadius: '8px', border: '1px solid rgba(200, 16, 46, 0.14)', boxShadow: '0 14px 32px rgba(70, 44, 42, 0.08)'
              }}>
                <div style={{
                  background: 'linear-gradient(90deg, #8f0d22 0%, #c8102e 100%)',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  fontWeight: 'bold',
                  lineHeight: '1.2',
                  display: 'flex',
                  flexDirection: 'column',
                  padding: '10px',
                  cursor: 'pointer'
                }}
                  onClick={() => {
                    const isLoggedIn = localStorage.getItem('isLoggedIn'); 
                    if (isLoggedIn !== null) {
                      localStorage.setItem('isLoggedIn', isLoggedIn);
                    }
                    if (location.pathname === '' || location.pathname === '/analyze') {
                      // If coming from these routes, clear data
                      localStorage.removeItem("generatedStoredCode");
                      localStorage.removeItem("generatedcodeId");
                      dispatch(storeCode(""));
                    }
                    navigate('/');
                  }}
                >
                  <span className='sideNavTitle'>{expanded ? 'J&J Companion' : 'J&J'}</span>
                </div>
              </div>
              <Box
                sx={{
                  display: 'flex',
                  height: '100px',
                  alignItems: 'center',
                  py: 1,

                }}
              >
                {!expanded ? <Button sx={{
                  background: '#c8102e',
                  borderRadius: '999px',
                  minWidth: '40px !important',
                  position: 'relative',
                  left: '10px',
                  height: '40px',
                  '&:hover': {
                    backgroundColor: 'linear-gradient(to bottom, #b31429 0%, #b31429 50%, #a0042b 50%, #a0042b 100%)',
                  }, textTransform: 'capitalize'
                }} variant="contained" onClick={handleSourceClick}>
                  <AddIcon sx={{fontSize:'18px !important'}} />
                </Button> : <Button sx={{
                  fontSize: '15px !important',
                  background: 'linear-gradient(135deg, #c8102e 0%, #8f0d22 100%)',
                  borderRadius: '999px',
                  width: '170px',
                  height: '48px',
                  left: '20px',
                  '&:hover': {
                    backgroundColor: 'linear-gradient(90deg, #244766 0%, #2972C7 100%)',
                  }, textTransform: 'capitalize'
                }} variant="contained" onClick={handleSourceClick}>
                  <AddIcon sx={{fontSize:'18px !important', marginRight:'8px'}} />  Add Source
                </Button>}
                <IconButton
                  size="small"
                  onClick={toggleExpanded}
                  sx={{
                    position: 'relative',
                    left: '20px',
                    left: expanded ? '40px' : '15px',
                    background: '#fff',
                    color: '#c8102e',
                    border: '1px solid rgba(200, 16, 46, 0.18)',
                    '&:hover': {
                      background: '#fff4f4'
                    },
                    '& svg': {
                      height: '18px !important',
                      width: '18px !important',
                    }
                  }}
                >
                  {expanded ? <MenuOpenIcon /> : <MenuIcon />}
                </IconButton>

              </Box>
            </Box>
          )}

          <Box sx={{ mt: 1 }}>
            {topNavItems.map((item, i) => renderNavItem(item, i))}
          </Box>
        </Box>

        <Box sx={{ mb: '15px', right: '18px' }}>
          {bottomNavItems.map((item, i) => renderNavItem(item, i))}
        </Box>
      </Box>
    </Box>

  );
};

export default SideNav;
