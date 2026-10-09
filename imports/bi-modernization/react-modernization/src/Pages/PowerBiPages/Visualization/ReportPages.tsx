import React, { useState } from "react";
import {
  Box,
  Typography,
  Input,
  Chip,
  Accordion,
  AccordionSummary,
  AccordionDetails
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ContentCard from "../../../core/CardContent/CardContent.tsx";
import ReusableCard from "../../../core/Card/Card.tsx";
import SliderDrawer from "../../../core/SliderDrawer/SliderDrawer.tsx";
import { useOutletContext } from "react-router-dom";
import { useSelector } from "react-redux";
import { RootState } from "../../../utils/Store.ts";

const Report = () => {
  const { sideNavWidth } = useOutletContext() as any;

  const reduxData = useSelector((state: RootState) => state.apiData.data);
  const localStorageData = localStorage.getItem("analyzeResponse");
  const parsedLocalData = localStorageData
    ? JSON.parse(localStorageData)
    : null;

  const dataToUse = parsedLocalData || reduxData;
  const pages = dataToUse?.agent_result?.["Report Pages"] || [];

  const [searchTerm, setSearchTerm] = useState("");
  const [selectedPage, setSelectedPage] = useState<any>(null);
  const [openDrawer, setOpenDrawer] = useState(false);

  // 🔍 Search
  const filteredPages = pages.filter((p: any) =>
    p.page_name.toLowerCase().includes(searchTerm.toLowerCase())
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
          Report Pages
        </Typography>
      }
      searchComponent={searchComponent}
      sideNavWidth={sideNavWidth}
    >
      {/* 🔥 Page Cards */}
      <Box display="flex" flexWrap="wrap" gap={2} mt={2}>
        {filteredPages.length === 0 ? (
          <Typography sx={{ mx: "auto", mt: 5, color: "#94a3b8" }}>
            No pages found.
          </Typography>
        ) : (
          filteredPages.map((p: any, i: number) => (
            <ReusableCard
              key={i}
              width={320}
              height={170}
              headingLabel="Page :"
              headingValue={p.page_name}
              description={
                <Box>
                  <Typography fontSize="13px">
                    <b>Visuals:</b> {p.visuals.length}
                  </Typography>

                  <Typography fontSize="13px" color="gray">
                    Types:{" "}
                    {[...new Set(p.visuals.map((v: any) => v.visual_type))]
                      .slice(0, 3)
                      .join(", ")}
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
                    setSelectedPage(p);
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
        width="45%"
        title={
          <Typography fontWeight={600}>
            Page: {selectedPage?.page_name}
          </Typography>
        }
      >
        {selectedPage && (
          <Box display="flex" flexDirection="column" gap={2}>
            {/* Summary */}
            <Box>
              <Typography>
                <b>Total Visuals:</b> {selectedPage.visuals.length}
              </Typography>
            </Box>

            {/* 🔥 Visuals */}
            {selectedPage.visuals.map((v: any, i: number) => (
              <Accordion
                key={i}
                sx={{
                  borderRadius: "10px",
                  overflow: "hidden",
                  border: "1px solid #e2e8f0",
                  "&:before": { display: "none" },
                }}
              >
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Box display="flex" alignItems="center" gap={1}>
                    <Typography fontSize="14px" fontWeight={600}>
                      {v.visual_type}
                    </Typography>
                  </Box>
                </AccordionSummary>

                <AccordionDetails>
                  <Box
                    sx={{
                      p: 2,
                      borderRadius: "12px",
                      border: "1px solid #e2e8f0",
                      background: "#f8fafc",
                    }}
                  >
                    {/* Tables */}
                    <Box mb={2}>
                      <Typography fontWeight={600} fontSize="13px" mb={1}>
                        Tables Used
                      </Typography>

                      {v.tables_used?.length > 0 ? (
                        <Box display="flex" gap={1} flexWrap="wrap">
                          {v.tables_used.map((t: string, idx: number) => (
                            <Chip
                              key={idx}
                              label={t}
                              size="small"
                              color="primary"
                              sx={{ fontWeight: 500 }}
                            />
                          ))}
                        </Box>
                      ) : (
                        <Typography fontSize="12px" color="gray">
                          N/A
                        </Typography>
                      )}
                    </Box>

                    {/* Columns */}
                    <Box>
                      <Typography fontWeight={600} fontSize="13px" mb={1}>
                        Columns Used
                      </Typography>

                      {v.columns_used?.length > 0 ? (
                        <Box display="flex" gap={1} flexWrap="wrap">
                          {v.columns_used.map((c: string, idx: number) => (
                            <Chip
                              key={idx}
                              label={c}
                              size="small"
                              color="primary"
                              sx={{ fontWeight: 500 }}
                            />
                          ))}
                        </Box>
                      ) : (
                        <Typography fontSize="12px" color="gray">
                          N/A
                        </Typography>
                      )}
                    </Box>
                  </Box>
                </AccordionDetails>
              </Accordion>
            ))}
          </Box>
        )}
      </SliderDrawer>
    </ContentCard>
  );
};

export default Report;