let uploadedFiles: File[] = [];

export const setUploadedFileContext = (files: File | File[] | null | undefined) => {
  if (!files) {
    uploadedFiles = [];
    return;
  }

  uploadedFiles = Array.isArray(files) ? files : [files];
};

export const getUploadedFileContext = () => uploadedFiles;

export const getUploadedFileByName = (fileName?: string | null) => {
  if (!fileName) return uploadedFiles[0] || null;
  return uploadedFiles.find((file) => file.name === fileName) || null;
};
