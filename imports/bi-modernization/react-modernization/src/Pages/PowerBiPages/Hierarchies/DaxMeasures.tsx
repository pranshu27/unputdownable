import React, { useState } from "react";
import {
  Box,
  Typography,
  Input,
  Chip
} from "@mui/material";
import ContentCard from "../../../core/CardContent/CardContent.tsx";
import ReusableCard from "../../../core/Card/Card.tsx";
import SliderDrawer from "../../../core/SliderDrawer/SliderDrawer.tsx";
import CustomPagination from "../../../core/CustomPagination/CustomPagination.tsx";
import { useOutletContext } from "react-router-dom";
import { useSelector } from "react-redux";
import { RootState } from "../../../utils/Store.ts";

const DaxMeasures = () => {
  const { sideNavWidth } = useOutletContext() as any;

  const reduxData = useSelector((state: RootState) => state.apiData.data);
  const localStorageData = localStorage.getItem("analyzeResponse");
  const parsedLocalData = localStorageData
    ? JSON.parse(localStorageData)
    : null;

  const dataToUse = parsedLocalData || reduxData;
  const measures = dataToUse?.agent_result?.["DAX Measures"] || [];

  const [searchTerm, setSearchTerm] = useState("");
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(50);
  const [selectedMeasure, setSelectedMeasure] = useState<any>(null);
  const [openDrawer, setOpenDrawer] = useState(false);

  // 🔍 Search
  const filteredList = measures.filter((m: any) =>
    m.name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const paginatedData = filteredList.slice(
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
      heading={
        <Typography sx={{fontWeight:'600'}} color='rgba(0, 48, 135, 1)' fontSize='20px !important'>
          DAX Measures
        </Typography>
      }
      searchComponent={searchComponent}
      sideNavWidth={sideNavWidth}
      bottomContent={
        <CustomPagination
          count={filteredList.length}
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
        {paginatedData.map((m: any, i: number) => (
          <ReusableCard
            key={i}
            width={340}
            height={180}
            headingLabel="Measure : "
            headingValue={m.name}
            description={
              <Box>
                <Typography fontSize="13px" color="gray">
                  <b>Aggregation:</b> {m.aggregation}
                </Typography>

                <Typography fontSize="13px" color="gray">
                  <b>Reusable:</b> {m.reusable_metric ? "Yes" : "No"}
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
                  setSelectedMeasure(m);
                  setOpenDrawer(true);
                },
              },
            ]}
          />
        ))}
      </Box>

      {/* 🔥 Drawer */}
      <SliderDrawer
        open={openDrawer}
        onClose={() => setOpenDrawer(false)}
        width="45%"
        title={
          <Typography fontWeight={600}>
            {selectedMeasure?.name}
          </Typography>
        }
      >
        {selectedMeasure && (
          <Box display="flex" flexDirection="column" gap={2}>
            
            {/* 🔹 Basic Info */}
            <Box>
              <Typography><b>Aggregation:</b> {selectedMeasure.aggregation}</Typography>
              <Typography>
                <b>Reusable:</b> {selectedMeasure.reusable_metric ? "Yes" : "No"}
              </Typography>
            </Box>

            {/* 🔹 Expression (🔥 Code Block) */}
            <Box>
              <Typography fontWeight={600}>Expression</Typography>
              <Box
                sx={{
                  p: 2,
                  background: "#0f172a",
                  color: "#e2e8f0",
                  borderRadius: "8px",
                  fontSize: "12px",
                  fontFamily: "monospace",
                  overflow: "auto",
                }}
              >
                {selectedMeasure.expression}
              </Box>
            </Box>

            {/* 🔹 Dependencies */}
            <Box>
              <Typography fontWeight={600}>Depends On</Typography>

              <Box display="flex" gap={1} flexWrap="wrap" mt={1}>
                {selectedMeasure.depends_on_columns.map((col: string, i: number) => (
                  <Chip key={i} label={col} size="small" color="primary" />
                ))}
              </Box>
            </Box>

          </Box>
        )}
      </SliderDrawer>
    </ContentCard>
  );
};

export default DaxMeasures;