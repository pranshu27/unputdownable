import React, { useState } from 'react';
import {
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Typography,Box
} from '@mui/material';
import {
    TableContainer,
    Table,
    TableHead,
    TableBody,
    TableRow,
    TableCell,
    Paper
  } from "@mui/material";
  
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ContentCard from '../../core/CardContent/CardContent.tsx';
import { data, useOutletContext } from 'react-router-dom';
import { useSelector } from 'react-redux';
import { RootState } from '../../utils/Store.ts';
import { sanitizeToHTML } from '../../utils/SanitizeAndRender.tsx';

const DashboardAnalysis = () => {
  const { sideNavWidth } = useOutletContext();
  const reduxData = useSelector((state: RootState) => state.apiData.data);
  const localStorageData = localStorage.getItem('analyzeResponse');
  const parsedLocalData = localStorageData ? JSON.parse(localStorageData) : null;
  const dataToUse = parsedLocalData || reduxData;
const rawDashboards = dataToUse.Dashboards || reduxData?.Dashboards;
// [{
//     "name": dataToUse?.Dashboards[0]?.name.length > 0 ? dataToUse.Dashboards[0].name : "Empty",
//     "object_id": dataToUse?.Dashboards[0]?.object_id.length > 0 ? dataToUse.Dashboards[0].object_id : "Empty",
//     "width": 1169,
//     "height": 827,
//     "background_color": "#FFFFFF",
//     "components": [
//         {
//             "name": "Heat Map",
//             "object_id": "3",
//             "position": {
//                 "x": 684,
//                 "y": 7013,
//                 "width": 42472,
//                 "height": 54116
//             },
//             "font_size": 8,
//             "color": "#000000"
//         },
//         {
//             "name": "Moving Average Dual Axis",
//             "object_id": "9",
//             "position": {
//                 "x": 684,
//                 "y": 61129,
//                 "width": 42472,
//                 "height": 37904
//             },
//             "font_size": 8,
//             "color": "#000000"
//         },
//         {
//             "name": "Measure Names and Value",
//             "object_id": "11",
//             "position": {
//                 "x": 43156,
//                 "y": 7013,
//                 "width": 42473,
//                 "height": 54116
//             },
//             "font_size": 8,
//             "color": "#000000"
//         },
//         {
//             "name": "Scatter",
//             "object_id": "12",
//             "position": {
//                 "x": 43156,
//                 "y": 61129,
//                 "width": 42473,
//                 "height": 37904
//             },
//             "font_size": 8,
//             "color": "#000000"
//         },
//         {
//             "name": "[federated.00jclz20xo74nq1f9c6jn1c0ujs7].[none:Grouping, Sub-Grouping - Split 1:nk]",
//             "object_id": "15",
//             "position": {
//                 "x": 85629,
//                 "y": 7013,
//                 "width": 13687,
//                 "height": 15477
//             },
//             "font_size": 8,
//             "color": "#000000"
//         },
//         {
//             "name": "[federated.00jclz20xo74nq1f9c6jn1c0ujs7].[none:Region:nk]",
//             "object_id": "16",
//             "position": {
//                 "x": 85629,
//                 "y": 22490,
//                 "width": 13687,
//                 "height": 18258
//             },
//             "font_size": 8,
//             "color": "#000000"
//         }
//     ]
// }
// ]

const dashboards = Array.isArray(rawDashboards)
  ? rawDashboards
  : rawDashboards
  ? [rawDashboards]
  : [];
  return (
    <div>
     
    <ContentCard
        heading={
            <Typography
            variant="h6"
            fontWeight="600"
            color="rgba(0,48,135,1)"
            fontSize="20px"
            >
            Dashboards
            </Typography>
        }
        sideNavWidth={sideNavWidth}
        >
        {dashboards.length === 0 ? (
            <Typography color="text.secondary">No dashboards found.</Typography>
        ) : (
            dashboards.map((dashboard, dIndex) => (
            <Box
                key={dIndex}
                sx={{
                border: "1px solid #e0e6ef",
                borderRadius: "16px",
                padding: "20px",
                background: "#ffffff",
                boxShadow: "0px 4px 14px rgba(0,0,0,0.06)",
                mb: 4,
                }}
            >
                {/* Dashboard Title */}
                <Typography
                fontWeight={700}
                fontSize="22px"
                color="rgba(0,107,194,1)"
                mb={1}
                >
                {dashboard.name}
                </Typography>

                {/* Dashboard Meta Details */}
                <Box
                display="flex"
                gap="40px"
                mb={3}
                flexWrap="wrap"
                sx={{ color: "rgba(100,116,139,1)", fontSize: "15px" }}
                >
                <div>📐 Size: <strong>{dashboard.width} × {dashboard.height}</strong></div>
                <div>🎨 Background: <strong>{dashboard.background_color}</strong></div>
                <div>🆔 Object ID: <strong>{dashboard.object_id}</strong></div>
                </Box>

                {/* Components Section */}
                <Typography
                fontWeight={600}
                fontSize="18px"
                color="#003087"
                mb={2}
                >
                Components
                </Typography>

                <TableContainer component={Paper} sx={{ borderRadius: 2 }}>
        <Table>
          <TableHead>
            <TableRow sx={{ backgroundColor: "rgba(0,107,194,0.1)" }}>
              <TableCell><strong>Name</strong></TableCell>
              <TableCell><strong>Width</strong></TableCell>
              <TableCell><strong>Height</strong></TableCell>
              <TableCell><strong>X</strong></TableCell>
              <TableCell><strong>Y</strong></TableCell>
              <TableCell><strong>Font Size</strong></TableCell>
              <TableCell><strong>Color</strong></TableCell>
            </TableRow>
          </TableHead>

          <TableBody>
            {dashboard.components.map((comp, i) => (
              <TableRow key={i}>
                <TableCell>{comp.name}</TableCell>
                <TableCell>{comp.position.width}</TableCell>
                <TableCell>{comp.position.height}</TableCell>
                <TableCell>{comp.position.x}</TableCell>
                <TableCell>{comp.position.y}</TableCell>
                <TableCell>{comp.font_size}</TableCell>
                <TableCell>
                  <Box
                    sx={{
                      width: 20,
                      height: 20,
                      borderRadius: "4px",
                      border: "1px solid #ccc",
                      backgroundColor: comp.color,
                    }}
                  ></Box>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
            </Box>
            ))
        )}
        </ContentCard>


    </div>
  );
};

export default DashboardAnalysis;
