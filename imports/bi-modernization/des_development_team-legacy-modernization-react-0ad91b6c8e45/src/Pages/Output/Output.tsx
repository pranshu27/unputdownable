import React, { useState } from 'react';
import ContentCard from '../../core/CardContent/CardContent.tsx';
import { useOutletContext } from 'react-router-dom';
import { Box, Typography, Tooltip, IconButton, Divider, Input } from '@mui/material';
import CustomPagination from '../../core/CustomPagination/CustomPagination.tsx';
import ReusableCard from '../../core/Card/Card.tsx';
import './Output.scss';
import { useSelector } from 'react-redux';
import { RootState } from '../../utils/Store.ts';
import SliderDrawer from '../../core/SliderDrawer/SliderDrawer.tsx';
import { ExpandLess, ExpandMore } from '@mui/icons-material';
import DataTable from '../../core/DataTable/DataTable.tsx';


 
function getSampleCardData(fileDetails) {
  switch (fileDetails?.etlTool) {
    case "ssis":
      return [
        { key: "ObjectName", label: "Object Name" },
        { key: "OutputType", label: "Output Type" },
        { key: "Description", label: "Description" },
        { key: "DestinationDetails", label: "DestinationDetails" }
      ];
    case "sas":
      return [
        { key: "node_id", label: "Node Id" },
        { key: "node_type", label: "Node Type" },
        { key: "type", label: "Type" },
        { key: "description", label: "Description" },
        { key: "libref", label: "Lib Ref" },
        { key: "path", label: "Path" }
      ];
    case "talend":
       return [
        { key: "node_type", label: "Node Type" },
        { key: "name", label: "Name" },
        { key: "id", label: "ID" },
        { key: "connectionID", label: "Connection ID" },
        { key: "baseType", label: "Base Type" },
        { key: "serialize", label: "Serialize" },
        { key: "description", label: "Description" },
        { key: "output_type", label: "Output Type" },
     ];
    default:
      return [
        { key: "node_type", label: "Node Type" },
        { key: "id", label: "Id" },
        { key: "baseType", label: "Base Type" },
        { key: "authentication_method", label: "Next Node" },
        { key: "serialize", label: "Serialize" },
        { key: "description", label: "Description" },
        { key: "output_type", label: "Output Type" }
      ];
  }
}
 

const Output = () => {
  const { sideNavWidth } = useOutletContext();
  const reduxData = useSelector((state: RootState) => state.apiData.data);
  const localStorageData = localStorage.getItem('analyzeResponse');
  const parsedLocalData = localStorageData ? JSON.parse(localStorageData) : null;
  const dataToUse = parsedLocalData || reduxData;
  const response = dataToUse.output ||dataToUse.outputs || [];

  const [searchTerm, setSearchTerm] = useState(''); 
  const [searchTermslider, setSearchTermslider] = useState(''); 

  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(50);
  const [selectedCard, setSelectedCard] = useState<any>(null);
  const [showAttributes, setShowAttributes] = useState(true);
  const [showFieldNames, setShowFieldNames] = useState(true);
  const [openDrawer, setopenPopup] = useState(false);
  const handleChangePage = (event, newPage) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  const handleSearchChange = (event) => {
    setSearchTerm(event.target.value);
    setPage(0); 
  };

  const handleSearchChangeSlider = (event) => {
    setSearchTermslider(event.target.value);
  };

  const handlePopupClose = () => {
    setopenPopup(false);
    setSearchTermslider('');
  };

  const filteredData = response.filter((res) => {
    const search = searchTerm.toLowerCase();
    const name = res.name || res.ObjectName || '';
    const description = res.description || res.Description || '';
    return (
      name.toLowerCase().includes(search) ||
      description.toLowerCase().includes(search)
    );
  });

  const paginatedData = filteredData.slice(
    page * rowsPerPage,
    page * rowsPerPage + rowsPerPage
  );

  const handleViewMoreClick = (res) => {
    setSelectedCard(res);
    setopenPopup(true);
    setSearchTermslider('');
  };

  const fileDetails = JSON.parse(localStorage.getItem('fileDetails') as any);
  const sampleCardData = getSampleCardData(fileDetails)

  const fieldData = selectedCard?.FieldNames || selectedCard?.field_names ||selectedCard?.fn || {};
  const filteredFieldEntries = Object.entries(fieldData).filter(([key, value]) => {
    const search = searchTermslider.toLowerCase();
    return (
      key.toLowerCase().includes(search) ||
      (typeof value === 'string' && value.toLowerCase().includes(search))
    );
  });
  const searchComponent = (
    <Input
      placeholder="Search…"
      value={searchTerm}
      onChange={handleSearchChange}
      sx={{
        boxShadow: '0px 4px 15px 0px rgba(133, 160, 186, 0.15)',
        px: 1.5,
        py: 0.5,
        width: 300,
        background: 'white',
        borderRadius: '28px',
        border: '1px solid #dddddd',
        '&:after': { borderBottom: 'none' },
        '&:before': { borderBottom: 'none' },
        '&:hover:not(.Mui-disabled):before': { borderBottom: 'none !important' },
      }}
      size="small"
    />
  );

  return (
    <ContentCard
      searchComponent={searchComponent}
      heading={
        <Typography fontWeight='600' color='rgba(0, 48, 135, 1)' fontSize='20px !important'>
          Output
        </Typography> as any
      }
      sideNavWidth={sideNavWidth}
      bottomContent={
        <CustomPagination
          count={filteredData.length}
          page={page}
          rowsPerPage={rowsPerPage}
          onPageChange={handleChangePage}
          onRowsPerPageChange={handleChangeRowsPerPage}
        /> as any
      }
    >
      <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
        {paginatedData.length === 0 ? (
          <div>No Data Found</div>
        ) : (
          paginatedData.map((res: any, i: number) => (
            <ReusableCard
              key={i}
              width={333}
              height={175}
              headingLabel={`Name:`}
              headingValue={res.name ? res.name : res.ObjectName}
              description={
                <Box display="flex" gap={1}>
                  <Typography variant="body2" color='rgba(100, 116, 139, 1)' fontWeight="600" fontSize="14px !important">
                    Description:
                  </Typography>
                  <Tooltip title={(res.description || res.Description) || 'N/A'}>
                    <Typography
                      variant="body2"
                      sx={{
                        display: '-webkit-box',
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: 'vertical',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'normal',
                        color: 'rgba(100, 116, 139, 1)',
                        fontWeight: 400,
                        fontSize: "14px !important",
                        maxWidth: '250px',
                      }}
                    >
                      {(res.description || res.Description) || 'N/A'}
                    </Typography>
                  </Tooltip>
                </Box>
              }
              layout='vertical'
              buttons={[
                {
                  label: 'View More',
                  backgroundRequired: false,
                  outlineRequired: false,
                  color: 'secondary',
                  onClick: () => handleViewMoreClick(res),
                  btnStylings: {
                    color: '#1C4473',
                    border: '1px solid #1C4473',
                    marginRight: '10px',
                    marginTop: '10px',
                    borderRadius: '8px',
                    width: '108px',
                    height: '32px'
                  },
                },
              ] as any}
            />
          ))
        )}
      </div>

         <SliderDrawer
        open={openDrawer}
        onClose={handlePopupClose}
        title={`Name : ${selectedCard?.name || selectedCard?.ObjectName}`}
        titleStylings={{
          color: 'rgba(0, 48, 135, 1)',
          fontSize: '20px',
          fontWeight: 500,
          backgroundColor: '#ffffff'
        }}
        onPrimaryClick={() => console.log('primary')}
        onSecondaryClick={() => console.log('secondary')}
        disablePrimaryBtn={false}
        disableSecondaryBtn={false}
        width='35%'
      >
        {selectedCard && (
          <Box display="flex" flexDirection="column" gap={2}>
            {sampleCardData.map((item, idx) => (
              <Typography key={idx} sx={{ color: 'rgba(100, 116, 139, 1)', fontWeight: '500' }}>
                <strong sx={{ fontSize: '14px', fontWeight: '600' }}>{item.label}:</strong>{' '}
                {String(selectedCard[item.key]) || "N/A"}
              </Typography>
            ))}
                {(selectedCard.output_details) && (
                            <>
                        <Divider />

                                 <Box mt={2}>
                                    <Box
                                        display="flex"
                                        onClick={() => setShowAttributes((prev) => !prev)}
                                        alignItems="center"
                                        gap={2}
                                        justifyContent="space-between"
                                        sx={{ cursor: 'pointer' }}
                                    >
                                        <Typography
                                            variant="subtitle1"
                                            sx={{
                                                color: 'rgba(71, 85, 105, 1)',
                                                fontSize: '20px',
                                                fontWeight: '600',
                                            }}
                                        >
                                            Output Details
                                        </Typography>
                                        <IconButton size="small">
                                            {showAttributes ? <ExpandLess /> : <ExpandMore />}
                                        </IconButton>
                                    </Box>

                                    {showAttributes && (
                                        <Box mt={1} ml={1} display="flex" flexDirection="column" gap={1}>
                                            {Object.entries(selectedCard.output_details || selectedCard.ConnectionDetails).map(
                                                ([key, value], index) => (
                                                    <Typography
                                                        key={index}
                                                        sx={{
                                                            color: 'rgba(100, 116, 139, 1)',
                                                            fontSize: '14px',
                                                            fontWeight: '500',
                                                        }}
                                                    >
                                                        <strong>{key} :</strong> {String(value) || 'N/A'}
                                                    </Typography>
                                                )
                                            )}
                                        </Box>
                                    )}
                                </Box>
                            </>
                        )}
            {(selectedCard?.ObjectName || selectedCard?.node_type || selectedCard?.name) && (
              <>
                <Divider />
                <Box mt={2}>
                  <Box
                    display="flex"
                    onClick={() => setShowFieldNames((prev) => !prev)}
                    sx={{ cursor: 'pointer' }}
                    alignItems="center"
                    justifyContent="space-between"
                  >
                    <Typography
                      variant="subtitle1"
                      sx={{
                        color: 'rgba(71, 85, 105, 1)',
                        fontSize: '20px',
                        fontWeight: '600'
                      }}
                    >
                      Field Names
                    </Typography>
                    <IconButton size="small">
                      {showFieldNames ? <ExpandLess /> : <ExpandMore />}
                    </IconButton>
                  </Box>

                  {showFieldNames && (
                    <Box mt={1}>
                      <DataTable
                        data={filteredFieldEntries.map(([key, value]) => ({ key, value }))}
                        columns={[
                          { header: 'Key', field: 'key' },
                          { header: 'Value', field: 'value' },
                        ]}
                        showCheckbox={false}
                        disableSearch={false}
                        editRowId={null}
                        searchTerm={searchTermslider}
                        onSearchChange={handleSearchChangeSlider}
                        Height="450"
                      />
                    </Box>
                  )}
                </Box>
              </>
            )}
          </Box>
        )}
      </SliderDrawer>
    </ContentCard>
  );
};

export default Output;
