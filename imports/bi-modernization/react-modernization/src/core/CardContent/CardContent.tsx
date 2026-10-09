import React from 'react';
import {
  Box,
  Card,
  CardContent,
  IconButton,
  Tooltip,
} from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import { useNavigate } from 'react-router-dom';

const ContentCard = ({
  children,
  sideNavWidth = 74,
  headerHeight = 0,
  cardMargin = 16,
  heading = null,
  bottomContent = null,
  noscroll = false,
  showBackButton = false,
  headerActions = null, 
  searchComponent = null, // <-- NEW PROP
  headerComponent = null,
  flat = false, // <-- NEW flat PROP
  noPadding = false,
}) => {
  const navigate = useNavigate();

  return (
    <Box
      sx={{
        position: 'absolute',
        top: 0,
        left: sideNavWidth,
        right: 0,
        bottom: 0,
        padding: flat ? '0px' : `10px 18px ${cardMargin}px`,
        boxSizing: 'border-box',
        display: 'flex',
        flexDirection: 'column',
        gap: flat ? '0px' : '10px',
        background: flat ? 'var(--surface-bg)' :
          'radial-gradient(circle at 18% 0%, rgba(200,16,46,0.08), transparent 28%), linear-gradient(180deg, #fbf8f7 0%, #f4eeee 100%)',
      }}
    >
      {headerComponent}
      <Card
        sx={{
          width: '100%',
          flex: 1,
          minHeight: 0,
          bgcolor: flat ? 'var(--surface-bg)' : '#fffdfc',
          overflow: 'hidden',
          display: 'flex',
          borderRadius: flat ? '0px' : '8px',
          border: flat ? 'none' : '1px solid rgba(126, 113, 109, 0.18)',
          boxShadow: flat ? 'none' : '0 22px 70px rgba(70, 44, 42, 0.08)',
          flexDirection: 'column',
        }}
      >
        <CardContent
          sx={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            p: 0,
          }}
        >
          {heading && (
            <Box
              sx={{
                px: 3,
                paddingTop: '16px',
                paddingBottom: '8px',
                backgroundColor: '#fffdfc',
                zIndex: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25, minWidth: 0 }}>
                {showBackButton && (
                  <Tooltip title="Go Back" arrow>
                    <IconButton onClick={() => navigate(-1)}>
                      <ArrowBackIcon />
                    </IconButton>
                  </Tooltip>
                )}
                {heading}
                {/* {activeFileLabel && (
                  <Box
                    component="span"
                    sx={{
                      color: '#6b7280',
                      fontSize: '13px',
                      fontWeight: 500,
                      maxWidth: 360,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                    title={activeFileLabel}
                  >
                    {activeFileLabel}
                  </Box>
                )} */}
              </Box>

              {searchComponent && (
                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                  {searchComponent}
                </Box>
              )}
                {headerActions && (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                  {headerActions && (
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  {headerActions}
                  </Box>
                  )}
                </Box>
              )}
            </Box>
          )}
          <Box
            sx={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              minHeight: 0,
              overflowY: noscroll ? 'visible' : 'auto',
              px: (flat || noPadding) ? 0 : 3,
              paddingTop: (flat || noPadding) ? 0 : '8px',
              paddingBottom: (flat || noPadding) ? 0 : '16px',
            }}
          >
            {children}
          </Box>
        </CardContent>

        {bottomContent && (
          <Box
            sx={{
              borderTop: '1px solid #eee',
              p: 1.5,
              bgcolor: '#fff',
              boxShadow: '0px -4px 6px -2px rgba(0,0,0,0.1)',
              zIndex: 1,
            }}
          >
            {bottomContent}
          </Box>
        )}
      </Card>
    </Box>
  );
};

export default ContentCard;
