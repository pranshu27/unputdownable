import React, { useState, useMemo } from 'react';
import { Tabs, Tab, Typography, Box } from '@mui/material';
import { useOutletContext } from 'react-router-dom';
import ContentCard from '../../../core/CardContent/CardContent.tsx';
import CustomPagination from '../../../core/CustomPagination/CustomPagination.tsx';
import DataTable from '../../../core/DataTable/DataTable.tsx';
import { useSelector } from 'react-redux';
import { RootState } from '../../../utils/Store.ts';

interface OutletContextType {
    sideNavWidth: number;
}


const DataTransformation = () => {
    const { sideNavWidth } = useOutletContext<OutletContextType>();
    const [tabIndex, setTabIndex] = useState(0);
    const [columnsCache, setColumnsCache] = useState<{ [key: number]: any[] }>({});
    const [searchTerm, setSearchTerm] = useState('');
    const [page, setPage] = useState(0);
    const [rowsPerPage, setRowsPerPage] = useState(50);
    const reduxData = useSelector((state: RootState) => state.apiData.data);
    const localStorageData = localStorage.getItem('analyzeResponse');
    const parsedLocalData = localStorageData ? JSON.parse(localStorageData) : null;

    const dataToUse = parsedLocalData || reduxData;


    const currentData = dataToUse?.agent_result?.Transformations|| '';

    const filteredData = useMemo(() => {
        return currentData.filter((row) =>
            Object.values(row).some((val) =>
                String(val).toLowerCase().includes(searchTerm.toLowerCase())
            )
        );
    }, [currentData, searchTerm]);

    const paginatedData = useMemo(() => {
        const start = page * rowsPerPage;
        return filteredData.slice(start, start + rowsPerPage);
    }, [filteredData, page, rowsPerPage]);

    const getColumns = (data) => {
        if (!data || !data.length) return [];
        return Object.keys(data[0]).map((key) => ({
            header: key,
            field: key
        }));
    };

    const currentColumns = useMemo(() => {
        if (!columnsCache[tabIndex]) {
            const newCols = getColumns(currentData).map((col) => ({
                field: col.field,
                header: col.field
                    ? col.field
                        .replace(/_/g, ' ')
                        .replace(/\b\w/g, (c) => c.toUpperCase())
                    : '',
            }));

            setColumnsCache((prev) => ({
                ...prev,
                [tabIndex]: newCols,
            }));

            return newCols;
        }

        return columnsCache[tabIndex];
    }, [tabIndex, currentData, columnsCache]);


    const handleChangePage = (_event, newPage) => setPage(newPage);
    const handleChangeRowsPerPage = (event) => {
        setRowsPerPage(parseInt(event.target.value, 10));
        setPage(0);
    };

    const handleSearchChange = (event) => {
        setSearchTerm(event.target.value);
        setPage(0);
    };

    return (
        <ContentCard
            heading={<Typography  color='rgba(51, 51, 51, 1)' fontSize='20px !important' fontWeight='600' sx={{fontWeight:'600'}} color='rgba(0, 48, 135, 1)' fontSize='20px !important'>Transformations</Typography>}
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
            <Tabs value={tabIndex} onChange={(_, val) => {
                setTabIndex(val);
                setSearchTerm('');
                setPage(0);
            }} className='tabs' sx={{width:'calc(100% - 400px)'}}>
                <Tab label="Transformations" sx={{
                    textTransform: 'capitalize', 
                    fontSize:'14px !important',
                    fontWeight:'600',
                    color: tabIndex === 0 ? 'rgba(51, 51, 51, 1)' : 'rgba(100, 116, 139, 1)',
                    borderBottom: tabIndex === 0 ? '2px solid rgba(51, 51, 51, 1)' : '',
                    '&.Mui-selected': {
                      color: 'rgba(51, 51, 51, 1)',
                      borderBottom: '2px solid rgba(51, 51, 51, 1)',
                    }
                }} />
            </Tabs>

            <Box>
                {tabIndex === 0 && (
                    <DataTable
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
                        containerHeight ='275'
                        additionalStylings={{position:'relative',top:'-60px',zIndex:'0'}}
                    />
                )}
                {tabIndex === 0 && (

                    <DataTable
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
                        containerHeight ='275'
                        additionalStylings={{position:'relative',top:'-60px',zIndex:'0'}}
                    />
                )}
            </Box>
        </ContentCard>
    );
};

export default DataTransformation;
