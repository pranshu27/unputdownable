import React, { useState } from "react";
import { Box, Typography, Input } from "@mui/material";
import { useOutletContext } from "react-router-dom";
import { useSelector } from 'react-redux';
import { RootState } from '../../../utils/Store.ts';
import ReusableCard from "../../../core/Card/Card.tsx";
import ContentCard from "../../../core/CardContent/CardContent.tsx";
import SliderDrawer from "../../../core/SliderDrawer/SliderDrawer.tsx";
import CustomPagination from "../../../core/CustomPagination/CustomPagination.tsx";

const Filters = () => {
  const { sideNavWidth } = useOutletContext() as any;
  const reduxData = useSelector((state: RootState) => state.apiData.data);
  const localStorageData = localStorage.getItem('analyzeResponse');
  const parsedLocalData = localStorageData ? JSON.parse(localStorageData) : null;
  const dataToUse = parsedLocalData || reduxData;
  const filters = dataToUse?.Filters || '';

  // ------------------------ States ------------------------
  const [searchTerm, setSearchTerm] = useState("");
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(50);
  const [selectedFilter, setSelectedFilter] = useState<any>(null);
  const [openDrawer, setOpenDrawer] = useState(false);

  // ------------------------ Search Logic ------------------------
  const filteredList = filters.filter((f) =>
    f.name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const paginatedData = filteredList.slice(
    page * rowsPerPage,
    page * rowsPerPage + rowsPerPage
  );

  const searchComponent = (
    <Input
      placeholder="Search filters…"
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
          Filters
        </Typography>
      }
      searchComponent={searchComponent}
      sideNavWidth={sideNavWidth}
      bottomContent={
        <CustomPagination
          count={filteredList.length}
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
          marginTop: "10px",
          gap: "20px",
          flexWrap: "wrap",
        }}
      >
        {paginatedData.map((f, i) => (
          <ReusableCard
            key={i}
            width={333}
            height={175}
            headingLabel="Filter Name:"
            headingValue={f.name}
            description={
              <Box  display="flex">
                <Typography fontWeight={600}>Object ID:</Typography>
                <Typography fontSize={13}>{f.object_id}</Typography>
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
                  setSelectedFilter(f);
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
        title={<b>Filter: {selectedFilter?.name}</b>}
      >
        {selectedFilter && (
          <Box display="flex" flexDirection="column" gap={2}>
            <Typography>
              <strong>Object ID:</strong> {selectedFilter.object_id}
            </Typography>

            <Typography>
              <strong>Columns:</strong>
            </Typography>
            {selectedFilter.columns.map((c, idx) => (
              <Typography key={idx} sx={{ pl: 2 }}>
                • {c}
              </Typography>
            ))}

            <Typography>
              <strong>Formatting:</strong>
            </Typography>
            {Object.entries(selectedFilter.formatting).map(([k, v], idx) => (
              <Typography key={idx} sx={{ pl: 2 }}>
                • <b>{k}:</b> {v || "N/A"}
              </Typography>
            ))}

            <Typography>
              <strong>Interactivity:</strong>
            </Typography>
            {Object.entries(selectedFilter.interactivity).map(([k, v], idx) => (
              <Typography key={idx} sx={{ pl: 2 }}>
                • <b>{k}:</b> {v || "N/A"}
              </Typography>
            ))}

            <Typography>
              <strong>Sorting:</strong>
            </Typography>
            {Object.entries(selectedFilter.sorting).map(([k, v], idx) => (
              <Typography key={idx} sx={{ pl: 2 }}>
                • <b>{k}:</b> {v || "N/A"}
              </Typography>
            ))}

            <Typography>
              <strong>Background Color:</strong> {selectedFilter.background_color || "None"}
            </Typography>
          </Box>
        )}
      </SliderDrawer>
    </ContentCard>
  );
};

export default Filters;
