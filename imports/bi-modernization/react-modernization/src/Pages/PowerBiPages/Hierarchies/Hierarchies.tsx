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

const Hierarchies = () => {
    const { sideNavWidth } = useOutletContext() as any;
  
    const reduxData = useSelector((state: RootState) => state.apiData.data);
    const localStorageData = localStorage.getItem("analyzeResponse");
    const parsedLocalData = localStorageData ? JSON.parse(localStorageData) : null;
  
    const dataToUse = parsedLocalData || reduxData;
  
    // Final Hierarchies Data
    const response = dataToUse?.Hierarchies || '';
  
    const [page, setPage] = useState(0);
    const [rowsPerPage, setRowsPerPage] = useState(50);
    const [searchTerm, setSearchTerm] = useState("");
  
    const handleChangePage = (_event, newPage) => setPage(newPage);
    const handleChangeRowsPerPage = (event) => {
      const newRows = parseInt(event.target.value, 10);
      setRowsPerPage(!isNaN(newRows) ? newRows : 50);
      setPage(0);
    };
  
    const handleSearchChange = (event) => {
      setSearchTerm(event.target.value);
      setPage(0);
    };
  
    // Search only inside name or members
    const filteredResponse = response.filter((item) => {
      const search = searchTerm.toLowerCase();
      return (
        item.name.toLowerCase().includes(search) ||
        item.members.some((m) => m.toLowerCase().includes(search))
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
          boxShadow: "0px 4px 15px rgba(133, 160, 186, 0.15)",
          px: 1.5,
          py: 0.5,
          width: 300,
          background: "white",
          borderRadius: "28px",
          border: "1px solid #dddddd",
        }}
        size="small"
      />
    );
  
    return (
      <ContentCard
        searchComponent={searchComponent}
        heading={
          <Typography
            variant="h6"
            fontWeight="600"
            color="rgba(0, 48, 135, 1)"
            fontSize="20px !important"
          >
            Hierarchies
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
            <Typography
              variant="body1"
              sx={{
                color: "gray",
                mt: 4,
                mx: "auto",
                fontSize: "18px",
                fontWeight: 500,
              }}
            >
              No data found.
            </Typography>
          ) : (
            paginatedData.map((item, i) => (
              <ReusableCard
                key={i}
                width={330}
                height={200}
                headingLabel="Hierarchy:"
                headingValue={item.name}
                description={
                  <Box mt={1}>
                    <Typography
                      fontSize="14px"
                      fontWeight="600"
                      color="rgba(100, 116, 139, 1)"
                    >
                      Members:
                    </Typography>
  
                    <ul
                      style={{
                        marginLeft: "18px",
                        marginTop: "5px",
                        fontSize: "13px",
                        color: "rgba(71, 85, 105, 1)",
                      }}
                    >
                      {item.members.map((m, idx) => (
                        <li key={idx}>{m}</li>
                      ))}
                    </ul>
                  </Box>
                }
                layout="vertical"
                buttons={[]}
              />
            ))
          )}
        </div>
      </ContentCard>
    );
  };
    
  
  export default Hierarchies;
  
