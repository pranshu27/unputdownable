import React, { useState } from 'react';
import ReusableCard from '../../../core/Card/Card.tsx';
import {
  Box,
  Typography,
  Input,
  Chip
} from '@mui/material';
import ContentCard from '../../../core/CardContent/CardContent.tsx';
import { useOutletContext } from 'react-router-dom';
import CustomPagination from '../../../core/CustomPagination/CustomPagination.tsx';
import { useSelector } from 'react-redux';
import { RootState } from '../../../utils/Store.ts';
import SliderDrawer from '../../../core/SliderDrawer/SliderDrawer.tsx';

const DataSource = () => {
  const reduxData = useSelector((state: RootState) => state.apiData.data);

  const localStorageData = localStorage.getItem("analyzeResponse");
  const parsedLocalData = localStorageData ? JSON.parse(localStorageData) : null;

  const dataToUse = parsedLocalData || reduxData;
  const response = dataToUse?.agent_result?.['Data Sources'] || [];

  const { sideNavWidth } = useOutletContext() as any;

  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(50);
  const [selectedCard, setSelectedCard] = useState<any>(null);
  const [openDrawer, setOpenDrawer] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");

  // 🔍 Search
  const filteredResponse = response.filter((item: any) => {
    const s = searchTerm.toLowerCase();
    return (
      item?.name?.toLowerCase().includes(s) ||
      item?.source_type?.toLowerCase().includes(s) ||
      item?.connection_mode?.toLowerCase().includes(s)
    );
  });

  const paginatedData = filteredResponse.slice(
    page * rowsPerPage,
    page * rowsPerPage + rowsPerPage
  );
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
          Data Sources
        </Typography>
      }
      sideNavWidth={sideNavWidth}
      bottomContent={
        <CustomPagination
          count={filteredResponse.length}
          page={page}
          rowsPerPage={rowsPerPage}
          onPageChange={(_, newPage) => setPage(newPage)}
          onRowsPerPageChange={(e) => {
            setRowsPerPage(parseInt(e.target.value, 10));
            setPage(0);
          }}
        />
      }
    >
      {/* 🔥 Cards */}
      <Box display="flex" flexWrap="wrap" gap={2} mt={2}>
        {paginatedData.length === 0 ? (
          <Typography sx={{ mx: "auto", mt: 5, color: "#94a3b8" }}>
            No data sources found.
          </Typography>
        ) : (
          paginatedData.map((res: any, i: number) => (
            <ReusableCard
              key={i}
              width={320}
              height={180}
              headingLabel="Source : "
              headingValue={res.name}
              description={
                <Box>
                  <Typography fontSize="13px">
                    <b>Type:</b> {res.source_type}
                  </Typography>

                  <Typography fontSize="13px">
                    <b>Connection:</b> {res.connection_mode}
                  </Typography>

                  <Typography fontSize="13px">
                     Fields: {res.fields?.length || 0}
                  </Typography>
                </Box>
              }
              buttons={[
                {
                  label: "View Details",
                  btnStylings: {
                    fontSize: "12px",
                    fontWeight: 600,
                    color: "#1C4473",
                    border: "1px solid #1C4473",
                    borderRadius: "8px",
                    width: "108px",
                  },
                  onClick: () => {
                    setSelectedCard(res);
                    setOpenDrawer(true);
                  },
                },
              ]}
            />
          ))
        )}
      </Box>

      {/* 🔥 Drawer */}
      <SliderDrawer
        open={openDrawer}
        onClose={() => setOpenDrawer(false)}
        width="40%"
        title={
          <Typography fontWeight={600}>
            {selectedCard?.name}
          </Typography>
        }
      >
        {selectedCard && (
          <Box display="flex" flexDirection="column" gap={2}>

            {/* 🔹 Basic Info */}
            <Box
              sx={{
                p: 2,
                border: "1px solid #e2e8f0",
                borderRadius: "10px",
                background: "#f8fafc"
              }}
            >
              <Typography><b>Source Type:</b> {selectedCard.source_type || "N/A"}</Typography>
              <Typography><b>Connection Mode:</b> {selectedCard.connection_mode || "N/A"}</Typography>
              <Typography><b>Server:</b> {selectedCard.server || "N/A"}</Typography>
              <Typography><b>Database:</b> {selectedCard.database || "N/A"}</Typography>
            </Box>

            {/* 🔹 Fields */}
            <Box>
              <Typography fontWeight={600} mb={1}>
                Fields
              </Typography>

              {selectedCard.fields?.length > 0 ? (
                <Box display="flex" gap={1} flexWrap="wrap">
                  {selectedCard.fields.map((f: string, i: number) => (
                    <Chip
                      key={i}
                      label={f}
                      size="small"
                      color="primary"   // ✅ correct
                    />
                  ))}
                </Box>
              ) : (
                <Typography color="gray">N/A</Typography>
              )}
            </Box>

            {/* 🔹 Other Info */}
            <Box>
              <Typography><b>Schema:</b> {selectedCard.schema || "N/A"}</Typography>
              <Typography><b>Gateway:</b> {selectedCard.gateway || "N/A"}</Typography>
              <Typography><b>Refresh:</b> {selectedCard.refresh_frequency || "N/A"}</Typography>
            </Box>

          </Box>
        )}
      </SliderDrawer>
    </ContentCard>
  );
};

export default DataSource;