import React, { useState } from 'react';
import ReusableCard from '../../../core/Card/Card.tsx';
import { Box, Typography, Tooltip, IconButton, Divider, Input } from '@mui/material';
import { ExpandLess, ExpandMore } from '@mui/icons-material';
import ContentCard from '../../../core/CardContent/CardContent.tsx';
import { useOutletContext } from 'react-router-dom';
import CustomPagination from '../../../core/CustomPagination/CustomPagination.tsx';
import { useSelector } from 'react-redux';
import { RootState } from '../../../utils/Store.ts';
import SliderDrawer from '../../../core/SliderDrawer/SliderDrawer.tsx';
import DataTable from '../../../core/DataTable/DataTable.tsx';

const DataModel = () => {
    const { sideNavWidth } = useOutletContext() as any;
    const reduxData = useSelector((state: RootState) => state.apiData.data);
    const localStorageData = localStorage.getItem('analyzeResponse');
    const parsedLocalData = localStorageData ? JSON.parse(localStorageData) : null;
    const dataToUse = parsedLocalData || reduxData;
  
    // Use new Data Model response structure
    const response = dataToUse?.['Data Model'] || '';
  
    const [page, setPage] = useState(0);
    const [rowsPerPage, setRowsPerPage] = useState(50);
    const [selectedCard, setSelectedCard] = useState<any>(null);
    const [openDrawer, setOpenDrawer] = useState(false);
    const [showFields, setShowFields] = useState(true);
    const [searchTerm, setSearchTerm] = useState('');
    const [searchTermSlider, setSearchTermSlider] = useState('');
  
    const handleChangePage = (event, newPage) => setPage(newPage);
    const handleChangeRowsPerPage = (event) => {
      const newRows = parseInt(event.target.value, 10);
      setRowsPerPage(!isNaN(newRows) ? newRows : 50);
      setPage(0);
    };
  
    const handleViewMoreClick = (res) => {
      setSelectedCard(res);
      setOpenDrawer(true);
    };
  
    const handlePopupClose = () => {
      setOpenDrawer(false);
      setSearchTermSlider('');
    };
  
    const handleSearchChange = (event) => {
      setSearchTerm(event.target.value);
      setPage(0);
    };
  
    const handleSearchChangeSlider = (event) => {
      setSearchTermSlider(event.target.value);
      setPage(0);
    };
  
    // Filter tables based on table_name or tool
    const filteredResponse = response.filter((item) => {
      const search = searchTerm.toLowerCase();
      return (
        item.table_name.toLowerCase().includes(search) ||
        item.tool.toLowerCase().includes(search)
      );
    });
  
    const paginatedData = filteredResponse.slice(
      page * rowsPerPage,
      page * rowsPerPage + rowsPerPage
    );
  
    // Filter fields in drawer based on search
    const filteredFields = selectedCard?.fields?.filter((f) => {
      const search = searchTermSlider.toLowerCase();
      return f.name.toLowerCase().includes(search) || f.type.toLowerCase().includes(search);
    }) || [];
  
    const searchComponent = (
      <Input
        placeholder="Search…"
        value={searchTerm}
        onChange={handleSearchChange}
        sx={{
          boxShadow: '0px 4px 15px 0px rgba(133, 160, 186, 0.15)',
          px: 1.5,
          py: 0.5,
          width: 300,
          background: 'white',
          borderRadius: '28px',
          border: '1px solid #dddddd',
          '&:after': { borderBottom: 'none' },
          '&:before': { borderBottom: 'none' },
          '&:hover:not(.Mui-disabled):before': { borderBottom: 'none !important' },
        }}
        size="small"
      />
    );
  
    return (
      <ContentCard
        searchComponent={searchComponent}
        heading={
          <Typography variant="h6" fontWeight="600" color="rgba(0, 48, 135, 1)" fontSize="20px !important">
            Data Model
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
        <div style={{ display: 'flex', marginTop: '10px', gap: '20px', flexWrap: 'wrap', flexDirection: 'row', justifyContent: 'flexStart' }}>
          {paginatedData.length === 0 ? (
            <Typography variant="body1" sx={{ color: 'gray', mt: 4, mx: 'auto', fontSize: '18px', fontWeight: 500 }}>
              No data found.
            </Typography>
          ) : (
            paginatedData.map((res: any, i: any) => (
              <ReusableCard
                key={i}
                width={333}
                height={175}
                headingLabel="Table Name:"
                headingValue={res.table_name}
                description={
                  <Box display="flex" gap={1}>
                    <Typography variant="body2" color="rgba(100, 116, 139, 1)" fontWeight="600" fontSize="14px !important">
                      Tool:
                    </Typography>
                    <Typography variant="body2" sx={{ color: 'rgba(100, 116, 139, 1)', fontWeight: 400, fontSize: '14px !important' }}>
                      {res.tool || 'N/A'}
                    </Typography>
                  </Box>
                }
                layout="vertical"
                buttons={[{
                  label: 'View More',
                  backgroundRequired: false,
                  outlineRequired: false,
                  color: 'secondary',
                  btnStylings: {
                    fontSize: '12px !important',
                    fontWeight: '600',
                    color: '#1C4473',
                    border: '1px solid #1C4473',
                    marginRight: '10px',
                    marginTop: '10px',
                    borderRadius: '8px',
                    width: '108px',
                    height: '32px !important'
                  },
                  onClick: () => handleViewMoreClick(res),
                }]}
                Height="24"
              />
            ))
          )}
        </div>
  
        <SliderDrawer
          open={openDrawer}
          onClose={handlePopupClose}
          title={<span><b>Table Name:</b> {selectedCard?.table_name || ''}</span>}
          titleStylings={{
            color: 'rgba(0, 48, 135, 1)',
            fontSize: '20px',
            fontWeight: 500,
            backgroundColor: 'rgba(231, 238, 248, 1)',
          }}
          onPrimaryClick={() => console.log('primary')}
          onSecondaryClick={() => console.log('secondary')}
          disablePrimaryBtn={false}
          disableSecondaryBtn={false}
          width="35%"
        >
          {selectedCard && (
            <Box display="flex" flexDirection="column" gap={2}>
              <Box
                display="flex"
                onClick={() => setShowFields((prev) => !prev)}
                sx={{ cursor: 'pointer' }}
                alignItems="center"
                justifyContent="space-between"
              >
                <Typography variant="subtitle1" sx={{ color: 'rgba(71, 85, 105, 1)', fontSize: '20px', fontWeight: '600' }}>
                  Fields
                </Typography>
                <IconButton size="small">
                  {showFields ? <ExpandLess /> : <ExpandMore />}
                </IconButton>
              </Box>
  
              {showFields && (
                <Box mt={1}>
                  <DataTable
                    data={filteredFields.map((f) => ({ key: f.name, value: f.type }))}
                    columns={[
                      { header: 'Field Name', field: 'key' },
                      { header: 'Data Type', field: 'value' },
                    ]}
                    showCheckbox={false}
                    disableSearch={false}
                    editRowId={null}
                    Height="450"
                    searchTerm={searchTermSlider}
                    onSearchChange={handleSearchChangeSlider}
                  />
                </Box>
              )}
            </Box>
          )}
        </SliderDrawer>
      </ContentCard>
    );
  };
  
  export default DataModel;
  
