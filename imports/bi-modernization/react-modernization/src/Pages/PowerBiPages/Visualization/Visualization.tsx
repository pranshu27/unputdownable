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
import {
    Accordion,
    AccordionSummary,
    AccordionDetails,
  } from "@mui/material";
  import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
  const Visualization = () => {
    const { sideNavWidth } = useOutletContext() as any;
  
    const reduxData = useSelector((state: RootState) => state.apiData.data);
    const localStorageData = localStorage.getItem('analyzeResponse');
    const parsedLocalData = localStorageData ? JSON.parse(localStorageData) : null;
    const dataToUse = parsedLocalData || reduxData;
    const visualizations = dataToUse?.Visualizations|| '';
   
  
    const [page, setPage] = useState(0);
    const [rowsPerPage, setRowsPerPage] = useState(50);
    const [searchTerm, setSearchTerm] = useState("");
    const [selectedItem, setSelectedItem] = useState<any>(null);
    const [openDrawer, setOpenDrawer] = useState(false);
  
    // ------------------------ Search Logic ------------------------
    const filteredData = visualizations.filter((v) =>
      v.name.toLowerCase().includes(searchTerm.toLowerCase())
    );
  
    const paginatedData = filteredData.slice(
      page * rowsPerPage,
      page * rowsPerPage + rowsPerPage
    );
  
    const searchComponent = (
      <Input
        placeholder="Search visualizations…"
        value={searchTerm}
        onChange={(e) => setSearchTerm(e.target.value)}
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
        heading={
          <Typography variant="h6" fontWeight={600} color="rgba(0,48,135,1)">
            Visualizations
          </Typography>
        }
        searchComponent={searchComponent}
        sideNavWidth={sideNavWidth}
        bottomContent={
          <CustomPagination
            count={filteredData.length}
            page={page}
            rowsPerPage={rowsPerPage}
            onPageChange={(e, newPage) => setPage(newPage)}
            onRowsPerPageChange={(e) => {
              setRowsPerPage(parseInt(e.target.value, 10));
              setPage(0);
            }}
          />
        }
      >
        {/* --------- Cards Layout --------- */}
        <div
          style={{
            display: "flex",
            gap: "20px",
            flexWrap: "wrap",
            marginTop: "10px",
          }}
        >
          {paginatedData.map((viz, i) => (
            <ReusableCard
              key={i}
              width={333}
              height={175}
              headingLabel="Name:"
              headingValue={viz.name}
              description={
                <Box>
                  <Typography fontWeight={600}>Type:</Typography>
                  <Typography fontSize={13}>{viz.type}</Typography>
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
                    setSelectedItem(viz);
                    setOpenDrawer(true);
                  },
                },
              ]}
            />
          ))}
        </div>
  
        {/* --------- Drawer --------- */}
        <SliderDrawer
          open={openDrawer}
          onClose={() => setOpenDrawer(false)}
          width="40%"
          title={<b>Visualization: {selectedItem?.name}</b>}
        >
          {selectedItem && (
            <Box display="flex" flexDirection="column" gap={2}>
              <Typography>
                <strong>Type:</strong> {selectedItem.type}
              </Typography>
  
              <Typography>
                <strong>Dimensions:</strong>
              </Typography>
              {selectedItem.dimensions.map((d, idx) => (
                <Typography key={idx} sx={{ pl: 2 }}>
                  • {d}
                </Typography>
              ))}
  
              <Typography>
                <strong>Measures:</strong>
              </Typography>
              {selectedItem.measures.map((m, idx) => (
                <Typography key={idx} sx={{ pl: 2 }}>
                  • {m}
                </Typography>
              ))}
  
              <Typography>
                <strong>Filters:</strong>
              </Typography>
              {selectedItem.filters.map((f, idx) => (
                <Typography key={idx} sx={{ pl: 2 }}>
                  • {f}
                </Typography>
              ))}
  
              <Typography>
                <strong>Chart Mappings:</strong>
              </Typography>
              {Object.entries(selectedItem.chart_mappings).map(
                ([key, value], idx) => (
                  <Typography key={idx} sx={{ pl: 2 }}>
                    • <b>{key}:</b> {value || "N/A"}
                  </Typography>
                )
              )}
            </Box>
          )}
        </SliderDrawer>
      </ContentCard>
    );
  };
  
  export default Visualization;
  
  
