import React from 'react';
import { Box, Typography, TablePagination } from '@mui/material';

const CustomPagination = ({
  count,
  page,
  rowsPerPage,
  onPageChange,
  onRowsPerPageChange,
  rowsPerPageOptions = [50,75,100],
}) => {
  const from = count === 0 ? 0 : page * rowsPerPage + 1;
  const to = Math.min(count, (page + 1) * rowsPerPage);

  return (
    <Box
      sx={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        px: 2,
        py: 0,
        backgroundColor: '#fff',
      }}
    >
      <Typography variant="body2" sx={{color:'rgba(148, 163, 184, 1)',fontSize:'14px !important',fontWeight:'400'}}>
        Showing {from} to {to} of {count} records
      </Typography>

      <TablePagination
        component="div"
        sx={{color:'rgba(148, 163, 184, 1)',fontSize:'14px !important',fontWeight:'400'}}
        count={count}
        page={page}
        onPageChange={onPageChange}
        rowsPerPage={rowsPerPage}
        onRowsPerPageChange={onRowsPerPageChange}
        rowsPerPageOptions={rowsPerPageOptions}
      />
    </Box>
  );
};

export default CustomPagination;
