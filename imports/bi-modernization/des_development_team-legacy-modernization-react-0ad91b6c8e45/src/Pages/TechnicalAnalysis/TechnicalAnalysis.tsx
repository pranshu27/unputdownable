import React, { useState } from 'react';
import {
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Typography
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ContentCard from '../../core/CardContent/CardContent.tsx';
import { useOutletContext } from 'react-router-dom';
import { useSelector } from 'react-redux';
import { RootState } from '../../utils/Store.ts';
import { sanitizeToHTML } from '../../utils/SanitizeAndRender.tsx';
import './TechnicalAnalysis.scss';

const TechnicalAnalysis = () => {
  const { sideNavWidth } = useOutletContext();
  const reduxData = useSelector((state: RootState) => state.apiData.data);
  const localStorageData = localStorage.getItem('analyzeResponse');
  const parsedLocalData = localStorageData ? JSON.parse(localStorageData) : null;
  const dataToUse = parsedLocalData || reduxData;

  const markdownArray = dataToUse?.summary || [];
  const rawMarkdown = markdownArray[0] || '';
  
  const sectionChunks = (rawMarkdown || '').split(/\n(?=\d+\.\s)/).filter(Boolean);


  const accordionData = sectionChunks.map((chunk) => {
    const lines = chunk.split('\n');
    const titleLine = lines[0].replace(/^\d+\.\s*/, ''); 
    const contentLines = lines
    .slice(1)
    .join('\n')
    .replace(
      /(\*\*[^*]+\*\*:)/g, 
      '<br/><br/>$1'
    )
    .replace(
      /(\*\*[^*]+\*\*:.*?)(?=\n\*\*|$)/gs,
      '$1<br/>'
    );  
    return {
      title: titleLine.replace(/\*\*/g, '').trim(), // remove '**'
      content: sanitizeToHTML(contentLines, 'markdown'),
    };
  });
  

  const [expanded, setExpanded] = useState<string | false>('panel0');

  const handleChange = (panel: string) => (_: React.SyntheticEvent, isExpanded: boolean) => {
    setExpanded(isExpanded ? panel : false);
  };
  return (
    <div>
     
      <ContentCard
        
        heading={
          <Typography variant="h6" fontWeight='600 !important' color="rgba(0, 48, 135, 1)" fontSize="20px !important">
            Technical Analysis
          </Typography>
}
        sideNavWidth={sideNavWidth}
      >
        {accordionData.length === 0 ? (
          <Typography color="text.secondary">No technical analysis data available.</Typography>
        ) : (
          accordionData.map((section, index) => (
            <Accordion 
              key={index}
              expanded={expanded === `panel${index}`}
              onChange={handleChange(`panel${index}`)}
              sx={{
                borderBottom:'1px solid #ededed',
                boxShadow:'none !important',
                marginBottom: '8px',
                '&::before': {
                  height: 0,
                },
              }}
            >
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography fontWeight={600} color="rgba(0, 107, 194, 1)">
                  {section.title.replace(/:\s*$/, '')}
                </Typography>
              </AccordionSummary>
              <AccordionDetails>
                <div
                  className="markdown-content"
                  dangerouslySetInnerHTML={{ __html: section.content }}
                   style={{ color: 'rgba(100, 116, 139, 1)',fontSize:'16px !important' }}
                />
              </AccordionDetails>
            </Accordion>
          ))
        )}
       
      </ContentCard>

    </div>
  );
};

export default TechnicalAnalysis;
