import React from 'react';
import {
  Card,
  CardContent,
  CardActions,
  Typography,
  Box,
  Button,
  Tooltip,
  Divider,
} from '@mui/material';

const ReusableCard = ({
  width = 320,
  height = 220,
  headingLabel = '',
  headingValue = '',
  description = '',
  buttons = [],
  layout = '',
  Height = '32',
  btnStylings
}) => {
  const isVertical = layout === 'vertical';

  return (
    <Box
    >
      <Card
        sx={{
          width,
          borderRadius: '28px',
          height,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          boxSizing: 'border-box',
          padding: 0,
          boxShadow:
            `0px 4px 10px -5px rgba(0, 48, 135, 0.04), 
  0px 4px 20px -5px rgba(0, 48, 135, 0.05)`,
          transition: 'transform 0.2s, box-shadow 0.2s',
          '&:hover': {
            transform: 'scale(1.02)',
            boxShadow: 6,
          },
          cursor: 'pointer',
          overflow: 'hidden',
        }}
      >
        <Box sx={{ background: 'linear-gradient(rgb(2, 10, 12) 0%, rgb(35, 61, 83) 60.1%, rgb(24, 43, 60) 100%)' }}>
          <Box sx={{
            padding: '15px', display: 'flex'
            , alignItems: 'center',
            justifyContent: 'flex-start'
          }}>
          
            <Typography
              variant="body2"
              sx={{
                overflow: 'hidden',
                maxWidth: '100%',
                marginRight: '5px',
                color: 'white',
                fontSize: '14px !important',
                fontWeight: 700,
              }}
            >
              {headingLabel}
            </Typography>
            {/* </Tooltip> */}

            {/* <Tooltip title={headingValue}> */}
            <Tooltip title={headingValue} arrow>
              <Typography
                variant="subtitle2"
                sx={{
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  textAlign: 'right',
                  maxWidth: '60%',
                  color: 'white',
                  fontSize: '14px !important',
                  fontWeight: 600,
                }}
              >
                {headingValue}
              </Typography>
            </Tooltip>
          </Box>
        </Box>

        <CardContent
          sx={{
            flexGrow: 2,
            overflow: 'hidden',
            paddingTop: '10px',
            p: 2,
            background: '#ffffff'
          }}
        >
          <Box
            sx={{
              height: '120px',
              overflowY: 'auto',
              width: '100%',
              fontSize: '14px !important'
            }}
          >
            <Typography
              variant="body2"
              sx={{
                whiteSpace: 'normal',
                wordWrap: 'break-word',
              }}
            >
              {description}
            </Typography>
          </Box>
        </CardContent>


        <Box>
          <Divider />
          <CardActions
            sx={{
              p: 0,
              background: '#ffffff',
              pt: 0.5,
              pb: 0.5,
              justifyContent: 'flex-end',
              flexWrap: 'wrap',
              // height: `${Height}px`
            }}
          >
            {buttons.map((btn, index) => {
              const getVariant = () => {
                if (btn.backgroundRequired) return 'contained';
                if (btn.outlineRequired) return 'outlined';
                return 'text';
              };

              return (
                <Button
                  key={index}
                  // variant={getVariant()}
                  color={btn.color || 'primary'}
                  size="small"
                  onClick={btn.onClick}
                  sx={{ ...btn.btnStylings, ml: 1, mb: 1, textTransform: 'capitalize', borderRadius: '28px' }}
                >
                  {btn.label}
                </Button>
              );
            })}
          </CardActions>
        </Box>
      </Card>
    </Box>
  );
};

export default ReusableCard;
