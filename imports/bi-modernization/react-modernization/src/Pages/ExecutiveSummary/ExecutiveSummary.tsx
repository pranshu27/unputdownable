import React, { useState } from 'react';
import ContentCard from '../../core/CardContent/CardContent.tsx';
import { sanitizeToHTML } from '../../utils/SanitizeAndRender.tsx';
import { Typography, Button, Box } from '@mui/material';
import { useOutletContext } from 'react-router-dom';
import ReactQuill from 'react-quill';
import 'react-quill/dist/quill.snow.css';
import './ExecutiveSummary.scss'
import { useDispatch, useSelector } from 'react-redux';
import { RootState } from '../../utils/Store.ts';
import { htmlToText } from 'html-to-text';
import { updateExecutiveSummary } from '../../utils/DataSlice.ts';

interface OutletContextType {
  sideNavWidth: number;
}

const ExecutiveSummary = () => {
  const { sideNavWidth } = useOutletContext<OutletContextType>();
  const reduxData = useSelector((state: RootState) => state.apiData.data);
  const localStorageData = localStorage.getItem('analyzeResponse');
  const parsedLocalData = localStorageData ? JSON.parse(localStorageData) : null;

  const dataToUse = parsedLocalData || reduxData;
  // data
  const dummyMarkdown = dataToUse.executivesummary ?? dataToUse.executive_summary ?? dataToUse.agent_result.executive_summary;

  const safeHtml = sanitizeToHTML(dummyMarkdown, 'markdown');

  const [content, setContent] = useState(safeHtml);
  const dispatch = useDispatch();

  const toolbarOptions = [
    ['bold', 'italic', 'underline', 'strike'],
    ['blockquote', 'code-block'],
    [{ list: 'ordered' }, { list: 'bullet' }],
    [{ header: [1, 2, 3, false] }],
    [{ color: [] }, { background: [] }],
    [{ align: [] }],
    ['clean'],
  ];

  const modules = {
    toolbar: toolbarOptions,
  };

  const formats = [
    'header', 'bold', 'italic', 'underline', 'strike',
    'blockquote', 'code-block',
    'list', 'bullet',
    'color', 'background', 'align'
  ];

  const handleQuillSave = () => {
    dispatch(updateExecutiveSummary(content));
  };

  return (
    <Box>
      <ContentCard
        heading={<Typography sx={{fontWeight:'600'}} color='rgba(0, 48, 135, 1)' fontSize='20px !important'>Executive Summary</Typography>}
        sideNavWidth={sideNavWidth}
        noscroll={true}
      >
        <div>
  <style>
    {`
      .ql-editor {
        color: rgba(100, 116, 139, 1);
        font-size: 16px;
      }
    `}
  </style>

  <ReactQuill
    value={content}
    onChange={(value) => {
      setContent(value);
      dispatch(updateExecutiveSummary(value));
    // const plainText = htmlToText(content, {
    //   wordwrap: false,
    //   tables: true 
    // });

    localStorage.setItem('content', value)
    }}
    modules={modules}
    formats={formats}
    theme="snow"
    style={{ minHeight: '300px', marginBottom: '16px', borderRadius:'28px' }}
  />
</div>

      </ContentCard>
    </Box>
  );
};

export default ExecutiveSummary;
