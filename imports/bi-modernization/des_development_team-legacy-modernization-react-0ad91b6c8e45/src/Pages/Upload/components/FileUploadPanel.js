import React, { useState, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Upload, FileCode, X, CheckCircle2, AlertCircle, File } from 'lucide-react';
import { Button } from '../../CodeGen/CodeGenComponents/button.tsx';
import { cn } from '../../../Lib/utils.ts';
import {
  FolderOpen,
  Cloud,
  Link2
} from "lucide-react";
export default function FileUploadPanel({ onFileSelect, selectedFile, onRemoveFile }) {
  const [isDragging, setIsDragging] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const fileInputRef = useRef(null);
  const selectedFiles = Array.isArray(selectedFile) ? selectedFile : selectedFile ? [selectedFile] : [];

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const files = Array.from(e.dataTransfer.files || []);
    if (files.length) processFiles(files);
  };

  const handleFileSelect = (e) => {
    const files = Array.from(e.target.files || []);
    if (files.length) processFiles(files);
  };

  const processFiles = (files) => {
    if (!files.length) return;
  
    setUploadProgress(0);
  
    const interval = setInterval(() => {
      setUploadProgress((prev) => {
        if (prev >= 100) {
          clearInterval(interval);
  
          const mergedFiles = [
            ...selectedFiles,
            ...files
          ];
  
          const uniqueFiles =
            mergedFiles.filter(
              (file, index, self) =>
                index ===
                self.findIndex(
                  (f) =>
                    f.name === file.name &&
                    f.size === file.size
                )
            );
  
          onFileSelect(uniqueFiles);
  
          return 100;
        }
  
        return prev + 10;
      });
    }, 100);
  };

  const removeFile = (fileToRemove) => {
    if (!fileToRemove) {
      onFileSelect([]);
      setUploadProgress(0);
      return;
    }

    const updatedFiles = selectedFiles.filter(
      (file) =>
        !(
          file.name === fileToRemove.name &&
          file.size === fileToRemove.size
        )
    );

    onFileSelect(updatedFiles);

    if (!updatedFiles.length) {
      setUploadProgress(0);
    }
  };
  const [showFolderModal, setShowFolderModal] = useState(false);
  const folderInputRef = useRef(null);
  const supportedFormats = [
    { ext: 'PBIX', color: 'bg-red-100 text-red-700' },
    { ext: 'TWB', color: 'bg-orange-100 text-orange-700' },
    { ext: 'MULTI', color: 'bg-stone-100 text-stone-700' },
    { ext: 'VALIDATED', color: 'bg-emerald-100 text-emerald-700' },
  ];
  const handleFolderSelect = async () => {
    try {
      const dirHandle = await window.showDirectoryPicker();
  
      const files = [];
  
      for await (const entry of dirHandle.values()) {
        if (entry.kind === "file") {
          const file = await entry.getFile();
          files.push(file);
        }
      }
  
      if (files.length) {
        processFiles(files);
      }
    } catch (err) {
      console.log("Folder selection cancelled");
    }
  };

  return (
    <div className="space-y-6">
      {showFolderModal && (
  <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
    <div className="bg-white rounded-2xl p-6 w-[420px] shadow-xl">
      
      <h3 className="text-lg font-semibold text-stone-900">
        Upload Folder
      </h3>

      <p className="text-sm text-stone-500 mt-2">
        This will import all supported files from your selected folder.
        Make sure the folder contains PBIX/TWB files only.
      </p>

      <div className="flex justify-end gap-3 mt-6">
        <button
          onClick={() => setShowFolderModal(false)}
          className="px-4 py-2 rounded-lg border border-stone-200 text-stone-600"
        >
          Cancel
        </button>

        <button
          onClick={async () => {
            setShowFolderModal(false);
            await handleFolderSelect();
          }}
          className="px-4 py-2 rounded-lg bg-red-700 text-white hover:bg-red-800"
        >
          Continue
        </button>
      </div>
    </div>
  </div>
)}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-stone-900">Upload Source File</h2>
          <p className="text-sm text-stone-500 mt-1">
            Upload one or more `.pbix` or `.twb` files to begin AI-assisted migration analysis
          </p>
        </div>
        <div className="flex items-center gap-2">
          {supportedFormats.map(format => (
            <span 
              key={format.ext}
              className={cn("px-2 py-1 rounded text-xs font-medium", format.color)}
            >
              {format.ext}
            </span>
          ))}
        </div>
      </div>{/* Upload Source Options */}
{/* Primary Upload Action */}
{/* Import Options */}
{/* Upload Actions */}
<div className="flex flex-wrap gap-3">

  {/* Upload File */}
  <button
    onClick={() => fileInputRef.current?.click()}
    className="
      flex items-center gap-2
      px-4 py-3
      rounded-xl
      border border-red-200
      bg-red-50
      text-red-700
      text-sm font-medium
      hover:bg-red-100
      transition
    "
  >
    <Upload className="w-4 h-4" />
    Upload File
  </button>

  <input
    ref={fileInputRef}
    type="file"
    multiple
    accept=".pbix,.twb,.twbx"
    className="hidden"
    onChange={handleFileSelect}
  />

  {/* Upload Folder */}
  <button
onClick={() => setShowFolderModal(true)}
    className="
      flex items-center gap-2
      px-4 py-3
      rounded-xl
      border border-stone-200
      bg-white
      text-stone-700
      text-sm font-medium
      hover:border-red-200
      hover:bg-red-50
      transition
    "
  >
    <FolderOpen className="w-4 h-4" />
    Upload Folder
  </button>

  {/* Cloud Storage - Disabled */}
  <button
    disabled
    className="
      flex items-center gap-2
      px-4 py-3
      rounded-xl
      border border-stone-200
      bg-stone-50
      text-stone-400
      text-sm font-medium
      cursor-not-allowed
    "
  >
    <Cloud className="w-4 h-4" />
    Cloud Storage

    <span className="text-[10px] bg-stone-200 px-2 py-0.5 rounded-full">
      Soon
    </span>
  </button>

  {/* Import URL - Disabled */}
  <button
    disabled
    className="
      flex items-center gap-2
      px-4 py-3
      rounded-xl
      border border-stone-200
      bg-stone-50
      text-stone-400
      text-sm font-medium
      cursor-not-allowed
    "
  >
    <Link2 className="w-4 h-4" />
    Import URL

    <span className="text-[10px] bg-stone-200 px-2 py-0.5 rounded-full">
      Soon
    </span>
  </button>
</div>

      <AnimatePresence mode="wait">
        {!selectedFiles.length ? (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={cn(
              "relative border-2 border-dashed rounded-lg p-12 transition-all duration-300 cursor-pointer group",
              isDragging 
                ? "border-red-600 bg-red-50/60" 
                : "border-stone-200 hover:border-red-300 hover:bg-stone-50/60"
            )}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".pbix,.twb,.twbx"
              className="hidden"
              onChange={handleFileSelect}
            />
            
            <div className="flex flex-col items-center text-center">
              <motion.div 
                className={cn(
                  "w-16 h-16 rounded-lg flex items-center justify-center mb-4 transition-colors",
                  isDragging ? "bg-red-700" : "bg-gradient-to-br from-stone-100 to-stone-200 group-hover:from-red-50 group-hover:to-red-100"
                )}
                animate={isDragging ? { scale: [1, 1.1, 1] } : {}}
                transition={{ duration: 0.5, repeat: isDragging ? Infinity : 0 }}
              >
                <Upload className={cn(
                  "w-7 h-7 transition-colors",
                  isDragging ? "text-white" : "text-stone-400 group-hover:text-red-700"
                )} />
              </motion.div>
              
              <p className="text-stone-800 font-medium mb-1">
                {isDragging ? 'Release to upload' : 'Drop your file here or click to browse'}
              </p>
              <p className="text-sm text-stone-400">
  Supports multiple file formats
</p>
            </div>

            {/* Animated border on drag */}
            {isDragging && (
              <motion.div
                className="absolute inset-0 rounded-lg pointer-events-none"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                style={{
                  background: 'linear-gradient(90deg, transparent, rgba(200, 16, 46, 0.24), transparent)',
                  backgroundSize: '200% 100%',
                }}
              />
            )}
          </motion.div>
        ) : (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="bg-gradient-to-br from-stone-50 to-white border border-stone-200 rounded-lg p-6"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="w-14 h-14 rounded-lg bg-gradient-to-br from-red-700 to-red-900 flex items-center justify-center shadow-lg shadow-red-500/20">
                  <FileCode className="w-7 h-7 text-white" />
                </div>
                <div>
                  <p className="font-medium text-stone-900">
                    {selectedFiles.length === 1 ? selectedFiles[0].name : `${selectedFiles.length} files selected`}
                  </p>
                  <p className="text-sm text-stone-500">
                    {(selectedFiles.reduce((sum, file) => sum + file.size, 0) / 1024).toFixed(1)} KB total
                  </p>
                </div>
                
              </div>
              
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2 text-emerald-600">
                   {/* <CheckCircle2 className="w-5 h-5" /> */}
                  <span className="text-sm font-medium">Ready</span>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => { onFileSelect([]); if (onRemoveFile) onRemoveFile('all'); }}
                  className="text-slate-400 hover:text-red-500 hover:bg-red-50"
                >
                  <X className="w-5 h-5" />
                </Button>
              </div>
            </div>
            <div className="mt-4 flex gap-3">
  <Button
    variant="outline"
    onClick={() => fileInputRef.current?.click()}
    className="border-red-200 text-red-700 hover:bg-red-50"
  >
    + Add More Files
  </Button>

  <input
    ref={fileInputRef}
    type="file"
    multiple
    accept=".pbix,.twb,.twbx"
    className="hidden"
    onChange={handleFileSelect}
  />
</div>
            
<div className="mt-5 grid gap-2">
  {selectedFiles.map((file, index) => {
    const fileExtension =
      file.name.split(".").pop()?.toUpperCase() ||
      "FILE";
    return (
      <div
        key={`${file.name}-${file.size}`}
        className="flex items-center justify-between rounded-lg border border-stone-200 bg-white px-3 py-2 hover:border-red-200 transition"
      >
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-stone-900">
            {file.name}
          </p>

          <p className="text-xs text-stone-500">
            {(file.size / 1024).toFixed(1)} KB • {fileExtension}
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[10px] font-bold text-emerald-700">
            Uploaded
          </span>
          <button
            onClick={() => onRemoveFile(index)}
            className="p-1 hover:bg-red-50 rounded-lg transition-colors"
          >
            <X className="w-3.5 h-3.5 text-slate-400 hover:text-red-600" />
          </button>
        </div>
      </div>
    );
  })}
</div>

            {uploadProgress < 100 && (
              <div className="mt-4">
                <div className="h-1.5 bg-stone-100 rounded-full overflow-hidden">
                  <motion.div
                    className="h-full bg-gradient-to-r from-red-700 to-red-900 rounded-full"
                    initial={{ width: 0 }}
                    animate={{ width: `${uploadProgress}%` }}
                  />
                </div>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
    
  );
}
