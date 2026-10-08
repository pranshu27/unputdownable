import React, { useState, useRef } from 'react';
import { useEffect } from "react";
import { useNavigate } from 'react-router-dom';
import { Box, Typography, Button } from '@mui/material';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import ErrorIcon from '@mui/icons-material/Error';
import DeleteIcon from '@mui/icons-material/Delete';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import { useDispatch } from 'react-redux';
import { setFormData } from '../../utils/formSlice.ts';
import { setApiData } from "../../utils/DataSlice.ts";
import { useQueryClient } from '@tanstack/react-query';
import Loader from "../../core/Loader/Loader.tsx";
import Toaster from "../../core/Toaster/Toaster.tsx";
import ReEngineeringCards from './components/ReEngineeringCards.tsx';
import TileSelector from './components/TileSelector.tsx';
import storage from '../../Assets/storage.svg';
import ai from '/images/AI.jpg';
import './upload.scss';
import InfoIcon from '@mui/icons-material/Info';
import FileUploadZone from './components/FileUploadZone.tsx'

// Import icons
import AlteryxIcon from '../../Assets/Alteryx.png';
import SSISIcon from '../../Assets/ssis.png';
import BigQueryIcon from '../../Assets/Bigquerylogo1.png';
import PowerBiIcon from '../../Assets/powerbi.png';
import DbtIcon from '../../Assets/DBT.png';
import PysparkIcon from '../../../src/Assets/Py Spark Logo 1.png';
import DataiquIcon from '../../Assets/dataiq.png';
import xpierLogo from '../../Assets/xpier-logo.svg';
import { setSelectedCase  } from "../../utils/selectedCaseSlice.ts";
import InformaticaIcon from '../../Assets/Group4.png';
import QlickViewIcon from '../../Assets/OSK 2.png';
import DataStageIcon from '../../Assets/Group.png';
import MultiAgent from '../../Assets/mutiagent.png';
import PromptAgent from '../../Assets/prompt.png';
import TalendIcon from '../../Assets/Talend.png';
import TableautIcon from '../../Assets/tableau-icon.svg';
import WebfocusIcon from '../../Assets/webfocus.svg';
import DataBricks from '../../Assets/databricks.svg';
import Teradata from '../../Assets/teradata.svg';
import SqlIcon from '../../Assets/sql.svg';
import GPT from '../../Assets/openAi.svg';
import Gemini from '../../Assets/gemini.svg';
import SasIcon from '../../Assets/sas.svg';
import PythonIcon from '../../Assets/python.svg';
import CodeIcon from '@mui/icons-material/Code';
import SpringBoot from '../../Assets/spring-boot-icon.svg';

import AnalyticsIcon from '@mui/icons-material/Analytics';

const generateCacheKey = ({ fileName, etlTool, model }) =>
    ['upload', fileName, etlTool, model].join('_');

type WorkflowType = 'data' | 'sttm' | 'migration' | null;

interface SourceTool {
    key: string;
    value: string;
    icon: string;
    label: string;
}

interface TargetTech {
    key: string;
    value: string;
    icon: string;
    label: string;
}

interface Framework {
    key: string;
    value: string;
    label: string;
}

interface AIModel {
    key: string;
    value: string;
    label: string;
}


const UploadPage = () => {
  const navigate = useNavigate();

  const handleWorkflowSelect = (workflow: string) => {
    localStorage.setItem("selectedWorkflow", workflow);

    switch (workflow) {
      case "data":
        navigate("/data");
        break;
      case "sttm":
        navigate("/sttm");
        break;
      case "migration":
        navigate("/migration");
        break;
      default:
        navigate("/");
    }
  };



  return (
    <Box className="upload-page">
      <ReEngineeringCards onSelectWorkflow={handleWorkflowSelect} />

    </Box>
  );
};

export default UploadPage;
