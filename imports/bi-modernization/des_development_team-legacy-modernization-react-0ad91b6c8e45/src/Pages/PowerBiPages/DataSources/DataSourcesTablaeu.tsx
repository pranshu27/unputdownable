import React, { useState } from 'react';
import ReusableCard from '../../../core/Card/Card.tsx';
import { Box, Typography, Tooltip, IconButton, Divider, Input } from '@mui/material';
import { ExpandLess, ExpandMore } from '@mui/icons-material';
import ContentCard from '../../../core/CardContent/CardContent.tsx';
import { useOutletContext } from 'react-router-dom';
import CustomPagination from '../../../core/CustomPagination/CustomPagination.tsx';
import { useSelector } from 'react-redux';
import { RootState } from '../../..//utils/Store.ts';
import SliderDrawer from '../../../core/SliderDrawer/SliderDrawer.tsx';
import DataTable from '../../../core/DataTable/DataTable.tsx';

const DataSourceTablue = () => {
  const reduxData = useSelector((state: RootState) => state.apiData.data);
  const localStorageData = localStorage.getItem("analyzeResponse");
  const parsedLocalData = localStorageData ? JSON.parse(localStorageData) : null;

  const dataToUse = parsedLocalData || reduxData;

  // IMPORTANT: Your actual datasources
  const response =dataToUse?.['Data Sources'] || ''; 
  const { sideNavWidth } = useOutletContext() as any;


  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(50);
  const [selectedCard, setSelectedCard] = useState<any>(null);
  const [openDrawer, setOpenDrawer] = useState(false);
  const [showAttributes, setShowAttributes] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");

  const handleChangePage = (event, newPage) => setPage(newPage);

  const handleChangeRowsPerPage = (event) => {
    const newRows = parseInt(event.target.value, 10);
    setRowsPerPage(isNaN(newRows) ? 50 : newRows);
    setPage(0);
  };

  const handleSearchChange = (e) => {
    setSearchTerm(e.target.value.toLowerCase());
    setPage(0);
  };

  // -------------------- Search Filter --------------------
  const filteredResponse = response.filter((item) => {
    const s = searchTerm;
    return (
      item?.name?.toLowerCase()?.includes(s) ||
      item?.tool?.toLowerCase()?.includes(s) ||
      item?.type?.toLowerCase()?.includes(s) ||
      item?.connection_details?.toLowerCase()?.includes(s) ||
      item?.used_by?.join(",")?.toLowerCase()?.includes(s)
    );
  });

  const paginatedData = filteredResponse.slice(
    page * rowsPerPage,
    page * rowsPerPage + rowsPerPage
  );

  const searchComponent = (
    <Input
      placeholder="Search…"
      value={searchTerm}
      onChange={handleSearchChange}
      sx={{
        px: 1.5,
        py: 0.5,
        width: 300,
        background: "white",
        borderRadius: "28px",
        border: "1px solid #ddd",
      }}
    />
  );

  return (
    <ContentCard
      searchComponent={searchComponent}
      heading={
        <Typography variant="h6" fontWeight={600} color="rgba(0,48,135,1)">
          Data Sources
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
      <div
        style={{
          display: "flex",
          marginTop: "10px",
          gap: "20px",
          flexWrap: "wrap",
        }}
      >
        {paginatedData.length === 0 ? (
          <Typography>No data found.</Typography>
        ) : (
          paginatedData.map((res, i) => (
            <ReusableCard
              key={i}
              width={333}
              height={175}
              headingLabel="Name:"
              headingValue={res?.name}
              description={
                <Box display="flex" gap={1}>
                  <Typography fontWeight={600}>Tool:</Typography>
                  <Typography>{res?.tool}</Typography>
                </Box>
              }
              layout="vertical"
              buttons={[
                {
                  label: "View More",
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
      </div>

      {/* -------------------- Drawer -------------------- */}
      <SliderDrawer
        open={openDrawer}
        onClose={() => setOpenDrawer(false)}
        title={<b>Data Source: {selectedCard?.name}</b>}
        width="35%"
      >
        {selectedCard && (
          <Box display="flex" flexDirection="column" gap={2}>
            {Object.entries(selectedCard).map(([key, value], idx) => {
              if (Array.isArray(value))
                value = value.join(", ");

              if (typeof value === "boolean")
                value = value ? "Yes" : "No";

              return (
                <Typography key={idx}>
                  <strong>{key.replace(/_/g, " ")}: </strong>
                  {value || "N/A"}
                </Typography>
              );
            })}
          </Box>
        )}
      </SliderDrawer>
    </ContentCard>
  );
};

export default DataSourceTablue;
