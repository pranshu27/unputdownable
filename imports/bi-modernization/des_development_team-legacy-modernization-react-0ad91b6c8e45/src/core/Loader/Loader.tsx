// src/core/Loader/Loader.js
import React from 'react';
import { CircularProgress, Box } from '@mui/material';

const Loader = ({show}) => {
   if(!show) {
    return;
   }

  return (
      <Box
    sx={{
      position: 'fixed', 
      top: 0,
      left: 0,
      width: '100vw',
      height: '100vh',
      backgroundColor: 'rgba(255, 255, 255, 0.6)',
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      zIndex: 2000, 
    }}
  >
    <CircularProgress size={60} thickness={5} />
  </Box>
  )
}

export default Loader;
