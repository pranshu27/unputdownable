import React, { useState } from 'react';
import ReusableCard from '../../../core/Card/Card.tsx';
import {
  Box,
  Typography,
  IconButton,
  Input,
  Chip
} from '@mui/material';
import { ExpandLess, ExpandMore, TableChart } from '@mui/icons-material';
import ContentCard from '../../../core/CardContent/CardContent.tsx';
import { useOutletContext } from 'react-router-dom';
import CustomPagination from '../../../core/CustomPagination/CustomPagination.tsx';
import { useSelector } from 'react-redux';
import { RootState } from '../../../utils/Store.ts';
import SliderDrawer from '../../../core/SliderDrawer/SliderDrawer.tsx';

const Tables = () => {
  const { sideNavWidth } = useOutletContext() as any;
  const reduxData = useSelector((state: RootState) => state.apiData.data);

  const localStorageData = localStorage.getItem('analyzeResponse');
  const parsedLocalData = localStorageData ? JSON.parse(localStorageData) : null;

  const dataToUse = parsedLocalData || reduxData;
  const response = dataToUse?.agent_result?.Tables || [];

  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(50);
  const [selectedCard, setSelectedCard] = useState<any>(null);
  const [openDrawer, setOpenDrawer] = useState(false);
  const [showFields, setShowFields] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [searchTermSlider, setSearchTermSlider] = useState('');

  // Pagination
  const handleChangePage = (_: any, newPage: number) => setPage(newPage);

  const handleChangeRowsPerPage = (event: any) => {
    const newRows = parseInt(event.target.value, 10);
    setRowsPerPage(!isNaN(newRows) ? newRows : 50);
    setPage(0);
  };

  // Drawer
  const handleViewMoreClick = (res: any) => {
    setSelectedCard(res);
    setOpenDrawer(true);
  };

  const handlePopupClose = () => {
    setOpenDrawer(false);
    setSearchTermSlider('');
  };

  // Search
  const handleSearchChange = (event: any) => {
    setSearchTerm(event.target.value);
    setPage(0);
  };

  const handleSearchChangeSlider = (event: any) => {
    setSearchTermSlider(event.target.value);
  };

  // Filter Tables
  const filteredResponse = response.filter((item: any) => {
    const search = searchTerm.toLowerCase();
    return (
      item.name.toLowerCase().includes(search) ||
      item.source_object.toLowerCase().includes(search)
    );
  });

  const paginatedData = filteredResponse.slice(
    page * rowsPerPage,
    page * rowsPerPage + rowsPerPage
  );

  // Filter Fields
  const filteredFields =
    selectedCard?.columns?.filter((f: any) => {
      const search = searchTermSlider.toLowerCase();
      return (
        f.name.toLowerCase().includes(search) ||
        f.data_type.toLowerCase().includes(search)
      );
    }) || [];

  // Search Input
  const searchComponent = (
    <Input
      placeholder="Search data sources..."
      value={searchTerm}
      onChange={(e) => setSearchTerm(e.target.value)}
      disableUnderline   // ✅ important
      sx={{
        px: 2,
        py: 0.5,
        width: 300,
        background: "#fff",
        borderRadius: "25px",
        border: "1px solid #ddd",
        fontSize: "14px",
  
        '& input::placeholder': {
          color: '#94a3b8',
          opacity: 1,
        },
  
        '&:hover': {
          border: "1px solid #94a3b8",
        },
  
        '&:focus-within': {
          border: "1px solid #1976d2",
          boxShadow: "0 0 0 2px rgba(25,118,210,0.1)",
        },
      }}
    />
  );

  return (
    <ContentCard
      searchComponent={searchComponent}
      heading={
        <Typography sx={{fontWeight:'600'}} color='rgba(0, 48, 135, 1)' fontSize='20px !important'>
          Tables
        </Typography>
      }
      sideNavWidth={sideNavWidth}
      bottomContent={
        <CustomPagination
          count={filteredResponse.length}
          page={page}
          rowsPerPage={rowsPerPage}
          onPageChange={handleChangePage}
          onRowsPerPageChange={handleChangeRowsPerPage}
        />
      }
    >
      {/* TABLE CARDS */}
      <Box display="flex" flexWrap="wrap" gap={2} mt={2}>
        {paginatedData.length === 0 ? (
          <Typography sx={{ mx: 'auto', mt: 5, color: '#94a3b8' }}>
            No tables match your search.
          </Typography>
        ) : (
          paginatedData.map((res: any, i: number) => (
            <ReusableCard
              key={i}
              width={320}
              height={190}
              headingLabel="Table : "
              headingValue={res.name}
              headingIcon={<TableChart />}
              description={
                <Box>
                  <Typography fontSize="13px" color="gray">
                    Source: {res.source_object}
                  </Typography>

                  <Box display="flex" justifyContent="space-between" mt={1}>
                    <Typography fontSize="12px" color="gray">
                      Columns: {res.columns?.length}
                    </Typography>

                    <Typography fontSize="12px" color="gray">
                      {res.is_materialized ? 'Materialized' : 'Virtual'}
                    </Typography>
                  </Box>
                </Box>
              }
              layout="vertical"
              buttons={[
                {
                  label: 'View Fields',
                  color: 'secondary',
                  btnStylings: {
                    fontSize: "12px",
                    fontWeight: 600,
                    color: "#1C4473",
                    border: "1px solid #1C4473",
                    borderRadius: "8px",
                    width: "108px",
                  },
                  onClick: () => handleViewMoreClick(res),
                },
              ]}
            />
          ))
        )}
      </Box>

      {/* DRAWER */}
      <SliderDrawer
        open={openDrawer}
        onClose={handlePopupClose}
        width="35%"
        title={
          <Box>
            <Typography fontWeight={600}>{selectedCard?.name}</Typography>
            <Typography fontSize="12px" color="gray">
              {selectedCard?.columns?.length} fields •{' '}
              {selectedCard?.is_materialized ? 'Materialized' : 'Virtual'}
            </Typography>
          </Box>
        }
      >
        {selectedCard && (
          <Box display="flex" flexDirection="column" gap={2}>

            {/* 🔹 Table Info */}
            <Box
              sx={{
                p: 2,
                border: '1px solid #e2e8f0',
                borderRadius: '8px',
                background: '#f8fafc'
              }}
            >
              <Typography fontWeight={600} fontSize="16px">
                Table Details
              </Typography>

              <Box mt={1} display="grid" gridTemplateColumns="1fr 1fr" gap={1}>
                <Typography fontSize="13px"><b>Name:</b> {selectedCard.name}</Typography>
                <Typography fontSize="13px"><b>Source:</b> {selectedCard.source_object}</Typography>
                <Typography fontSize="13px"><b>Columns:</b> {selectedCard.columns?.length}</Typography>
                <Typography fontSize="13px">
                  <b>Materialized:</b> {selectedCard.is_materialized ? 'Yes' : 'No'}
                </Typography>
                <Typography fontSize="13px">
                  <b>Row Count:</b> {selectedCard.row_count_estimate || 'N/A'}
                </Typography>
              </Box>
            </Box>

            {/* 🔹 Fields Header */}
            <Box
              display="flex"
              justifyContent="space-between"
              alignItems="center"
              onClick={() => setShowFields(!showFields)}
              sx={{ cursor: 'pointer' }}
            >
              <Typography fontWeight={600} fontSize="18px">
                Columns
              </Typography>

              <IconButton size="small">
                {showFields ? <ExpandLess /> : <ExpandMore />}
              </IconButton>
            </Box>

            {/* 🔹 Search */}
            <Input
              placeholder="Search columns..."
              value={searchTermSlider}
              onChange={handleSearchChangeSlider}
              sx={{
                px: 1.5,
                py: 0.5,
                border: '1px solid #ddd',
                borderRadius: '20px',
              }}
            />

            {/* 🔥 Columns Table (FULL INFO) */}
            {showFields && (
              <Box sx={{ maxHeight: 450, overflow: 'auto' }}>
                {filteredFields.map((f: any, i: number) => (
                  <Box
                    key={i}
                    sx={{
                      p: 1.5,
                      mb: 1,
                      borderRadius: '8px',
                      border: '1px solid #e2e8f0',
                      background: '#fff',
                      '&:hover': { background: '#f1f5f9' },
                    }}
                  >
                    {/* Name */}
                    <Typography fontWeight={600}>
                      {f.name}
                    </Typography>

                    {/* Source */}
                    <Typography fontSize="12px" color="gray">
                      Source: {f.source_column}
                    </Typography>

                    {/* Type */}
                    <Typography fontSize="12px" color="gray">
                      Type: {f.data_type}
                    </Typography>

                    {/* Flags */}
                    <Box mt={1} display="flex" gap={1} flexWrap="wrap">
                      {f.nullable && <Chip label="Nullable" size="small" color="info" />}
                      {f.hidden && <Chip label="Hidden" size="small" color="default" />}
                      {f.used_in_filters && <Chip label="Filter" size="small" color="primary" />}
                      {f.used_in_relationships && <Chip label="Relation" size="small" color="success" />}
                      {f.used_in_groupby && <Chip label="GroupBy" size="small" color="warning" />}
                      {f.used_in_calculations && <Chip label="Calc" size="small" color="secondary" />}
                      {f.distinct_count_high && <Chip label="High Distinct" size="small" color="error" />}
                    </Box>

                    {/* Description */}
                    {f.description && (
                      <Typography mt={1} fontSize="12px" color="#64748b">
                        {f.description}
                      </Typography>
                    )}
                  </Box>
                ))}
              </Box>
            )}
          </Box>
        )}
      </SliderDrawer>
    </ContentCard>
  );
};

export default Tables;