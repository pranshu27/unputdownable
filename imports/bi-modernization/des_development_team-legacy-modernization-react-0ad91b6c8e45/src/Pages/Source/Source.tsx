import React, { useState } from 'react';
import ReusableCard from '../../core/Card/Card.tsx';
import {
  Box,
  Typography,
  Tooltip,
  IconButton,
  Divider,
  Input,
  Tabs,
  Tab,
} from '@mui/material';
import { ExpandLess, ExpandMore } from '@mui/icons-material';
import ContentCard from '../../core/CardContent/CardContent.tsx';
import { useOutletContext } from 'react-router-dom';
import CustomPagination from '../../core/CustomPagination/CustomPagination.tsx';
import './Source.scss';
import { useSelector } from 'react-redux';
import { RootState } from '../../utils/Store.ts';
import SliderDrawer from '../../core/SliderDrawer/SliderDrawer.tsx';
import DataTable from '../../core/DataTable/DataTable.tsx';

/* ---------- Helpers ---------- */

function getSampleCardData(etlTool: string) {
  switch (etlTool) {
    case 'ssis':
      return [
        { key: 'SourceType', label: 'Source Type' },
        { key: 'nodeId', label: 'Node Id' },
        { key: 'Description', label: 'Description' },
        { key: 'NextNodes', label: 'Next Nodes' },
      ];
    case 'sas':
      return [
        { key: 'node_id', label: 'Node ID' },
        { key: 'node_type', label: 'Node Type' },
        { key: 'path', label: 'Path' },
        { key: 'description', label: 'Description' },
        { key: 'type', label: 'Type' },
        { key: 'libref', label: 'Lib Ref' }
      ];
    case 'talend':
      return [
        { key: 'id', label: 'Node ID' },
        { key: 'name', label: 'Source Name' },
        { key: 'sourceType', label: 'Source Type' },
        { key: 'connection_type', label: 'Connection Type' },
        { key: 'description', label: 'Description' },
        { key: 'authentication_method', label: 'Authentication Method' },
      ];
    default:
      return [
        { key: 'connectionID', label: 'Connection ID' },
        { key: 'nodeId', label: 'Node Id' },
        { key: 'description', label: 'Description' },
        { key: 'connection_type', label: 'Connection Type' },
        { key: 'authentication_method', label: 'Authentication' },
      ];
  }
}

/* ---------- Component ---------- */

const Source = () => {
  const { sideNavWidth } = useOutletContext() as any;

  const reduxData = useSelector((state: RootState) => state.apiData.data);
  const localStorageData = localStorage.getItem('analyzeResponse');
  const parsedLocalData = localStorageData ? JSON.parse(localStorageData) : null;
  const dataToUse = parsedLocalData || reduxData;

  const sources = dataToUse?.source || dataToUse?.sources || [];
  const environments = dataToUse?.environment || [];
  const hasEnvironments = Array.isArray(environments) && environments.length > 0;

  const fileDetails = JSON.parse(localStorage.getItem('fileDetails') as any);
  const etlTool = fileDetails?.etlTool?.toLowerCase?.();

  /* ---------- State ---------- */

  const [activeTab, setActiveTab] = useState<'sources' | 'envs'>('sources');
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(50);
  const [selectedCard, setSelectedCard] = useState<any>(null);
  const [openDrawer, setOpenDrawer] = useState(false);
  const [showAttributes, setShowAttributes] = useState(true);
  const [showFieldNames, setShowFieldNames] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [searchTermSlider, setSearchTermSlider] = useState('');

  /* ---------- Filtering ---------- */

  const filteredSources = sources.filter((item: any) => {
    const search = searchTerm.toLowerCase();
    return (
      item?.sourceName?.toLowerCase?.().includes(search) ||
      item?.ObjectName?.toLowerCase?.().includes(search) ||
      item?.description?.toLowerCase?.().includes(search) ||
      item?.Description?.toLowerCase?.().includes(search)
    );
  });

  const paginatedSources = filteredSources.slice(
    page * rowsPerPage,
    page * rowsPerPage + rowsPerPage
  );

  const sampleCardData = getSampleCardData(etlTool);

  const fieldData =
    selectedCard?.FieldNames ||
    selectedCard?.field_names ||
    selectedCard?.fn ||
    {};

  const filteredFieldEntries = Object.entries(fieldData).filter(
    ([key, value]) => {
      const search = searchTermSlider.toLowerCase();
      return (
        key.toLowerCase().includes(search) ||
        (typeof value === 'string' && value.toLowerCase().includes(search))
      );
    }
  );

  /* ---------- UI ---------- */

  const searchComponent = (
    <Input
      placeholder="Search…"
      value={searchTerm}
      onChange={(e) => {
        setSearchTerm(e.target.value);
        setPage(0);
      }}
      sx={{
        boxShadow: '0px 4px 15px rgba(133,160,186,0.15)',
        px: 1.5,
        py: 0.5,
        width: 300,
        background: 'white',
        borderRadius: '28px',
        border: '1px solid #ddd',
      }}
      size="small"
    />
  );

  return (
    <ContentCard
      searchComponent={searchComponent}
      heading={
        <Typography fontWeight={600} color="rgba(0,48,135,1)" fontSize={20}>
          Source
        </Typography>
      }
      sideNavWidth={sideNavWidth}
      bottomContent={
        activeTab === 'sources' && (
          <CustomPagination
            count={filteredSources.length}
            page={page}
            rowsPerPage={rowsPerPage}
            onPageChange={(_, p) => setPage(p)}
            onRowsPerPageChange={(e) => {
              setRowsPerPage(parseInt(e.target.value, 10) || 50);
              setPage(0);
            }}
          />
        )
      }
    >
      {/* ---------- Tabs (ONLY if envs exist) ---------- */}
      {hasEnvironments && (
        <Tabs
          value={activeTab}
          onChange={(_, val) => setActiveTab(val)}
          sx={{ mb: 2 }}
        >
          <Tab label="Sources" value="sources" />
          <Tab label="Environments" value="envs" />
        </Tabs>
      )}

      {/* ---------- SOURCES ---------- */}
      {(!hasEnvironments || activeTab === 'sources') && (
        <Box display="flex" flexWrap="wrap" gap={2} mt={1}>
          {paginatedSources.length === 0 ? (
            <Typography sx={{ mt: 4, mx: 'auto' }}>
              No data found.
            </Typography>
          ) : (
            paginatedSources.map((res: any, i: number) => (
              <ReusableCard
                key={i}
                width={333}
                height={175}
                headingLabel="Source Name:"
                headingValue={
                  res.name ||
                  res.ObjectName ||
                  res.sourceName ||
                  'N/A'
                }
                description={
                  <Box display="flex" gap={1}>
                    <Typography fontWeight={600}>Description:</Typography>
                    <Tooltip title={res.description || res.Description || 'N/A'}>
                      <Typography noWrap maxWidth={230}>
                        {res.description || res.Description || 'N/A'}
                      </Typography>
                    </Tooltip>
                  </Box>
                }
                layout="vertical"
                buttons={[
                  {
                    label: 'View More',
                    onClick: () => {
                      setSelectedCard(res);
                      setOpenDrawer(true);
                    },
                  },
                ]}
              />
            ))
          )}
        </Box>
      )}

      {/* ---------- ENVIRONMENTS ---------- */}
      {hasEnvironments && activeTab === 'envs' && (
        <Box mt={2}>
          <DataTable
            data={environments}
            columns={[
              { header: 'Type', field: 'type' },
              { header: 'Name', field: 'name' },
              { header: 'Value', field: 'value' },
              { header: 'Description', field: 'description' },
            ]}
            showCheckbox={false}
            Height="500"
          />
        </Box>
      )}

      {/* ---------- DRAWER ---------- */}
      <SliderDrawer
        open={openDrawer}
        onClose={() => setOpenDrawer(false)}
        title={selectedCard?.name || selectedCard?.sourceName || ''}
        width="35%"
      >
        {selectedCard && (
          <Box>
            {sampleCardData.map((item, idx) => (
              <Typography key={idx}>
                <b>{item.label}:</b> {selectedCard[item.key] || 'N/A'}
              </Typography>
            ))}

            <Divider sx={{ my: 2 }} />

            <DataTable
              data={filteredFieldEntries.map(([k, v]) => ({
                key: k,
                value: String(v),
              }))}
              columns={[
                { header: 'Key', field: 'key' },
                { header: 'Value', field: 'value' },
              ]}
              Height="400"
            />
          </Box>
        )}
      </SliderDrawer>
    </ContentCard>
  );
};

export default Source;
