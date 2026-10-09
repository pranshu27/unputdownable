import React, { useState } from "react";
import ReusableCard from "../../../core/Card/Card.tsx";
import { Box, Typography, Input } from "@mui/material";
import ContentCard from "../../../core/CardContent/CardContent.tsx";
import { useOutletContext } from "react-router-dom";
import CustomPagination from "../../../core/CustomPagination/CustomPagination.tsx";
import SliderDrawer from "../../../core/SliderDrawer/SliderDrawer.tsx";
import { useSelector } from 'react-redux';
import { RootState } from '../../../utils/Store.ts';

const SheetsComponent = () => {
  const { sideNavWidth } = useOutletContext() as any;
  const reduxData = useSelector((state: RootState) => state.apiData.data);
  const localStorageData = localStorage.getItem('analyzeResponse');
  const parsedLocalData = localStorageData ? JSON.parse(localStorageData) : null;
  const dataToUse = parsedLocalData || reduxData;
  const sheets = dataToUse?.Sheets || '';


  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(50);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedItem, setSelectedItem] = useState<any>(null);
  const [openDrawer, setOpenDrawer] = useState(false);

  // ------------------------ Search Logic ------------------------
  const filteredData = sheets.filter((s) =>
    s.name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const paginatedData = filteredData.slice(
    page * rowsPerPage,
    page * rowsPerPage + rowsPerPage
  );

  const searchComponent = (
    <Input
      placeholder="Search sheets…"
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
          Sheets
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
        {paginatedData.map((sheet, i) => (
          <ReusableCard
            key={i}
            width={333}
            height={160}
            headingLabel="Sheet Name:"
            headingValue={sheet.name}
            description={
              <Box>
                <Typography fontWeight={600}>Object ID:</Typography>
                <Typography fontSize={13}>{sheet.object_id}</Typography>
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
                  setSelectedItem(sheet);
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
        title={<b>Sheet Details</b>}
      >
        {selectedItem && (
          <Box display="flex" flexDirection="column" gap={2}>
            <Typography>
              <strong>Name:</strong> {selectedItem.name}
            </Typography>

            <Typography>
              <strong>Object ID:</strong> {selectedItem.object_id}
            </Typography>
          </Box>
        )}
      </SliderDrawer>
    </ContentCard>
  );
};

export default SheetsComponent;
