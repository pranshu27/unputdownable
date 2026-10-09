import React, { useState, useMemo } from 'react';
import { Tabs, Tab, Typography, Box } from '@mui/material';
import { useOutletContext } from 'react-router-dom';
import ContentCard from '../../core/CardContent/CardContent.tsx';
import CustomPagination from '../../core/CustomPagination/CustomPagination.tsx';
import DataTable from '../../core/DataTable/DataTable.tsx';
import './Transformations.scss';
import { useSelector } from 'react-redux';
import { RootState } from '../../utils/Store.ts';

interface OutletContextType {
    sideNavWidth: number;
}

const Transformations = () => {
    const { sideNavWidth } = useOutletContext<OutletContextType>();
    const [tabIndex, setTabIndex] = useState(0);
    const [searchTerm, setSearchTerm] = useState('');
    const [page, setPage] = useState(0);
    const [rowsPerPage, setRowsPerPage] = useState(50);
    const reduxData = useSelector((state: RootState) => state.apiData.data);
    const localStorageData = localStorage.getItem('analyzeResponse');
    const parsedLocalData = localStorageData ? JSON.parse(localStorageData) : null;

    const dataToUse = parsedLocalData || reduxData || {};
    
    const tranformationResponse =
        dataToUse?.transformations ??
        dataToUse?.commands ??
        [];

    const customCalculationResponse =
        dataToUse?.customCalculations ??
        dataToUse?.variables ??
        [];

    const containers = dataToUse?.containers || [];
    const macros = dataToUse?.macro || [];

    // Build responses array dynamically
    const responses = [tranformationResponse, customCalculationResponse];
    
    // Build tabs array dynamically
    const tabs = [
        {
            label: (() => {
                const fileData = localStorage.getItem('fileDetails');
                const parsedData = fileData ? JSON.parse(fileData) : null;
                return parsedData?.filename?.includes('.bteq') || parsedData?.filename?.includes('.sql')
                    ? 'Commands'
                    : 'Transformations';
            })()
        },
        {
            label: (() => {
                const fileData = localStorage.getItem('fileDetails');
                const parsedData = fileData ? JSON.parse(fileData) : null;
                return parsedData?.filename?.includes('.bteq') || parsedData?.filename?.includes('.sql')
                    ? 'Variables'
                    : 'Custom Calculations';
            })()
        }
    ];

    // Add containers if exists
    if (containers.length > 0) {
        responses.push(containers);
        tabs.push({ label: 'Containers' });
    }

    // Add macros if exists
    if (macros.length > 0) {
        responses.push(macros);
        tabs.push({ label: 'Macros' });
    }

    const currentData = responses[tabIndex] || [];

    const filteredData = useMemo(() => {
        if (!Array.isArray(currentData) || currentData.length === 0) {
            return [];
        }
        return currentData.filter((row) =>
            Object.values(row || {}).some((val) =>
                String(val).toLowerCase().includes(searchTerm.toLowerCase())
            )
        );
    }, [currentData, searchTerm]);

    const paginatedData = useMemo(() => {
        const start = page * rowsPerPage;
        return filteredData.slice(start, start + rowsPerPage);
    }, [filteredData, page, rowsPerPage]);

    // Generate columns directly without caching - this is the key fix!
    const currentColumns = useMemo(() => {
        if (!currentData || !Array.isArray(currentData) || currentData.length === 0) {
            return [];
        }

        const firstRow = currentData[0];
        if (!firstRow || typeof firstRow !== 'object') {
            return [];
        }

        return Object.keys(firstRow).map((key) => ({
            field: key,
            header: key
                .replace(/_/g, ' ')
                .replace(/\b\w/g, (c) => c.toUpperCase())
        }));
    }, [currentData, tabIndex]); // Added tabIndex as dependency to force recalculation

    const handleChangePage = (_event, newPage) => {
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

    const handleTabChange = (_, val) => {
        setTabIndex(val);
        setSearchTerm('');
        setPage(0);
    };

    return (
        <ContentCard
            heading={
                <Typography color='rgba(0, 48, 135, 1)' fontSize='20px !important' fontWeight='600'>
                    Transformations
                </Typography>
            }
            sideNavWidth={sideNavWidth}
            bottomContent={
                <CustomPagination
                    count={filteredData.length}
                    page={page}
                    rowsPerPage={rowsPerPage}
                    onPageChange={handleChangePage}
                    onRowsPerPageChange={handleChangeRowsPerPage}
                />
            }
            noscroll={true}
        >
            <Tabs 
                value={tabIndex} 
                onChange={handleTabChange}
                className='tabs' 
                sx={{ width: 'calc(100% - 400px)' }}
            >
                {tabs.map((tab, index) => (
                    <Tab
                        key={index}
                        label={tab.label}
                        sx={{
                            textTransform: 'capitalize',
                            fontSize: '14px !important',
                            fontWeight: '600',
                            color: tabIndex === index ? 'rgba(0, 45, 138, 1)' : 'rgba(100, 116, 139, 1)',
                            borderBottom: tabIndex === index ? '2px solid rgba(41, 107, 194, 1)' : ''
                        }}
                    />
                ))}
            </Tabs>

            <Box>
                {currentData.length === 0 || paginatedData.length === 0 ? (
                    <Box sx={{ p: 4, textAlign: 'center', mt: 2 }}>
                        <Typography variant="h6" color="text.secondary">
                            No data available for {tabs[tabIndex]?.label}
                        </Typography>
                    </Box>
                ) : (
                    <DataTable
                        key={tabIndex} // Force re-render when tab changes
                        data={paginatedData}
                        columns={currentColumns}
                        showCheckbox={false}
                        actions={[]}
                        disableSearch={false}
                        onActionClick={() => console.log('empty')}
                        onRowSelect={() => console.log('empty')}
                        editRowId={null}
                        editedData={null}
                        onEditChange={() => console.log('empty')}
                        Height='430'
                        searchTerm={searchTerm}
                        onSearchChange={handleSearchChange}
                        containerHeight='275'
                        additionalStylings={{ position: 'relative', top: '-60px', zIndex: '0' }}
                    />
                )}
            </Box>
        </ContentCard>
    );
};

export default Transformations;