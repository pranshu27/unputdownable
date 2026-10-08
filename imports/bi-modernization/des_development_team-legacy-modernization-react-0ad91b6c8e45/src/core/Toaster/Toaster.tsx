import React, { useEffect } from 'react';
import {
  Snackbar,
  Alert,
  IconButton,
  Typography,
  Slide,
  Tooltip
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';

const Toaster = ({
  open,
  onClose,
  title,
  message,
  icon,
  severity = 'info',
  duration = 4000
}) => {

  useEffect(() => {
    if (open) {
      const timer = setTimeout(onClose, duration);
      return () => clearTimeout(timer);
    }
  }, [open, duration, onClose]);

  return (
    <Snackbar
      open={open}
      onClose={onClose}
      anchorOrigin={{ vertical: 'top', horizontal: 'right' }}
      TransitionComponent={Slide}
      TransitionProps={{
        direction: 'left',
        timeout: { enter: 1000, exit: 300 }
      }}
      sx={{
        top: '30px !important',
        maxWidth: '360px',
        width: '100%'
      }}
    >
      <Alert
        severity={severity as any}
        icon={icon}
        sx={{
          alignItems: 'flex-start',
          backgroundColor: '#fff',
          color: '#000',
          boxShadow: 3,
          width: '100%'
        }}
        action={
          <Tooltip title="Close">
            <IconButton
              aria-label="close"
              onClick={onClose}
              sx={{ width: '40px', height: '40px', padding: '6px' }}
            >
              <CloseIcon fontSize="inherit" sx={{ width: '30px', height: '30px' }} />
            </IconButton>
          </Tooltip>
        }
      >
        <Typography variant='subtitle1' fontWeight='bold' gutterBottom>{title}</Typography>
        <Typography variant='body2'>{message}</Typography>
      </Alert>
    </Snackbar>
  );
};

export default Toaster;
