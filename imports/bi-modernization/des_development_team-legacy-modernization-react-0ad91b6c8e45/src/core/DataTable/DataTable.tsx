import React, { useMemo } from 'react';
import {
  Box,
  Checkbox,
  IconButton,
  Input,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
  Tooltip,
  Menu,
  MenuItem,
  ListItemText,
} from '@mui/material';
import ViewColumnIcon from '@mui/icons-material/ViewColumn';
import { styled } from '@mui/material/styles';
import zIndex from '@mui/material/styles/zIndex';

const StyledTableRow = styled(TableRow)(({ index }) => ({
  backgroundColor: index % 2 === 0 ? '#ffffff' : '#f9f9f9',
}));

const StyledTableCell = styled(TableCell)(() => ({
  whiteSpace: 'nowrap',
}));

const DataTable = ({
  data = [],
  columns = [],
  showCheckbox = false,
  actions = () => [],
  onRowSelect = () => {},
  onActionClick = () => {},
  editRowId = null,
  editedData = {},
  onEditChange = () => {},
  Height = '250',
  searchTerm = '',
  onSearchChange = () => {},
  disableSearch = true,
  columnHeadersStyling,
  containerHeight = 300,
  additionalStylings
}) => {
  const [anchorEl, setAnchorEl] = React.useState(null);
  const [visibleColumns, setVisibleColumns] = React.useState(columns.map(col => col.field));
  const [sortConfig, setSortConfig] = React.useState({ field: null, direction: 'asc' });
  const [selected, setSelected] = React.useState([]);

  const toggleColumnVisibility = (field) => {
    setVisibleColumns(prev =>
      prev.includes(field) ? prev.filter(f => f !== field) : [...prev, field]
    );
  };

  const handleSort = (field) => {
    setSortConfig(prev => ({
      field,
      direction: prev.field === field && prev.direction === 'asc' ? 'desc' : 'asc',
    }));
  };

  const renderCellValue = (value) => {
    if (Array.isArray(value)) {
      return value.map((v, i) =>
        typeof v === 'object' ? JSON.stringify(v) : String(v)
      ).join(', ');
    }
    if (typeof value === 'object' && value !== null) {
      return JSON.stringify(value);
    }
    return value !== undefined && value !== null ? String(value) : '';
  };

  const sortedData = useMemo(() => {
    if (!sortConfig.field) return data;
    return [...data].sort((a, b) => {
      const aValue = a[sortConfig.field];
      const bValue = b[sortConfig.field];
      if (aValue < bValue) return sortConfig.direction === 'asc' ? -1 : 1;
      if (aValue > bValue) return sortConfig.direction === 'asc' ? 1 : -1;
      return 0;
    });
  }, [data, sortConfig]);

  const handleSelectAll = (e) => {
    if (e.target.checked) {
      const allIds = sortedData.map((row) => row.id);
      setSelected(allIds);
      onRowSelect(allIds);
    } else {
      setSelected([]);
      onRowSelect([]);
    }
  };

  const handleSelectRow = (id) => {
    const updated = selected.includes(id)
      ? selected.filter((sid) => sid !== id)
      : [...selected, id];
    setSelected(updated);
    onRowSelect(updated);
  };

  return (
    <Paper sx={{...additionalStylings,  width: '100%', overflow: 'auto', p: 2, boxShadow: 'none', backgroundColor: 'transparent' }}>
      {!disableSearch && (
        <Box display="flex" justifyContent="flex-end" mb={2} sx={{zIndex:10}}>
          <Input
            placeholder="Search…"
            value={searchTerm}
            onChange={onSearchChange}
            sx={{
              boxShadow: '0px 4px 15px 0px rgba(133, 160, 186, 0.15)',
              px: 1.5,
              py: 0.5,
              width: 300,
              background: 'white',
              borderRadius: '28px',
              border:'1px solid #dddddd',
              '&:after': { borderBottom: 'none' },
              '&:before': { borderBottom: 'none' },
              '&:hover:not(.Mui-disabled):before': { borderBottom: 'none !important' },
            }}
            size="small"
          />
          <Tooltip title="Show/Hide Columns">
            <IconButton onClick={(e) => setAnchorEl(e.currentTarget)}>
              <ViewColumnIcon sx={{ color: '#1976D2' ,width: 24, height: 24}} />
            </IconButton>
          </Tooltip>
          <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={() => setAnchorEl(null)}>
            {columns.map((col) => (
              <MenuItem key={col.field} onClick={() => toggleColumnVisibility(col.field)}>
                <Checkbox checked={visibleColumns.includes(col.field)} />
                <ListItemText primary={col.header} />
              </MenuItem>
            ))}
          </Menu>
        </Box>
      )}

      <TableContainer
        sx={{
          height: `calc(100vh - ${containerHeight}px)`,
          overflow: 'auto',
          borderRadius: '15px',
          boxShadow: `0px 10px 10px -5px rgba(0, 48, 135, 0.02), 0px 10px 25px -5px rgba(0, 48, 135, 0.02)`,
        }}
      >
        <Table stickyHeader sx={{ minWidth: 'max-content' }}>
          <TableHead>
            <TableRow>
              {showCheckbox && (
                <StyledTableCell
                  padding="checkbox"
                  sx={{
                    position: 'sticky',
                    top: 0,
                   background: ' linear-gradient(0deg, rgba(0, 0, 0, 0.2), rgba(0, 0, 0, 0.2)), linear-gradient(0deg, rgba(231, 238, 248, 0.9), rgba(231, 238, 248, 0.9))',
                    zIndex: 11,
                  }}
                >
                  <Checkbox
                    checked={selected.length > 0 && selected.length === sortedData.length}
                    onChange={handleSelectAll}
                    sx={{ color: 'white' }}
                  />
                </StyledTableCell>
              )}
              {columns.map((col) =>
                visibleColumns.includes(col.field) ? (
                  <StyledTableCell
                    key={col.field}
                    sx={{
                      position: 'sticky',
                      top: 0,
                      zIndex: 10,
                      background: 'linear-gradient(rgb(2, 10, 12) 0%, rgb(35, 61, 83) 60.1%, rgb(24, 43, 60) 100%)',
                      color: 'white',
                      fontWeight: 500,
                      fontSize: '14px !important',
                    }}
                    sortDirection={sortConfig.field === col.field ? sortConfig.direction : false}
                  >
                    <TableSortLabel
                      active={sortConfig.field === col.field}
                      direction={sortConfig.direction}
                      onClick={() => handleSort(col.field)}
                      sx={{ color: 'white' }}
                    >
                      {col.header}
                    </TableSortLabel>
                  </StyledTableCell>
                ) : null
              )}
              {actions.length > 0 && (
                <StyledTableCell
                  sx={{
                    position: 'sticky',
                    top: 0,
                    right: 0,
                    zIndex: 11,
                    background: ' linear-gradient(0deg, rgba(0, 0, 0, 0.2), rgba(0, 0, 0, 0.2)), linear-gradient(0deg, rgba(231, 238, 248, 0.9), rgba(231, 238, 248, 0.9))',
                    color: 'white',
                  }}
                >
                  Actions
                </StyledTableCell>
              )}
            </TableRow>
          </TableHead>

          <TableBody>
            {sortedData.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={columns.length + (showCheckbox ? 1 : 0) + (actions.length > 0 ? 1 : 0)}
                  align="center"
                >
                  No data found
                </TableCell>
              </TableRow>
            ) : (
              sortedData.map((row, rowIndex) => {
                const isEditing = editRowId === row.id;
                return (
                  <StyledTableRow key={row.id || rowIndex} index={rowIndex}>
                    {showCheckbox && (
                      <StyledTableCell padding="checkbox">
                        <Checkbox
                          checked={selected.includes(row.id)}
                          onChange={() => handleSelectRow(row.id)}
                        />
                      </StyledTableCell>
                    )}

                    {columns.map((col) =>
                      visibleColumns.includes(col.field) ? (
                        <StyledTableCell key={col.field}>
                          {isEditing ? (
                            <Input
                              value={editedData[col.field] || ''}
                              onChange={(e) => onEditChange(col.field, e.target.value)}
                              size="small"
                              fullWidth
                            />
                          ) : (
                            <Tooltip title={renderCellValue(row[col.field])} arrow>
                              <span
                                style={{
                                  display: 'inline-block',
                                  maxWidth: '180px',
                                  overflow: 'hidden',
                                  whiteSpace: 'nowrap',
                                  textOverflow: 'ellipsis',
                                  color: 'rgba(100, 116, 139, 1)',
                                  fontWeight: 400,
                                }}
                              >
                                {renderCellValue(row[col.field])}
                              </span>
                            </Tooltip>
                          )}
                        </StyledTableCell>
                      ) : null
                    )}

                    {actions.length > 0 && (
                      <StyledTableCell sx={{ right: 0, backgroundColor: '#fff', zIndex: 1 }}>
                        {actions(row).map((action, index) => (
                          <Tooltip key={index} title={action.label}>
                            <IconButton onClick={() => onActionClick(action.key, row)}>
                              {action.icon}
                            </IconButton>
                          </Tooltip>
                        ))}
                      </StyledTableCell>
                    )}
                  </StyledTableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );
};

export default DataTable;
