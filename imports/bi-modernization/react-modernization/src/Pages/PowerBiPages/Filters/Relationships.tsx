import React, { useState } from "react";
import { Box, Typography, Input, Chip } from "@mui/material";
import { useOutletContext } from "react-router-dom";
import { useSelector } from "react-redux";
import { RootState } from "../../../utils/Store.ts";
import ReusableCard from "../../../core/Card/Card.tsx";
import ContentCard from "../../../core/CardContent/CardContent.tsx";
import SliderDrawer from "../../../core/SliderDrawer/SliderDrawer.tsx";
import CustomPagination from "../../../core/CustomPagination/CustomPagination.tsx";

const Relationships = () => {
  const { sideNavWidth } = useOutletContext() as any;

  const reduxData = useSelector((state: RootState) => state.apiData.data);
  const localStorageData = localStorage.getItem("analyzeResponse");
  const parsedLocalData = localStorageData
    ? JSON.parse(localStorageData)
    : null;

  const dataToUse = parsedLocalData || reduxData;
  const relationships = dataToUse?.agent_result?.Relationships || [];

  const [searchTerm, setSearchTerm] = useState("");
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(50);
  const [selectedRel, setSelectedRel] = useState<any>(null);
  const [openDrawer, setOpenDrawer] = useState(false);

  // 🔍 Search
  const filteredList = relationships.filter((r: any) => {
    const search = searchTerm.toLowerCase();
    return (
      r.left_table.toLowerCase().includes(search) ||
      r.right_table.toLowerCase().includes(search)
    );
  });

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
          Relationships
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
        {paginatedData.map((r: any, i: number) => (
          <ReusableCard
            key={i}
            width={340}
            height={180}
            headingLabel="Relationship :"
            headingValue={`${r.left_table} → ${r.right_table}`}
            description={
              <Box>
                <Typography fontSize="13px" color="gray">
                  <b>From:</b> {r.left_table}
                </Typography>

                <Typography fontSize="13px" color="gray">
                  <b>To:</b> {r.right_table}
                </Typography>
              </Box>
            }
            buttons={[
              {
                label: "View Details",
                btnStylings: {
                  fontSize: "12px",
                  border: "1px solid #1C4473",
                  borderRadius: "6px",
                },
                onClick: () => {
                  setSelectedRel(r);
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
        width="40%"
        title={
          <Typography fontWeight={600}>
            {selectedRel?.left_table} → {selectedRel?.right_table}
          </Typography>
        }
      >
        {selectedRel && (
          <Box display="flex" flexDirection="column" gap={2}>

            {/* 🔹 Relationship Summary */}
            <Box
              sx={{
                p: 2,
                border: '1px solid #e2e8f0',
                borderRadius: '8px',
                background: '#f8fafc'
              }}
            >
              <Typography fontWeight={600}>Relationship Details</Typography>

              <Box mt={1} display="grid" gridTemplateColumns="1fr 1fr" gap={1}>
                <Typography><b>Left Table:</b> {selectedRel.left_table}</Typography>
                <Typography><b>Right Table:</b> {selectedRel.right_table}</Typography>

                <Typography><b>Left Column:</b> {selectedRel.left_column}</Typography>
                <Typography><b>Right Column:</b> {selectedRel.right_column}</Typography>

                <Typography><b>Cardinality:</b> {selectedRel.cardinality}</Typography>
                <Typography><b>Join Type:</b> {selectedRel.join_type}</Typography>

                <Typography>
                  <b>Active:</b> {selectedRel.active ? "Yes" : "No"}
                </Typography>

                <Typography>
                  <b>Bidirectional:</b> {selectedRel.bidirectional_filter ? "Yes" : "No"}
                </Typography>

                <Typography>
                  <b>Integrity Enforced:</b> {selectedRel.enforced_integrity ? "Yes" : "No"}
                </Typography>
              </Box>
            </Box>

            {/* 🔹 Status Chips */}
            <Box display="flex" gap={1} flexWrap="wrap">
              {selectedRel.active ? (
                <Chip label="Active" color="success" />
              ) : (
                <Chip label="Inactive" color="error" />
              )}

              {selectedRel.bidirectional_filter && (
                <Chip label="Bidirectional Filter" color="info" />
              )}

              <Chip label={`Join: ${selectedRel.join_type}`} color="secondary" />
              <Chip label={`Cardinality: ${selectedRel.cardinality}`} color="primary" />
            </Box>

          </Box>
        )}
      </SliderDrawer>
    </ContentCard>
  );
};

export default Relationships;