import React, { useRef, useState } from 'react';
import { Box, Typography, Button, LinearProgress } from '@mui/material';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import InsertDriveFileIcon from '@mui/icons-material/InsertDriveFile';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import './FileUploadZone.scss';
import FolderIcon from '@mui/icons-material/Folder';
import { useNavigate } from 'react-router-dom';

interface FileUploadZoneProps {
  selectedFile: File | null;
  onFileChange: (file: File | null) => void;
  acceptedFormats?: string[];
  stepNumber?: number;
}


const FileUploadZone: React.FC<FileUploadZoneProps> = ({
  selectedFile,
  onFileChange,
  acceptedFormats = ['XML', 'ZIP', 'DTSX'],
  stepNumber
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };
  const navigate = useNavigate();


  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      simulateUpload(files[0]);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      simulateUpload(files[0]);
    }
  };

  const simulateUpload = (file: File) => {
    setUploadProgress(0);
    const interval = setInterval(() => {
      setUploadProgress((prev) => {
        if (prev >= 100) {
          clearInterval(interval);
          onFileChange(file);
          return 100;
        }
        return prev + 10;
      });
    }, 100);
  };

  const handleDelete = () => {
    onFileChange(null);
    setUploadProgress(0);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  };
  const analyseExisting = (type: any) => {
    navigate(`/${type}`);
}

  return (
    <Box className="file-upload-zone-container">
      <Box className="file-upload-header">
        {stepNumber && (
          <Box className="step-badge">
            <span className="step-number">{stepNumber}</span>
          </Box>
        )}
        <Typography variant="h6" className="file-upload-title">
          Upload Source File
        </Typography>
      </Box>

      <Box
        className={`upload-dropzone ${isDragging ? 'dragging' : ''} ${selectedFile ? 'has-file' : ''}`}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >
        {!selectedFile ? (
          <>
            <Box className="upload-icon-wrapper">
              <CloudUploadIcon className="upload-icon" />
              <Box className="icon-pulse" />
            </Box>

            <Typography className="upload-title">
              Drop your file here or click to browse
            </Typography>

            <Typography className="upload-subtitle">
              Supported formats: {acceptedFormats.join(', ')}
            </Typography>
            <Box sx={{display:'flex', gap:'15px'}}>
            <Button
              component="label"
              className="browse-button"
              startIcon={<InsertDriveFileIcon />}
            >
              Choose File
              <input
                ref={fileInputRef}
                type="file"
                hidden
                onChange={handleFileSelect}
              />
            </Button>
            <Button
                className="browse-button"
                startIcon={<FolderIcon />}
                onClick={() => analyseExisting("analyze")}
                >
                Analyse Existing
                </Button>
            </Box>


            <Box className="upload-decoration">
              <Box className="decoration-circle circle-1" />
              <Box className="decoration-circle circle-2" />
              <Box className="decoration-circle circle-3" />
            </Box>
          </>
        ) : (
          <Box className="file-preview">
            <Box className="file-icon-wrapper">
              <InsertDriveFileIcon className="file-icon" />
              <CheckCircleIcon className="success-badge" />
            </Box>

            <Box className="file-details">
              <Typography className="file-name">
                {selectedFile.name}
              </Typography>
              <Typography className="file-size">
                {formatFileSize(selectedFile.size)}
              </Typography>
            </Box>

            {uploadProgress < 100 && (
              <Box className="progress-wrapper">
                <LinearProgress
                  variant="determinate"
                  value={uploadProgress}
                  className="upload-progress"
                />
                <Typography className="progress-text">
                  {uploadProgress}%
                </Typography>
              </Box>
            )}

            {uploadProgress === 100 && (
              <Box className="success-message">
                <CheckCircleIcon className="success-icon" />
                <Typography className="success-text">
                  Upload Complete
                </Typography>
              </Box>
            )}

            <Button
              className="delete-button"
              startIcon={<DeleteOutlineIcon />}
              onClick={handleDelete}
            >
              Remove File
            </Button>
          </Box>
        )}
      </Box>
    </Box>
  );
};

export default FileUploadZone;